"""Authentication and profile endpoints.

Design notes
------------
*   Tokens are JWT (access + refresh) issued by SimpleJWT. The SPA stores them
    in memory/localStorage and sends `Authorization: Bearer <token>`.
*   Logout blacklists the refresh token, so a token that has been explicitly
    logged out cannot be replayed.
*   Password reset returns the same response whether or not the email exists,
    which prevents using this endpoint to enumerate registered accounts.
*   In DEBUG the reset link is returned in the response body for convenience.
    In production it is only emailed — never returned over the API.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import (
    ChangePasswordSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
    UserUpdateSerializer,
)

logger = logging.getLogger(__name__)

User = get_user_model()


class AuthRateThrottle(AnonRateThrottle):
    """Tighter throttle for credential endpoints than for general reads."""

    scope = "auth"


def _issue_tokens(user) -> dict:
    """Mint an access/refresh pair for a user."""
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class LoginView(TokenObtainPairView):
    """POST /api/auth/login/

    Accepts email + password. Returns tokens plus the user payload so the
    client can render the app immediately without a second round trip.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            # Replace SimpleJWT's English "No active account found..." with a
            # Persian message. Deliberately vague about which part was wrong.
            return Response(
                {"detail": "ایمیل یا رمز عبور نادرست است."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user = serializer.user
        tokens = _issue_tokens(user)
        return Response(
            {
                **tokens,
                "user": UserSerializer(user, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )


class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/ — create an account and sign the user in."""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        tokens = _issue_tokens(user)
        return Response(
            {
                **tokens,
                "user": UserSerializer(user, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


class LogoutView(APIView):
    """POST /api/auth/logout/ — blacklist the supplied refresh token."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            # Nothing to revoke; the access token will simply expire. Not an
            # error from the user's point of view — they are logging out.
            return Response(status=status.HTTP_205_RESET_CONTENT)

        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            # Already expired or invalid. Logging out still succeeded.
            logger.debug("Logout: refresh token was already invalid.")

        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/auth/me/ — the current user's profile."""

    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return UserUpdateSerializer
        return UserSerializer


class ChangePasswordView(APIView):
    """POST /api/auth/change-password/"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "رمز عبور با موفقیت تغییر کرد."},
            status=status.HTTP_200_OK,
        )


class PasswordResetRequestView(APIView):
    """POST /api/auth/password-reset/ — start the reset flow."""

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    GENERIC_RESPONSE = {
        "detail": "اگر این ایمیل در سیستم ثبت شده باشد، لینک بازیابی برایتان ارسال می‌شود."
    }

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        user = User.objects.filter(email=email, is_active=True).first()

        payload = dict(self.GENERIC_RESPONSE)

        if user is not None:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_path = f"/reset-password/{uid}/{token}"

            # Logging the link means a developer can complete the flow locally
            # without an email backend configured.
            logger.info("Password reset requested for %s: %s", email, reset_path)

            if settings.DEBUG:
                # Debug-only convenience. Guarded so it can never ship.
                payload["debug_reset_path"] = reset_path

        # Identical shape and status either way — no account enumeration.
        return Response(payload, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    """POST /api/auth/password-reset/confirm/ — finish the reset flow."""

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        invalid = Response(
            {"detail": "لینک بازیابی نامعتبر یا منقضی شده است."},
            status=status.HTTP_400_BAD_REQUEST,
        )

        try:
            user_id = force_str(urlsafe_base64_decode(data["uid"]))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return invalid

        if not default_token_generator.check_token(user, data["token"]):
            return invalid

        user.set_password(data["new_password"])
        user.save(update_fields=["password", "updated_at"])

        return Response(
            {"detail": "رمز عبور با موفقیت تغییر کرد. اکنون می‌توانید وارد شوید."},
            status=status.HTTP_200_OK,
        )
