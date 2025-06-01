from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Count, Q, Avg
from django.utils import timezone
from .models import Campaign, CampaignTemplate, CampaignRecipient, AudienceSegment
from .serializers import (
    CampaignSerializer, CampaignDetailSerializer, CreateCampaignSerializer,
    AudienceSegmentSerializer, CampaignStatsSerializer, LaunchCampaignSerializer
)
from .tasks import launch_campaign_task, pause_campaign_task
import logging

logger = logging.getLogger(__name__)


class CampaignListCreateView(generics.ListCreateAPIView):
    """
    List campaigns or create a new campaign
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CreateCampaignSerializer
        return CampaignSerializer
    
    def get_queryset(self):
        queryset = Campaign.objects.filter(merchant=self.request.user)
        
        # Apply filters
        status_filter = self.request.query_params.get('status')
        channel_filter = self.request.query_params.get('channel')
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if channel_filter:
            queryset = queryset.filter(channel=channel_filter)
        
        return queryset.order_by('-created_at')


class CampaignDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete a campaign
    """
    serializer_class = CampaignDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Campaign.objects.filter(merchant=self.request.user)
    
    def destroy(self, request, *args, **kwargs):
        campaign = self.get_object()
        
        if campaign.status in ['running', 'processing']:
            return Response({
                'error': 'Cannot delete a running campaign'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        return super().destroy(request, *args, **kwargs)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def launch_campaign(request, campaign_id):
    """
    Launch a campaign
    """
    campaign = get_object_or_404(
        Campaign,
        id=campaign_id,
        merchant=request.user
    )
    
    if campaign.status != Campaign.CampaignStatus.DRAFT:
        return Response({
            'error': f'Cannot launch campaign with status: {campaign.status}'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    serializer = LaunchCampaignSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    validated_data = serializer.validated_data
    
    with transaction.atomic():
        if validated_data.get('launch_immediately', True):
            # Launch immediately
            campaign.status = Campaign.CampaignStatus.RUNNING
            campaign.started_at = timezone.now()
            campaign.save()
            
            # Queue campaign processing
            launch_campaign_task.delay(str(campaign.id))
            
            message = 'Campaign launched successfully'
        else:
            # Schedule for later
            campaign.status = Campaign.CampaignStatus.SCHEDULED
            campaign.scheduled_at = validated_data['scheduled_at']
            campaign.save()
            
            # Schedule campaign launch
            launch_campaign_task.apply_async(
                args=[str(campaign.id)],
                eta=campaign.scheduled_at
            )
            
            message = 'Campaign scheduled successfully'
        
        # Create event
        from .models import CampaignEvent
        CampaignEvent.objects.create(
            campaign=campaign,
            event_type='launched' if validated_data.get('launch_immediately') else 'scheduled',
            event_data=validated_data,
            user=request.user
        )
    
    return Response({
        'message': message,
        'campaign': CampaignDetailSerializer(campaign).data
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def pause_campaign(request, campaign_id):
    """
    Pause a running campaign
    """
    campaign = get_object_or_404(
        Campaign,
        id=campaign_id,
        merchant=request.user
    )
    
    if campaign.status not in [Campaign.CampaignStatus.RUNNING, Campaign.CampaignStatus.SCHEDULED]:
        return Response({
            'error': f'Cannot pause campaign with status: {campaign.status}'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    with transaction.atomic():
        campaign.status = Campaign.CampaignStatus.PAUSED
        campaign.save()
        
        # Create event
        from .models import CampaignEvent
        CampaignEvent.objects.create(
            campaign=campaign,
            event_type='paused',
            event_data={'paused_by': 'user'},
            user=request.user
        )
        
        # Queue pause processing
        pause_campaign_task.delay(str(campaign.id))
    
    return Response({
        'message': 'Campaign paused successfully',
        'campaign': CampaignDetailSerializer(campaign).data
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def resume_campaign(request, campaign_id):
    """
    Resume a paused campaign
    """
    campaign = get_object_or_404(
        Campaign,
        id=campaign_id,
        merchant=request.user
    )
    
    if campaign.status != Campaign.CampaignStatus.PAUSED:
        return Response({
            'error': f'Cannot resume campaign with status: {campaign.status}'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    with transaction.atomic():
        campaign.status = Campaign.CampaignStatus.RUNNING
        campaign.save()
        
        # Create event
        from .models import CampaignEvent
        CampaignEvent.objects.create(
            campaign=campaign,
            event_type='resumed',
            event_data={'resumed_by': 'user'},
            user=request.user
        )
        
        # Queue campaign processing
        launch_campaign_task.delay(str(campaign.id))
    
    return Response({
        'message': 'Campaign resumed successfully',
        'campaign': CampaignDetailSerializer(campaign).data
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def cancel_campaign(request, campaign_id):
    """
    Cancel a campaign
    """
    campaign = get_object_or_404(
        Campaign,
        id=campaign_id,
        merchant=request.user
    )
    
    if campaign.status in [Campaign.CampaignStatus.COMPLETED, Campaign.CampaignStatus.CANCELLED]:
        return Response({
            'error': f'Cannot cancel campaign with status: {campaign.status}'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    with transaction.atomic():
        campaign.status = Campaign.CampaignStatus.CANCELLED
        campaign.completed_at = timezone.now()
        campaign.save()
        
        # Create event
        from .models import CampaignEvent
        CampaignEvent.objects.create(
            campaign=campaign,
            event_type='cancelled',
            event_data={'cancelled_by': 'user'},
            user=request.user
        )
    
    return Response({
        'message': 'Campaign cancelled successfully',
        'campaign': CampaignDetailSerializer(campaign).data
    })


class CampaignRecipientsView(generics.ListAPIView):
    """
    List campaign recipients
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        campaign_id = self.kwargs['campaign_id']
        campaign = get_object_or_404(
            Campaign,
            id=campaign_id,
            merchant=self.request.user
        )
        
        queryset = CampaignRecipient.objects.filter(campaign=campaign)
        
        # Apply filters
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.order_by('-created_at')
    
    def get_serializer_class(self):
        from .serializers import CampaignRecipientSerializer
        return CampaignRecipientSerializer


class AudienceSegmentListCreateView(generics.ListCreateAPIView):
    """
    List or create audience segments
    """
    serializer_class = AudienceSegmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return AudienceSegment.objects.filter(
            merchant=self.request.user
        ).order_by('-created_at')


class AudienceSegmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete an audience segment
    """
    serializer_class = AudienceSegmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return AudienceSegment.objects.filter(merchant=self.request.user)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def campaign_stats(request):
    """
    Get campaign statistics for the merchant
    """
    merchant = request.user
    campaigns = Campaign.objects.filter(merchant=merchant)
    
    # Basic stats
    total_campaigns = campaigns.count()
    active_campaigns = campaigns.filter(
        status__in=[Campaign.CampaignStatus.RUNNING, Campaign.CampaignStatus.SCHEDULED]
    ).count()
    completed_campaigns = campaigns.filter(
        status=Campaign.CampaignStatus.COMPLETED
    ).count()
    
    # Aggregated metrics
    aggregated = campaigns.aggregate(
        total_recipients=Count('recipients'),
        total_sent=Count('recipients', filter=Q(recipients__status='sent')),
        total_delivered=Count('recipients', filter=Q(recipients__status='delivered')),
        avg_success_rate=Avg('total_delivered')
    )
    
    # Channel breakdown
    channel_breakdown = dict(
        campaigns.values('channel').annotate(
            count=Count('id')
        ).values_list('channel', 'count')
    )
    
    # Recent activity (last 10 campaign events)
    from .models import CampaignEvent
    recent_events = CampaignEvent.objects.filter(
        campaign__merchant=merchant
    ).order_by('-created_at')[:10]
    
    recent_activity = []
    for event in recent_events:
        recent_activity.append({
            'campaign_name': event.campaign.name,
            'event_type': event.event_type,
            'created_at': event.created_at,
            'user': event.user.username if event.user else None
        })
    
    stats = {
        'total_campaigns': total_campaigns,
        'active_campaigns': active_campaigns,
        'completed_campaigns': completed_campaigns,
        'total_recipients': aggregated['total_recipients'] or 0,
        'total_sent': aggregated['total_sent'] or 0,
        'total_delivered': aggregated['total_delivered'] or 0,
        'average_success_rate': aggregated['avg_success_rate'] or 0,
        'channel_breakdown': channel_breakdown,
        'recent_activity': recent_activity
    }
    
    return Response(stats)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def duplicate_campaign(request, campaign_id):
    """
    Duplicate an existing campaign
    """
    original_campaign = get_object_or_404(
        Campaign,
        id=campaign_id,
        merchant=request.user
    )
    
    with transaction.atomic():
        # Create new campaign
        new_campaign = Campaign.objects.create(
            merchant=request.user,
            name=f"{original_campaign.name} (Copy)",
            description=original_campaign.description,
            channel=original_campaign.channel,
            target_audience=original_campaign.target_audience,
            budget_limit=original_campaign.budget_limit,
            daily_limit=original_campaign.daily_limit,
            settings=original_campaign.settings,
            status=Campaign.CampaignStatus.DRAFT
        )
        
        # Copy template if exists
        if hasattr(original_campaign, 'template'):
            CampaignTemplate.objects.create(
                campaign=new_campaign,
                subject=original_campaign.template.subject,
                message=original_campaign.template.message,
                html_content=original_campaign.template.html_content,
                variables=original_campaign.template.variables
            )
        
        # Copy recipients
        original_recipients = CampaignRecipient.objects.filter(
            campaign=original_campaign
        )
        
        new_recipients = []
        for recipient in original_recipients:
            new_recipients.append(CampaignRecipient(
                campaign=new_campaign,
                recipient=recipient.recipient,
                recipient_data=recipient.recipient_data
            ))
        
        if new_recipients:
            CampaignRecipient.objects.bulk_create(new_recipients)
            new_campaign.estimated_recipients = len(new_recipients)
            new_campaign.save()
        
        # Create event
        from .models import CampaignEvent
        CampaignEvent.objects.create(
            campaign=new_campaign,
            event_type='duplicated',
            event_data={'original_campaign_id': str(original_campaign.id)},
            user=request.user
        )
    
    return Response({
        'message': 'Campaign duplicated successfully',
        'campaign': CampaignDetailSerializer(new_campaign).data
    }, status=status.HTTP_201_CREATED)
