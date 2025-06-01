from celery import shared_task
from django.utils import timezone
from django.db import transaction
from .models import RecipientImport, Recipient, RecipientList, RecipientListMembership
import csv
import io
import json
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def process_recipient_import_task(self, import_id, csv_content=None, recipients_data=None):
    """
    Process bulk recipient import from CSV or JSON data
    """
    try:
        import_record = RecipientImport.objects.get(id=import_id)
        
        # Update status to processing
        import_record.status = 'processing'
        import_record.started_at = timezone.now()
        import_record.save()
        
        recipients_to_process = []
        
        # Parse data based on format
        if csv_content:
            # Parse CSV content
            csv_reader = csv.DictReader(io.StringIO(csv_content))
            recipients_to_process = list(csv_reader)
        elif recipients_data:
            # Use provided JSON data
            recipients_to_process = recipients_data
        else:
            raise ValueError("No data provided for import")
        
        import_record.total_rows = len(recipients_to_process)
        import_record.save()
        
        # Process recipients in batches
        batch_size = 100
        successful_imports = 0
        failed_imports = 0
        duplicate_skips = 0
        error_log = []
        
        for i in range(0, len(recipients_to_process), batch_size):
            batch = recipients_to_process[i:i + batch_size]
            
            with transaction.atomic():
                for row_index, recipient_data in enumerate(batch, start=i + 1):
                    try:
                        # Validate required fields
                        email = recipient_data.get('email', '').strip()
                        phone = recipient_data.get('phone', '').strip()
                        device_token = recipient_data.get('device_token', '').strip()
                        
                        # At least one contact method required
                        if not any([email, phone, device_token]):
                            error_log.append({
                                'row': row_index,
                                'error': 'At least one contact method (email, phone, device_token) required'
                            })
                            failed_imports += 1
                            continue
                        
                        # Check for duplicates
                        existing_recipient = None
                        if email:
                            existing_recipient = Recipient.objects.filter(
                                merchant=import_record.merchant,
                                email=email
                            ).first()
                        
                        if not existing_recipient and phone:
                            existing_recipient = Recipient.objects.filter(
                                merchant=import_record.merchant,
                                phone=phone
                            ).first()
                        
                        if existing_recipient:
                            # Update existing recipient
                            existing_recipient.first_name = recipient_data.get('first_name', existing_recipient.first_name)
                            existing_recipient.last_name = recipient_data.get('last_name', existing_recipient.last_name)
                            existing_recipient.phone = phone or existing_recipient.phone
                            existing_recipient.email = email or existing_recipient.email
                            existing_recipient.device_token = device_token or existing_recipient.device_token
                            existing_recipient.whatsapp = recipient_data.get('whatsapp', existing_recipient.whatsapp)
                            
                            # Update custom fields
                            custom_fields = existing_recipient.custom_fields or {}
                            for key, value in recipient_data.items():
                                if key not in ['email', 'phone', 'device_token', 'first_name', 'last_name', 'whatsapp']:
                                    custom_fields[key] = value
                            existing_recipient.custom_fields = custom_fields
                            
                            existing_recipient.save()
                            duplicate_skips += 1
                            
                            # Add to recipient list if specified
                            if import_record.recipient_list:
                                RecipientListMembership.objects.get_or_create(
                                    recipient_list=import_record.recipient_list,
                                    recipient=existing_recipient,
                                    defaults={'added_by': import_record.merchant}
                                )
                        else:
                            # Create new recipient
                            custom_fields = {}
                            for key, value in recipient_data.items():
                                if key not in ['email', 'phone', 'device_token', 'first_name', 'last_name', 'whatsapp']:
                                    custom_fields[key] = value
                            
                            new_recipient = Recipient.objects.create(
                                merchant=import_record.merchant,
                                email=email,
                                phone=phone,
                                device_token=device_token,
                                whatsapp=recipient_data.get('whatsapp', ''),
                                first_name=recipient_data.get('first_name', ''),
                                last_name=recipient_data.get('last_name', ''),
                                custom_fields=custom_fields
                            )
                            
                            successful_imports += 1
                            
                            # Add to recipient list if specified
                            if import_record.recipient_list:
                                RecipientListMembership.objects.create(
                                    recipient_list=import_record.recipient_list,
                                    recipient=new_recipient,
                                    added_by=import_record.merchant
                                )
                        
                    except Exception as e:
                        error_log.append({
                            'row': row_index,
                            'error': str(e),
                            'data': recipient_data
                        })
                        failed_imports += 1
                        logger.error(f"Error processing recipient at row {row_index}: {e}")
        
        # Update import record with results
        import_record.successful_imports = successful_imports
        import_record.failed_imports = failed_imports
        import_record.duplicate_skips = duplicate_skips
        import_record.error_log = error_log
        import_record.status = 'completed'
        import_record.completed_at = timezone.now()
        import_record.save()
        
        # Update recipient list counters
        if import_record.recipient_list:
            recipient_list = import_record.recipient_list
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
        
        logger.info(f"Import {import_id} completed: {successful_imports} successful, {failed_imports} failed, {duplicate_skips} duplicates")
        
    except RecipientImport.DoesNotExist:
        logger.error(f"Recipient import {import_id} not found")
    except Exception as exc:
        logger.error(f"Error processing recipient import {import_id}: {exc}")
        
        # Update import record as failed
        try:
            import_record = RecipientImport.objects.get(id=import_id)
            import_record.status = 'failed'
            import_record.error_log = [{'error': str(exc)}]
            import_record.completed_at = timezone.now()
            import_record.save()
        except:
            pass


