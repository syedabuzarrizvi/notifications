from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Count
from .models import Template, TemplateVersion, TemplatePreview, TemplateTag
from .serializers import (
    TemplateSerializer, TemplateDetailSerializer, TemplateVersionSerializer,
    TemplatePreviewSerializer, CreateTemplatePreviewSerializer, TemplateTagSerializer,
    RenderTemplateSerializer, DuplicateTemplateSerializer, TemplateStatsSerializer
)
import logging

logger = logging.getLogger(__name__)


class TemplateListCreateView(generics.ListCreateAPIView):
    """
    List templates or create a new template
    """
    serializer_class = TemplateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = Template.objects.filter(merchant=self.request.user, is_active=True)
        
        # Apply filters
        channel = self.request.query_params.get('channel')
        category = self.request.query_params.get('category')
        search = self.request.query_params.get('search')
        
        if channel:
            queryset = queryset.filter(channel=channel)
        if category:
            queryset = queryset.filter(category=category)
        if search:
            queryset = queryset.filter(name__icontains=search)
        
        return queryset.order_by('-updated_at')


class TemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete a template
    """
    serializer_class = TemplateDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Template.objects.filter(merchant=self.request.user)
    
    def destroy(self, request, *args, **kwargs):
        template = self.get_object()
        
        if template.is_system:
            return Response({
                'error': 'Cannot delete system templates'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Soft delete - mark as inactive instead of actual deletion
        template.is_active = False
        template.save()
        
        return Response(status=status.HTTP_204_NO_CONTENT)


class TemplateVersionListView(generics.ListAPIView):
    """
    List template versions
    """
    serializer_class = TemplateVersionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        template_id = self.kwargs['template_id']
        template = get_object_or_404(
            Template,
            id=template_id,
            merchant=self.request.user
        )
        return TemplateVersion.objects.filter(template=template)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def revert_template_version(request, template_id, version_number):
    """
    Revert template to a specific version
    """
    template = get_object_or_404(
        Template,
        id=template_id,
        merchant=request.user
    )
    
    version = get_object_or_404(
        TemplateVersion,
        template=template,
        version_number=version_number
    )
    
    with transaction.atomic():
        # Update template with version data
        template.subject = version.subject
        template.content = version.content
        template.html_content = version.html_content
        template.variables = version.variables
        template.save()
        
        # Create new version entry
        latest_version = TemplateVersion.objects.filter(
            template=template
        ).order_by('-version_number').first()
        
        new_version_number = latest_version.version_number + 1
        
        TemplateVersion.objects.create(
            template=template,
            version_number=new_version_number,
            subject=template.subject,
            content=template.content,
            html_content=template.html_content,
            variables=template.variables,
            change_summary=f'Reverted to version {version_number}',
            changed_by=request.user
        )
    
    return Response({
        'message': f'Template reverted to version {version_number}',
        'template': TemplateDetailSerializer(template).data
    })


class TemplatePreviewListCreateView(generics.ListCreateAPIView):
    """
    List or create template previews
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CreateTemplatePreviewSerializer
        return TemplatePreviewSerializer
    
    def get_queryset(self):
        template_id = self.kwargs['template_id']
        template = get_object_or_404(
            Template,
            id=template_id,
            merchant=self.request.user
        )
        return TemplatePreview.objects.filter(template=template)
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        template_id = self.kwargs['template_id']
        template = get_object_or_404(
            Template,
            id=template_id,
            merchant=self.request.user
        )
        context['template'] = template
        return context


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def render_template(request, template_id):
    """
    Render template with provided variables
    """
    template = get_object_or_404(
        Template,
        id=template_id,
        merchant=request.user
    )
    
    serializer = RenderTemplateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    variables = serializer.validated_data['variables']
    
    try:
        # Simple variable substitution
        rendered_subject = template.subject
        rendered_content = template.content
        rendered_html = template.html_content
        
        for key, value in variables.items():
            placeholder = f"{{{key}}}"
            rendered_subject = rendered_subject.replace(placeholder, str(value))
            rendered_content = rendered_content.replace(placeholder, str(value))
            if rendered_html:
                rendered_html = rendered_html.replace(placeholder, str(value))
        
        return Response({
            'rendered_subject': rendered_subject,
            'rendered_content': rendered_content,
            'rendered_html': rendered_html,
            'variables_used': variables
        })
        
    except Exception as e:
        return Response({
            'error': f'Template rendering failed: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def duplicate_template(request, template_id):
    """
    Duplicate an existing template
    """
    original_template = get_object_or_404(
        Template,
        id=template_id,
        merchant=request.user
    )
    
    serializer = DuplicateTemplateSerializer(
        data=request.data,
        context={'request': request}
    )
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    with transaction.atomic():
        # Create new template
        new_template = Template.objects.create(
            merchant=request.user,
            name=serializer.validated_data['name'],
            description=serializer.validated_data.get('description', original_template.description),
            category=original_template.category,
            channel=original_template.channel,
            subject=original_template.subject,
            content=original_template.content,
            html_content=original_template.html_content,
            variables=original_template.variables
        )
        
        # Create initial version
        TemplateVersion.objects.create(
            template=new_template,
            version_number=1,
            subject=new_template.subject,
            content=new_template.content,
            html_content=new_template.html_content,
            variables=new_template.variables,
            change_summary=f'Duplicated from template: {original_template.name}',
            changed_by=request.user
        )
    
    return Response({
        'message': 'Template duplicated successfully',
        'template': TemplateSerializer(new_template).data
    }, status=status.HTTP_201_CREATED)


class TemplateTagListCreateView(generics.ListCreateAPIView):
    """
    List or create template tags
    """
    serializer_class = TemplateTagSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return TemplateTag.objects.filter(
            merchant=self.request.user
        ).order_by('name')


class TemplateTagDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete a template tag
    """
    serializer_class = TemplateTagSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return TemplateTag.objects.filter(merchant=self.request.user)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def template_stats(request):
    """
    Get template statistics for the merchant
    """
    merchant = request.user
    templates = Template.objects.filter(merchant=merchant, is_active=True)
    
    # Basic stats
    total_templates = templates.count()
    
    # Templates by channel
    templates_by_channel = dict(
        templates.values('channel').annotate(
            count=Count('id')
        ).values_list('channel', 'count')
    )
    
    # Templates by category
    templates_by_category = dict(
        templates.values('category').annotate(
            count=Count('id')
        ).values_list('category', 'count')
    )
    
    # Most used templates
    most_used = templates.filter(
        usage_count__gt=0
    ).order_by('-usage_count')[:5]
    
    most_used_templates = []
    for template in most_used:
        most_used_templates.append({
            'id': template.id,
            'name': template.name,
            'usage_count': template.usage_count,
            'last_used': template.last_used,
            'channel': template.channel
        })
    
    # Recent templates
    recent = templates.order_by('-created_at')[:5]
    recent_templates = []
    for template in recent:
        recent_templates.append({
            'id': template.id,
            'name': template.name,
            'channel': template.channel,
            'created_at': template.created_at
        })
    
    stats = {
        'total_templates': total_templates,
        'templates_by_channel': templates_by_channel,
        'templates_by_category': templates_by_category,
        'most_used_templates': most_used_templates,
        'recent_templates': recent_templates
    }
    
    return Response(stats)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def test_template(request, template_id):
    """
    Send a test notification using the template
    """
    template = get_object_or_404(
        Template,
        id=template_id,
        merchant=request.user
    )
    
    test_recipient = request.data.get('test_recipient')
    test_variables = request.data.get('variables', {})
    
    if not test_recipient:
        return Response({
            'error': 'test_recipient is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Render template with test variables
        rendered_subject = template.subject
        rendered_content = template.content
        
        for key, value in test_variables.items():
            placeholder = f"{{{key}}}"
            rendered_subject = rendered_subject.replace(placeholder, str(value))
            rendered_content = rendered_content.replace(placeholder, str(value))
        
        # Create test notification
        from notifications.models import Notification
        notification = Notification.objects.create(
            merchant=request.user,
            channel=template.channel,
            recipient=test_recipient,
            subject=rendered_subject,
            message=rendered_content,
            metadata={
                'template_id': str(template.id),
                'test_notification': True,
                **test_variables
            }
        )
        
        # Queue for sending
        from notifications.tasks import send_notification_task
        send_notification_task.delay(str(notification.id))
        
        # Update template usage
        template.increment_usage()
        
        return Response({
            'message': 'Test notification sent successfully',
            'notification_id': notification.id,
            'rendered_subject': rendered_subject,
            'rendered_content': rendered_content
        })
        
    except Exception as e:
        return Response({
            'error': f'Failed to send test notification: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)
