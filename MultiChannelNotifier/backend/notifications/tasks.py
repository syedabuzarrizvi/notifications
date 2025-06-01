from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from .models import Notification, BulkNotification, NotificationEvent, Provider, NotificationStatus, NotificationChannel
from .providers.email import EmailProvider
from .providers.sms import SMSProvider
from .providers.push import PushProvider
from .providers.whatsapp import WhatsAppProvider
import logging
import csv
import io

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_notification_task(self, notification_id):
    """
    Send a single notification
    """
    try:
        notification = Notification.objects.get(id=notification_id)
        
        # Check if notification is still pending
        if notification.status != NotificationStatus.PENDING:
            logger.info(f"Notification {notification_id} is not pending, skipping")
            return
        
        # Update status to processing
        notification.status = NotificationStatus.PROCESSING
        notification.save()
        
        # Create processing event
        NotificationEvent.objects.create(
            notification=notification,
            event_type='processing_started',
            event_data={'task_id': self.request.id}
        )
        
        # Get appropriate provider
        provider = get_provider_for_channel(notification.channel, notification.merchant)
        if not provider:
            raise Exception(f"No active provider found for channel: {notification.channel}")
        
        # Send notification
        result = provider.send(notification)
        
        if result['success']:
            # Update notification with success
            notification.status = Notification.NotificationStatus.SENT
            notification.sent_at = timezone.now()
            notification.provider = result.get('provider_name')
            notification.provider_message_id = result.get('message_id')
            notification.provider_response = result.get('response', {})
            notification.save()
            
            # Create sent event
            NotificationEvent.objects.create(
                notification=notification,
                event_type='sent',
                event_data={
                    'provider': result.get('provider_name'),
                    'message_id': result.get('message_id'),
                    'response': result.get('response', {})
                }
            )
            
            # Update merchant usage
            update_merchant_usage(notification.merchant, notification.channel)
            
            logger.info(f"Notification {notification_id} sent successfully")
        else:
            # Handle failure
            handle_notification_failure(notification, result.get('error', 'Unknown error'))
            
    except Notification.DoesNotExist:
        logger.error(f"Notification {notification_id} not found")
    except Exception as exc:
        logger.error(f"Error sending notification {notification_id}: {exc}")
        
        try:
            notification = Notification.objects.get(id=notification_id)
            handle_notification_failure(notification, str(exc))
        except:
            pass
        
        # Retry if possible
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (2 ** self.request.retries), exc=exc)


@shared_task
def process_bulk_notification_task(bulk_notification_id):
    """
    Process a bulk notification by creating individual notifications
    """
    try:
        bulk_notification = BulkNotification.objects.get(id=bulk_notification_id)
        
        # Check if bulk notification is still pending
        if bulk_notification.status != BulkNotification.NotificationStatus.PENDING:
            logger.info(f"Bulk notification {bulk_notification_id} is not pending, skipping")
            return
        
        # Update status to processing
        bulk_notification.status = BulkNotification.NotificationStatus.PROCESSING
        bulk_notification.started_at = timezone.now()
        bulk_notification.save()
        
        # Parse CSV data
        csv_reader = csv.DictReader(io.StringIO(bulk_notification.recipients_csv))
        recipients = list(csv_reader)
        
        # Create individual notifications
        notifications_created = 0
        for recipient_data in recipients:
            try:
                # Extract recipient based on channel
                recipient = get_recipient_from_data(recipient_data, bulk_notification.channel)
                if not recipient:
                    logger.warning(f"Could not extract recipient from data: {recipient_data}")
                    continue
                
                # Create notification
                notification = Notification.objects.create(
                    merchant=bulk_notification.merchant,
                    channel=bulk_notification.channel,
                    recipient=recipient,
                    subject=bulk_notification.subject,
                    message=bulk_notification.message,
                    metadata={
                        'bulk_notification_id': str(bulk_notification.id),
                        'recipient_data': recipient_data,
                        **bulk_notification.metadata
                    }
                )
                
                # Queue for sending
                send_notification_task.delay(str(notification.id))
                notifications_created += 1
                
            except Exception as e:
                logger.error(f"Error creating notification for recipient {recipient_data}: {e}")
                bulk_notification.failed_count += 1
        
        # Update bulk notification
        bulk_notification.processed_count = notifications_created
        bulk_notification.save()
        
        logger.info(f"Bulk notification {bulk_notification_id} processed: {notifications_created} notifications created")
        
    except BulkNotification.DoesNotExist:
        logger.error(f"Bulk notification {bulk_notification_id} not found")
    except Exception as exc:
        logger.error(f"Error processing bulk notification {bulk_notification_id}: {exc}")


@shared_task
def process_scheduled_notifications():
    """
    Process notifications scheduled for sending
    """
    now = timezone.now()
    scheduled_notifications = Notification.objects.filter(
        status=Notification.NotificationStatus.PENDING,
        scheduled_at__lte=now,
        scheduled_at__isnull=False
    )
    
    count = 0
    for notification in scheduled_notifications:
        send_notification_task.delay(str(notification.id))
        count += 1
    
    if count > 0:
        logger.info(f"Queued {count} scheduled notifications for sending")