@shared_task
def update_recipient_engagement_scores():
    """
    Update engagement scores for all recipients based on their activity
    """
    from .models import RecipientEngagement
    from django.db.models import Count, Avg, Q
    from datetime import timedelta
    
    # Get recipients with recent activity
    recent_date = timezone.now() - timedelta(days=30)
    
    recipients_with_activity = Recipient.objects.filter(
        engagements__created_at__gte=recent_date
    ).distinct()
    
    updated_count = 0
    
    for recipient in recipients_with_activity:
        # Calculate engagement score based on recent activity
        engagements = RecipientEngagement.objects.filter(
            recipient=recipient,
            created_at__gte=recent_date
        )
        
        # Weight different engagement types
        weights = {
            'sent': 1,
            'delivered': 2,
            'opened': 5,
            'clicked': 10,
            'unsubscribed': -5,
            'bounced': -2
        }
        
        total_score = 0
        for engagement in engagements:
            weight = weights.get(engagement.event_type, 1)
            total_score += weight
        
        # Normalize score (0-100 scale)
        max_possible_score = len(engagements) * 10  # Assuming best case all clicks
        if max_possible_score > 0:
            normalized_score = min(100, (total_score / max_possible_score) * 100)
        else:
            normalized_score = 0
        
        # Update recipient
        recipient.engagement_score = max(0, normalized_score)
        recipient.last_engagement = engagements.order_by('-created_at').first().created_at
        recipient.save(update_fields=['engagement_score', 'last_engagement'])
        
        updated_count += 1
    
    if updated_count > 0:
        logger.info(f"Updated engagement scores for {updated_count} recipients")


@shared_task
def cleanup_inactive_recipients():
    """
    Clean up recipients that haven't been active for a long time
    """
    from datetime import timedelta
    
    # Mark recipients as inactive if no activity for 1 year
    cutoff_date = timezone.now() - timedelta(days=365)
    
    inactive_recipients = Recipient.objects.filter(
        is_active=True,
        last_engagement__lt=cutoff_date
    ).exclude(
        # Don't deactivate recently created recipients
        created_at__gte=cutoff_date
    )
    
    updated_count = inactive_recipients.update(is_active=False)
    
    if updated_count > 0:
        logger.info(f"Marked {updated_count} recipients as inactive due to long inactivity")


