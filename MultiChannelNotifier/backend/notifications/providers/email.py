import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from .base import BaseProvider
import re
import logging

logger = logging.getLogger(__name__)


class EmailProvider(BaseProvider):
    """
    Email provider using SendGrid
    """
    
    def __init__(self, provider_config):
        super().__init__(provider_config)
        self.api_key = os.environ.get('SENDGRID_API_KEY')
        self.from_email = os.environ.get('SENDGRID_FROM_EMAIL', 'noreply@techrar.com')
        
        if not self.api_key:
            raise ValueError("SENDGRID_API_KEY environment variable is required")
        
        self.client = SendGridAPIClient(self.api_key)
    
    def validate_recipient(self, recipient: str) -> bool:
        """
        Validate email address format
        """
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(email_pattern, recipient))
    
    def send(self, notification):
        """
        Send email notification via SendGrid
        """
        try:
            if not self.validate_recipient(notification.recipient):
                return self.handle_provider_response(
                    {}, success=False, error=f"Invalid email address: {notification.recipient}"
                )
            
            # Prepare message
            message_data = self.prepare_message(notification)
            
            # Create SendGrid message
            message = Mail(
                from_email=Email(self.from_email),
                to_emails=To(notification.recipient),
                subject=notification.subject or "Notification"
            )
            
            # Set content based on metadata
            if notification.metadata.get('html_content'):
                message.content = Content("text/html", notification.metadata['html_content'])
            else:
                message.content = Content("text/plain", notification.message)
            
            # Add custom headers if specified
            if notification.metadata.get('headers'):
                for key, value in notification.metadata['headers'].items():
                    message.add_header(key, value)
            
            # Send email
            response = self.client.send(message)
            
            result = self.handle_provider_response({
                'message_id': response.headers.get('X-Message-Id'),
                'status_code': response.status_code,
                'headers': dict(response.headers)
            }, success=True)
            
            self.log_send_attempt(notification, result)
            return result
            
        except Exception as e:
            error_msg = f"SendGrid error: {str(e)}"
            result = self.handle_provider_response({}, success=False, error=error_msg)
            self.log_send_attempt(notification, result)
            return result


class MailgunProvider(BaseProvider):
    """
    Alternative email provider using Mailgun
    """
    
    def __init__(self, provider_config):
        super().__init__(provider_config)
        self.api_key = os.environ.get('MAILGUN_API_KEY')
        self.domain = os.environ.get('MAILGUN_DOMAIN')
        self.from_email = os.environ.get('MAILGUN_FROM_EMAIL', f'noreply@{self.domain}')
        
        if not self.api_key or not self.domain:
            raise ValueError("MAILGUN_API_KEY and MAILGUN_DOMAIN environment variables are required")
    
    def validate_recipient(self, recipient: str) -> bool:
        """
        Validate email address format
        """
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(email_pattern, recipient))
    
    def send(self, notification):
        """
        Send email notification via Mailgun
        """
        try:
            import requests
            
            if not self.validate_recipient(notification.recipient):
                return self.handle_provider_response(
                    {}, success=False, error=f"Invalid email address: {notification.recipient}"
                )
            
            # Prepare request
            url = f"https://api.mailgun.net/v3/{self.domain}/messages"
            auth = ("api", self.api_key)
            
            data = {
                "from": self.from_email,
                "to": notification.recipient,
                "subject": notification.subject or "Notification",
                "text": notification.message
            }
            
            # Add HTML content if specified
            if notification.metadata.get('html_content'):
                data["html"] = notification.metadata['html_content']
            
            # Send request
            response = requests.post(url, auth=auth, data=data)
            response.raise_for_status()
            
            response_data = response.json()
            
            result = self.handle_provider_response({
                'message_id': response_data.get('id'),
                'message': response_data.get('message'),
                'status_code': response.status_code
            }, success=True)
            
            self.log_send_attempt(notification, result)
            return result
            
        except Exception as e:
            error_msg = f"Mailgun error: {str(e)}"
            result = self.handle_provider_response({}, success=False, error=error_msg)
            self.log_send_attempt(notification, result)
            return result
