from rest_framework import serializers
from .models import Template, TemplateVersion, TemplatePreview, TemplateTag, TemplateTagAssignment
import re


class TemplateTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateTag
        fields = ['id', 'name', 'color', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def create(self, validated_data):
        validated_data['merchant'] = self.context['request'].user
        return super().create(validated_data)


class TemplateVersionSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source='changed_by.username', read_only=True)
    
    class Meta:
        model = TemplateVersion
        fields = [
            'id', 'version_number', 'subject', 'content', 'html_content',
            'variables', 'change_summary', 'changed_by_name', 'created_at'
        ]


class TemplatePreviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplatePreview
        fields = [
            'id', 'preview_name', 'sample_data', 'rendered_subject',
            'rendered_content', 'rendered_html', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'rendered_subject', 'rendered_content', 'rendered_html',
            'created_at', 'updated_at'
        ]


class TemplateSerializer(serializers.ModelSerializer):
    tags = TemplateTagSerializer(source='tag_assignments.tag', many=True, read_only=True)
    tag_ids = serializers.ListField(child=serializers.UUIDField(), write_only=True, required=False)
    extracted_variables = serializers.SerializerMethodField()
    
    class Meta:
        model = Template
        fields = [
            'id', 'name', 'description', 'category', 'channel',
            'subject', 'content', 'html_content', 'variables',
            'usage_count', 'last_used', 'is_active',
            'tags', 'tag_ids', 'extracted_variables',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'usage_count', 'last_used', 'created_at', 'updated_at'
        ]
    
    def get_extracted_variables(self, obj):
        """Extract variables from template content"""
        variables = set()
        content = f"{obj.subject} {obj.content}"
        
        # Find variables in {variable} format
        pattern = r'\{(\w+)\}'
        matches = re.findall(pattern, content)
        variables.update(matches)
        
        return list(variables)
    
    def create(self, validated_data):
        tag_ids = validated_data.pop('tag_ids', [])
        validated_data['merchant'] = self.context['request'].user
        
        template = super().create(validated_data)
        
        # Create initial version
        TemplateVersion.objects.create(
            template=template,
            version_number=1,
            subject=template.subject,
            content=template.content,
            html_content=template.html_content,
            variables=template.variables,
            change_summary='Initial version',
            changed_by=template.merchant
        )
        
        # Assign tags
        self._assign_tags(template, tag_ids)
        
        return template
    
    def update(self, instance, validated_data):
        tag_ids = validated_data.pop('tag_ids', None)
        
        # Check if content changed
        content_changed = any(
            validated_data.get(field) != getattr(instance, field)
            for field in ['subject', 'content', 'html_content', 'variables']
            if field in validated_data
        )
        
        template = super().update(instance, validated_data)
        
        # Create new version if content changed
        if content_changed:
            latest_version = TemplateVersion.objects.filter(
                template=template
            ).order_by('-version_number').first()
            
            new_version_number = (latest_version.version_number + 1) if latest_version else 1
            
            TemplateVersion.objects.create(
                template=template,
                version_number=new_version_number,
                subject=template.subject,
                content=template.content,
                html_content=template.html_content,
                variables=template.variables,
                change_summary='Updated via API',
                changed_by=self.context['request'].user
            )
        
        # Update tags if provided
        if tag_ids is not None:
            self._assign_tags(template, tag_ids)
        
        return template
    
    def _assign_tags(self, template, tag_ids):
        """Assign tags to template"""
        # Remove existing assignments
        TemplateTagAssignment.objects.filter(template=template).delete()
        
        # Create new assignments
        for tag_id in tag_ids:
            try:
                tag = TemplateTag.objects.get(id=tag_id, merchant=template.merchant)
                TemplateTagAssignment.objects.create(template=template, tag=tag)
            except TemplateTag.DoesNotExist:
                pass


class TemplateDetailSerializer(TemplateSerializer):
    versions = TemplateVersionSerializer(many=True, read_only=True)
    previews = TemplatePreviewSerializer(many=True, read_only=True)
    
    class Meta(TemplateSerializer.Meta):
        fields = TemplateSerializer.Meta.fields + ['versions', 'previews']


class CreateTemplatePreviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplatePreview
        fields = ['preview_name', 'sample_data']
    
    def create(self, validated_data):
        template = self.context['template']
        validated_data['template'] = template
        
        # Render preview content
        preview = super().create(validated_data)
        self._render_preview(preview)
        
        return preview
    
    def _render_preview(self, preview):
        """Render template with sample data"""
        try:
            # Simple variable substitution
            rendered_subject = preview.template.subject
            rendered_content = preview.template.content
            rendered_html = preview.template.html_content
            
            for key, value in preview.sample_data.items():
                placeholder = f"{{{key}}}"
                rendered_subject = rendered_subject.replace(placeholder, str(value))
                rendered_content = rendered_content.replace(placeholder, str(value))
                if rendered_html:
                    rendered_html = rendered_html.replace(placeholder, str(value))
            
            preview.rendered_subject = rendered_subject
            preview.rendered_content = rendered_content
            preview.rendered_html = rendered_html
            preview.save()
            
        except Exception as e:
            # If rendering fails, use original content
            preview.rendered_subject = preview.template.subject
            preview.rendered_content = preview.template.content
            preview.rendered_html = preview.template.html_content
            preview.save()


class RenderTemplateSerializer(serializers.Serializer):
    """Serializer for rendering template with variables"""
    variables = serializers.DictField(required=False, default=dict)
    
    def validate_variables(self, value):
        # Ensure all values are strings
        return {k: str(v) for k, v in value.items()}


class DuplicateTemplateSerializer(serializers.Serializer):
    """Serializer for duplicating a template"""
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    
    def validate_name(self, value):
        merchant = self.context['request'].user
        if Template.objects.filter(merchant=merchant, name=value).exists():
            raise serializers.ValidationError("Template with this name already exists.")
        return value


class TemplateStatsSerializer(serializers.Serializer):
    """Serializer for template statistics"""
    total_templates = serializers.IntegerField()
    templates_by_channel = serializers.DictField()
    templates_by_category = serializers.DictField()
    most_used_templates = serializers.ListField()
    recent_templates = serializers.ListField()
