from rest_framework import serializers
from .models import (
    Notification, BulkNotification, NotificationEvent, Provider,
    NotificationChannel, NotificationPriority, NotificationStatus
)
import csv
import io


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'id', 'channel', 'recipient', 'subject', 'message', 'metadata',
            'status', 'priority', 'scheduled_at', 'sent_at', 'delivered_at',
            'provider', 'provider_message_id', 'retry_count', 'idempotency_key',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status', 'sent_at', 'delivered_at', 'provider',
            'provider_message_id', 'retry_count', 'created_at', 'updated_at'
        ]

    def validate_idempotency_key(self, value):
        if value:
            merchant = self.context['request'].user
            existing = Notification.objects.filter(
                merchant=merchant,
                idempotency_key=value
            ).first()
            if existing:
                raise serializers.ValidationError(
                    f"Notification with idempotency key '{value}' already exists."
                )
        return value


class SendNotificationSerializer(serializers.Serializer):
    """
    Serializer for immediate notification sending
    """
    channel = serializers.ChoiceField(choices=NotificationChannel.choices)
    recipient = serializers.CharField(max_length=255)
    subject = serializers.CharField(max_length=255, required=False, allow_blank=True)
    message = serializers.CharField()
    metadata = serializers.JSONField(required=False, default=dict)
    priority = serializers.ChoiceField(
        choices=NotificationPriority.choices,
        default=NotificationPriority.NORMAL
    )
    idempotency_key = serializers.CharField(max_length=255, required=False)

    def validate_idempotency_key(self, value):
        if value:
            merchant = self.context['request'].user
            existing = Notification.objects.filter(
                merchant=merchant,
                idempotency_key=value
            ).first()
            if existing:
                # Return existing notification data instead of raising error
                self.existing_notification = existing
        return value


class ScheduleNotificationSerializer(serializers.Serializer):
    """
    Serializer for scheduling notifications
    """
    channel = serializers.ChoiceField(choices=NotificationChannel.choices)
    recipient = serializers.CharField(max_length=255)
    subject = serializers.CharField(max_length=255, required=False, allow_blank=True)
    message = serializers.CharField()
    metadata = serializers.JSONField(required=False, default=dict)
    priority = serializers.ChoiceField(
        choices=NotificationPriority.choices,
        default=NotificationPriority.NORMAL
    )
    scheduled_at = serializers.DateTimeField()
    idempotency_key = serializers.CharField(max_length=255, required=False)

    def validate_scheduled_at(self, value):
        from django.utils import timezone
        if value <= timezone.now():
            raise serializers.ValidationError("Scheduled time must be in the future.")
        return value


class BulkNotificationSerializer(serializers.ModelSerializer):
    recipients_file = serializers.FileField(write_only=True, required=False)
    recipients_data = serializers.ListField(write_only=True, required=False)

    class Meta:
        model = BulkNotification
        fields = [
            'id', 'name', 'channel', 'message', 'subject', 'total_recipients',
            'status', 'processed_count', 'success_count', 'failed_count',
            'scheduled_at', 'started_at', 'completed_at', 'metadata',
            'recipients_file', 'recipients_data', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'total_recipients', 'status', 'processed_count',
            'success_count', 'failed_count', 'started_at', 'completed_at',
            'created_at', 'updated_at'
        ]

    def validate(self, attrs):
        recipients_file = attrs.get('recipients_file')
        recipients_data = attrs.get('recipients_data')
        
        if not recipients_file and not recipients_data:
            raise serializers.ValidationError(
                "Either recipients_file or recipients_data must be provided."
            )
        
        if recipients_file and recipients_data:
            raise serializers.ValidationError(
                "Provide either recipients_file or recipients_data, not both."
            )
        
        return attrs

    def create(self, validated_data):
        recipients_file = validated_data.pop('recipients_file', None)
        recipients_data = validated_data.pop('recipients_data', None)
        
        # Process recipients
        recipients_csv = ""
        total_recipients = 0
        
        if recipients_file:
            # Read CSV file
            csv_content = recipients_file.read().decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(csv_content))
            recipients_list = list(csv_reader)
            total_recipients = len(recipients_list)
            recipients_csv = csv_content
        elif recipients_data:
            # Convert list to CSV
            if recipients_data:
                fieldnames = recipients_data[0].keys()
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(recipients_data)
                recipients_csv = output.getvalue()
                total_recipients = len(recipients_data)
        
        validated_data['recipients_csv'] = recipients_csv
        validated_data['total_recipients'] = total_recipients
        validated_data['merchant'] = self.context['request'].user
        
        return super().create(validated_data)


class NotificationEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationEvent
        fields = ['id', 'event_type', 'event_data', 'error_message', 'created_at']


class NotificationDetailSerializer(NotificationSerializer):
    events = NotificationEventSerializer(many=True, read_only=True)
    
    class Meta(NotificationSerializer.Meta):
        fields = NotificationSerializer.Meta.fields + ['events']


class ProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Provider
        fields = [
            'id', 'name', 'channel', 'is_active', 'rate_limit_per_minute',
            'rate_limit_per_hour', 'priority', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class NotificationStatusSerializer(serializers.Serializer):
    """
    Serializer for notification status queries
    """
    notification_id = serializers.UUIDField()
    status = serializers.CharField(read_only=True)
    sent_at = serializers.DateTimeField(read_only=True)
    delivered_at = serializers.DateTimeField(read_only=True)
    provider = serializers.CharField(read_only=True)
    provider_message_id = serializers.CharField(read_only=True)
    error_message = serializers.CharField(read_only=True)
