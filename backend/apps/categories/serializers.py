"""Category serializers."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import CATEGORY_COLOR_CHOICES, CATEGORY_ICON_CHOICES, Category
from .services import validate_hierarchy

_VALID_ICONS = {name for name, _ in CATEGORY_ICON_CHOICES}


class CategorySerializer(serializers.ModelSerializer):
    """Read serializer. Includes the computed fields the UI needs to render a
    category chip without extra requests."""

    full_path = serializers.CharField(read_only=True)
    is_subcategory = serializers.BooleanField(read_only=True)
    depth = serializers.IntegerField(read_only=True)
    parent_name = serializers.CharField(source="parent.name", read_only=True, default=None)

    class Meta:
        model = Category
        fields = (
            "id",
            "name",
            "kind",
            "icon",
            "color",
            "parent",
            "parent_name",
            "full_path",
            "is_subcategory",
            "depth",
            "is_default",
            "is_active",
            "sort_order",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "is_default", "created_at", "updated_at")


class CategoryWriteSerializer(serializers.ModelSerializer):
    """Create/update serializer with hierarchy and icon validation."""

    class Meta:
        model = Category
        fields = (
            "id",
            "name",
            "kind",
            "icon",
            "color",
            "parent",
            "is_active",
            "sort_order",
        )
        read_only_fields = ("id",)

    def validate_name(self, value):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("نام دسته‌بندی نمی‌تواند خالی باشد.")
        return cleaned

    def validate_icon(self, value):
        if value not in _VALID_ICONS:
            raise serializers.ValidationError(
                "آیکون انتخابی معتبر نیست. یکی از آیکون‌های فهرست را انتخاب کنید."
            )
        return value

    def validate_color(self, value):
        valid = {name for name, _ in CATEGORY_COLOR_CHOICES}
        if value not in valid:
            raise serializers.ValidationError("رنگ انتخابی معتبر نیست.")
        return value

    def validate_parent(self, value):
        """A parent must belong to the requesting user."""
        if value is None:
            return value
        request = self.context.get("request")
        if request and value.user_id != request.user.id:
            raise serializers.ValidationError("دسته‌بندی والد معتبر نیست.")
        return value

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user

        # On create, `kind` may be omitted (model default applies); resolve the
        # effective values so hierarchy validation sees the real state.
        instance = self.instance
        effective_kind = attrs.get("kind", getattr(instance, "kind", "expense"))
        effective_parent = attrs.get("parent", getattr(instance, "parent", None))
        effective_name = attrs.get("name", getattr(instance, "name", ""))

        # Duplicate name within the same user + kind.
        duplicates = Category.objects.filter(
            user=user, name=effective_name, kind=effective_kind
        )
        if instance is not None:
            duplicates = duplicates.exclude(pk=instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError(
                {"name": "دسته‌بندی با این نام قبلاً ساخته شده است."}
            )

        # Hierarchy rules, using a detached instance so we do not mutate the
        # real object before validation passes.
        probe = Category(
            pk=getattr(instance, "pk", None),
            user=user,
            name=effective_name,
            kind=effective_kind,
            parent=effective_parent,
        )
        try:
            validate_hierarchy(probe)
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise serializers.ValidationError(exc.message_dict) from exc
            raise serializers.ValidationError(exc.messages) from exc

        return attrs


class CategoryPickerSerializer(serializers.ModelSerializer):
    """Slim serializer for the transaction form, where payload size matters.

    Only returns active categories, and includes just enough to render a fast
    picker: id, name, icon, color and whether it is a subcategory.
    """

    full_path = serializers.CharField(read_only=True)
    is_subcategory = serializers.BooleanField(read_only=True)

    class Meta:
        model = Category
        fields = ("id", "name", "kind", "icon", "color", "parent", "full_path", "is_subcategory")
