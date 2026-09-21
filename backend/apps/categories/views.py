"""Category views.

User isolation is enforced by scoping every queryset through `get_queryset()`
and additionally by `IsOwner` on the object level.
"""

from __future__ import annotations

from django.db.models import Count, Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwner

from .models import CATEGORY_COLOR_CHOICES, CATEGORY_ICON_CHOICES, Category, CategoryKind
from .serializers import (
    CategoryPickerSerializer,
    CategorySerializer,
    CategoryWriteSerializer,
)


class CategoryViewSet(viewsets.ModelViewSet):
    """CRUD for categories, scoped to the authenticated user.

    list:   GET    /api/categories/
    create: POST   /api/categories/
    read:   GET    /api/categories/{id}/
    update: PATCH  /api/categories/{id}/
    delete: DELETE /api/categories/{id}/
    picker: GET    /api/categories/picker/
    meta:   GET    /api/categories/meta/
    """

    permission_classes = [IsOwner]
    filterset_fields = ["kind", "is_active", "parent"]
    search_fields = ["name"]
    ordering_fields = ["sort_order", "name", "created_at"]
    ordering = ["sort_order", "name"]

    def get_queryset(self):
        # The single source of isolation. Everything below builds on this.
        queryset = Category.objects.for_user(self.request.user).with_relations()

        # `top_level=true` is the common case for grouped lists.
        top_level = self.request.query_params.get("top_level")
        if top_level in ("true", "1"):
            queryset = queryset.filter(parent__isnull=True)

        # Annotate transaction counts so the UI can warn before deletion.
        return queryset.annotate(
            children_count=Count("children", distinct=True),
            transactions_count=Count("transactions", distinct=True),
        )

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return CategoryWriteSerializer
        if self.action == "picker":
            return CategoryPickerSerializer
        return CategorySerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        """Create, then respond with the full read representation.

        The write serializer omits the computed fields (`full_path`, `depth`,
        counts), so the client would have to refetch to render the new row.
        """
        write_serializer = self.get_serializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        instance = write_serializer.save(user=request.user)

        fresh = self.get_queryset().get(pk=instance.pk)
        read_serializer = CategorySerializer(fresh, context=self.get_serializer_context())
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Update, then respond with the full read representation."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        write_serializer = self.get_serializer(instance, data=request.data, partial=partial)
        write_serializer.is_valid(raise_exception=True)
        write_serializer.save()

        fresh = self.get_queryset().get(pk=instance.pk)
        read_serializer = CategorySerializer(fresh, context=self.get_serializer_context())
        return Response(read_serializer.data)

    def destroy(self, request, *args, **kwargs):
        """Refuse to delete a category that still has transactions.

        Cascading the delete would silently remove the user's financial history,
        which is indistinguishable from data loss. The user is asked to move or
        delete those transactions explicitly instead.
        """
        category = self.get_object()

        if category.transactions.exists():
            count = category.transactions.count()
            return Response(
                {
                    "detail": (
                        f"این دسته‌بندی {count} تراکنش دارد. ابتدا تراکنش‌ها را "
                        "جابه‌جا یا حذف کنید."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        if category.children.exists():
            return Response(
                {"detail": "ابتدا زیرمجموعه‌های این دسته‌بندی را حذف کنید."},
                status=status.HTTP_409_CONFLICT,
            )

        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["get"])
    def picker(self, request):
        """Compact list for the transaction form's category selector."""
        queryset = (
            Category.objects.for_user(request.user)
            .filter(is_active=True)
            .order_by("sort_order", "name")
        )

        kind = request.query_params.get("kind")
        if kind in dict(CategoryKind.choices):
            queryset = queryset.filter(kind=kind)

        serializer = CategoryPickerSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def meta(self, request):
        """Icon and color options for the category editor.

        Served from the backend so the client never has to hardcode a list that
        could fall out of sync with the validation rules.
        """
        return Response(
            {
                "icons": [{"name": name, "label": label} for name, label in CATEGORY_ICON_CHOICES],
                "colors": [{"name": name, "label": label} for name, label in CATEGORY_COLOR_CHOICES],
                "kinds": [{"value": value, "label": label} for value, label in CategoryKind.choices],
            }
        )

    @action(detail=False, methods=["get"], url_path="grouped")
    def grouped(self, request):
        """Expense (and income) categories as a parent/children tree.

        Used by the category management screen, where a flat list would obscure
        the hierarchy.
        """
        queryset = (
            Category.objects.for_user(request.user)
            .filter(is_active=True)
            .with_relations()
            .order_by("sort_order", "name")
        )

        kind = request.query_params.get("kind", CategoryKind.EXPENSE)
        queryset = queryset.filter(kind=kind)

        parents = [c for c in queryset if c.parent_id is None]
        children_by_parent: dict[int, list] = {}
        for category in queryset:
            if category.parent_id:
                children_by_parent.setdefault(category.parent_id, []).append(category)

        payload = []
        for parent in parents:
            data = CategorySerializer(parent).data
            data["children"] = CategorySerializer(
                children_by_parent.get(parent.pk, []), many=True
            ).data
            payload.append(data)

        return Response(payload)
