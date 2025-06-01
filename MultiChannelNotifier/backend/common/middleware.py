from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from django.core.cache import cache
from django.utils import timezone
from django.conf import settings
import time
import logging

logger = logging.getLogger(__name__)


class RateLimitMiddleware(MiddlewareMixin):
    """
    Rate limiting middleware for API requests
    """
    
    def process_request(self, request):
        if not getattr(settings, 'RATE_LIMIT_ENABLE', True):
            return None
        
        # Skip rate limiting for certain paths
        skip_paths = ['/admin/', '/static/', '/media/']
        if any(request.path.startswith(path) for path in skip_paths):
            return None
        
        # Get client identifier
        client_id = self.get_client_id(request)
        
        # Check rate limit
        if self.is_rate_limited(client_id, request):
            return JsonResponse({
                'error': 'Rate limit exceeded',
                'message': 'Too many requests. Please try again later.',
                'retry_after': getattr(settings, 'RATE_LIMIT_WINDOW', 3600)
            }, status=429)
        
        return None
    
    def get_client_id(self, request):
        """Get client identifier for rate limiting"""
        # Use API key if available
        api_key = request.headers.get('Authorization', '').replace('Bearer ', '')
        if api_key:
            return f"api_key:{api_key}"
        
        # Use user ID if authenticated
        if hasattr(request, 'user') and request.user.is_authenticated:
            return f"user:{request.user.id}"
        
        # Fall back to IP address
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        
        return f"ip:{ip}"
    
    def is_rate_limited(self, client_id, request):
        """Check if client is rate limited"""
        window = getattr(settings, 'RATE_LIMIT_WINDOW', 3600)  # 1 hour
        max_requests = getattr(settings, 'RATE_LIMIT_MAX_REQUESTS', 1000)
        
        cache_key = f"rate_limit:{client_id}"
        
        # Get current request count
        current_requests = cache.get(cache_key, 0)
        
        if current_requests >= max_requests:
            logger.warning(f"Rate limit exceeded for {client_id}")
            return True
        
        # Increment counter
        try:
            cache.add(cache_key, 0, window)
            cache.incr(cache_key)
        except ValueError:
            # Key doesn't exist, create it
            cache.set(cache_key, 1, window)
        
        return False


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log API requests for monitoring
    """
    
    def process_request(self, request):
        request.start_time = time.time()
        return None
    
    def process_response(self, request, response):
        # Skip logging for static files and admin
        skip_paths = ['/static/', '/media/', '/admin/']
        if any(request.path.startswith(path) for path in skip_paths):
            return response
        
        # Calculate request duration
        duration = 0
        if hasattr(request, 'start_time'):
            duration = time.time() - request.start_time
        
        # Log request details
        log_data = {
            'method': request.method,
            'path': request.path,
            'status_code': response.status_code,
            'duration': round(duration, 3),
            'user_id': getattr(request.user, 'id', None) if hasattr(request, 'user') else None,
            'ip_address': self.get_client_ip(request),
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            'timestamp': timezone.now().isoformat()
        }
        
        # Log based on status code
        if response.status_code >= 500:
            logger.error(f"Server Error: {log_data}")
        elif response.status_code >= 400:
            logger.warning(f"Client Error: {log_data}")
        else:
            logger.info(f"Request: {log_data}")
        
        return response
    
    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Add security headers to responses
    """
    
    def process_response(self, request, response):
        # CORS headers (if not handled by django-cors-headers)
        if not response.get('Access-Control-Allow-Origin'):
            response['Access-Control-Allow-Origin'] = '*'
        
        # Security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Content Security Policy
        if not response.get('Content-Security-Policy'):
            csp = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self' https:; "
                "connect-src 'self' https:; "
                "frame-ancestors 'none';"
            )
            response['Content-Security-Policy'] = csp
        
        return response


class APIKeyAuthenticationMiddleware(MiddlewareMixin):
    """
    Middleware to authenticate requests using API keys
    """
    
    def process_request(self, request):
        # Skip for certain paths
        skip_paths = ['/admin/', '/api/auth/']
        if any(request.path.startswith(path) for path in skip_paths):
            return None
        
        # Check for API key in headers
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return None
        
        try:
            from accounts.models import Merchant
            merchant = Merchant.objects.get(api_key=api_key, is_active=True)
            
            # Set user for the request
            request.user = merchant
            request._dont_enforce_csrf_checks = True
            
            logger.info(f"API key authentication successful for merchant: {merchant.username}")
            
        except Merchant.DoesNotExist:
            logger.warning(f"Invalid API key used: {api_key}")
            return JsonResponse({
                'error': 'Invalid API key',
                'message': 'The provided API key is not valid or has been deactivated.'
            }, status=401)
        
        return None


class ResponseTimeMiddleware(MiddlewareMixin):
    """
    Add response time header to responses
    """
    
    def process_request(self, request):
        request.start_time = time.time()
        return None
    
    def process_response(self, request, response):
        if hasattr(request, 'start_time'):
            duration = time.time() - request.start_time
            response['X-Response-Time'] = f"{duration:.3f}s"
        
        return response


class HealthCheckMiddleware(MiddlewareMixin):
    """
    Handle health check requests
    """
    
    def process_request(self, request):
        if request.path in ['/health/', '/health', '/healthz']:
            from django.http import JsonResponse
            from django.db import connection
            
            # Check database connection
            try:
                cursor = connection.cursor()
                cursor.execute("SELECT 1")
                db_status = "healthy"
            except Exception as e:
                db_status = f"unhealthy: {str(e)}"
            
            # Check cache
            try:
                from django.core.cache import cache
                cache.set('health_check', 'ok', 10)
                cache_result = cache.get('health_check')
                cache_status = "healthy" if cache_result == 'ok' else "unhealthy"
            except Exception as e:
                cache_status = f"unhealthy: {str(e)}"
            
            status_code = 200 if db_status == "healthy" and cache_status == "healthy" else 503
            
            return JsonResponse({
                'status': 'healthy' if status_code == 200 else 'unhealthy',
                'timestamp': timezone.now().isoformat(),
                'checks': {
                    'database': db_status,
                    'cache': cache_status
                }
            }, status=status_code)
        
        return None
