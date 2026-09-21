"""Budget views."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import transaction as db_transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.categories.models import Category, CategoryKind
from apps.core.jalali import (
    current_jalali_month,
    jalali_month_bounds,
    month_progress,
    resolve_month_param,
    to_persian_digits,
)
from apps.core.money import quantize_money
from apps.core.permissions import IsOwner

from .models import Budget, BudgetItem
from .serializers import (
    BudgetItemSerializer,
    BudgetItemWriteSerializer,
    BudgetSerializer,
    BudgetWriteSerializer,
    MonthlyPlanSerializer,
)
from .services import analyse_budget, empty_analysis, spent_by_category


class BudgetViewSet(viewsets.ModelViewSet):
    """CRUD for monthly budgets, plus the analysis endpoints.

    list:       GET    /api/budgets/
    create:     POST   /api/budgets/
    read:       GET    /api/budgets/{id}/
    update:     PATCH  /api/budgets/{id}/
    delete:     DELETE /api/budgets/{id}/
    current:    GET    /api/budgets/current/
    analysis:   GET    /api/budgets/{id}/analysis/
    by_month:   GET    /api/budgets/analysis/?month=1405-06
    performance:GET    /api/budgets/performance/
    plan:       POST   /api/budgets/plan/
    items:      POST   /api/budgets/{id}/items/
    """

    permission_classes = [IsOwner]
    search_fields = ["note"]
    ordering = ["-year", "-month"]

    def get_queryset(self):
        return Budget.objects.for_user(self.request.user).prefetch_related(
            "items__category", "items__category__parent"
        )

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return BudgetWriteSerializer
        return BudgetSerializer

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_month(self, request) -> tuple[int, int]:
        """Resolve the requested Jalali month, defaulting to the current one.

        Delegates to the shared helper in `apps.core.jalali` — see the note
        there on why four copies of this parsing was a bug rather than
        duplication for its own sake.
        """
        return resolve_month_param(request)

    def _get_or_none(self, year: int, month: int) -> Budget | None:
        return Budget.objects.for_user(self.request.user).filter(year=year, month=month).first()

    # ------------------------------------------------------------------
    # Create / update responses carry the analysis
    # ------------------------------------------------------------------

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        budget = serializer.save(user=request.user)

        analysis = analyse_budget(request.user, budget)
        return Response(
            {"budget": BudgetSerializer(budget).data, "analysis": analysis.to_dict()},
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        budget = serializer.save()

        analysis = analyse_budget(request.user, budget)
        return Response(
            {"budget": BudgetSerializer(budget).data, "analysis": analysis.to_dict()}
        )

    # ------------------------------------------------------------------
    # Analysis endpoints
    # ------------------------------------------------------------------

    @action(detail=False, methods=["get"])
    def current(self, request):
        """The analysis for the current Jalali month (or a requested month)."""
        year, month = self._resolve_month(request)
        return self._analysis_response(year, month)

    @action(detail=False, methods=["get"], url_path="analysis")
    def analysis_by_month(self, request):
        """Analysis for ?month=1405-06. Same payload shape as `current`."""
        year, month = self._resolve_month(request)
        return self._analysis_response(year, month)

    @action(detail=True, methods=["get"])
    def analysis(self, request, pk=None):
        budget = self.get_object()
        result = analyse_budget(request.user, budget)
        return Response(self._with_items(result, budget))

    def _analysis_response(self, year: int, month: int) -> Response:
        budget = self._get_or_none(year, month)
        if budget is None:
            # Not an error: render the month with real actuals and a prompt to
            # create a budget.
            return Response(empty_analysis(self.request.user, year, month).to_dict())
        result = analyse_budget(self.request.user, budget)
        return Response(self._with_items(result, budget))

    def _with_items(self, analysis, budget: Budget) -> dict:
        """Attach serialized items so the client can edit the budget inline."""
        payload = analysis.to_dict()
        payload["items"] = BudgetItemSerializer(
            budget.items.select_related("category", "category__parent"), many=True
        ).data
        payload["note"] = budget.note
        payload["is_active"] = budget.is_active
        return payload

    @action(detail=False, methods=["get"])
    def performance(self, request):
        """Dedicated budget performance view (spec section 11).

        Returns per-category performance for a month, ordered by how much
        attention each category needs, with a summary roll-up by status.
        """
        year, month = self._resolve_month(request)
        budget = self._get_or_none(year, month)

        if budget is None:
            return Response(
                {
                    **empty_analysis(request.user, year, month).to_dict(),
                    "summary": {
                        "safe": 0,
                        "normal": 0,
                        "near_limit": 0,
                        "over": 0,
                        "total_categories": 0,
                    },
                    "top_spending": [],
                }
            )

        analysis = analyse_budget(request.user, budget)
        payload = self._with_items(analysis, budget)

        counts = {"safe": 0, "normal": 0, "near_limit": 0, "over": 0}
        for item in analysis.categories:
            counts[item.status] = counts.get(item.status, 0) + 1

        payload["summary"] = {**counts, "total_categories": len(analysis.categories)}

        # Largest actual spenders this month, regardless of whether they were
        # budgeted — answers "where did the money actually go?".
        start, end = jalali_month_bounds(year, month)
        spend_map = spent_by_category(request.user, start, end)

        categories = {
            c.pk: c
            for c in Category.objects.for_user(request.user).filter(pk__in=spend_map.keys())
        }

        top = []
        for category_id, (amount, count) in sorted(
            spend_map.items(), key=lambda kv: -kv[1][0]
        )[:10]:
            category = categories.get(category_id)
            if category is None:
                continue
            top.append(
                {
                    "category_id": category_id,
                    "category_name": category.name,
                    "category_full_path": category.full_path,
                    "category_icon": category.icon,
                    "category_color": category.color,
                    "spent": str(quantize_money(amount)),
                    "transaction_count": count,
                }
            )
        payload["top_spending"] = top

        return Response(payload)

    # ------------------------------------------------------------------
    # Monthly planning
    # ------------------------------------------------------------------

    @action(detail=False, methods=["post"])
    @db_transaction.atomic
    def plan(self, request):
        """Set the whole monthly plan in one request (spec section 12)."""
        serializer = MonthlyPlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        year, month = data["year"], data["month"]

        budget, created = Budget.objects.get_or_create(
            user=request.user, year=year, month=month
        )

        # Plan figures.
        budget.expected_income = quantize_money(data["expected_income"])
        budget.savings_target = quantize_money(data["savings_target"])
        budget.investment_target = quantize_money(data["investment_target"])
        budget.debt_payment_target = quantize_money(data["debt_payment_target"])
        budget.save(
            update_fields=[
                "expected_income",
                "savings_target",
                "investment_target",
                "debt_payment_target",
                "updated_at",
            ]
        )

        allocations = data.get("allocations") or []

        if data.get("replace_allocations"):
            budget.items.all().delete()

        if allocations:
            # Validate every category belongs to the user and is an expense
            # category before writing anything.
            category_ids = [entry["category_id"] for entry in allocations]
            valid = {
                c.pk: c
                for c in Category.objects.for_user(request.user).filter(
                    pk__in=category_ids, kind=CategoryKind.EXPENSE
                )
            }

            invalid = [cid for cid in category_ids if cid not in valid]
            if invalid:
                return Response(
                    {
                        "detail": "برخی دسته‌بندی‌های انتخابی معتبر نیستند.",
                        "errors": {"allocations": invalid},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            for entry in allocations:
                defaults = {
                    "amount": entry["amount"],
                    "note": entry["note"],
                }
                # Only touch the flag when the client actually stated it. The
                # serializer hands back None for "not mentioned", which is not
                # the same as False — writing False here would erase a line the
                # user had marked non-negotiable.
                if entry["is_essential"] is not None:
                    defaults["is_essential"] = entry["is_essential"]

                BudgetItem.objects.update_or_create(
                    budget=budget,
                    category=valid[entry["category_id"]],
                    defaults=defaults,
                )

        analysis = analyse_budget(request.user, budget)

        return Response(
            {
                "budget": BudgetSerializer(budget).data,
                "analysis": self._with_items(analysis, budget),
                "created": created,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"])
    def copy(self, request):
        """Copy a month's budget into another month.

        Saves re-entering an entire budget every month, which is the single
        biggest source of drop-off in budgeting apps.
        """
        from_year = int(request.data.get("from_year", 0) or 0)
        from_month = int(request.data.get("from_month", 0) or 0)
        to_year = int(request.data.get("to_year", 0) or 0)
        to_month = int(request.data.get("to_month", 0) or 0)

        if not all([from_year, from_month, to_year, to_month]):
            return Response(
                {"detail": "ماه مبدأ و مقصد را مشخص کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        source = self._get_or_none(from_year, from_month)
        if source is None:
            return Response(
                {"detail": "بودجه ماه مبدأ پیدا نشد."}, status=status.HTTP_404_NOT_FOUND
            )

        if Budget.objects.for_user(request.user).filter(year=to_year, month=to_month).exists():
            return Response(
                {"detail": "برای ماه مقصد قبلاً بودجه ساخته شده است."},
                status=status.HTTP_409_CONFLICT,
            )

        with db_transaction.atomic():
            target = Budget.objects.create(
                user=request.user,
                year=to_year,
                month=to_month,
                expected_income=source.expected_income,
                savings_target=source.savings_target,
                investment_target=source.investment_target,
                debt_payment_target=source.debt_payment_target,
                note=source.note,
            )
            BudgetItem.objects.bulk_create(
                [
                    BudgetItem(
                        budget=target,
                        category=item.category,
                        amount=item.amount,
                        is_essential=item.is_essential,
                        note=item.note,
                    )
                    for item in source.items.all()
                ]
            )

        analysis = analyse_budget(request.user, target)
        return Response(
            {
                "budget": BudgetSerializer(target).data,
                "analysis": self._with_items(analysis, target),
            },
            status=status.HTTP_201_CREATED,
        )

    # ------------------------------------------------------------------
    # Budget items
    # ------------------------------------------------------------------

    @action(detail=True, methods=["get", "post"])
    def items(self, request, pk=None):
        """List or add budget lines for a budget."""
        budget = self.get_object()

        if request.method == "GET":
            return Response(
                BudgetItemSerializer(
                    budget.items.select_related("category", "category__parent"), many=True
                ).data
            )

        serializer = BudgetItemWriteSerializer(
            data=request.data, context={"request": request, "budget": budget}
        )
        serializer.is_valid(raise_exception=True)
        item = serializer.save()

        analysis = analyse_budget(request.user, budget)
        matching = next(
            (c for c in analysis.categories if c.category_id == item.category_id), None
        )

        return Response(
            {
                "item": BudgetItemSerializer(item).data,
                "analysis": matching.to_dict() if matching else None,
                "totals": analysis.to_dict()["totals"],
            },
            status=status.HTTP_201_CREATED,
        )


class BudgetItemViewSet(viewsets.ModelViewSet):
    """Direct manipulation of budget lines by id.

    Needed so the client can edit or delete a single line without knowing which
    budget it belongs to.

    update: PATCH  /api/budget-items/{id}/
    delete: DELETE /api/budget-items/{id}/
    """

    permission_classes = [IsOwner]
    serializer_class = BudgetItemWriteSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        # Scoped through the parent budget's user.
        return BudgetItem.objects.filter(
            budget__user=self.request.user
        ).select_related("category", "budget")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        instance = getattr(self, "_item_for_context", None)
        if instance is not None:
            context["budget"] = instance.budget
        elif self.kwargs.get("pk"):
            item = self.get_queryset().filter(pk=self.kwargs["pk"]).first()
            if item:
                context["budget"] = item.budget
        return context

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        self._item_for_context = instance

        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()

        analysis = analyse_budget(request.user, item.budget)
        matching = next(
            (c for c in analysis.categories if c.category_id == item.category_id), None
        )

        return Response(
            {
                "item": BudgetItemSerializer(item).data,
                "analysis": matching.to_dict() if matching else None,
                "totals": analysis.to_dict()["totals"],
            }
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        budget = instance.budget
        instance.delete()

        analysis = analyse_budget(request.user, budget)
        return Response({"totals": analysis.to_dict()["totals"]}, status=status.HTTP_200_OK)


class BudgetOverviewView(APIView):
    """Month-by-month budget totals for trend charts and the reports page.

    GET /api/budgets/overview/?months=6

    Returns one entry per Jalali month with budgeted, spent and the derived
    percentage, so the client can chart adherence over time without N requests.
    """

    permission_classes = [IsOwner]

    def get(self, request):
        from apps.core.jalali import add_jalali_months

        try:
            count = min(int(request.query_params.get("months", 6)), 24)
        except (TypeError, ValueError):
            count = 6

        year, month = current_jalali_month()
        months: list[dict] = []

        for offset in range(count - 1, -1, -1):
            y, m = add_jalali_months(year, month, -offset)

            budget = Budget.objects.for_user(request.user).filter(year=y, month=m).first()
            start, end = jalali_month_bounds(y, m)
            progress = month_progress(y, m)

            if budget is not None:
                analysis = analyse_budget(request.user, budget)
                budgeted = analysis.total_budgeted
                spent = analysis.total_spent
                income = analysis.actual_income
                expense = analysis.actual_expense
            else:
                empty = empty_analysis(request.user, y, m)
                budgeted = Decimal("0.00")
                spent = empty.total_spent
                income = empty.actual_income
                expense = empty.actual_expense

            months.append(
                {
                    "year": y,
                    "month": m,
                    "key": f"{y}-{m:02d}",
                    "label": to_persian_digits(f"{m:02d}/{y}"),
                    "days_in_month": progress["days_in_month"],
                    "has_budget": budget is not None,
                    "budgeted": str(quantize_money(budgeted)),
                    "spent": str(quantize_money(spent)),
                    "actual_income": str(quantize_money(income)),
                    "actual_expense": str(quantize_money(expense)),
                    "net": str(quantize_money(income - expense)),
                    "consumed_percent": str(
                        quantize_money(
                            (spent / budgeted * 100) if budgeted > 0 else Decimal("0")
                        )
                    ),
                }
            )

        return Response({"months": months})
