from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
import hashlib
import json


def generate_idempotency_key(merchant_id, data):
    """
    Generate idempotency key based on merchant and request data
    """
    # Create a hash of the important fields
    key_data = {
        'merchant_id': str(merchant_id),
        'channel': data.get('channel'),
        'recipient': data.get('recipient'),
        'message': data.get('message'),
        'subject': data.get('subject'),
    }
    
    key_string = json.dumps(key_data, sort_keys=True)
    return hashlib.md5(key_string.encode()).hexdigest()


def rate_limit_check(merchant, channel, limit_key='hourly'):
    """
    Check if merchant is within rate limits for a specific channel
    """
    cache_key = f"rate_limit:{merchant.id}:{channel}:{limit_key}"
    current_count = cache.get(cache_key, 0)
    
    # Get limits from merchant settings
    if limit_key == 'hourly':
        if channel == 'sms':
            limit = getattr(merchant.settings, 'daily_sms_limit', 1000) // 24
        elif channel == 'email':
            limit = getattr(merchant.settings, 'daily_email_limit', 10000) // 24
        elif channel == 'push':
            limit = getattr(merchant.settings, 'daily_push_limit', 50000) // 24
        elif channel == 'whatsapp':
            limit = getattr(merchant.settings, 'daily_whatsapp_limit', 1000) // 24
        else:
            limit = 100  # Default
    else:
        limit = 1000  # Default for other periods
    
    if current_count >= limit:
        return False, current_count, limit
    
    return True, current_count, limit


def increment_rate_limit(merchant, channel, limit_key='hourly'):
    """
    Increment rate limit counter
    """
    cache_key = f"rate_limit:{merchant.id}:{channel}:{limit_key}"
    
    # Set expiration based on limit key
    if limit_key == 'hourly':
        expire_seconds = 3600
    elif limit_key == 'daily':
        expire_seconds = 86400
    else:
        expire_seconds = 3600
    
    try:
        cache.add(cache_key, 0, expire_seconds)
        cache.incr(cache_key)
    except ValueError:
        # Key doesn't exist, create it
        cache.set(cache_key, 1, expire_seconds)


def check_provider_rate_limit(provider_name, limit_per_minute=100):
    """
    Check provider-specific rate limits
    """
    cache_key = f"provider_rate_limit:{provider_name}:minute"
    current_count = cache.get(cache_key, 0)
    
    if current_count >= limit_per_minute:
        return False, current_count, limit_per_minute
    
    return True, current_count, limit_per_minute


def increment_provider_rate_limit(provider_name):
    """
    Increment provider rate limit counter
    """
    cache_key = f"provider_rate_limit:{provider_name}:minute"
    
    try:
        cache.add(cache_key, 0, 60)  # 1 minute expiration
        cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, 60)


def validate_scheduled_time(scheduled_at):
    """
    Validate that scheduled time is in the future and reasonable
    """
    now = timezone.now()
    
    if scheduled_at <= now:
        return False, "Scheduled time must be in the future"
    
    # Don't allow scheduling more than 1 year in advance
    max_future = now + timedelta(days=365)
    if scheduled_at > max_future:
        return False, "Cannot schedule more than 1 year in advance"
    
    return True, None


def sanitize_phone_number(phone):
    """
    Sanitize and format phone number
    """
    import re
    
    # Remove all non-digit characters except +
    cleaned = re.sub(r'[^\d+]', '', phone)
    
    # Add + if not present
    if not cleaned.startswith('+'):
        # If it's 10 digits, assume US number
        if len(cleaned) == 10:
            cleaned = '+1' + cleaned
        else:
            cleaned = '+' + cleaned
    
    return cleaned


def validate_email(email):
    """
    Validate email address format
    """
    import re
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def get_notification_template(template_name, variables=None):
    """
    Get notification template with variable substitution
    """
    # This would typically load from database or file system
    templates = {
        'welcome': {
            'subject': 'Welcome to {company_name}!',
            'message': 'Hello {name}, welcome to {company_name}. We\'re excited to have you!'
        },
        'password_reset': {
            'subject': 'Password Reset Request',
            'message': 'Hello {name}, click here to reset your password: {reset_url}'
        },
        'order_confirmation': {
            'subject': 'Order Confirmation #{order_id}',
            'message': 'Your order #{order_id} has been confirmed. Total: {total_amount}'
        }
    }
    
    template = templates.get(template_name)
    if not template:
        return None
    
    # Substitute variables
    if variables:
        subject = template['subject'].format(**variables)
        message = template['message'].format(**variables)
        return {'subject': subject, 'message': message}
    
    return template


def batch_notifications(notifications, batch_size=100):
    """
    Split notifications into batches for processing
    """
    for i in range(0, len(notifications), batch_size):
        yield notifications[i:i + batch_size]


def calculate_delivery_window(priority, channel):
    """
    Calculate expected delivery window based on priority and channel
    """
    # Base delivery windows in minutes
    base_windows = {
        'email': 2,
        'sms': 1,
        'push': 0.5,
        'whatsapp': 2
    }
    
    priority_multipliers = {
        'urgent': 0.5,
        'high': 0.75,
        'normal': 1.0,
        'low': 2.0
    }
    
    base_window = base_windows.get(channel, 2)
    multiplier = priority_multipliers.get(priority, 1.0)
    
    return base_window * multiplier


def generate_tracking_pixel(notification_id):
    """
    Generate tracking pixel URL for email open tracking
    """
    from django.conf import settings
    base_url = getattr(settings, 'BASE_URL', 'https://api.techrar.com')
    return f"{base_url}/api/notifications/{notification_id}/track/open"


def log_notification_metrics(notification, event_type, additional_data=None):
    """
    Log notification metrics for analytics
    """
    from .models import NotificationEvent
    
    event_data = {
        'channel': notification.channel,
        'provider': notification.provider,
        'merchant_id': str(notification.merchant.id),
        'timestamp': timezone.now().isoformat()
    }
    
    if additional_data:
        event_data.update(additional_data)
    
    NotificationEvent.objects.create(
        notification=notification,
        event_type=event_type,
        event_data=event_data
    )
