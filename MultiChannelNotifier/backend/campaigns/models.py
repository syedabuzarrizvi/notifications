from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class CampaignStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    SCHEDULED = 'scheduled', 'Scheduled'
    RUNNING = 'running', 'Running'
    PAUSED = 'paused', 'Paused'
    COMPLETED = 'completed', 'Completed'
    CANCELLED = 'cancelled', 'Cancelled'


class Campaign(models.Model):
    """
    Campaign model for organizing and tracking notification campaigns
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='campaigns')
    
    # Campaign details
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Campaign settings
    channel = models.CharField(max_length=20, choices=[
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('push', 'Push Notification'),
        ('whatsapp', 'WhatsApp'),
    ])
    
    # Status and timing
    status = models.CharField(max_length=20, choices=CampaignStatus.choices, default=CampaignStatus.DRAFT)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Target audience
    target_audience = models.JSONField(default=dict, help_text="Audience targeting criteria")
    estimated_recipients = models.PositiveIntegerField(default=0)
    
    # Campaign metrics
    total_sent = models.PositiveIntegerField(default=0)
    total_delivered = models.PositiveIntegerField(default=0)
    total_failed = models.PositiveIntegerField(default=0)
    total_clicked = models.PositiveIntegerField(default=0)
    total_opened = models.PositiveIntegerField(default=0)
    
    # Budget and limits
    budget_limit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    daily_limit = models.PositiveIntegerField(null=True, blank=True)
    
    # Campaign settings
    settings = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'campaigns'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['merchant', 'status']),
            models.Index(fields=['channel', 'status']),
            models.Index(fields=['scheduled_at']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.channel}) - {self.status}"
    
    @property
    def success_rate(self):
        """Calculate campaign success rate"""
        if self.total_sent == 0:
            return 0
        return (self.total_delivered / self.total_sent) * 100
    
    @property
    def open_rate(self):
        """Calculate email open rate"""
        if self.total_delivered == 0:
            return 0
        return (self.total_opened / self.total_delivered) * 100
    
    @property
    def click_rate(self):
        """Calculate click-through rate"""
        if self.total_delivered == 0:
            return 0
        return (self.total_clicked / self.total_delivered) * 100


class CampaignTemplate(models.Model):
    """
    Template associated with a campaign
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.OneToOneField(Campaign, on_delete=models.CASCADE, related_name='template')
    
    # Template content
    subject = models.CharField(max_length=255, blank=True)
    message = models.TextField()
    html_content = models.TextField(blank=True)
    
    # Template variables
    variables = models.JSONField(default=dict, blank=True)
    
    # A/B testing
    is_variant = models.BooleanField(default=False)
    variant_name = models.CharField(max_length=100, blank=True)
    parent_template = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'campaign_templates'
    
    def __str__(self):
        return f"Template for {self.campaign.name}"


class CampaignRecipient(models.Model):
    """
    Recipients for a campaign
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='recipients')
    
    # Recipient details
    recipient = models.CharField(max_length=255)  # Email, phone, device token
    recipient_data = models.JSONField(default=dict, blank=True)  # Additional data for personalization
    
    # Status tracking
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
        ('opted_out', 'Opted Out'),
    ], default='pending')
    
    # Linked notification
    notification = models.ForeignKey(
        'notifications.Notification', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='campaign_recipient'
    )
    
    # Tracking
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    
    # Error tracking
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'campaign_recipients'
        unique_together = ['campaign', 'recipient']
        indexes = [
            models.Index(fields=['campaign', 'status']),
            models.Index(fields=['status', 'sent_at']),
        ]
    
    def __str__(self):
        return f"{self.recipient} - {self.campaign.name}"


class CampaignEvent(models.Model):
    """
    Track campaign lifecycle events
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='events')
    
    event_type = models.CharField(max_length=50)  # created, started, paused, completed, etc.
    event_data = models.JSONField(default=dict, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'campaign_events'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.campaign.name} - {self.event_type}"


class AudienceSegment(models.Model):
    """
    Reusable audience segments for targeting
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='audience_segments')
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Segment criteria
    criteria = models.JSONField(default=dict)
    
    # Cached recipient count
    recipient_count = models.PositiveIntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    
    # Usage tracking
    campaigns_used = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'audience_segments'
        unique_together = ['merchant', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.recipient_count} recipients)"
