"""Asset views, including net worth."""

from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsOwner

from .models import Asset, AssetType, AssetValuation
from .serializers import (
    AssetSerializer,
    AssetValuationSerializer,
    AssetValuationWriteSerializer,
    AssetWriteSerializer,
)
from .services import (
    annotate_current_value,
    asset_growth,
    asset_totals,
    asset_type_breakdown,
    net_worth,
    net_worth_history,
)


class AssetViewSet(viewsets.ModelViewSet):
    """CRUD for assets, plus valuations and totals.

    list:        GET    /api/assets/
    create:      POST   /api/assets/
    read:        GET    /api/assets/{id}/
    update:      PATCH  /api/assets/{id}/
    delete:      DELETE /api/assets/{id}/
    summary:     GET    /api/assets/summary/
    breakdown:   GET    /api/assets/breakdown/
    valuations:  GET/POST /api/assets/{id}/valuations/
    """

    permission_classes = [IsOwner]
    filterset_fields = ["asset_type", "is_active"]
    search_fields = ["name", "provider", "description"]
    ordering_fields = ["created_at", "name", "current_value_annotated"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return annotate_current_value(
            Asset.objects.for_user(self.request.user).with_valuations()
        )

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return AssetWriteSerializer
        return AssetSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        asset = serializer.save(user=request.user)

        fresh = self.get_queryset().get(pk=asset.pk)
        return Response(AssetSerializer(fresh).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        fresh = self.get_queryset().get(pk=instance.pk)
        return Response(AssetSerializer(fresh).data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Totals plus the net-worth figure."""
        payload = asset_totals(request.user)
        payload["net_worth"] = net_worth(request.user)
        return Response(payload)

    @action(detail=False, methods=["get"])
    def breakdown(self, request):
        """Assets grouped by type with portfolio share."""
        return Response(
            {
                "by_type": asset_type_breakdown(request.user),
                "types": [{"value": v, "label": l} for v, l in AssetType.choices],
            }
        )

    @action(detail=True, methods=["get", "post"], url_path="valuations")
    def valuations(self, request, pk=None):
        """List or record valuations for an asset."""
        asset = self.get_object()

        if request.method == "GET":
            return Response(
                AssetValuationSerializer(asset.valuations.all(), many=True).data
            )

        serializer = AssetValuationWriteSerializer(
            data=request.data, context={"request": request, "asset": asset}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(asset=asset)

        fresh = self.get_queryset().get(pk=asset.pk)
        return Response(
            {
                "asset": AssetSerializer(fresh).data,
                "totals": asset_totals(request.user),
            },
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"valuations/(?P<valuation_id>[^/.]+)",
    )
    def delete_valuation(self, request, pk=None, valuation_id=None):
        asset = self.get_object()

        try:
            valuation = asset.valuations.get(pk=valuation_id)
        except AssetValuation.DoesNotExist:
            return Response(
                {"detail": "این ارزش‌گذاری پیدا نشد."}, status=status.HTTP_404_NOT_FOUND
            )

        # Refuse to remove the last valuation: the asset would fall back to its
        # purchase value, silently changing the user's net worth.
        if asset.valuations.count() <= 1:
            return Response(
                {
                    "detail": (
                        "حداقل یک ارزش‌گذاری برای هر دارایی لازم است. "
                        "برای تغییر آن، مقدار جدیدی ثبت کنید."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        valuation.delete()

        fresh = self.get_queryset().get(pk=asset.pk)
        return Response({"asset": AssetSerializer(fresh).data, "totals": asset_totals(request.user)})


class NetWorthView(APIView):
    """Net worth summary and history.

    GET /api/net-worth/            → current figures
    GET /api/net-worth/history/    → monthly series (?months=12)
    """

    permission_classes = [IsOwner]

    def get(self, request):
        return Response(net_worth(request.user))


class NetWorthHistoryView(APIView):
    """Monthly net-worth series for charting."""

    permission_classes = [IsOwner]

    def get(self, request):
        try:
            months = min(int(request.query_params.get("months", 12)), 36)
        except (TypeError, ValueError):
            months = 12

        history = net_worth_history(request.user, months=months)

        # Compute the change across the window so the chart can annotate it.
        if len(history) >= 2:
            first = float(history[0]["net_worth"])
            last = float(history[-1]["net_worth"])
            change = last - first
        else:
            change = 0.0

        return Response(
            {
                "history": history,
                "change": str(round(change, 2)),
                "months": months,
            }
        )


class AssetGrowthView(APIView):
    """Valuation history for the asset-growth report.

    GET /api/assets/growth/?asset=<id>
    """

    permission_classes = [IsOwner]

    def get(self, request):
        asset_id = request.query_params.get("asset")
        try:
            asset_id = int(asset_id) if asset_id else None
        except (TypeError, ValueError):
            asset_id = None

        return Response({"history": asset_growth(request.user, asset_id=asset_id)})
