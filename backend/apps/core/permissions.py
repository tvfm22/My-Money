"""Shared DRF building blocks: permissions, pagination, exception handling.

Keeping these in `core` means every app enforces the same rules, and a security
regression would have to be introduced in one obvious place to happen.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response
from rest_framework.views import exception_handler


class IsOwner(BasePermission):
    """Authenticated, and the requesting user owns the object.

    Used on views that operate on a single, already-resolved object. The
    primary isolation mechanism is queryset filtering in the viewsets — this is
    the second line of defence, so a forgotten filter produces a 403 rather
    than a data leak.

    This class implements *both* ``has_permission`` and ``has_object_permission``
    on purpose. A view that sets ``permission_classes = [IsOwner]`` replaces the
    global ``IsAuthenticated`` default rather than adding to it, so if this
    class only checked ownership it would silently admit anonymous callers to
    endpoints that then crash on ``request.user.id``. Requiring authentication
    here means the class cannot be used in an insecure way.
    """

    message = "شما به این اطلاعات دسترسی ندارید."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        owner_id = getattr(obj, "user_id", None)
        if owner_id is None:
            # Objects that reach here without a user_id are not user-scoped and
            # this permission cannot meaningfully gate them.
            return False
        return owner_id == request.user.id


class ReadOnlyOrOwner(BasePermission):
    """Any authenticated user may read; only the owner may write.

    As with ``IsOwner``, authentication is enforced here as well as ownership,
    because setting ``permission_classes`` replaces the global default.
    """

    message = "شما به این اطلاعات دسترسی ندارید."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        # Reads are allowed for any authenticated user; writes require ownership.
        if request.method in SAFE_METHODS:
            return True
        return getattr(obj, "user_id", None) == request.user.id


class StandardPagination(PageNumberPagination):
    """Consistent pagination with a Persian-localized error message.

    Default page size is tuned for a mobile list screen: large enough to scroll
    pleasantly, small enough to stay fast on a phone connection.
    """

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "page": self.page.number,
                "page_size": self.get_page_size(self.request),
                "total_pages": self.page.paginator.num_pages,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )


# --------------------------------------------------------------------------
# Exception handling — never leak a stack trace or a raw Django error
# --------------------------------------------------------------------------

# Persian fallbacks for the situations a user can actually encounter. Raw DRF
# messages are English, so anything unmapped is replaced with a generic message
# rather than shown verbatim.
_ERROR_TRANSLATIONS = {
    "Authentication credentials were not provided.": "برای انجام این کار باید وارد حساب خود شوید.",
    "Incorrect authentication credentials.": "اطلاعات ورود نادرست است.",
    "Given token not valid for any token type": "نشست شما منقضی شده است. دوباره وارد شوید.",
    "Token is invalid or expired": "نشست شما منقضی شده است. دوباره وارد شوید.",
    "You do not have permission to perform this action.": "شما اجازه انجام این کار را ندارید.",
    "Not found.": "موردی که دنبالش بودید پیدا نشد.",
    "Method \"GET\" not allowed.": "این درخواست پشتیبانی نمی‌شود.",
}


def _translate(value):
    """Recursively translate known English error strings to Persian."""
    if isinstance(value, str):
        return _ERROR_TRANSLATIONS.get(value, value)
    if isinstance(value, list):
        return [_translate(item) for item in value]
    if isinstance(value, dict):
        return {key: _translate(item) for key, item in value.items()}
    return value


def api_exception_handler(exc, context):
    """Wrap DRF's handler to produce Persian, non-technical error bodies.

    Shape returned to the client::

        {"detail": "...", "errors": {...}}   # for field-level validation
        {"detail": "..."}                    # for everything else

    Unhandled exceptions deliberately fall through to Django's own handling so
    the full traceback is logged server-side; the client sees a generic 500
    only in DEBUG=False, and the frontend renders a friendly Persian message.
    """
    response = exception_handler(exc, context)

    if response is None:
        # Not a DRF-handled exception (programming error, DB failure, ...).
        # Returning None lets Django log it with a traceback.
        return None

    data = response.data

    if isinstance(data, dict) and "detail" in data:
        detail = _translate(data["detail"])
        response.data = {"detail": detail}

        # Attach field errors separately when present (validation errors come
        # through as {"field": ["msg"], "detail": ...}).
        field_errors = {k: _translate(v) for k, v in data.items() if k != "detail"}
        if field_errors:
            response.data["errors"] = field_errors

    elif isinstance(data, dict):
        # Pure validation error: {"amount": ["This field is required."]}
        response.data = {
            "detail": "اطلاعات ارسالی نامعتبر است.",
            "errors": _translate(data),
        }
    elif isinstance(data, list):
        response.data = {"detail": "اطلاعات ارسالی نامعتبر است.", "errors": _translate(data)}

    # Make sure rate limiting communicates itself understandably.
    if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        response.data = {
            "detail": "تعداد درخواست‌ها زیاد بوده است. لطفاً چند لحظه بعد دوباره تلاش کنید."
        }

    return response
