from rest_framework import serializers
from django.utils import timezone
from .models import Campaign, CampaignTemplate, CampaignRecipient, CampaignEvent, AudienceSegment
from templates.models import Template
import csv
import io


class CampaignTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampaignTemplate
        fields = [
            'id', 'subject', 'message', 'html_content', 'variables',
            'is_variant', 'variant_name', 'parent_template',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CampaignRecipientSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampaignRecipient
        fields = [
            'id', 'recipient', 'recipient_data', 'status',
            'sent_at', 'delivered_at', 'opened_at', 'clicked_at',
            'error_message', 'retry_count', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status', 'sent_at', 'delivered_at', 'opened_at',
            'clicked_at', 'error_message', 'retry_count', 'created_at', 'updated_at'
        ]


class CampaignEventSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = CampaignEvent
        fields = ['id', 'event_type', 'event_data', 'user_name', 'created_at']


class CampaignSerializer(serializers.ModelSerializer):
    template = CampaignTemplateSerializer(read_only=True)
    success_rate = serializers.ReadOnlyField()
    open_rate = serializers.ReadOnlyField()
    click_rate = serializers.ReadOnlyField()
    
    class Meta:
        model = Campaign
        fields = [
            'id', 'name', 'description', 'channel', 'status',
            'scheduled_at', 'started_at', 'completed_at',
            'target_audience', 'estimated_recipients',
            'total_sent', 'total_delivered', 'total_failed',
            'total_clicked', 'total_opened',
            'budget_limit', 'daily_limit', 'settings',
            'template', 'success_rate', 'open_rate', 'click_rate',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'total_sent', 'total_delivered', 'total_failed',
            'total_clicked', 'total_opened', 'started_at', 'completed_at',
            'created_at', 'updated_at'
        ]
    
    def validate_scheduled_at(self, value):
        if value and value <= timezone.now():
            raise serializers.ValidationError("Scheduled time must be in the future.")
        return value


class CreateCampaignSerializer(serializers.ModelSerializer):
    template_data = CampaignTemplateSerializer(write_only=True)
    recipients_file = serializers.FileField(write_only=True, required=False)
    recipients_data = serializers.ListField(write_only=True, required=False)
    template_id = serializers.UUIDField(write_only=True, required=False)
    
    class Meta:
        model = Campaign
        fields = [
            'name', 'description', 'channel', 'scheduled_at',
            'target_audience', 'budget_limit', 'daily_limit', 'settings',
            'template_data', 'recipients_file', 'recipients_data', 'template_id'
        ]
    
    def validate(self, attrs):
        template_data = attrs.get('template_data')
        template_id = attrs.get('template_id')
        
        if not template_data and not template_id:
            raise serializers.ValidationError(
                "Either template_data or template_id must be provided."
            )
        
        if template_data and template_id:
            raise serializers.ValidationError(
                "Provide either template_data or template_id, not both."
            )
        
        return attrs
    
    def create(self, validated_data):
        template_data = validated_data.pop('template_data', None)
        template_id = validated_data.pop('template_id', None)
        recipients_file = validated_data.pop('recipients_file', None)
        recipients_data = validated_data.pop('recipients_data', None)
        
        # Create campaign
        validated_data['merchant'] = self.context['request'].user
        campaign = Campaign.objects.create(**validated_data)
        
        # Create or link template
        if template_data:
            CampaignTemplate.objects.create(
                campaign=campaign,
                **template_data
            )
        elif template_id:
            try:
                from templates.models import Template
                template = Template.objects.get(
                    id=template_id,
                    merchant=campaign.merchant
                )
                CampaignTemplate.objects.create(
                    campaign=campaign,
                    subject=template.subject,
                    message=template.content,
                    html_content=template.html_content,
                    variables=template.variables
                )
            except Template.DoesNotExist:
                raise serializers.ValidationError(
                    f"Template with id {template_id} not found."
                )
        
        # Process recipients
        if recipients_file or recipients_data:
            self._process_recipients(campaign, recipients_file, recipients_data)
        
        # Create campaign event
        CampaignEvent.objects.create(
            campaign=campaign,
            event_type='created',
            event_data={'source': 'api'},
            user=campaign.merchant
        )
        
        return campaign
    
    def _process_recipients(self, campaign, recipients_file, recipients_data):
        """Process and add recipients to campaign"""
        recipients = []
        
        if recipients_file:
            # Read CSV file
            csv_content = recipients_file.read().decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(csv_content))
            recipients = list(csv_reader)
        elif recipients_data:
            recipients = recipients_data
        
        # Create recipient records
        recipient_objects = []
        for recipient_data in recipients:
            recipient = self._extract_recipient(recipient_data, campaign.channel)
            if recipient:
                recipient_objects.append(CampaignRecipient(
                    campaign=campaign,
                    recipient=recipient,
                    recipient_data=recipient_data
                ))
        
        if recipient_objects:
            CampaignRecipient.objects.bulk_create(recipient_objects)
            campaign.estimated_recipients = len(recipient_objects)
            campaign.save()
    
    def _extract_recipient(self, recipient_data, channel):
        """Extract recipient contact info based on channel"""
        if channel == 'email':
            return recipient_data.get('email') or recipient_data.get('Email')
        elif channel == 'sms':
            return recipient_data.get('phone') or recipient_data.get('Phone')
        elif channel == 'push':
            return recipient_data.get('device_token') or recipient_data.get('Device_Token')
        elif channel == 'whatsapp':
            return (recipient_data.get('whatsapp') or 
                   recipient_data.get('WhatsApp') or 
                   recipient_data.get('phone'))
        return None


class CampaignDetailSerializer(CampaignSerializer):
    template = CampaignTemplateSerializer(read_only=True)
    events = CampaignEventSerializer(many=True, read_only=True)
    recipients_count = serializers.SerializerMethodField()
    
    class Meta(CampaignSerializer.Meta):
        fields = CampaignSerializer.Meta.fields + ['events', 'recipients_count']
    
    def get_recipients_count(self, obj):
        return obj.recipients.count()


class AudienceSegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AudienceSegment
        fields = [
            'id', 'name', 'description', 'criteria', 'recipient_count',
            'campaigns_used', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'recipient_count', 'campaigns_used', 'created_at', 'updated_at'
        ]
    
    def create(self, validated_data):
        validated_data['merchant'] = self.context['request'].user
        return super().create(validated_data)


class CampaignStatsSerializer(serializers.Serializer):
    """Serializer for campaign statistics"""
    total_campaigns = serializers.IntegerField()
    active_campaigns = serializers.IntegerField()
    completed_campaigns = serializers.IntegerField()
    total_recipients = serializers.IntegerField()
    total_sent = serializers.IntegerField()
    total_delivered = serializers.IntegerField()
    average_success_rate = serializers.FloatField()
    channel_breakdown = serializers.DictField()
    recent_activity = serializers.ListField()


class LaunchCampaignSerializer(serializers.Serializer):
    """Serializer for launching a campaign"""
    launch_immediately = serializers.BooleanField(default=True)
    scheduled_at = serializers.DateTimeField(required=False)
    
    def validate(self, attrs):
        if not attrs.get('launch_immediately') and not attrs.get('scheduled_at'):
            raise serializers.ValidationError(
                "scheduled_at is required when launch_immediately is False"
            )
        
        if attrs.get('scheduled_at') and attrs['scheduled_at'] <= timezone.now():
            raise serializers.ValidationError(
                "Scheduled time must be in the future"
            )
        
        return attrs
