"""Transaction filtering.

The filter set is deliberately rich, because "find that one payment" is the
single most common thing a user does in a finance app, and every extra round of
narrowing that the backend supports is a round the user does not have to do by
scrolling.

Jalali-aware date filtering
---------------------------
Filters accept Jalali dates (`date_from=۱۴۰۵/۰۶/۰۱`) as well as ISO Gregorian
ones, and also accept a `month=1405-06` shortcut, because "this month" is how
users actually think about their money. Conversion happens here so the database
only ever sees Gregorian dates.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

import django_filters as filters
from django.db.models import Q

from apps.core.jalali import jalali_month_bounds, to_latin_digits

from .models import SpendingType, Transaction, TransactionType


def _parse_flexible_date(value: str) -> dt.date | None:
    """Parse either an ISO date or a Jalali date into a Gregorian `date`."""
    if not value:
        return None

    raw = to_latin_digits(str(value)).strip().replace("-", "/").replace(".", "/")

    # YYYY/MM/DD
    if len(raw.split("/")) == 3:
        try:
            parts = raw.split("/")
            if len(parts[0]) >= 4:
                year = int(parts[0])
                if year < 1700:
                    # Looks like a Jalali year.
                    from apps.core.jalali import parse_jalali

                    return parse_jalali(raw)
                return dt.date(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, TypeError):
            return None

    # ISO with dashes already normalized above; try stdlib as a fallback.
    try:
        return dt.date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


class TransactionFilter(filters.FilterSet):
    """Filters for the transaction list endpoint."""

    # --- Dates -------------------------------------------------------------
    date_from = filters.CharFilter(method="filter_date_from", label="از تاریخ")
    date_to = filters.CharFilter(method="filter_date_to", label="تا تاریخ")

    # Convenience: ?month=1405-06 or ?month=1405/06
    month = filters.CharFilter(method="filter_month", label="ماه")
    year = filters.CharFilter(method="filter_year", label="سال")

    # Relative shortcuts that save the client from doing date math.
    period = filters.ChoiceFilter(
        method="filter_period",
        choices=[
            ("today", "امروز"),
            ("yesterday", "دیروز"),
            ("this_week", "این هفته"),
            ("this_month", "این ماه"),
            ("last_month", "ماه گذشته"),
            ("last_7_days", "۷ روز گذشته"),
            ("last_30_days", "۳۰ روز گذشته"),
            ("this_year", "امسال"),
        ],
        label="بازه",
    )

    # --- Category ---------------------------------------------------------
    category = filters.NumberFilter(field_name="category_id")
    # Includes subcategories of the given category — this is what a user means
    # when they filter by "خوراک".
    category_group = filters.NumberFilter(method="filter_category_group")

    # --- Direction / account ---------------------------------------------
    transaction_type = filters.ChoiceFilter(
        choices=TransactionType.choices, field_name="transaction_type"
    )
    account = filters.NumberFilter(field_name="account_id")

    # --- Spending classification -----------------------------------------
    # `?spending_type=essential` narrows to one bucket. `?spending_type=unclassified`
    # is the odd one out: it selects expenses the user never classified, which is
    # the only way to reach rows written before the feature existed.
    spending_type = filters.CharFilter(method="filter_spending_type")

    # --- Amount range -----------------------------------------------------
    amount_min = filters.CharFilter(method="filter_amount_min")
    amount_max = filters.CharFilter(method="filter_amount_max")

    # --- Tags -------------------------------------------------------------
    tag = filters.NumberFilter(field_name="tags__id")
    tag_name = filters.CharFilter(field_name="tags__name", lookup_expr="iexact")

    class Meta:
        model = Transaction
        fields = [
            "date_from",
            "date_to",
            "month",
            "year",
            "period",
            "category",
            "category_group",
            "transaction_type",
            "account",
            "spending_type",
            "amount_min",
            "amount_max",
            "tag",
            "tag_name",
        ]

    # ------------------------------------------------------------------
    # Date filters
    # ------------------------------------------------------------------

    def filter_date_from(self, queryset, name, value):
        parsed = _parse_flexible_date(value)
        if parsed is None:
            return queryset
        return queryset.filter(occurred_on__gte=parsed)

    def filter_date_to(self, queryset, name, value):
        parsed = _parse_flexible_date(value)
        if parsed is None:
            return queryset
        return queryset.filter(occurred_on__lte=parsed)

    def filter_month(self, queryset, name, value):
        """?month=1405-06 filters to that entire Jalali month."""
        raw = to_latin_digits(str(value)).replace("-", "/")
        parts = raw.split("/")
        if len(parts) != 2:
            return queryset
        try:
            year, month = int(parts[0]), int(parts[1])
        except ValueError:
            return queryset
        if not (1 <= month <= 12):
            return queryset

        first, last = jalali_month_bounds(year, month)
        return queryset.filter(occurred_on__gte=first, occurred_on__lte=last)

    def filter_year(self, queryset, name, value):
        raw = to_latin_digits(str(value))
        try:
            year = int(raw)
        except ValueError:
            return queryset
        first, _ = jalali_month_bounds(year, 1)
        _, last = jalali_month_bounds(year, 12)
        return queryset.filter(occurred_on__gte=first, occurred_on__lte=last)

    def filter_period(self, queryset, name, value):
        from apps.core.jalali import current_jalali_month

        today = dt.date.today()

        if value == "today":
            return queryset.filter(occurred_on=today)
        if value == "yesterday":
            return queryset.filter(occurred_on=today - dt.timedelta(days=1))
        if value == "this_week":
            # Persian week starts Saturday.
            from apps.core.jalali import jalali_weekday_index

            days_since_saturday = jalali_weekday_index(today)
            start = today - dt.timedelta(days=days_since_saturday)
            return queryset.filter(occurred_on__gte=start, occurred_on__lte=today)
        if value == "last_7_days":
            return queryset.filter(occurred_on__gte=today - dt.timedelta(days=6))
        if value == "last_30_days":
            return queryset.filter(occurred_on__gte=today - dt.timedelta(days=29))
        if value == "this_month":
            year, month = current_jalali_month(today)
            first, last = jalali_month_bounds(year, month)
            return queryset.filter(occurred_on__gte=first, occurred_on__lte=last)
        if value == "last_month":
            year, month = current_jalali_month(today)
            if month == 1:
                year, month = year - 1, 12
            else:
                month -= 1
            first, last = jalali_month_bounds(year, month)
            return queryset.filter(occurred_on__gte=first, occurred_on__lte=last)
        if value == "this_year":
            year, _ = current_jalali_month(today)
            first, _ = jalali_month_bounds(year, 1)
            _, last = jalali_month_bounds(year, 12)
            return queryset.filter(occurred_on__gte=first, occurred_on__lte=last)

        return queryset

    # ------------------------------------------------------------------
    # Category / amount filters
    # ------------------------------------------------------------------

    def filter_category_group(self, queryset, name, value):
        """Match a category and all of its direct children."""
        from apps.categories.models import Category

        request = self.request
        try:
            category = Category.objects.get(pk=value, user=request.user)
        except Category.DoesNotExist:
            return queryset.none()

        child_ids = list(category.children.values_list("pk", flat=True))
        return queryset.filter(category_id__in=[category.pk, *child_ids])

    # ------------------------------------------------------------------
    # Spending classification
    # ------------------------------------------------------------------

    def filter_spending_type(self, queryset, name, value):
        """Narrow to one classification, or to the unclassified remainder.

        An unknown value filters to nothing rather than being ignored. A filter
        that silently falls back to "everything" looks like a broken UI, not
        like a typo, and that is the more expensive failure of the two.
        """
        raw = to_latin_digits(str(value)).strip().lower()

        if raw in ("", "all", "همه"):
            return queryset

        if raw in ("unclassified", "none", "دسته‌بندی‌نشده"):
            return queryset.filter(
                transaction_type=TransactionType.EXPENSE, spending_type=""
            )

        if raw not in SpendingType.values:
            return queryset.none()

        # A classification only ever describes an expense, so pin the direction
        # too — otherwise `?spending_type=essential` would silently return
        # income rows that happen to carry a stale value.
        return queryset.filter(
            transaction_type=TransactionType.EXPENSE, spending_type=raw
        )

    def _parse_amount(self, value) -> Decimal | None:
        if value in (None, ""):
            return None
        # Accept '1,000,000', '۱۰۰۰۰۰۰' and plain digits.
        cleaned = to_latin_digits(str(value)).replace(",", "").replace("٬", "").strip()
        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None

    def filter_amount_min(self, queryset, name, value):
        amount = self._parse_amount(value)
        if amount is None:
            return queryset
        return queryset.filter(amount__gte=amount)

    def filter_amount_max(self, queryset, name, value):
        amount = self._parse_amount(value)
        if amount is None:
            return queryset
        return queryset.filter(amount__lte=amount)
