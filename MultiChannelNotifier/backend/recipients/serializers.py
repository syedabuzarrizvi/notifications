from rest_framework import serializers
from .models import (
    RecipientList, Recipient, RecipientListMembership, 
    RecipientImport, RecipientTag, RecipientTagAssignment,
    RecipientEngagement
)
import csv
import io


class RecipientTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecipientTag
        fields = ['id', 'name', 'color', 'description', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def create(self, validated_data):
        validated_data['merchant'] = self.context['request'].user
        return super().create(validated_data)


class RecipientSerializer(serializers.ModelSerializer):
    tags = RecipientTagSerializer(source='tag_assignments.tag', many=True, read_only=True)
    tag_ids = serializers.ListField(child=serializers.UUIDField(), write_only=True, required=False)
    full_name = serializers.ReadOnlyField()
    
    class Meta:
        model = Recipient
        fields = [
            'id', 'email', 'phone', 'device_token', 'whatsapp',
            'first_name', 'last_name', 'full_name', 'custom_fields',
            'is_active', 'email_opted_in', 'sms_opted_in', 
            'push_opted_in', 'whatsapp_opted_in',
            'last_engagement', 'engagement_score',
            'tags', 'tag_ids', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'last_engagement', 'engagement_score', 'created_at', 'updated_at'
        ]
    
    def validate(self, attrs):
        # At least one contact method required
        contact_methods = [attrs.get('email'), attrs.get('phone'), attrs.get('device_token')]
        if not any(contact_methods):
            raise serializers.ValidationError(
                "At least one contact method (email, phone, or device_token) is required."
            )
        return attrs
    
    def create(self, validated_data):
        tag_ids = validated_data.pop('tag_ids', [])
        validated_data['merchant'] = self.context['request'].user
        
        recipient = super().create(validated_data)
        self._assign_tags(recipient, tag_ids)
        
        return recipient
    
    def update(self, instance, validated_data):
        tag_ids = validated_data.pop('tag_ids', None)
        
        recipient = super().update(instance, validated_data)
        
        if tag_ids is not None:
            self._assign_tags(recipient, tag_ids)
        
        return recipient
    
    def _assign_tags(self, recipient, tag_ids):
        """Assign tags to recipient"""
        # Remove existing assignments
        RecipientTagAssignment.objects.filter(recipient=recipient).delete()
        
        # Create new assignments
        for tag_id in tag_ids:
            try:
                tag = RecipientTag.objects.get(id=tag_id, merchant=recipient.merchant)
                RecipientTagAssignment.objects.create(recipient=recipient, tag=tag)
            except RecipientTag.DoesNotExist:
                pass


class RecipientListSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecipientList
        fields = [
            'id', 'name', 'description', 'total_recipients', 'active_recipients',
            'is_active', 'auto_sync', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'total_recipients', 'active_recipients', 'created_at', 'updated_at'
        ]
    
    def create(self, validated_data):
        validated_data['merchant'] = self.context['request'].user
        return super().create(validated_data)


class RecipientListDetailSerializer(RecipientListSerializer):
    recent_recipients = serializers.SerializerMethodField()
    
    class Meta(RecipientListSerializer.Meta):
        fields = RecipientListSerializer.Meta.fields + ['recent_recipients']
    
    def get_recent_recipients(self, obj):
        recent_memberships = RecipientListMembership.objects.filter(
            recipient_list=obj,
            is_active=True
        ).select_related('recipient').order_by('-added_at')[:5]
        
        recipients = [membership.recipient for membership in recent_memberships]
        return RecipientSerializer(recipients, many=True, context=self.context).data


class RecipientListMembershipSerializer(serializers.ModelSerializer):
    recipient = RecipientSerializer(read_only=True)
    added_by_name = serializers.CharField(source='added_by.username', read_only=True)
    
    class Meta:
        model = RecipientListMembership
        fields = [
            'id', 'recipient', 'added_at', 'added_by_name', 'is_active'
        ]


class AddRecipientsToListSerializer(serializers.Serializer):
    """Serializer for adding recipients to a list"""
    recipient_ids = serializers.ListField(child=serializers.UUIDField())
    
    def validate_recipient_ids(self, value):
        merchant = self.context['request'].user
        existing_count = Recipient.objects.filter(
            id__in=value,
            merchant=merchant
        ).count()
        
        if existing_count != len(value):
            raise serializers.ValidationError(
                f"Some recipients not found. Expected {len(value)}, found {existing_count}."
            )
        
        return value


class BulkRecipientImportSerializer(serializers.ModelSerializer):
    recipients_file = serializers.FileField(write_only=True)
    recipients_data = serializers.ListField(write_only=True, required=False)
    
    class Meta:
        model = RecipientImport
        fields = [
            'id', 'filename', 'file_size', 'status', 'total_rows',
            'successful_imports', 'failed_imports', 'duplicate_skips',
            'error_log', 'started_at', 'completed_at', 'created_at',
            'recipients_file', 'recipients_data'
        ]
        read_only_fields = [
            'id', 'status', 'total_rows', 'successful_imports',
            'failed_imports', 'duplicate_skips', 'error_log',
            'started_at', 'completed_at', 'created_at'
        ]
    
    def validate(self, attrs):
        recipients_file = attrs.get('recipients_file')
        recipients_data = attrs.get('recipients_data')
        
        if not recipients_file and not recipients_data:
            raise serializers.ValidationError(
                "Either recipients_file or recipients_data must be provided."
            )
        
        return attrs
    
    def create(self, validated_data):
        recipients_file = validated_data.pop('recipients_file', None)
        recipients_data = validated_data.pop('recipients_data', None)
        
        validated_data['merchant'] = self.context['request'].user
        
        if recipients_file:
            validated_data['filename'] = recipients_file.name
            validated_data['file_size'] = recipients_file.size
        else:
            validated_data['filename'] = 'bulk_import.json'
            validated_data['file_size'] = len(str(recipients_data))
        
        import_record = super().create(validated_data)
        
        # Process import asynchronously
        from .tasks import process_recipient_import_task
        if recipients_file:
            # Save file content temporarily or process directly
            csv_content = recipients_file.read().decode('utf-8')
            process_recipient_import_task.delay(
                str(import_record.id),
                csv_content=csv_content
            )
        else:
            process_recipient_import_task.delay(
                str(import_record.id),
                recipients_data=recipients_data
            )
        
        return import_record


class RecipientEngagementSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecipientEngagement
        fields = [
            'id', 'event_type', 'channel', 'notification_id',
            'campaign_id', 'event_data', 'created_at'
        ]


class RecipientStatsSerializer(serializers.Serializer):
    """Serializer for recipient statistics"""
    total_recipients = serializers.IntegerField()
    active_recipients = serializers.IntegerField()
    opted_in_email = serializers.IntegerField()
    opted_in_sms = serializers.IntegerField()
    opted_in_push = serializers.IntegerField()
    opted_in_whatsapp = serializers.IntegerField()
    engagement_breakdown = serializers.DictField()
    recent_engagements = serializers.ListField()
    top_engaged_recipients = serializers.ListField()


class ExportRecipientsSerializer(serializers.Serializer):
    """Serializer for exporting recipients"""
    format = serializers.ChoiceField(choices=['csv', 'json'], default='csv')
    include_inactive = serializers.BooleanField(default=False)
    include_opted_out = serializers.BooleanField(default=False)
    recipient_list_id = serializers.UUIDField(required=False)
    
    def validate_recipient_list_id(self, value):
        if value:
            merchant = self.context['request'].user
            try:
                RecipientList.objects.get(id=value, merchant=merchant)
            except RecipientList.DoesNotExist:
                raise serializers.ValidationError("Recipient list not found.")
        return value


class RecipientSearchSerializer(serializers.Serializer):
    """Serializer for recipient search"""
    query = serializers.CharField(max_length=255)
    channel = serializers.ChoiceField(
        choices=['email', 'sms', 'push', 'whatsapp'],
        required=False
    )
    opted_in_only = serializers.BooleanField(default=True)
    active_only = serializers.BooleanField(default=True)
    tags = serializers.ListField(child=serializers.UUIDField(), required=False)
