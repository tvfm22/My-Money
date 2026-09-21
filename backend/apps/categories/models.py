"""Expense and income categories.

Design
------
A single `Category` model serves both expense and income categories, separated
by `kind`. Two separate tables would duplicate every field, every serializer,
and every view, for no benefit — the only real difference is which transaction
direction can reference them.

Subcategories
-------------
Self-referential `parent` FK, one level deep. This is enforced in validation
rather than by schema so that the rule is expressed in one readable place and
can be relaxed later without a data migration.

Icons and colors
----------------
`icon` stores a Lucide icon name (e.g. ``"utensils"``) and `color` stores a
named design token from the frontend palette (e.g. ``"orange"``), not a raw hex
value. Storing tokens means a palette change updates every category at once,
and prevents a user picking a color that fails contrast in dark mode.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MinLengthValidator, RegexValidator
from django.db import models
from django.db.models import Q


class CategoryKind(models.TextChoices):
    EXPENSE = "expense", "هزینه"
    INCOME = "income", "درآمد"


# Design tokens the frontend palette exposes. Validated server-side so the
# database can never hold a token the UI does not know how to render.
CATEGORY_COLOR_CHOICES = [
    ("slate", "خاکستری"),
    ("red", "قرمز"),
    ("orange", "نارنجی"),
    ("amber", "کهربایی"),
    ("yellow", "زرد"),
    ("lime", "لیمویی"),
    ("green", "سبز"),
    ("teal", "فیروزه‌ای"),
    ("cyan", "آبی روشن"),
    ("blue", "آبی"),
    ("indigo", "نیلی"),
    ("violet", "بنفش"),
    ("purple", "ارغوانی"),
    ("pink", "صورتی"),
    ("rose", "گلبهی"),
]

# Lucide icon names that are valid for a category. Kept as an explicit list so
# a typo is a validation error rather than a silently blank icon in the UI.
CATEGORY_ICON_CHOICES = [
    # Food
    ("utensils", "غذا"),
    ("utensils-crossed", "رستوران"),
    ("coffee", "کافه"),
    ("pizza", "فست‌فود"),
    ("shopping-basket", "خرید مواد غذایی"),
    # Transport
    ("car", "خودرو"),
    ("bus", "اتوبوس"),
    ("plane", "هواپیما"),
    ("train", "قطار"),
    ("bike", "دوچرخه"),
    ("fuel", "سوخت"),
    ("taxi", "تاکسی"),
    # Shopping
    ("shopping-bag", "خرید"),
    ("shopping-cart", "سبد خرید"),
    ("shirt", "پوشاک"),
    ("footprints", "کفش"),
    ("gem", "زیورآلات"),
    # Home
    ("home", "خانه"),
    ("building", "ساختمان"),
    ("sofa", "مبلمان"),
    ("wrench", "تعمیرات"),
    ("zap", "برق"),
    ("droplet", "آب"),
    ("flame", "گاز"),
    ("wifi", "اینترنت"),
    ("phone", "تلفن"),
    ("receipt", "قبض"),
    # Health
    ("heart-pulse", "سلامت"),
    ("pill", "دارو"),
    ("stethoscope", "پزشک"),
    ("dumbbell", "ورزش"),
    ("activity", "فعالیت"),
    # Leisure
    ("gamepad-2", "بازی"),
    ("film", "فیلم"),
    ("music", "موسیقی"),
    ("ticket", "بلیت"),
    ("palette", "هنر"),
    # Learning
    ("book-open", "کتاب"),
    ("graduation-cap", "آموزش"),
    ("languages", "زبان"),
    ("monitor", "دوره آنلاین"),
    # Travel
    ("palm-tree", "سفر"),
    ("hotel", "هتل"),
    ("luggage", "چمدان"),
    ("map-pin", "مقصد"),
    # Subscriptions & services
    ("repeat", "اشتراک"),
    ("cloud", "سرویس ابری"),
    ("shield", "بیمه"),
    ("landmark", "بانک"),
    ("credit-card", "کارت"),
    # Family & personal
    ("users", "خانواده"),
    ("baby", "کودک"),
    ("scissors", "آرایشگاه"),
    ("sparkles", "مراقبت شخصی"),
    ("paw-print", "حیوان خانگی"),
    ("gift", "هدیه"),
    ("hand-heart", "کمک"),
    # Income
    ("wallet", "کیف پول"),
    ("briefcase", "حقوق"),
    ("trending-up", "سرمایه‌گذاری"),
    ("piggy-bank", "پس‌انداز"),
    ("coins", "درآمد متفرقه"),
    ("percent", "سود"),
    ("award", "پاداش"),
    ("hand-coins", "وام دریافتی"),
    # Generic
    ("tag", "عمومی"),
    ("circle-ellipsis", "سایر"),
    ("more-horizontal", "متفرقه"),
    ("star", "مهم"),
    ("help-circle", "نامشخص"),
]

_ICON_NAMES = {name for name, _ in CATEGORY_ICON_CHOICES}
_COLOR_NAMES = {name for name, _ in CATEGORY_COLOR_CHOICES}

hex_color_validator = RegexValidator(
    regex=r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$",
    message="کد رنگ باید در قالب #RRGGBB باشد.",
)


class CategoryQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(user=user)

    def expenses(self):
        return self.filter(kind=CategoryKind.EXPENSE)

    def incomes(self):
        return self.filter(kind=CategoryKind.INCOME)

    def top_level(self):
        return self.filter(parent__isnull=True)

    def with_relations(self):
        """Prefetch everything the list serializer touches."""
        return self.select_related("parent")


class Category(models.Model):
    """A user-defined expense or income category, optionally nested one level."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="categories",
        verbose_name="کاربر",
    )

    name = models.CharField(
        "نام",
        max_length=60,
        validators=[MinLengthValidator(1, "نام دسته‌بندی نمی‌تواند خالی باشد.")],
    )

    kind = models.CharField(
        "نوع",
        max_length=10,
        choices=CategoryKind.choices,
        default=CategoryKind.EXPENSE,
        db_index=True,
    )

    icon = models.CharField(
        "آیکون",
        max_length=40,
        default="circle-ellipsis",
        help_text="نام آیکون از کتابخانه Lucide",
    )

    # A design token, not a hex code. Validated against the known palette.
    color = models.CharField(
        "رنگ",
        max_length=20,
        choices=CATEGORY_COLOR_CHOICES,
        default="slate",
    )

    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="دسته والد",
    )

    # Categories created during registration. Protected from deletion so the
    # default set stays coherent, but otherwise fully editable.
    is_default = models.BooleanField("پیش‌فرض", default=False)

    # Lets a user hide a category from pickers without losing its history.
    is_active = models.BooleanField("فعال", default=True)

    sort_order = models.PositiveSmallIntegerField("ترتیب نمایش", default=100)

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    objects = CategoryQuerySet.as_manager()

    class Meta:
        verbose_name = "دسته‌بندی"
        verbose_name_plural = "دسته‌بندی‌ها"
        ordering = ("sort_order", "name")
        constraints = [
            # A user cannot have two categories with the same name and kind.
            # Enforced at the database level as well as in the serializer.
            models.UniqueConstraint(
                fields=["user", "name", "kind"],
                name="unique_category_name_per_user_kind",
            ),
            # A category cannot be its own parent.
            models.CheckConstraint(
                condition=~Q(pk=models.F("parent")),
                name="category_parent_not_self",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "kind", "is_active"], name="cat_user_kind_active_idx"),
            models.Index(fields=["user", "parent"], name="cat_user_parent_idx"),
        ]

    def __str__(self) -> str:
        if self.parent_id:
            return f"{self.parent.name} › {self.name}"
        return self.name

    @property
    def full_path(self) -> str:
        """'خوراک › رستوران' for display."""
        if self.parent_id and self.parent is not None:
            return f"{self.parent.name} › {self.name}"
        return self.name

    @property
    def is_subcategory(self) -> bool:
        return self.parent_id is not None

    @property
    def depth(self) -> int:
        """0 for a top-level category, 1 for a subcategory."""
        return 1 if self.parent_id else 0

    def icon_is_valid(self) -> bool:
        return self.icon in _ICON_NAMES
