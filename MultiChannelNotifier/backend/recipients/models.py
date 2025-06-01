from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class RecipientList(models.Model):
    """
    Managed lists of recipients for campaigns
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recipient_lists')
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # List metadata
    total_recipients = models.PositiveIntegerField(default=0)
    active_recipients = models.PositiveIntegerField(default=0)
    
    # List settings
    is_active = models.BooleanField(default=True)
    auto_sync = models.BooleanField(default=False, help_text="Auto-sync with external sources")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'recipient_lists'
        unique_together = ['merchant', 'name']
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"{self.name} ({self.total_recipients} recipients)"


class Recipient(models.Model):
    """
    Individual recipient with contact information
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recipients')
    
    # Contact information
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    device_token = models.CharField(max_length=255, blank=True, help_text="Push notification token")
    whatsapp = models.CharField(max_length=20, blank=True)
    
    # Personal information
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    
    # Additional data
    custom_fields = models.JSONField(default=dict, blank=True)
    
    # Status and preferences
    is_active = models.BooleanField(default=True)
    email_opted_in = models.BooleanField(default=True)
    sms_opted_in = models.BooleanField(default=True)
    push_opted_in = models.BooleanField(default=True)
    whatsapp_opted_in = models.BooleanField(default=True)
    
    # Tracking
    last_engagement = models.DateTimeField(null=True, blank=True)
    engagement_score = models.FloatField(default=0.0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'recipients'
        indexes = [
            models.Index(fields=['merchant', 'email']),
            models.Index(fields=['merchant', 'phone']),
            models.Index(fields=['is_active', 'email_opted_in']),
        ]
    
    def __str__(self):
        name = f"{self.first_name} {self.last_name}".strip()
        if name:
            return name
        return self.email or self.phone or str(self.id)
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    def get_contact_for_channel(self, channel):
        """Get contact information for specific channel"""
        channel_mapping = {
            'email': self.email,
            'sms': self.phone,
            'push': self.device_token,
            'whatsapp': self.whatsapp or self.phone
        }
        return channel_mapping.get(channel)
    
    def is_opted_in_for_channel(self, channel):
        """Check if recipient is opted in for specific channel"""
        opt_in_mapping = {
            'email': self.email_opted_in,
            'sms': self.sms_opted_in,
            'push': self.push_opted_in,
            'whatsapp': self.whatsapp_opted_in
        }
        return opt_in_mapping.get(channel, False)


class RecipientListMembership(models.Model):
    """
    Many-to-many relationship between recipients and lists
    """
    recipient_list = models.ForeignKey(RecipientList, on_delete=models.CASCADE, related_name='memberships')
    recipient = models.ForeignKey(Recipient, on_delete=models.CASCADE, related_name='list_memberships')
    
    # Membership metadata
    added_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'recipient_list_memberships'
        unique_together = ['recipient_list', 'recipient']
        indexes = [
            models.Index(fields=['recipient_list', 'is_active']),
        ]


class RecipientImport(models.Model):
    """
    Track bulk import operations
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recipient_imports')
    recipient_list = models.ForeignKey(RecipientList, on_delete=models.CASCADE, related_name='imports', null=True, blank=True)
    
    # Import details
    filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField()
    
    # Import status
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ], default='pending')
    
    # Import results
    total_rows = models.PositiveIntegerField(default=0)
    successful_imports = models.PositiveIntegerField(default=0)
    failed_imports = models.PositiveIntegerField(default=0)
    duplicate_skips = models.PositiveIntegerField(default=0)
    
    # Error tracking
    error_log = models.JSONField(default=list, blank=True)
    
    # Processing timestamps
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'recipient_imports'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Import {self.filename} - {self.status}"


class RecipientTag(models.Model):
    """
    Tags for organizing recipients
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recipient_tags')
    
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, default='#007bff')
    description = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'recipient_tags'
        unique_together = ['merchant', 'name']
    
    def __str__(self):
        return self.name


class RecipientTagAssignment(models.Model):
    """
    Many-to-many relationship between recipients and tags
    """
    recipient = models.ForeignKey(Recipient, on_delete=models.CASCADE, related_name='tag_assignments')
    tag = models.ForeignKey(RecipientTag, on_delete=models.CASCADE, related_name='recipient_assignments')
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'recipient_tag_assignments'
        unique_together = ['recipient', 'tag']


class RecipientEngagement(models.Model):
    """
    Track recipient engagement metrics
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(Recipient, on_delete=models.CASCADE, related_name='engagements')
    
    # Engagement details
    event_type = models.CharField(max_length=50)  # sent, delivered, opened, clicked, unsubscribed
    channel = models.CharField(max_length=20)
    
    # Associated notification/campaign
    notification_id = models.UUIDField(null=True, blank=True)
    campaign_id = models.UUIDField(null=True, blank=True)
    
    # Event metadata
    event_data = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'recipient_engagements'
        indexes = [
            models.Index(fields=['recipient', 'event_type']),
            models.Index(fields=['channel', 'event_type']),
            models.Index(fields=['created_at']),
        ]
