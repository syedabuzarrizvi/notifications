from rest_framework import permissions
from django.contrib.auth import get_user_model

User = get_user_model()


class IsMerchant(permissions.BasePermission):
    """
    Permission class to check if user is a merchant
    """
    
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            isinstance(request.user, User)
        )


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Permission class to allow only owners to modify objects
    """
    
    def has_object_permission(self, request, view, obj):
        # Read permissions for any request
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions only for owner
        return obj.merchant == request.user


class HasValidAPIKey(permissions.BasePermission):
    """
    Permission class for API key authentication
    """
    
    def has_permission(self, request, view):
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return False
        
        try:
            merchant = User.objects.get(api_key=api_key, is_active=True)
            request.user = merchant
            return True
        except User.DoesNotExist:
            return False


class IsActiveUser(permissions.BasePermission):
    """
    Permission class to check if user is active
    """
    
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.is_active
        )


class HasNotificationPermission(permissions.BasePermission):
    """
    Permission class for notification operations
    """
    
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        
        # Check if user has reached notification limits
        if hasattr(request.user, 'settings'):
            settings = request.user.settings
            
            # Check daily limits (simplified check)
            if request.method == 'POST':
                channel = request.data.get('channel')
                if channel:
                    daily_limits = {
                        'email': settings.daily_email_limit,
                        'sms': settings.daily_sms_limit,
                        'push': settings.daily_push_limit,
                        'whatsapp': settings.daily_whatsapp_limit
                    }
                    
                    sent_today = {
                        'email': settings.email_sent_today,
                        'sms': settings.sms_sent_today,
                        'push': settings.push_sent_today,
                        'whatsapp': settings.whatsapp_sent_today
                    }
                    
                    limit = daily_limits.get(channel, 0)
                    sent = sent_today.get(channel, 0)
                    
                    if sent >= limit:
                        return False
        
        return True


class HasCampaignPermission(permissions.BasePermission):
    """
    Permission class for campaign operations
    """
    
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.is_active
        )
    
    def has_object_permission(self, request, view, obj):
        # User can only access their own campaigns
        return obj.merchant == request.user


class HasTemplatePermission(permissions.BasePermission):
    """
    Permission class for template operations
    """
    
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.is_active
        )
    
    def has_object_permission(self, request, view, obj):
        # User can only access their own templates
        if hasattr(obj, 'merchant'):
            return obj.merchant == request.user
        
        # For system templates, allow read-only access
        if hasattr(obj, 'is_system') and obj.is_system:
            return request.method in permissions.SAFE_METHODS
        
        return False


class HasRecipientPermission(permissions.BasePermission):
    """
    Permission class for recipient operations
    """
    
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.is_active
        )
    
    def has_object_permission(self, request, view, obj):
        # User can only access their own recipients
        return obj.merchant == request.user


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Permission class for admin-only write operations
    """
    
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        return (
            request.user and
            request.user.is_authenticated and
            request.user.is_staff
        )


class HasBulkOperationPermission(permissions.BasePermission):
    """
    Permission class for bulk operations with rate limiting
    """
    
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        
        # Check for bulk operation rate limits
        from django.core.cache import cache
        
        cache_key = f"bulk_operations:{request.user.id}"
        current_operations = cache.get(cache_key, 0)
        
        # Allow max 5 bulk operations per hour
        if current_operations >= 5:
            return False
        
        # Increment counter
        cache.set(cache_key, current_operations + 1, 3600)  # 1 hour
        
        return True


class HasWebSocketPermission(permissions.BasePermission):
    """
    Permission class for WebSocket connections
    """
    
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.is_active
        )


class RateLimitedPermission(permissions.BasePermission):
    """
    Permission class with built-in rate limiting
    """
    
    def __init__(self, rate_limit_key=None, max_requests=100, window=3600):
        self.rate_limit_key = rate_limit_key
        self.max_requests = max_requests
        self.window = window
    
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        
        from django.core.cache import cache
        
        # Create rate limit key
        key = self.rate_limit_key or f"rate_limit:{request.user.id}:{view.__class__.__name__}"
        
        current_requests = cache.get(key, 0)
        
        if current_requests >= self.max_requests:
            return False
        
        # Increment counter
        try:
            cache.add(key, 0, self.window)
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, self.window)
        
        return True


def get_permission_classes_for_view(view_name):
    """
    Helper function to get appropriate permission classes for a view
    """
    permission_map = {
        'notification': [IsMerchant, IsActiveUser, HasNotificationPermission],
        'campaign': [IsMerchant, IsActiveUser, HasCampaignPermission],
        'template': [IsMerchant, IsActiveUser, HasTemplatePermission],
        'recipient': [IsMerchant, IsActiveUser, HasRecipientPermission],
        'bulk': [IsMerchant, IsActiveUser, HasBulkOperationPermission],
        'admin': [permissions.IsAdminUser],
        'public': [permissions.AllowAny],
    }
    
    return permission_map.get(view_name, [IsMerchant, IsActiveUser])
