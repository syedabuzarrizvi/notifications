import os
from twilio.rest import Client
from .base import BaseProvider
import re
import logging

logger = logging.getLogger(__name__)


class SMSProvider(BaseProvider):
    """
    SMS provider using Twilio
    """
    
    def __init__(self, provider_config):
        super().__init__(provider_config)
        self.account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        self.auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
        self.from_number = os.environ.get('TWILIO_PHONE_NUMBER')
        
        if not all([self.account_sid, self.auth_token, self.from_number]):
            raise ValueError(
                "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER "
                "environment variables are required"
            )
        
        self.client = Client(self.account_sid, self.auth_token)
    
    def validate_recipient(self, recipient: str) -> bool:
        """
        Validate phone number format (basic validation)
        """
        # Remove common formatting characters
        phone = re.sub(r'[^\d+]', '', recipient)
        
        # Should start with + and have 10-15 digits
        phone_pattern = r'^\+\d{10,15}$'
        return bool(re.match(phone_pattern, phone))
    
    def normalize_phone_number(self, phone: str) -> str:
        """
        Normalize phone number format
        """
        # Remove all non-digit characters except +
        phone = re.sub(r'[^\d+]', '', phone)
        
        # Add + if not present and starts with country code
        if not phone.startswith('+'):
            # Assume US number if 10 digits, otherwise add +
            if len(phone) == 10:
                phone = '+1' + phone
            else:
                phone = '+' + phone
        
        return phone
    
    def send(self, notification):
        """
        Send SMS notification via Twilio
        """
        try:
            # Normalize phone number
            to_number = self.normalize_phone_number(notification.recipient)
            
            if not self.validate_recipient(to_number):
                return self.handle_provider_response(
                    {}, success=False, error=f"Invalid phone number: {notification.recipient}"
                )
            
            # Prepare message
            message_body = notification.message
            
            # Truncate message if too long (SMS limit is typically 160 characters)
            max_length = notification.metadata.get('max_length', 1600)  # Allow for long SMS
            if len(message_body) > max_length:
                message_body = message_body[:max_length-3] + "..."
            
            # Send SMS
            message = self.client.messages.create(
                body=message_body,
                from_=self.from_number,
                to=to_number
            )
            
            result = self.handle_provider_response({
                'message_id': message.sid,
                'status': message.status,
                'direction': message.direction,
                'from': message.from_,
                'to': message.to,
                'price': message.price,
                'price_unit': message.price_unit
            }, success=True)
            
            self.log_send_attempt(notification, result)
            return result
            
        except Exception as e:
            error_msg = f"Twilio SMS error: {str(e)}"
            result = self.handle_provider_response({}, success=False, error=error_msg)
            self.log_send_attempt(notification, result)
            return result


class AWSSSMSProvider(BaseProvider):
    """
    Alternative SMS provider using AWS SNS
    """
    
    def __init__(self, provider_config):
        super().__init__(provider_config)
        self.aws_access_key = os.environ.get('AWS_ACCESS_KEY_ID')
        self.aws_secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
        self.aws_region = os.environ.get('AWS_REGION', 'us-east-1')
        
        if not all([self.aws_access_key, self.aws_secret_key]):
            raise ValueError(
                "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables are required"
            )
    
    def validate_recipient(self, recipient: str) -> bool:
        """
        Validate phone number format
        """
        phone = re.sub(r'[^\d+]', '', recipient)
        phone_pattern = r'^\+\d{10,15}$'
        return bool(re.match(phone_pattern, phone))
    
    def send(self, notification):
        """
        Send SMS notification via AWS SNS
        """
        try:
            import boto3
            
            # Normalize phone number
            to_number = notification.recipient
            if not to_number.startswith('+'):
                to_number = '+' + re.sub(r'[^\d]', '', to_number)
            
            if not self.validate_recipient(to_number):
                return self.handle_provider_response(
                    {}, success=False, error=f"Invalid phone number: {notification.recipient}"
                )
            
            # Create SNS client
            sns = boto3.client(
                'sns',
                aws_access_key_id=self.aws_access_key,
                aws_secret_access_key=self.aws_secret_key,
                region_name=self.aws_region
            )
            
            # Send SMS
            response = sns.publish(
                PhoneNumber=to_number,
                Message=notification.message
            )
            
            result = self.handle_provider_response({
                'message_id': response['MessageId'],
                'response_metadata': response.get('ResponseMetadata', {})
            }, success=True)
            
            self.log_send_attempt(notification, result)
            return result
            
        except Exception as e:
            error_msg = f"AWS SNS error: {str(e)}"
            result = self.handle_provider_response({}, success=False, error=error_msg)
            self.log_send_attempt(notification, result)
            return result
