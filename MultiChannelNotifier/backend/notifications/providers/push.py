import os
import json
from .base import BaseProvider
import logging

logger = logging.getLogger(__name__)


class PushProvider(BaseProvider):
    """
    Push notification provider using Firebase Cloud Messaging (FCM)
    """
    
    def __init__(self, provider_config):
        super().__init__(provider_config)
        self.server_key = os.environ.get('FIREBASE_SERVER_KEY')
        
        if not self.server_key:
            raise ValueError("FIREBASE_SERVER_KEY environment variable is required")
        
        self.fcm_url = "https://fcm.googleapis.com/fcm/send"
    
    def validate_recipient(self, recipient: str) -> bool:
        """
        Validate FCM token format (basic validation)
        """
        # FCM tokens are typically long alphanumeric strings
        return len(recipient) > 50 and recipient.replace(':', '').replace('-', '').replace('_', '').isalnum()
    
    def send(self, notification):
        """
        Send push notification via Firebase Cloud Messaging
        """
        try:
            import requests
            
            if not self.validate_recipient(notification.recipient):
                return self.handle_provider_response(
                    {}, success=False, error=f"Invalid FCM token: {notification.recipient}"
                )
            
            # Prepare headers
            headers = {
                'Authorization': f'key={self.server_key}',
                'Content-Type': 'application/json'
            }
            
            # Prepare payload
            payload = {
                'to': notification.recipient,
                'notification': {
                    'title': notification.subject or 'Notification',
                    'body': notification.message
                }
            }
            
            # Add data payload if specified in metadata
            if notification.metadata.get('data'):
                payload['data'] = notification.metadata['data']
            
            # Add additional FCM options from metadata
            if notification.metadata.get('android'):
                payload['android'] = notification.metadata['android']
            
            if notification.metadata.get('apns'):
                payload['apns'] = notification.metadata['apns']
            
            if notification.metadata.get('webpush'):
                payload['webpush'] = notification.metadata['webpush']
            
            # Set priority
            if notification.priority == 'high' or notification.priority == 'urgent':
                payload['priority'] = 'high'
            else:
                payload['priority'] = 'normal'
            
            # Send request
            response = requests.post(
                self.fcm_url,
                headers=headers,
                data=json.dumps(payload)
            )
            
            response.raise_for_status()
            response_data = response.json()
            
            # Check if message was successful
            if response_data.get('success', 0) > 0:
                result = self.handle_provider_response({
                    'message_id': response_data.get('results', [{}])[0].get('message_id'),
                    'success_count': response_data.get('success', 0),
                    'failure_count': response_data.get('failure', 0),
                    'multicast_id': response_data.get('multicast_id'),
                    'results': response_data.get('results', [])
                }, success=True)
            else:
                error_msg = response_data.get('results', [{}])[0].get('error', 'Unknown FCM error')
                result = self.handle_provider_response(response_data, success=False, error=error_msg)
            
            self.log_send_attempt(notification, result)
            return result
            
        except Exception as e:
            error_msg = f"FCM Push error: {str(e)}"
            result = self.handle_provider_response({}, success=False, error=error_msg)
            self.log_send_attempt(notification, result)
            return result


class APNSProvider(BaseProvider):
    """
    Alternative push provider using Apple Push Notification Service (APNS)
    """
    
    def __init__(self, provider_config):
        super().__init__(provider_config)
        self.key_id = os.environ.get('APNS_KEY_ID')
        self.team_id = os.environ.get('APNS_TEAM_ID')
        self.bundle_id = os.environ.get('APNS_BUNDLE_ID')
        self.key_file = os.environ.get('APNS_KEY_FILE')  # Path to .p8 key file
        
        if not all([self.key_id, self.team_id, self.bundle_id, self.key_file]):
            raise ValueError(
                "APNS_KEY_ID, APNS_TEAM_ID, APNS_BUNDLE_ID, and APNS_KEY_FILE "
                "environment variables are required"
            )
    
    def validate_recipient(self, recipient: str) -> bool:
        """
        Validate APNS device token format
        """
        # APNS tokens are 64-character hex strings
        return len(recipient) == 64 and all(c in '0123456789abcdefABCDEF' for c in recipient)
    
    def send(self, notification):
        """
        Send push notification via APNS
        """
        try:
            from apns2.client import APNsClient
            from apns2.payload import Payload
            
            if not self.validate_recipient(notification.recipient):
                return self.handle_provider_response(
                    {}, success=False, error=f"Invalid APNS token: {notification.recipient}"
                )
            
            # Create APNS client
            client = APNsClient(self.key_file, key_id=self.key_id, team_id=self.team_id)
            
            # Create payload
            payload = Payload(
                alert={
                    'title': notification.subject or 'Notification',
                    'body': notification.message
                },
                sound='default',
                custom=notification.metadata.get('custom', {})
            )
            
            # Send notification
            client.send_notification(notification.recipient, payload, self.bundle_id)
            
            result = self.handle_provider_response({
                'device_token': notification.recipient,
                'bundle_id': self.bundle_id
            }, success=True)
            
            self.log_send_attempt(notification, result)
            return result
            
        except Exception as e:
            error_msg = f"APNS error: {str(e)}"
            result = self.handle_provider_response({}, success=False, error=error_msg)
            self.log_send_attempt(notification, result)
            return result
