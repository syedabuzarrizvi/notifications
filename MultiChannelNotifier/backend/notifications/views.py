from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from .models import Notification, BulkNotification, NotificationEvent, Provider
from .serializers import (
    NotificationSerializer, SendNotificationSerializer, ScheduleNotificationSerializer,
    BulkNotificationSerializer, NotificationDetailSerializer, ProviderSerializer,
    NotificationStatusSerializer
)
from .tasks import send_notification_task, process_bulk_notification_task
from common.throttling import NotificationRateThrottle
import logging

logger = logging.getLogger(__name__)


class NotificationRateThrottleClass(UserRateThrottle):
    scope = 'notification'


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@throttle_classes([NotificationRateThrottleClass])
def send_notification(request):
    """
    Send immediate notification
    """
    serializer = SendNotificationSerializer(data=request.data, context={'request': request})
    
    if serializer.is_valid():
        # Check for existing notification with same idempotency key
        if hasattr(serializer, 'existing_notification'):
            existing = serializer.existing_notification
            return Response({
                'message': 'Notification already exists',
                'notification': NotificationSerializer(existing).data
            }, status=status.HTTP_200_OK)
        
        # Create new notification
        with transaction.atomic():
            notification = Notification.objects.create(
                merchant=request.user,
                **serializer.validated_data
            )
            
            # Create initial event
            NotificationEvent.objects.create(
                notification=notification,
                event_type='created',
                event_data={'source': 'api'}
            )
        
        # Queue for immediate sending
        send_notification_task.delay(str(notification.id))
        
        return Response({
            'message': 'Notification queued for sending',
            'notification': NotificationSerializer(notification).data
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@throttle_classes([NotificationRateThrottleClass])
def schedule_notification(request):
    """
    Schedule notification for future delivery
    """
    serializer = ScheduleNotificationSerializer(data=request.data, context={'request': request})
    
    if serializer.is_valid():
        with transaction.atomic():
            notification = Notification.objects.create(
                merchant=request.user,
                **serializer.validated_data
            )
            
            # Create scheduled event
            NotificationEvent.objects.create(
                notification=notification,
                event_type='scheduled',
                event_data={
                    'scheduled_at': serializer.validated_data['scheduled_at'].isoformat(),
                    'source': 'api'
                }
            )
        
        return Response({
            'message': 'Notification scheduled successfully',
            'notification': NotificationSerializer(notification).data
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@throttle_classes([NotificationRateThrottleClass])
def cancel_notification(request, notification_id):
    """
    Cancel a scheduled notification
    """
    notification = get_object_or_404(
        Notification,
        id=notification_id,
        merchant=request.user
    )
    
    if notification.status not in [Notification.NotificationStatus.PENDING]:
        return Response({
            'error': f'Cannot cancel notification with status: {notification.status}'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    with transaction.atomic():
        notification.status = Notification.NotificationStatus.CANCELLED
        notification.save()
        
        NotificationEvent.objects.create(
            notification=notification,
            event_type='cancelled',
            event_data={'cancelled_by': 'user', 'source': 'api'}
        )
    
    return Response({
        'message': 'Notification cancelled successfully',
        'notification': NotificationSerializer(notification).data
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def notification_status(request, notification_id):
    """
    Get notification delivery status
    """
    notification = get_object_or_404(
        Notification,
        id=notification_id,
        merchant=request.user
    )
    
    return Response(NotificationDetailSerializer(notification).data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@throttle_classes([NotificationRateThrottleClass])
def send_bulk_notification(request):
    """
    Send bulk notifications
    """
    serializer = BulkNotificationSerializer(data=request.data, context={'request': request})
    
    if serializer.is_valid():
        bulk_notification = serializer.save()
        
        # Queue bulk processing
        if bulk_notification.scheduled_at:
            # Schedule for later
            process_bulk_notification_task.apply_async(
                args=[str(bulk_notification.id)],
                eta=bulk_notification.scheduled_at
            )
        else:
            # Process immediately
            process_bulk_notification_task.delay(str(bulk_notification.id))
        
        return Response({
            'message': 'Bulk notification queued for processing',
            'bulk_notification': BulkNotificationSerializer(bulk_notification).data
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class NotificationListView(generics.ListAPIView):
    """
    List merchant notifications with filtering
    """
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = Notification.objects.filter(merchant=self.request.user)
        
        # Apply filters
        channel = self.request.query_params.get('channel')
        status_filter = self.request.query_params.get('status')
        
        if channel:
            queryset = queryset.filter(channel=channel)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.order_by('-created_at')


class BulkNotificationListView(generics.ListAPIView):
    """
    List merchant bulk notifications
    """
    serializer_class = BulkNotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return BulkNotification.objects.filter(
            merchant=self.request.user
        ).order_by('-created_at')


class BulkNotificationDetailView(generics.RetrieveAPIView):
    """
    Get bulk notification details
    """
    serializer_class = BulkNotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return BulkNotification.objects.filter(merchant=self.request.user)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def cancel_bulk_notification(request, bulk_id):
    """
    Cancel a bulk notification
    """
    bulk_notification = get_object_or_404(
        BulkNotification,
        id=bulk_id,
        merchant=request.user
    )
    
    if bulk_notification.status not in [BulkNotification.NotificationStatus.PENDING]:
        return Response({
            'error': f'Cannot cancel bulk notification with status: {bulk_notification.status}'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    bulk_notification.status = BulkNotification.NotificationStatus.CANCELLED
    bulk_notification.save()
    
    return Response({
        'message': 'Bulk notification cancelled successfully',
        'bulk_notification': BulkNotificationSerializer(bulk_notification).data
    })


class ProviderListView(generics.ListAPIView):
    """
    List available notification providers
    """
    serializer_class = ProviderSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Provider.objects.filter(is_active=True)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_stats(request):
    """
    Get dashboard statistics for the merchant
    """
    merchant = request.user
    
    # Get stats for different time periods
    from django.db.models import Count, Q
    from datetime import datetime, timedelta
    
    now = timezone.now()
    today = now.date()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    
    # Base queryset
    notifications = Notification.objects.filter(merchant=merchant)
    
    stats = {
        'total_notifications': notifications.count(),
        'today_notifications': notifications.filter(created_at__date=today).count(),
        'week_notifications': notifications.filter(created_at__gte=week_ago).count(),
        'month_notifications': notifications.filter(created_at__gte=month_ago).count(),
        
        # Status breakdown
        'status_breakdown': dict(
            notifications.values('status').annotate(count=Count('status')).values_list('status', 'count')
        ),
        
        # Channel breakdown
        'channel_breakdown': dict(
            notifications.values('channel').annotate(count=Count('channel')).values_list('channel', 'count')
        ),
        
        # Success rate
        'success_rate': {
            'total': notifications.count(),
            'sent': notifications.filter(status=Notification.NotificationStatus.SENT).count(),
            'delivered': notifications.filter(status=Notification.NotificationStatus.DELIVERED).count(),
            'failed': notifications.filter(status=Notification.NotificationStatus.FAILED).count(),
        }
    }
    
    # Calculate percentages
    if stats['success_rate']['total'] > 0:
        total = stats['success_rate']['total']
        stats['success_rate']['sent_percentage'] = round((stats['success_rate']['sent'] / total) * 100, 2)
        stats['success_rate']['delivered_percentage'] = round((stats['success_rate']['delivered'] / total) * 100, 2)
        stats['success_rate']['failed_percentage'] = round((stats['success_rate']['failed'] / total) * 100, 2)
    
    return Response(stats)
