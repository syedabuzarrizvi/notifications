from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid


class Merchant(AbstractUser):
    """
    Extended user model for merchants
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company_name = models.CharField(max_length=255)
    api_key = models.CharField(max_length=255, unique=True, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Rate limiting fields
    requests_count = models.PositiveIntegerField(default=0)
    requests_reset_time = models.DateTimeField(null=True, blank=True)
    
    # Fix reverse accessor conflicts
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to.',
        related_name='merchant_set',
        related_query_name='merchant',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name='merchant_set',
        related_query_name='merchant',
    )
    
    class Meta:
        db_table = 'merchants'
        
    def __str__(self):
        return f"{self.username} - {self.company_name}"
    
    def save(self, *args, **kwargs):
        if not self.api_key:
            self.api_key = str(uuid.uuid4())
        super().save(*args, **kwargs)


class MerchantSettings(models.Model):
    """
    Merchant-specific settings and preferences
    """
    merchant = models.OneToOneField(Merchant, on_delete=models.CASCADE, related_name='settings')
    
    # Provider preferences
    preferred_sms_provider = models.CharField(max_length=50, default='twilio')
    preferred_email_provider = models.CharField(max_length=50, default='sendgrid')
    preferred_push_provider = models.CharField(max_length=50, default='firebase')
    preferred_whatsapp_provider = models.CharField(max_length=50, default='whatsapp_business')
    
    # Notification limits
    daily_sms_limit = models.PositiveIntegerField(default=1000)
    daily_email_limit = models.PositiveIntegerField(default=10000)
    daily_push_limit = models.PositiveIntegerField(default=50000)
    daily_whatsapp_limit = models.PositiveIntegerField(default=1000)
    
    # Usage tracking
    sms_sent_today = models.PositiveIntegerField(default=0)
    email_sent_today = models.PositiveIntegerField(default=0)
    push_sent_today = models.PositiveIntegerField(default=0)
    whatsapp_sent_today = models.PositiveIntegerField(default=0)
    
    # Reset tracking
    usage_reset_date = models.DateField(auto_now_add=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'merchant_settings'
