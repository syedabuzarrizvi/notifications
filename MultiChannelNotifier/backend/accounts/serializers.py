from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from .models import Merchant, MerchantSettings


class MerchantRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    
    class Meta:
        model = Merchant
        fields = ('username', 'email', 'password', 'password_confirm', 'first_name', 
                 'last_name', 'company_name')
        
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        merchant = Merchant.objects.create_user(**validated_data)
        MerchantSettings.objects.create(merchant=merchant)
        return merchant


class MerchantLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()
    
    def validate(self, attrs):
        username = attrs.get('username')
        password = attrs.get('password')
        
        if username and password:
            merchant = authenticate(username=username, password=password)
            if not merchant:
                raise serializers.ValidationError('Invalid credentials')
            if not merchant.is_active:
                raise serializers.ValidationError('Account is deactivated')
            attrs['merchant'] = merchant
        else:
            raise serializers.ValidationError('Must provide username and password')
        
        return attrs


class MerchantProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 
                 'company_name', 'is_active', 'created_at')
        read_only_fields = ('id', 'username', 'created_at')


class MerchantSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = MerchantSettings
        fields = ('preferred_sms_provider', 'preferred_email_provider',
                 'preferred_push_provider', 'preferred_whatsapp_provider',
                 'daily_sms_limit', 'daily_email_limit', 'daily_push_limit',
                 'daily_whatsapp_limit', 'sms_sent_today', 'email_sent_today',
                 'push_sent_today', 'whatsapp_sent_today')
        read_only_fields = ('sms_sent_today', 'email_sent_today', 
                          'push_sent_today', 'whatsapp_sent_today')
