from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from .models import (
    RecipientList, Recipient, RecipientListMembership,
    RecipientImport, RecipientTag, RecipientEngagement
)
from .serializers import (
    RecipientListSerializer, RecipientListDetailSerializer,
    RecipientSerializer, RecipientListMembershipSerializer,
    AddRecipientsToListSerializer, BulkRecipientImportSerializer,
    RecipientTagSerializer, RecipientEngagementSerializer,
    RecipientStatsSerializer, ExportRecipientsSerializer,
    RecipientSearchSerializer
)
import csv
import json
import logging

logger = logging.getLogger(__name__)


class RecipientListCreateView(generics.ListCreateAPIView):
    """
    List recipient lists or create a new list
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method == 'GET':
            return RecipientListSerializer
        return RecipientListSerializer
    
    def get_queryset(self):
        return RecipientList.objects.filter(
            merchant=self.request.user,
            is_active=True
        ).order_by('-updated_at')


class RecipientListDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete a recipient list
    """
    serializer_class = RecipientListDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return RecipientList.objects.filter(merchant=self.request.user)
    
    def destroy(self, request, *args, **kwargs):
        recipient_list = self.get_object()
        
        # Soft delete - mark as inactive
        recipient_list.is_active = False
        recipient_list.save()
        
        return Response(status=status.HTTP_204_NO_CONTENT)


