from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import login
from .models import Merchant, MerchantSettings
from .serializers import (
    MerchantRegistrationSerializer, 
    MerchantLoginSerializer,
    MerchantProfileSerializer,
    MerchantSettingsSerializer
)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def register(request):
    """
    Register a new merchant
    """
    serializer = MerchantRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        merchant = serializer.save()
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(merchant)
        
        return Response({
            'message': 'Merchant registered successfully',
            'merchant': MerchantProfileSerializer(merchant).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login_view(request):
    """
    Authenticate merchant and return JWT tokens
    """
    serializer = MerchantLoginSerializer(data=request.data)
    if serializer.is_valid():
        merchant = serializer.validated_data['merchant']
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(merchant)
        
        return Response({
            'message': 'Login successful',
            'merchant': MerchantProfileSerializer(merchant).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def logout(request):
    """
    Logout user by blacklisting refresh token
    """
    try:
        refresh_token = request.data["refresh"]
        token = RefreshToken(refresh_token)
        token.blacklist()
        return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)


class MerchantProfileView(generics.RetrieveUpdateAPIView):
    """
    Get and update merchant profile
    """
    serializer_class = MerchantProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user


class MerchantSettingsView(generics.RetrieveUpdateAPIView):
    """
    Get and update merchant settings
    """
    serializer_class = MerchantSettingsSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        settings, created = MerchantSettings.objects.get_or_create(
            merchant=self.request.user
        )
        return settings


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def api_key(request):
    """
    Get merchant API key for external integrations
    """
    merchant = request.user
    return Response({
        'api_key': merchant.api_key,
        'usage_info': {
            'sms_sent_today': merchant.settings.sms_sent_today,
            'email_sent_today': merchant.settings.email_sent_today,
            'push_sent_today': merchant.settings.push_sent_today,
            'whatsapp_sent_today': merchant.settings.whatsapp_sent_today,
        }
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def regenerate_api_key(request):
    """
    Regenerate merchant API key
    """
    merchant = request.user
    merchant.api_key = None  # Will generate new one on save
    merchant.save()
    
    return Response({
        'message': 'API key regenerated successfully',
        'api_key': merchant.api_key
    })
