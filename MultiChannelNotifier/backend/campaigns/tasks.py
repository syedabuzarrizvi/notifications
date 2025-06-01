from celery import shared_task
from django.utils import timezone
from django.db import transaction
from .models import Campaign, CampaignRecipient, CampaignEvent
from notifications.models import Notification, NotificationEvent
from notifications.tasks import send_notification_task
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def launch_campaign_task(self, campaign_id):
    """
    Launch a campaign by creating individual notifications for all recipients
    """
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        
        # Check if campaign is in correct state
        if campaign.status not in [Campaign.CampaignStatus.RUNNING, Campaign.CampaignStatus.SCHEDULED]:
            logger.info(f"Campaign {campaign_id} is not in launchable state: {campaign.status}")
            return
        
        # Update campaign status
        with transaction.atomic():
            campaign.status = Campaign.CampaignStatus.RUNNING
            campaign.started_at = timezone.now()
            campaign.save()
            
            # Create launch event
            CampaignEvent.objects.create(
                campaign=campaign,
                event_type='launch_started',
                event_data={'task_id': self.request.id}
            )
        
        # Get campaign template
        if not hasattr(campaign, 'template'):
            logger.error(f"Campaign {campaign_id} has no template")
            return
        
        template = campaign.template
        
        # Process recipients in batches
        recipients = CampaignRecipient.objects.filter(
            campaign=campaign,
            status='pending'
        ).select_related('campaign')
        
        batch_size = 100
        total_processed = 0
        
        for i in range(0, recipients.count(), batch_size):
            batch = recipients[i:i + batch_size]
            
            with transaction.atomic():
                for recipient in batch:
                    try:
                        # Render message with recipient data
                        rendered_subject = template.subject
                        rendered_message = template.message
                        
                        # Simple variable substitution
                        for key, value in recipient.recipient_data.items():
                            placeholder = f"{{{key}}}"
                            rendered_subject = rendered_subject.replace(placeholder, str(value))
                            rendered_message = rendered_message.replace(placeholder, str(value))
                        
                        # Create notification
                        notification = Notification.objects.create(
                            merchant=campaign.merchant,
                            channel=campaign.channel,
                            recipient=recipient.recipient,
                            subject=rendered_subject,
                            message=rendered_message,
                            metadata={
                                'campaign_id': str(campaign.id),
                                'recipient_id': str(recipient.id),
                                'template_id': str(template.id),
                                **recipient.recipient_data
                            }
                        )
                        
                        # Link notification to recipient
                        recipient.notification = notification
                        recipient.save()
                        
                        # Queue notification for sending
                        send_notification_task.delay(str(notification.id))
                        
                        total_processed += 1
                        
                    except Exception as e:
                        logger.error(f"Error processing recipient {recipient.id}: {e}")
                        recipient.status = 'failed'
                        recipient.error_message = str(e)
                        recipient.save()
                        
                        campaign.total_failed += 1
        
        # Update campaign metrics
        campaign.total_sent = total_processed
        campaign.save()
        
        # Create completion event
        CampaignEvent.objects.create(
            campaign=campaign,
            event_type='launch_completed',
            event_data={
                'total_processed': total_processed,
                'task_id': self.request.id
            }
        )
        
        logger.info(f"Campaign {campaign_id} launched successfully: {total_processed} notifications created")
        
    except Campaign.DoesNotExist:
        logger.error(f"Campaign {campaign_id} not found")
    except Exception as exc:
        logger.error(f"Error launching campaign {campaign_id}: {exc}")
        
        # Update campaign status to failed
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            campaign.status = Campaign.CampaignStatus.CANCELLED
            campaign.save()
            
            CampaignEvent.objects.create(
                campaign=campaign,
                event_type='launch_failed',
                event_data={'error': str(exc), 'task_id': self.request.id}
            )
        except:
            pass


@shared_task
def pause_campaign_task(campaign_id):
    """
    Pause a running campaign
    """
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        
        # Cancel pending notifications for this campaign
        pending_notifications = Notification.objects.filter(
            metadata__campaign_id=str(campaign.id),
            status='pending'
        )
        
        cancelled_count = 0
        for notification in pending_notifications:
            notification.status = 'cancelled'
            notification.save()
            
            # Create cancellation event
            NotificationEvent.objects.create(
                notification=notification,
                event_type='cancelled',
                event_data={'reason': 'campaign_paused'}
            )
            
            cancelled_count += 1
        
        # Create pause event
        CampaignEvent.objects.create(
            campaign=campaign,
            event_type='paused',
            event_data={'cancelled_notifications': cancelled_count}
        )
        
        logger.info(f"Campaign {campaign_id} paused: {cancelled_count} notifications cancelled")
        
    except Campaign.DoesNotExist:
        logger.error(f"Campaign {campaign_id} not found")
    except Exception as e:
        logger.error(f"Error pausing campaign {campaign_id}: {e}")


