from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from django.core.cache import cache
from django.conf import settings
import time


class NotificationRateThrottle(UserRateThrottle):
    """
    Custom throttling for notification endpoints
    """
    scope = 'notification'
    
    def get_cache_key(self, request, view):
        if request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }
    
    def throttle_success(self):
        """
        Inserts the current request's timestamp along with the key
        into the cache.
        """
        self.history.insert(0, self.now)
        self.cache.set(self.key, self.history, self.duration)
        return True


class BulkOperationThrottle(UserRateThrottle):
    """
    Throttling for bulk operations like campaign launches and imports
    """
    scope = 'bulk_operation'
    rate = '10/hour'
    
    def get_cache_key(self, request, view):
        if request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        
        return f"bulk_throttle_{self.scope}_{ident}"


class ProviderRateThrottle:
    """
    Provider-specific rate limiting
    """
    
    def __init__(self, provider_name, rate_per_minute=100):
        self.provider_name = provider_name
        self.rate_per_minute = rate_per_minute
        self.window = 60  # 1 minute
    
    def is_allowed(self):
        """Check if provider is within rate limits"""
        cache_key = f"provider_rate_{self.provider_name}"
        current_count = cache.get(cache_key, 0)
        
        if current_count >= self.rate_per_minute:
            return False
        
        # Increment counter
        try:
            cache.add(cache_key, 0, self.window)
            cache.incr(cache_key)
        except ValueError:
            cache.set(cache_key, 1, self.window)
        
        return True
    
    def get_retry_after(self):
        """Get seconds until rate limit resets"""
        cache_key = f"provider_rate_{self.provider_name}"
        ttl = cache.ttl(cache_key)
        return max(ttl, 0) if ttl is not None else 0


class APIKeyRateThrottle:
    """
    Rate limiting based on API key
    """
    
    def __init__(self, api_key, rate_per_hour=1000):
        self.api_key = api_key
        self.rate_per_hour = rate_per_hour
        self.window = 3600  # 1 hour
    
    def is_allowed(self):
        """Check if API key is within rate limits"""
        cache_key = f"api_key_rate_{self.api_key}"
        current_count = cache.get(cache_key, 0)
        
        if current_count >= self.rate_per_hour:
            return False
        
        # Increment counter
        try:
            cache.add(cache_key, 0, self.window)
            cache.incr(cache_key)
        except ValueError:
            cache.set(cache_key, 1, self.window)
        
        return True


class ChannelSpecificThrottle(UserRateThrottle):
    """
    Channel-specific rate limiting (email, SMS, etc.)
    """
    
    def __init__(self, channel):
        super().__init__()
        self.channel = channel
        self.scope = f'{channel}_notification'
    
    def get_cache_key(self, request, view):
        if request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        
        return f"channel_throttle_{self.channel}_{ident}"
    
    def get_rate(self):
        """Get rate limit based on channel and user settings"""
        if hasattr(self.request, 'user') and self.request.user.is_authenticated:
            user = self.request.user
            if hasattr(user, 'settings'):
                settings = user.settings
                
                # Get daily limits and convert to hourly
                daily_limits = {
                    'email': getattr(settings, 'daily_email_limit', 10000),
                    'sms': getattr(settings, 'daily_sms_limit', 1000),
                    'push': getattr(settings, 'daily_push_limit', 50000),
                    'whatsapp': getattr(settings, 'daily_whatsapp_limit', 1000)
                }
                
                daily_limit = daily_limits.get(self.channel, 1000)
                hourly_limit = daily_limit // 24
                
                return f"{hourly_limit}/hour"
        
        # Default rates
        default_rates = {
            'email': '417/hour',  # 10000/24
            'sms': '42/hour',     # 1000/24
            'push': '2083/hour',  # 50000/24
            'whatsapp': '42/hour' # 1000/24
        }
        
        return default_rates.get(self.channel, '100/hour')


class MerchantRateThrottle(UserRateThrottle):
    """
    Merchant-specific rate limiting with custom limits
    """
    scope = 'merchant'
    
    def get_rate(self):
        """Get rate limit based on merchant tier/settings"""
        if hasattr(self.request, 'user') and self.request.user.is_authenticated:
            user = self.request.user
            
            # Check if user has custom rate limits
            if hasattr(user, 'settings'):
                # Could be based on subscription tier, usage history, etc.
                return '1000/hour'  # Default for authenticated merchants
        
        return '100/hour'  # Default for others


class DynamicRateThrottle:
    """
    Dynamic rate limiting that adjusts based on system load
    """
    
    def __init__(self, base_rate=100, load_factor_key='system_load'):
        self.base_rate = base_rate
        self.load_factor_key = load_factor_key
    
    def get_current_rate(self):
        """Calculate current rate based on system load"""
        load_factor = cache.get(self.load_factor_key, 1.0)
        
        # Reduce rate if system is under heavy load
        if load_factor > 0.8:
            adjusted_rate = int(self.base_rate * 0.5)
        elif load_factor > 0.6:
            adjusted_rate = int(self.base_rate * 0.7)
        else:
            adjusted_rate = self.base_rate
        
        return adjusted_rate
    
    def is_allowed(self, identifier):
        """Check if request is allowed under current rate"""
        current_rate = self.get_current_rate()
        cache_key = f"dynamic_rate_{identifier}"
        
        current_count = cache.get(cache_key, 0)
        
        if current_count >= current_rate:
            return False
        
        # Increment counter
        try:
            cache.add(cache_key, 0, 60)  # 1 minute window
            cache.incr(cache_key)
        except ValueError:
            cache.set(cache_key, 1, 60)
        
        return True


def get_throttle_classes_for_view(view_name):
    """
    Helper function to get appropriate throttle classes for a view
    """
    throttle_map = {
        'notification_send': [NotificationRateThrottle],
        'bulk_operation': [BulkOperationThrottle],
        'campaign': [MerchantRateThrottle],
        'template': [MerchantRateThrottle],
        'recipient': [MerchantRateThrottle],
        'default': [UserRateThrottle, AnonRateThrottle]
    }
    
    return throttle_map.get(view_name, throttle_map['default'])


def check_provider_rate_limit(provider_name, rate_per_minute=100):
    """
    Utility function to check provider rate limits
    """
    throttle = ProviderRateThrottle(provider_name, rate_per_minute)
    return throttle.is_allowed()


def increment_merchant_usage(merchant, operation_type='api_call'):
    """
    Track merchant API usage for analytics and billing
    """
    cache_key = f"merchant_usage_{merchant.id}_{operation_type}"
    
    try:
        cache.add(cache_key, 0, 86400)  # 24 hour window
        cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, 86400)


def get_rate_limit_status(user):
    """
    Get current rate limit status for a user
    """
    if not user.is_authenticated:
        return {'limit': 100, 'remaining': 100, 'reset': time.time() + 3600}
    
    # Get user's current usage
    cache_key = f"throttle_user_{user.pk}"
    current_usage = cache.get(cache_key, [])
    
    # Calculate remaining requests
    now = time.time()
    window = 3600  # 1 hour
    recent_requests = [req_time for req_time in current_usage if now - req_time < window]
    
    # Get user's rate limit
    limit = 1000  # Default
    if hasattr(user, 'settings'):
        # Could be customized based on user tier
        limit = 1000
    
    remaining = max(0, limit - len(recent_requests))
    reset = now + window
    
    return {
        'limit': limit,
        'remaining': remaining,
        'reset': reset,
        'usage': len(recent_requests)
    }
