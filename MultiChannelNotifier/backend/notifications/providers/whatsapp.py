import os
import json
from .base import BaseProvider
import re
import logging

logger = logging.getLogger(__name__)


class WhatsAppProvider(BaseProvider):
    """
    WhatsApp provider using WhatsApp Business API
    """
    
    def __init__(self, provider_config):
        super().__init__(provider_config)
        self.access_token = os.environ.get('WHATSAPP_ACCESS_TOKEN')
        self.phone_number_id = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
        
        if not all([self.access_token, self.phone_number_id]):
            raise ValueError(
                "WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID "
                "environment variables are required"
            )
        
        self.api_url = f"https://graph.facebook.com/v18.0/{self.phone_number_id}/messages"
    
    def validate_recipient(self, recipient: str) -> bool:
        """
        Validate WhatsApp phone number format
        """
        # Remove common formatting characters
        phone = re.sub(r'[^\d+]', '', recipient)
        
        # Should be 10-15 digits, with optional + prefix
        phone_pattern = r'^\+?\d{10,15}$'
        return bool(re.match(phone_pattern, phone))
    
    def normalize_phone_number(self, phone: str) -> str:
        """
        Normalize phone number for WhatsApp (remove + and formatting)
        """
        # Remove all non-digit characters
        phone = re.sub(r'[^\d]', '', phone)
        
        # Remove leading 0 if present (common in some countries)
        if phone.startswith('0'):
            phone = phone[1:]
        
        return phone
    
    def send(self, notification):
        """
        Send WhatsApp message via WhatsApp Business API
        """
        try:
            import requests
            
            # Normalize phone number
            to_number = self.normalize_phone_number(notification.recipient)
            
            if not self.validate_recipient(notification.recipient):
                return self.handle_provider_response(
                    {}, success=False, error=f"Invalid WhatsApp number: {notification.recipient}"
                )
            
            # Prepare headers
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            # Prepare message payload
            payload = {
                'messaging_product': 'whatsapp',
                'to': to_number,
                'type': 'text',
                'text': {
                    'body': notification.message
                }
            }
            
            # Handle different message types based on metadata
            if notification.metadata.get('template'):
                # Template message
                template_data = notification.metadata['template']
                payload.update({
                    'type': 'template',
                    'template': {
                        'name': template_data['name'],
                        'language': template_data.get('language', {'code': 'en'}),
                        'components': template_data.get('components', [])
                    }
                })
                payload.pop('text', None)
            
            elif notification.metadata.get('media'):
                # Media message
                media_data = notification.metadata['media']
                media_type = media_data['type']  # image, video, audio, document
                
                payload.update({
                    'type': media_type,
                    media_type: {
                        'link': media_data['url'],
                        'caption': notification.message if media_type in ['image', 'video'] else None
                    }
                })
                payload.pop('text', None)
            
            # Send request
            response = requests.post(
                self.api_url,
                headers=headers,
                data=json.dumps(payload)
            )
            
            response.raise_for_status()
            response_data = response.json()
            
            # Extract message ID from response
            message_id = None
            if 'messages' in response_data and response_data['messages']:
                message_id = response_data['messages'][0].get('id')
            
            result = self.handle_provider_response({
                'message_id': message_id,
                'wa_id': response_data.get('contacts', [{}])[0].get('wa_id'),
                'response': response_data
            }, success=True)
            
            self.log_send_attempt(notification, result)
            return result
            
        except Exception as e:
            error_msg = f"WhatsApp API error: {str(e)}"
            result = self.handle_provider_response({}, success=False, error=error_msg)
            self.log_send_attempt(notification, result)
            return result


class TwilioWhatsAppProvider(BaseProvider):
    """
    Alternative WhatsApp provider using Twilio's WhatsApp API
    """
    
    def __init__(self, provider_config):
        super().__init__(provider_config)
        self.account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        self.auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
        self.from_number = os.environ.get('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')
        
        if not all([self.account_sid, self.auth_token]):
            raise ValueError(
                "TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN environment variables are required"
            )
        
        from twilio.rest import Client
        self.client = Client(self.account_sid, self.auth_token)
    
    def validate_recipient(self, recipient: str) -> bool:
        """
        Validate phone number format
        """
        phone = re.sub(r'[^\d+]', '', recipient)
        phone_pattern = r'^\+\d{10,15}$'
        return bool(re.match(phone_pattern, phone))
    
    def send(self, notification):
        """
        Send WhatsApp message via Twilio
        """
        try:
            # Format phone number for WhatsApp
            to_number = notification.recipient
            if not to_number.startswith('whatsapp:'):
                if not to_number.startswith('+'):
                    to_number = '+' + re.sub(r'[^\d]', '', to_number)
                to_number = f'whatsapp:{to_number}'
            
            if not self.validate_recipient(notification.recipient):
                return self.handle_provider_response(
                    {}, success=False, error=f"Invalid WhatsApp number: {notification.recipient}"
                )
            
            # Send message
            message = self.client.messages.create(
                body=notification.message,
                from_=self.from_number,
                to=to_number
            )
            
            result = self.handle_provider_response({
                'message_id': message.sid,
                'status': message.status,
                'from': message.from_,
                'to': message.to
            }, success=True)
            
            self.log_send_attempt(notification, result)
            return result
            
        except Exception as e:
            error_msg = f"Twilio WhatsApp error: {str(e)}"
            result = self.handle_provider_response({}, success=False, error=error_msg)
            self.log_send_attempt(notification, result)
            return result
