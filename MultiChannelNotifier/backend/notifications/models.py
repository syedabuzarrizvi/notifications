from django.db import models
from django.contrib.auth import get_user_model
import uuid


User = get_user_model()


class NotificationChannel(models.TextChoices):
    EMAIL = 'email', 'Email'
    SMS = 'sms', 'SMS'
    PUSH = 'push', 'Push Notification'
    WHATSAPP = 'whatsapp', 'WhatsApp'


class NotificationStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    PROCESSING = 'processing', 'Processing'
    SENT = 'sent', 'Sent'
    DELIVERED = 'delivered', 'Delivered'
    FAILED = 'failed', 'Failed'
    CANCELLED = 'cancelled', 'Cancelled'


class NotificationPriority(models.TextChoices):
    LOW = 'low', 'Low'
    NORMAL = 'normal', 'Normal'
    HIGH = 'high', 'High'
    URGENT = 'urgent', 'Urgent'


class Notification(models.Model):
    """
    Core notification model representing a single notification to be sent
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    
    # Notification details
    channel = models.CharField(max_length=20, choices=NotificationChannel.choices)
    recipient = models.CharField(max_length=255)  # Phone, email, or device token
    subject = models.CharField(max_length=255, blank=True)
    message = models.TextField()
    
    # Additional data for rich notifications
    metadata = models.JSONField(default=dict, blank=True)
    
    # Status and tracking
    status = models.CharField(max_length=20, choices=NotificationStatus.choices, default=NotificationStatus.PENDING)
    priority = models.CharField(max_length=10, choices=NotificationPriority.choices, default=NotificationPriority.NORMAL)
    
    # Scheduling
    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    # Provider information
    provider = models.CharField(max_length=50, blank=True)
    provider_message_id = models.CharField(max_length=255, blank=True)
    provider_response = models.JSONField(default=dict, blank=True)
    
    # Retry mechanism
    retry_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=3)
    
    # Idempotency
    idempotency_key = models.CharField(max_length=255, db_index=True, null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'notifications'
        indexes = [
            models.Index(fields=['merchant', 'status']),
            models.Index(fields=['channel', 'status']),
            models.Index(fields=['scheduled_at']),
            models.Index(fields=['idempotency_key']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['merchant', 'idempotency_key'],
                name='unique_merchant_idempotency',
                condition=models.Q(idempotency_key__isnull=False)
            )
        ]
    
    def __str__(self):
        return f"{self.channel} to {self.recipient} - {self.status}"


class NotificationEvent(models.Model):
    """
    Track notification lifecycle events
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name='events')
    
    event_type = models.CharField(max_length=50)  # created, sent, delivered, failed, etc.
    event_data = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'notification_events'
        ordering = ['-created_at']


class BulkNotification(models.Model):
    """
    Represents a bulk notification job
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bulk_notifications')
    
    # Bulk job details
    name = models.CharField(max_length=255)
    channel = models.CharField(max_length=20, choices=NotificationChannel.choices)
    message = models.TextField()
    subject = models.CharField(max_length=255, blank=True)
    
    # Recipients data
    recipients_csv = models.TextField()  # Store CSV data
    total_recipients = models.PositiveIntegerField(default=0)
    
    # Status tracking
    status = models.CharField(max_length=20, choices=NotificationStatus.choices, default=NotificationStatus.PENDING)
    processed_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    
    # Scheduling
    scheduled_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Additional settings
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'bulk_notifications'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} - {self.channel} ({self.total_recipients} recipients)"


class Provider(models.Model):
    """
    Configuration for notification providers
    """
    name = models.CharField(max_length=50, unique=True)
    channel = models.CharField(max_length=20, choices=NotificationChannel.choices)
    is_active = models.BooleanField(default=True)
    
    # Provider configuration
    config = models.JSONField(default=dict)
    
    # Rate limits
    rate_limit_per_minute = models.PositiveIntegerField(default=100)
    rate_limit_per_hour = models.PositiveIntegerField(default=1000)
    
    # Priority for provider selection
    priority = models.PositiveIntegerField(default=1)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'providers'
        ordering = ['priority']
    
    def __str__(self):
        return f"{self.name} ({self.channel})"
