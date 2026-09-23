"""Root URL configuration. All API routes are mounted under /api/."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health(request):
    """Lightweight liveness probe — no authentication, no database access."""
    return JsonResponse({"status": "ok", "app": "my-money"})


def index(request):
    """Explain what this port is.

    The backend serves only `/api/`. Opening the API host directly used to
    return a bare Django 404, which reads like a broken server rather than a
    wrong address. This points at the real entry point instead.
    """
    return JsonResponse(
        {
            "app": "my-money",
            "message": (
                "این آدرس API بک‌اند است. برای دیدن برنامه، آدرس فرانت‌اند را باز کنید."
            ),
            "api": "/api/",
            "health": "/api/health/",
            "web_app": "http://127.0.0.1:5173/",
            "demo_login": {"email": "demo@mymoney.ir", "password": "demo12345"},
        },
        json_dumps_params={"ensure_ascii": False, "indent": 2},
    )


api_patterns = [
    path("auth/", include("apps.users.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.categories.urls")),
    path("", include("apps.transactions.urls")),
    path("", include("apps.budgets.urls")),
    path("", include("apps.debts.urls")),
    path("", include("apps.assets.urls")),
    path("", include("apps.reports.urls")),
    path("", include("apps.insights.urls")),
    path("", include("apps.sms.urls")),
]

urlpatterns = [
    path("", index, name="index"),
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/", include((api_patterns, "api"))),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
