"""Category domain logic: default seeding and hierarchy validation.

Kept out of views and serializers so the rules can be reused (e.g. by the
seeding command and by registration) and tested directly.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import CATEGORY_ICON_CHOICES, Category, CategoryKind

# ---------------------------------------------------------------------------
# The default category set.
#
# Each entry is (name, icon, color, [(subcategory_name, icon), ...]).
# Colors are assigned semantically rather than randomly: food is warm, transport
# is blue, health is red, income is green — so charts are readable before the
# user has customized anything.
# ---------------------------------------------------------------------------

DEFAULT_EXPENSE_CATEGORIES = [
    ("خوراک", "shopping-basket", "green", [
        ("میوه و سبزیجات", "shopping-basket"),
        ("نان و لبنیات", "shopping-basket"),
        ("گوشت و پروتئین", "shopping-basket"),
    ]),
    ("رستوران و کافه", "utensils-crossed", "orange", [
        ("رستوران", "utensils"),
        ("کافه", "coffee"),
        ("فست‌فود", "pizza"),
    ]),
    ("حمل‌ونقل", "bus", "blue", [
        ("تاکسی و اسنپ", "taxi"),
        ("سوخت", "fuel"),
        ("حمل‌ونقل عمومی", "bus"),
    ]),
    ("خرید", "shopping-bag", "purple", [
        ("لوازم خانه", "sofa"),
        ("لوازم دیجیتال", "monitor"),
    ]),
    ("پوشاک", "shirt", "pink", [
        ("لباس", "shirt"),
        ("کفش", "footprints"),
    ]),
    ("مسکن", "home", "indigo", [
        ("اجاره", "home"),
        ("شارژ ساختمان", "building"),
        ("تعمیرات", "wrench"),
    ]),
    ("قبض‌ها", "receipt", "cyan", [
        ("برق", "zap"),
        ("آب", "droplet"),
        ("گاز", "flame"),
        ("اینترنت", "wifi"),
        ("تلفن همراه", "phone"),
    ]),
    ("سلامت", "heart-pulse", "red", [
        ("دارو", "pill"),
        ("ویزیت پزشک", "stethoscope"),
    ]),
    ("سرگرمی", "gamepad-2", "violet", [
        ("بازی", "gamepad-2"),
        ("فیلم و سریال", "film"),
        ("موسیقی", "music"),
    ]),
    ("آموزش", "graduation-cap", "teal", [
        ("کتاب", "book-open"),
        ("دوره آموزشی", "monitor"),
    ]),
    ("سفر", "palm-tree", "amber", [
        ("بلیت", "ticket"),
        ("اقامت", "hotel"),
    ]),
    ("اشتراک‌ها", "repeat", "slate", [
        ("سرویس ابری", "cloud"),
    ]),
    ("خانواده", "users", "rose", [
        ("کودک", "baby"),
        ("هدیه", "gift"),
    ]),
    ("مراقبت شخصی", "sparkles", "pink", [
        ("آرایشگاه", "scissors"),
        ("ورزش", "dumbbell"),
    ]),
    ("سایر", "circle-ellipsis", "slate", []),
]

DEFAULT_INCOME_CATEGORIES = [
    ("حقوق", "briefcase", "green", []),
    ("درآمد آزاد", "wallet", "teal", []),
    ("سرمایه‌گذاری", "trending-up", "blue", []),
    ("هدیه دریافتی", "gift", "pink", []),
    ("سود بانکی", "percent", "cyan", []),
    ("سایر درآمدها", "coins", "slate", []),
]


@transaction.atomic
def seed_default_categories(user) -> list[Category]:
    """Create the default category tree for a new user.

    Idempotent: if the user already has default categories, nothing is created
    and the existing *top-level* set is returned. That makes it safe to call
    from registration and from any future "restore defaults" action.

    Returns the categories on the first run (parents, subcategories and income
    categories — 56 in total), or the existing top-level categories on
    subsequent runs.
    """
    existing = Category.objects.filter(user=user, is_default=True)
    if existing.exists():
        return list(existing.top_level())

    created: list[Category] = []

    for index, (name, icon, color, children) in enumerate(DEFAULT_EXPENSE_CATEGORIES):
        parent = Category.objects.create(
            user=user,
            name=name,
            kind=CategoryKind.EXPENSE,
            icon=icon,
            color=color,
            is_default=True,
            sort_order=index * 10,
        )
        created.append(parent)

        for child_index, (child_name, child_icon) in enumerate(children):
            created.append(
                Category.objects.create(
                    user=user,
                    name=child_name,
                    kind=CategoryKind.EXPENSE,
                    icon=child_icon,
                    # Subcategories inherit the parent's color so a chart
                    # grouping by parent stays visually coherent.
                    color=color,
                    parent=parent,
                    is_default=True,
                    sort_order=index * 10 + child_index + 1,
                )
            )

    for index, (name, icon, color, _children) in enumerate(DEFAULT_INCOME_CATEGORIES):
        created.append(
            Category.objects.create(
                user=user,
                name=name,
                kind=CategoryKind.INCOME,
                icon=icon,
                color=color,
                is_default=True,
                sort_order=index * 10,
            )
        )

    return created


def validate_hierarchy(category: Category) -> None:
    """Enforce the one-level nesting rule.

    Called from the serializer because it needs both the incoming `parent` and
    the instance being edited, which model-level `clean()` alone cannot fully
    express for a partial update.
    """
    parent = category.parent

    if parent is None:
        return

    if parent.pk == category.pk:
        raise ValidationError({"parent": "یک دسته‌بندی نمی‌تواند والد خودش باشد."})

    if parent.parent_id is not None:
        raise ValidationError(
            {"parent": "دسته‌بندی فقط تا یک سطح زیرمجموعه پشتیبانی می‌شود."}
        )

    if parent.kind != category.kind:
        raise ValidationError(
            {"parent": "نوع دسته‌بندی فرزند باید با نوع دسته والد یکسان باشد."}
        )

    if parent.user_id != category.user_id:
        raise ValidationError({"parent": "دسته‌بندی والد معتبر نیست."})

    # Prevent creating a cycle: a category that already has children cannot be
    # moved under something that is (transitively) its own descendant.
    if category.pk and Category.objects.filter(parent=category).exists():
        if parent.pk == category.pk:
            raise ValidationError(
                {"parent": "این دسته‌بندی زیرمجموعه دارد و نمی‌تواند جابه‌جا شود."}
            )


def category_descendants(category: Category) -> list[int]:
    """IDs of a category and its direct children (one level)."""
    ids = [category.pk]
    ids.extend(category.children.values_list("pk", flat=True))
    return ids


def valid_icon_names() -> set[str]:
    return {name for name, _ in CATEGORY_ICON_CHOICES}


def resolve_sort_order(user, kind: str, parent_id=None) -> int:
    """Suggest the next free sort order in a given bucket."""
    from django.db.models import Max

    aggregate = Category.objects.filter(
        user=user, kind=kind, parent_id=parent_id
    ).aggregate(top=Max("sort_order"))

    top = aggregate["top"]
    return (top + 10) if top is not None else 0