class RecipientListMembersView(generics.ListAPIView):
    """
    List members of a recipient list
    """
    serializer_class = RecipientListMembershipSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        list_id = self.kwargs['list_id']
        recipient_list = get_object_or_404(
            RecipientList,
            id=list_id,
            merchant=self.request.user
        )
        
        queryset = RecipientListMembership.objects.filter(
            recipient_list=recipient_list,
            is_active=True
        ).select_related('recipient')
        
        # Apply filters
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(recipient__email__icontains=search) |
                Q(recipient__first_name__icontains=search) |
                Q(recipient__last_name__icontains=search) |
                Q(recipient__phone__icontains=search)
            )
        
        return queryset.order_by('-added_at')


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def add_recipients_to_list(request, list_id):
    """
    Add recipients to a recipient list
    """
    recipient_list = get_object_or_404(
        RecipientList,
        id=list_id,
        merchant=request.user
    )
    
    serializer = AddRecipientsToListSerializer(
        data=request.data,
        context={'request': request}
    )
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    recipient_ids = serializer.validated_data['recipient_ids']
    
    with transaction.atomic():
        added_count = 0
        existing_count = 0
        
        for recipient_id in recipient_ids:
            recipient = get_object_or_404(
                Recipient,
                id=recipient_id,
                merchant=request.user
            )
            
            membership, created = RecipientListMembership.objects.get_or_create(
                recipient_list=recipient_list,
                recipient=recipient,
                defaults={
                    'added_by': request.user,
                    'is_active': True
                }
            )
            
            if created:
                added_count += 1
            elif not membership.is_active:
                membership.is_active = True
                membership.save()
                added_count += 1
            else:
                existing_count += 1
        
        # Update list counters
        recipient_list.total_recipients = RecipientListMembership.objects.filter(
            recipient_list=recipient_list,
            is_active=True
        ).count()
        
        recipient_list.active_recipients = RecipientListMembership.objects.filter(
            recipient_list=recipient_list,
            is_active=True,
            recipient__is_active=True
        ).count()
        
        recipient_list.save()
    
    return Response({
        'message': f'Added {added_count} recipients to list',
        'added_count': added_count,
        'existing_count': existing_count,
        'total_recipients': recipient_list.total_recipients
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def remove_recipients_from_list(request, list_id):
    """
    Remove recipients from a recipient list
    """
    recipient_list = get_object_or_404(
        RecipientList,
        id=list_id,
        merchant=request.user
    )
    
    recipient_ids = request.data.get('recipient_ids', [])
    
    if not recipient_ids:
        return Response({
            'error': 'recipient_ids is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    with transaction.atomic():
        removed_count = RecipientListMembership.objects.filter(
            recipient_list=recipient_list,
            recipient_id__in=recipient_ids,
            is_active=True
        ).update(is_active=False)
        
        # Update list counters
        recipient_list.total_recipients = RecipientListMembership.objects.filter(
            recipient_list=recipient_list,
            is_active=True
        ).count()
        
        recipient_list.active_recipients = RecipientListMembership.objects.filter(
            recipient_list=recipient_list,
            is_active=True,
            recipient__is_active=True
        ).count()
        
        recipient_list.save()
    
    return Response({
        'message': f'Removed {removed_count} recipients from list',
        'removed_count': removed_count,
        'total_recipients': recipient_list.total_recipients
    })


class RecipientListCreateView(generics.ListCreateAPIView):
    """
    List recipients or create a new recipient
    """
    serializer_class = RecipientSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = Recipient.objects.filter(merchant=self.request.user, is_active=True)
        
        # Apply filters
        search = self.request.query_params.get('search')
        channel = self.request.query_params.get('channel')
        opted_in_only = self.request.query_params.get('opted_in_only', 'true').lower() == 'true'
        
        if search:
            queryset = queryset.filter(
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(phone__icontains=search)
            )
        
        if channel:
            # Filter by contact info and opt-in status for channel
            channel_filters = {
                'email': Q(email__isnull=False, email__ne='') & (Q(email_opted_in=True) if opted_in_only else Q()),
                'sms': Q(phone__isnull=False, phone__ne='') & (Q(sms_opted_in=True) if opted_in_only else Q()),
                'push': Q(device_token__isnull=False, device_token__ne='') & (Q(push_opted_in=True) if opted_in_only else Q()),
                'whatsapp': (Q(whatsapp__isnull=False, whatsapp__ne='') | Q(phone__isnull=False, phone__ne='')) & (Q(whatsapp_opted_in=True) if opted_in_only else Q())
            }
            
            if channel in channel_filters:
                queryset = queryset.filter(channel_filters[channel])
        
        return queryset.order_by('-created_at')


class RecipientDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete a recipient
    """
    serializer_class = RecipientSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Recipient.objects.filter(merchant=self.request.user)
    
    def destroy(self, request, *args, **kwargs):
        recipient = self.get_object()
        
        # Soft delete - mark as inactive
        recipient.is_active = False
        recipient.save()
        
        return Response(status=status.HTTP_204_NO_CONTENT)


class BulkRecipientImportView(generics.CreateAPIView):
    """
    Bulk import recipients from CSV or JSON
    """
    serializer_class = BulkRecipientImportSerializer
    permission_classes = [permissions.IsAuthenticated]


class RecipientImportListView(generics.ListAPIView):
    """
    List recipient import operations
    """
    serializer_class = BulkRecipientImportSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return RecipientImport.objects.filter(
            merchant=self.request.user
        ).order_by('-created_at')


class RecipientTagListCreateView(generics.ListCreateAPIView):
    """
    List or create recipient tags
    """
    serializer_class = RecipientTagSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return RecipientTag.objects.filter(
            merchant=self.request.user
        ).order_by('name')


class RecipientTagDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete a recipient tag
    """
    serializer_class = RecipientTagSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return RecipientTag.objects.filter(merchant=self.request.user)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def recipient_stats(request):
    """
    Get recipient statistics for the merchant
    """
    merchant = request.user
    recipients = Recipient.objects.filter(merchant=merchant)
    
    # Basic stats
    total_recipients = recipients.count()
    active_recipients = recipients.filter(is_active=True).count()
    
    # Opt-in stats
    opted_in_email = recipients.filter(is_active=True, email_opted_in=True, email__isnull=False).exclude(email='').count()
    opted_in_sms = recipients.filter(is_active=True, sms_opted_in=True, phone__isnull=False).exclude(phone='').count()
    opted_in_push = recipients.filter(is_active=True, push_opted_in=True, device_token__isnull=False).exclude(device_token='').count()
    opted_in_whatsapp = recipients.filter(is_active=True, whatsapp_opted_in=True).filter(Q(whatsapp__isnull=False) | Q(phone__isnull=False)).count()
    
    # Engagement breakdown
    engagements = RecipientEngagement.objects.filter(
        recipient__merchant=merchant
    ).values('event_type').annotate(count=Count('id'))
    
    engagement_breakdown = {item['event_type']: item['count'] for item in engagements}
    
    # Recent engagements
    recent_engagements = RecipientEngagement.objects.filter(
        recipient__merchant=merchant
    ).select_related('recipient').order_by('-created_at')[:10]
    
    recent_engagements_data = []
    for engagement in recent_engagements:
        recent_engagements_data.append({
            'recipient_name': engagement.recipient.full_name or engagement.recipient.email,
            'event_type': engagement.event_type,
            'channel': engagement.channel,
            'created_at': engagement.created_at
        })
    
    # Top engaged recipients
    top_engaged = recipients.filter(
        engagement_score__gt=0
    ).order_by('-engagement_score')[:5]
    
    top_engaged_recipients = []
    for recipient in top_engaged:
        top_engaged_recipients.append({
            'id': recipient.id,
            'name': recipient.full_name or recipient.email,
            'engagement_score': recipient.engagement_score,
            'last_engagement': recipient.last_engagement
        })
    
    stats = {
        'total_recipients': total_recipients,
        'active_recipients': active_recipients,
        'opted_in_email': opted_in_email,
        'opted_in_sms': opted_in_sms,
        'opted_in_push': opted_in_push,
        'opted_in_whatsapp': opted_in_whatsapp,
        'engagement_breakdown': engagement_breakdown,
        'recent_engagements': recent_engagements_data,
        'top_engaged_recipients': top_engaged_recipients
    }
    
    return Response(stats)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def export_recipients(request):
    """
    Export recipients to CSV or JSON
    """
    serializer = ExportRecipientsSerializer(
        data=request.data,
        context={'request': request}
    )
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    validated_data = serializer.validated_data
    format_type = validated_data['format']
    include_inactive = validated_data['include_inactive']
    include_opted_out = validated_data['include_opted_out']
    recipient_list_id = validated_data.get('recipient_list_id')
    
    # Build queryset
    queryset = Recipient.objects.filter(merchant=request.user)
    
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    
    if recipient_list_id:
        queryset = queryset.filter(
            list_memberships__recipient_list_id=recipient_list_id,
            list_memberships__is_active=True
        )
    
    recipients = queryset.distinct()
    
    if format_type == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="recipients.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'email', 'phone', 'device_token', 'whatsapp',
            'first_name', 'last_name', 'is_active',
            'email_opted_in', 'sms_opted_in', 'push_opted_in', 'whatsapp_opted_in',
            'engagement_score', 'created_at'
        ])
        
        for recipient in recipients:
            writer.writerow([
                recipient.email,
                recipient.phone,
                recipient.device_token,
                recipient.whatsapp,
                recipient.first_name,
                recipient.last_name,
                recipient.is_active,
                recipient.email_opted_in,
                recipient.sms_opted_in,
                recipient.push_opted_in,
                recipient.whatsapp_opted_in,
                recipient.engagement_score,
                recipient.created_at.isoformat()
            ])
        
        return response
    
    else:  # JSON format
        recipients_data = RecipientSerializer(recipients, many=True).data
        
        response = HttpResponse(
            json.dumps(recipients_data, indent=2, default=str),
            content_type='application/json'
        )
        response['Content-Disposition'] = 'attachment; filename="recipients.json"'
        
        return response


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def search_recipients(request):
    """
    Search recipients based on criteria
    """
    serializer = RecipientSearchSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    validated_data = serializer.validated_data
    query = validated_data['query']
    channel = validated_data.get('channel')
    opted_in_only = validated_data['opted_in_only']
    active_only = validated_data['active_only']
    tag_ids = validated_data.get('tags', [])
    
    # Build search queryset
    queryset = Recipient.objects.filter(merchant=request.user)
    
    if active_only:
        queryset = queryset.filter(is_active=True)
    
    # Text search
    queryset = queryset.filter(
        Q(email__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query) |
        Q(phone__icontains=query)
    )
    
    # Channel filter
    if channel:
        channel_filters = {
            'email': Q(email__isnull=False, email__ne='') & (Q(email_opted_in=True) if opted_in_only else Q()),
            'sms': Q(phone__isnull=False, phone__ne='') & (Q(sms_opted_in=True) if opted_in_only else Q()),
            'push': Q(device_token__isnull=False, device_token__ne='') & (Q(push_opted_in=True) if opted_in_only else Q()),
            'whatsapp': (Q(whatsapp__isnull=False, whatsapp__ne='') | Q(phone__isnull=False, phone__ne='')) & (Q(whatsapp_opted_in=True) if opted_in_only else Q())
        }
        
        if channel in channel_filters:
            queryset = queryset.filter(channel_filters[channel])
    
    # Tag filter
    if tag_ids:
        queryset = queryset.filter(tag_assignments__tag_id__in=tag_ids)
    
    recipients = queryset.distinct()[:100]  # Limit results
    
    return Response({
        'recipients': RecipientSerializer(recipients, many=True).data,
        'total_found': recipients.count()
    })