@shared_task
def retry_failed_notifications():
    """
    Retry failed notifications that haven't exceeded max retries
    """
    failed_notifications = Notification.objects.filter(
        status=Notification.NotificationStatus.FAILED,
        retry_count__lt=models.F('max_retries')
    )
    
    count = 0
    for notification in failed_notifications:
        notification.retry_count += 1
        notification.status = Notification.NotificationStatus.PENDING
        notification.save()
        
        # Create retry event
        NotificationEvent.objects.create(
            notification=notification,
            event_type='retry',
            event_data={'retry_count': notification.retry_count}
        )
        
        send_notification_task.delay(str(notification.id))
        count += 1
    
    if count > 0:
        logger.info(f"Queued {count} notifications for retry")


@shared_task
def update_bulk_notification_status(bulk_notification_id):
    """
    Update bulk notification status based on individual notification results
    """
    try:
        bulk_notification = BulkNotification.objects.get(id=bulk_notification_id)
        
        # Count notifications by status
        from django.db.models import Count, Q
        
        results = Notification.objects.filter(
            metadata__bulk_notification_id=str(bulk_notification.id)
        ).aggregate(
            total=Count('id'),
            sent=Count('id', filter=Q(status=Notification.NotificationStatus.SENT)),
            delivered=Count('id', filter=Q(status=Notification.NotificationStatus.DELIVERED)),
            failed=Count('id', filter=Q(status=Notification.NotificationStatus.FAILED)),
            pending=Count('id', filter=Q(status=Notification.NotificationStatus.PENDING)),
            processing=Count('id', filter=Q(status=Notification.NotificationStatus.PROCESSING)),
        )
        
        # Update bulk notification
        bulk_notification.success_count = results['sent'] + results['delivered']
        bulk_notification.failed_count = results['failed']
        
        # Update status if all processed
        if results['pending'] == 0 and results['processing'] == 0:
            bulk_notification.status = BulkNotification.NotificationStatus.SENT
            bulk_notification.completed_at = timezone.now()
        
        bulk_notification.save()
        
    except BulkNotification.DoesNotExist:
        logger.error(f"Bulk notification {bulk_notification_id} not found")


def get_provider_for_channel(channel, merchant):
    """
    Get the appropriate provider for a channel based on merchant preferences
    """
    # Get merchant preferred provider
    preferred_provider = getattr(
        merchant.settings, 
        f'preferred_{channel}_provider', 
        None
    )
    
    # Try to get preferred provider first
    if preferred_provider:
        try:
            provider_config = Provider.objects.get(
                name=preferred_provider,
                channel=channel,
                is_active=True
            )
            return create_provider_instance(channel, provider_config)
        except Provider.DoesNotExist:
            pass
    
    # Fallback to first available provider
    try:
        provider_config = Provider.objects.filter(
            channel=channel,
            is_active=True
        ).first()
        
        if provider_config:
            return create_provider_instance(channel, provider_config)
    except Provider.DoesNotExist:
        pass
    
    return None


def create_provider_instance(channel, provider_config):
    """
    Create provider instance based on channel
    """
    if channel == Notification.NotificationChannel.EMAIL:
        return EmailProvider(provider_config)
    elif channel == Notification.NotificationChannel.SMS:
        return SMSProvider(provider_config)
    elif channel == Notification.NotificationChannel.PUSH:
        return PushProvider(provider_config)
    elif channel == Notification.NotificationChannel.WHATSAPP:
        return WhatsAppProvider(provider_config)
    
    return None


def handle_notification_failure(notification, error_message):
    """
    Handle notification failure
    """
    notification.status = Notification.NotificationStatus.FAILED
    notification.save()
    
    # Create failure event
    NotificationEvent.objects.create(
        notification=notification,
        event_type='failed',
        event_data={'error': error_message}
    )
    
    logger.error(f"Notification {notification.id} failed: {error_message}")


def update_merchant_usage(merchant, channel):
    """
    Update merchant daily usage counters
    """
    settings = merchant.settings
    field_name = f'{channel}_sent_today'
    
    # Reset if new day
    if settings.usage_reset_date < timezone.now().date():
        settings.sms_sent_today = 0
        settings.email_sent_today = 0
        settings.push_sent_today = 0
        settings.whatsapp_sent_today = 0
        settings.usage_reset_date = timezone.now().date()
    
    # Increment counter
    current_count = getattr(settings, field_name, 0)
    setattr(settings, field_name, current_count + 1)
    settings.save()


def get_recipient_from_data(recipient_data, channel):
    """
    Extract recipient contact info from CSV data based on channel
    """
    if channel == Notification.NotificationChannel.EMAIL:
        return recipient_data.get('email') or recipient_data.get('Email')
    elif channel == Notification.NotificationChannel.SMS:
        return recipient_data.get('phone') or recipient_data.get('Phone')
    elif channel == Notification.NotificationChannel.PUSH:
        return recipient_data.get('device_token') or recipient_data.get('Device_Token')
    elif channel == Notification.NotificationChannel.WHATSAPP:
        return recipient_data.get('whatsapp') or recipient_data.get('WhatsApp') or recipient_data.get('phone')
    
    return None