@shared_task
def update_campaign_metrics_task(campaign_id):
    """
    Update campaign metrics based on notification results
    """
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        
        # Get all notifications for this campaign
        notifications = Notification.objects.filter(
            metadata__campaign_id=str(campaign.id)
        )
        
        # Count by status
        from django.db.models import Count, Q
        
        metrics = notifications.aggregate(
            total_sent=Count('id', filter=Q(status__in=['sent', 'delivered'])),
            total_delivered=Count('id', filter=Q(status='delivered')),
            total_failed=Count('id', filter=Q(status='failed')),
            total_clicked=Count('id', filter=Q(events__event_type='clicked')),
            total_opened=Count('id', filter=Q(events__event_type='opened'))
        )
        
        # Update campaign metrics
        campaign.total_sent = metrics['total_sent']
        campaign.total_delivered = metrics['total_delivered']
        campaign.total_failed = metrics['total_failed']
        campaign.total_clicked = metrics['total_clicked']
        campaign.total_opened = metrics['total_opened']
        
        # Check if campaign is complete
        total_recipients = campaign.recipients.filter(status__in=['sent', 'delivered', 'failed']).count()
        expected_recipients = campaign.recipients.count()
        
        if total_recipients >= expected_recipients:
            campaign.status = Campaign.CampaignStatus.COMPLETED
            campaign.completed_at = timezone.now()
            
            # Create completion event
            CampaignEvent.objects.create(
                campaign=campaign,
                event_type='completed',
                event_data={
                    'total_sent': campaign.total_sent,
                    'total_delivered': campaign.total_delivered,
                    'total_failed': campaign.total_failed,
                    'success_rate': campaign.success_rate
                }
            )
        
        campaign.save()
        
        logger.info(f"Campaign {campaign_id} metrics updated")
        
    except Campaign.DoesNotExist:
        logger.error(f"Campaign {campaign_id} not found")
    except Exception as e:
        logger.error(f"Error updating campaign metrics {campaign_id}: {e}")


@shared_task
def process_scheduled_campaigns():
    """
    Process campaigns scheduled for launch
    """
    now = timezone.now()
    scheduled_campaigns = Campaign.objects.filter(
        status=Campaign.CampaignStatus.SCHEDULED,
        scheduled_at__lte=now
    )
    
    count = 0
    for campaign in scheduled_campaigns:
        # Update status and launch
        campaign.status = Campaign.CampaignStatus.RUNNING
        campaign.save()
        
        # Queue launch task
        launch_campaign_task.delay(str(campaign.id))
        count += 1
    
    if count > 0:
        logger.info(f"Queued {count} scheduled campaigns for launch")


@shared_task
def cleanup_old_campaign_events():
    """
    Clean up old campaign events to manage database size
    """
    from datetime import timedelta
    
    cutoff_date = timezone.now() - timedelta(days=90)  # Keep events for 90 days
    
    deleted_count = CampaignEvent.objects.filter(
        created_at__lt=cutoff_date
    ).delete()[0]
    
    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} old campaign events")


@shared_task
def generate_campaign_report(campaign_id):
    """
    Generate detailed campaign report
    """
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        
        # Collect campaign data
        report_data = {
            'campaign_name': campaign.name,
            'channel': campaign.channel,
            'status': campaign.status,
            'created_at': campaign.created_at.isoformat(),
            'started_at': campaign.started_at.isoformat() if campaign.started_at else None,
            'completed_at': campaign.completed_at.isoformat() if campaign.completed_at else None,
            'metrics': {
                'total_recipients': campaign.recipients.count(),
                'total_sent': campaign.total_sent,
                'total_delivered': campaign.total_delivered,
                'total_failed': campaign.total_failed,
                'total_opened': campaign.total_opened,
                'total_clicked': campaign.total_clicked,
                'success_rate': campaign.success_rate,
                'open_rate': campaign.open_rate,
                'click_rate': campaign.click_rate
            }
        }
        
        # Get recipient breakdown
        from django.db.models import Count
        recipient_status = campaign.recipients.values('status').annotate(
            count=Count('id')
        )
        
        report_data['recipient_breakdown'] = {
            item['status']: item['count'] for item in recipient_status
        }
        
        # Get engagement timeline
        notifications = Notification.objects.filter(
            metadata__campaign_id=str(campaign.id)
        ).prefetch_related('events')
        
        engagement_events = []
        for notification in notifications:
            for event in notification.events.all():
                engagement_events.append({
                    'timestamp': event.created_at.isoformat(),
                    'event_type': event.event_type,
                    'recipient': notification.recipient
                })
        
        # Sort by timestamp
        engagement_events.sort(key=lambda x: x['timestamp'])
        report_data['engagement_timeline'] = engagement_events
        
        # Store report (could be saved to file system, database, or sent via email)
        logger.info(f"Campaign report generated for {campaign_id}")
        
        return report_data
        
    except Campaign.DoesNotExist:
        logger.error(f"Campaign {campaign_id} not found")
    except Exception as e:
        logger.error(f"Error generating campaign report {campaign_id}: {e}")


@shared_task
def sync_campaign_recipient_status():
    """
    Sync campaign recipient status with notification status
    """
    # Find recipients where notification status doesn't match
    from django.db.models import Q
    
    recipients_to_update = CampaignRecipient.objects.filter(
        notification__isnull=False
    ).exclude(
        status=models.F('notification__status')
    )
    
    updated_count = 0
    for recipient in recipients_to_update:
        notification = recipient.notification
        
        # Map notification status to recipient status
        status_mapping = {
            'pending': 'pending',
            'processing': 'pending',
            'sent': 'sent',
            'delivered': 'delivered',
            'failed': 'failed',
            'cancelled': 'failed'
        }
        
        new_status = status_mapping.get(notification.status, recipient.status)
        
        if new_status != recipient.status:
            recipient.status = new_status
            
            # Update timestamps
            if new_status == 'sent' and not recipient.sent_at:
                recipient.sent_at = notification.sent_at
            elif new_status == 'delivered' and not recipient.delivered_at:
                recipient.delivered_at = notification.delivered_at
            
            recipient.save()
            updated_count += 1
    
    if updated_count > 0:
        logger.info(f"Updated {updated_count} campaign recipient statuses")
