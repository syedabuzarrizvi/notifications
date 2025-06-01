from abc import ABC, abstractmethod
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class BaseProvider(ABC):
    """
    Abstract base class for notification providers
    """
    
    def __init__(self, provider_config):
        self.provider_config = provider_config
        self.name = provider_config.name
        self.channel = provider_config.channel
        self.config = provider_config.config
    
    @abstractmethod
    def send(self, notification) -> Dict[str, Any]:
        """
        Send a notification
        
        Returns:
            Dict with keys:
            - success: bool
            - message_id: str (if successful)
            - response: dict (provider response)
            - error: str (if failed)
            - provider_name: str
        """
        pass
    
    @abstractmethod
    def validate_recipient(self, recipient: str) -> bool:
        """
        Validate recipient format
        """
        pass
    
    def log_send_attempt(self, notification, result):
        """
        Log send attempt for monitoring
        """
        status = "SUCCESS" if result['success'] else "FAILED"
        logger.info(
            f"[{self.name}] {status} - Notification {notification.id} "
            f"to {notification.recipient[:10]}... "
            f"Channel: {self.channel}"
        )
        
        if not result['success']:
            logger.error(f"Error: {result.get('error', 'Unknown error')}")
    
    def prepare_message(self, notification):
        """
        Prepare message content based on notification
        """
        return {
            'recipient': notification.recipient,
            'subject': notification.subject,
            'message': notification.message,
            'metadata': notification.metadata
        }
    
    def handle_provider_response(self, response, success=True, error=None):
        """
        Standardize provider response format
        """
        return {
            'success': success,
            'provider_name': self.name,
            'response': response if isinstance(response, dict) else {},
            'message_id': response.get('message_id') if isinstance(response, dict) else None,
            'error': error
        }
