from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class TemplateCategory(models.TextChoices):
    MARKETING = 'marketing', 'Marketing'
    TRANSACTIONAL = 'transactional', 'Transactional'
    NOTIFICATION = 'notification', 'Notification'
    PROMOTIONAL = 'promotional', 'Promotional'
    SYSTEM = 'system', 'System'


class Template(models.Model):
    """
    Reusable message templates for notifications
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='templates')
    
    # Template details
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=TemplateCategory.choices, default=TemplateCategory.MARKETING)
    
    # Channel settings
    channel = models.CharField(max_length=20, choices=[
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('push', 'Push Notification'),
        ('whatsapp', 'WhatsApp'),
        ('multi', 'Multi-channel'),
    ])
    
    # Content
    subject = models.CharField(max_length=255, blank=True, help_text="Subject line for email/push notifications")
    content = models.TextField(help_text="Main message content")
    html_content = models.TextField(blank=True, help_text="HTML version for email")
    
    # Template variables
    variables = models.JSONField(default=dict, blank=True, help_text="Template variables for personalization")
    
    # Usage tracking
    usage_count = models.PositiveIntegerField(default=0)
    last_used = models.DateTimeField(null=True, blank=True)
    
    # Template settings
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False, help_text="System templates cannot be deleted")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'templates'
        unique_together = ['merchant', 'name']
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['merchant', 'channel']),
            models.Index(fields=['category', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.channel})"
    
    def increment_usage(self):
        """Increment usage counter and update last used timestamp"""
        from django.utils import timezone
        self.usage_count += 1
        self.last_used = timezone.now()
        self.save(update_fields=['usage_count', 'last_used'])


class TemplateVersion(models.Model):
    """
    Version history for templates
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(Template, on_delete=models.CASCADE, related_name='versions')
    
    version_number = models.PositiveIntegerField()
    subject = models.CharField(max_length=255, blank=True)
    content = models.TextField()
    html_content = models.TextField(blank=True)
    variables = models.JSONField(default=dict, blank=True)
    
    # Change tracking
    change_summary = models.TextField(blank=True)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'template_versions'
        unique_together = ['template', 'version_number']
        ordering = ['-version_number']
    
    def __str__(self):
        return f"{self.template.name} v{self.version_number}"


class TemplatePreview(models.Model):
    """
    Preview renderings of templates with sample data
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(Template, on_delete=models.CASCADE, related_name='previews')
    
    preview_name = models.CharField(max_length=255)
    sample_data = models.JSONField(default=dict, help_text="Sample variable values for preview")
    
    # Rendered content
    rendered_subject = models.CharField(max_length=255, blank=True)
    rendered_content = models.TextField()
    rendered_html = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'template_previews'
        unique_together = ['template', 'preview_name']
    
    def __str__(self):
        return f"Preview: {self.template.name} - {self.preview_name}"


class TemplateTag(models.Model):
    """
    Tags for organizing templates
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='template_tags')
    
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, default='#007bff', help_text="Hex color code")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'template_tags'
        unique_together = ['merchant', 'name']
    
    def __str__(self):
        return self.name


class TemplateTagAssignment(models.Model):
    """
    Many-to-many relationship between templates and tags
    """
    template = models.ForeignKey(Template, on_delete=models.CASCADE, related_name='tag_assignments')
    tag = models.ForeignKey(TemplateTag, on_delete=models.CASCADE, related_name='template_assignments')
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'template_tag_assignments'
        unique_together = ['template', 'tag']
