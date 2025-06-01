from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/notifications/(?P<merchant_id>\w+)/$', consumers.NotificationConsumer.as_asgi()),
    re_path(r'ws/campaigns/(?P<merchant_id>\w+)/$', consumers.CampaignConsumer.as_asgi()),
    re_path(r'ws/dashboard/(?P<merchant_id>\w+)/$', consumers.DashboardConsumer.as_asgi()),
]
