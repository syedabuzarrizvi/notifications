#!/usr/bin/env python
import os
import sys
import django

# Add the backend directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'techrar.settings')
django.setup()

from django.contrib.auth import get_user_model
from campaigns.models import Campaign, CampaignTemplate
from notifications.models import NotificationChannel
from campaigns.models import CampaignStatus

User = get_user_model()

def create_sample_templates():
    # Get the first merchant user
    try:
        merchant = User.objects.first()
        if not merchant:
            print('No merchant user found')
            return
        
        # Create email campaign template
        email_campaign, created = Campaign.objects.get_or_create(
            name='Welcome Email Campaign',
            merchant=merchant,
            defaults={
                'description': 'Welcome new users to the platform',
                'channel': NotificationChannel.EMAIL,
                'status': CampaignStatus.DRAFT,
                'target_audience': {'segment': 'new_users'},
                'estimated_recipients': 100,
                'daily_limit': 500
            }
        )
        
        if created:
            CampaignTemplate.objects.create(
                campaign=email_campaign,
                subject='Welcome to {{company_name}}!',
                message='Hi {{first_name}}, welcome to our platform! We are excited to have you on board.',
                html_content='''
                <html>
                <body>
                    <h2>Welcome to {{company_name}}!</h2>
                    <p>Hi {{first_name}},</p>
                    <p>Welcome to our notification platform! We are excited to have you on board.</p>
                    <p>Get started by exploring our features:</p>
                    <ul>
                        <li>Send email notifications</li>
                        <li>SMS messaging</li>
                        <li>Push notifications</li>
                        <li>Campaign management</li>
                    </ul>
                    <p>Best regards,<br>The {{company_name}} Team</p>
                </body>
                </html>
                ''',
                variables={'company_name': 'Techrar', 'first_name': 'User'}
            )
        
        # Create SMS campaign template
        sms_campaign, created = Campaign.objects.get_or_create(
            name='Order Confirmation SMS',
            merchant=merchant,
            defaults={
                'description': 'Confirm customer orders via SMS',
                'channel': NotificationChannel.SMS,
                'status': CampaignStatus.DRAFT,
                'target_audience': {'segment': 'customers'},
                'estimated_recipients': 50,
                'daily_limit': 1000
            }
        )
        
        if created:
            CampaignTemplate.objects.create(
                campaign=sms_campaign,
                message='Hi {{customer_name}}, your order #{{order_id}} has been confirmed. Total: ${{amount}}. Expected delivery: {{delivery_date}}.',
                variables={'customer_name': 'Customer', 'order_id': '12345', 'amount': '99.99', 'delivery_date': '2025-06-05'}
            )
        
        # Create push notification template
        push_campaign, created = Campaign.objects.get_or_create(
            name='Daily Deals Push',
            merchant=merchant,
            defaults={
                'description': 'Daily deals and promotions via push notifications',
                'channel': NotificationChannel.PUSH,
                'status': CampaignStatus.DRAFT,
                'target_audience': {'segment': 'active_users'},
                'estimated_recipients': 1000,
                'daily_limit': 5000
            }
        )
        
        if created:
            CampaignTemplate.objects.create(
                campaign=push_campaign,
                subject='Daily Deals Alert!',
                message='Check out today\'s amazing deals - up to {{discount}}% off on {{category}}!',
                variables={'discount': '50', 'category': 'Electronics'}
            )
        
        print('Sample notification templates created successfully')
        
    except Exception as e:
        print(f'Error creating templates: {e}')

if __name__ == '__main__':
    create_sample_templates()