@shared_task
def sync_recipient_lists():
    """
    Sync recipient list counters and clean up memberships
    """
    updated_lists = 0
    
    for recipient_list in RecipientList.objects.filter(is_active=True):
        # Count active memberships
        total_recipients = RecipientListMembership.objects.filter(
            recipient_list=recipient_list,
            is_active=True
        ).count()
        
        active_recipients = RecipientListMembership.objects.filter(
            recipient_list=recipient_list,
            is_active=True,
            recipient__is_active=True
        ).count()
        
        # Update if counts have changed
        if (recipient_list.total_recipients != total_recipients or 
            recipient_list.active_recipients != active_recipients):
            
            recipient_list.total_recipients = total_recipients
            recipient_list.active_recipients = active_recipients
            recipient_list.save(update_fields=['total_recipients', 'active_recipients'])
            
            updated_lists += 1
    
    if updated_lists > 0:
        logger.info(f"Updated counters for {updated_lists} recipient lists")


@shared_task
def export_recipients_task(merchant_id, export_params):
    """
    Export recipients to file (async version of export functionality)
    """
    try:
        from accounts.models import Merchant
        merchant = Merchant.objects.get(id=merchant_id)
        
        # Build queryset based on export parameters
        queryset = Recipient.objects.filter(merchant=merchant)
        
        if not export_params.get('include_inactive', False):
            queryset = queryset.filter(is_active=True)
        
        if export_params.get('recipient_list_id'):
            queryset = queryset.filter(
                list_memberships__recipient_list_id=export_params['recipient_list_id'],
                list_memberships__is_active=True
            )
        
        recipients = queryset.distinct()
        
        # Generate export file
        format_type = export_params.get('format', 'csv')
        
        if format_type == 'csv':
            # Generate CSV content
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow([
                'email', 'phone', 'device_token', 'whatsapp',
                'first_name', 'last_name', 'is_active',
                'email_opted_in', 'sms_opted_in', 'push_opted_in', 'whatsapp_opted_in',
                'engagement_score', 'created_at'
            ])
            
            # Write data
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
            
            content = output.getvalue()
            
        else:  # JSON format
            from .serializers import RecipientSerializer
            recipients_data = RecipientSerializer(recipients, many=True).data
            content = json.dumps(recipients_data, indent=2, default=str)
        
        # Save to file system or send via email
        # For now, just log the success
        logger.info(f"Export completed for merchant {merchant_id}: {recipients.count()} recipients")
        
        return {
            'success': True,
            'total_exported': recipients.count(),
            'format': format_type
        }
        
    except Exception as e:
        logger.error(f"Error exporting recipients for merchant {merchant_id}: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@shared_task
def validate_recipient_data():
    """
    Validate and clean recipient data
    """
    import re
    
    # Validate email addresses
    invalid_emails = Recipient.objects.filter(
        email__isnull=False
    ).exclude(email='')
    
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    fixed_emails = 0
    
    for recipient in invalid_emails:
        if not re.match(email_pattern, recipient.email):
            # Mark as invalid or try to fix
            logger.warning(f"Invalid email for recipient {recipient.id}: {recipient.email}")
            # Could implement email cleaning logic here
    
    # Validate phone numbers
    invalid_phones = Recipient.objects.filter(
        phone__isnull=False
    ).exclude(phone='')
    
    fixed_phones = 0
    
    for recipient in invalid_phones:
        # Clean phone number
        cleaned_phone = re.sub(r'[^\d+]', '', recipient.phone)
        
        if cleaned_phone != recipient.phone:
            recipient.phone = cleaned_phone
            recipient.save(update_fields=['phone'])
            fixed_phones += 1
    
    logger.info(f"Data validation completed: {fixed_phones} phone numbers cleaned")
