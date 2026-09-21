"""Serializers for registration, authentication, and profile management."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

User = get_user_model()


def _run_password_validators(password: str, user=None) -> None:
    """Run Django's password validators and re-raise as a DRF error.

    Django's validators raise `django.core.exceptions.ValidationError` with
    English messages. We intercept them and map to Persian so the registration
    form never shows an untranslated string.
    """
    persian_messages = {
        "too_short": "رمز عبور باید حداقل ۸ کاراکتر باشد.",
        "too_common": "این رمز عبور بسیار رایج است. رمز دیگری انتخاب کنید.",
        "too_similar": "رمز عبور بیش از حد به اطلاعات حساب شما شبیه است.",
        "entirely_numeric": "رمز عبور نباید فقط عدد باشد.",
    }

    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        messages = []
        for message in exc.messages:
            mapped = None
            lowered = message.lower()
            if "at least 8 characters" in lowered or "too short" in lowered:
                mapped = persian_messages["too_short"]
            elif "too common" in lowered:
                mapped = persian_messages["too_common"]
            elif "too similar" in lowered:
                mapped = persian_messages["too_similar"]
            elif "entirely numeric" in lowered:
                mapped = persian_messages["entirely_numeric"]
            messages.append(mapped or "رمز عبور انتخابی قابل قبول نیست.")
        raise serializers.ValidationError(messages)


class UserSerializer(serializers.ModelSerializer):
    """Read serializer for the authenticated user's own profile."""

    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "display_name",
            "full_name",
            "date_joined",
        )
        read_only_fields = ("id", "email", "date_joined", "full_name")


class UserUpdateSerializer(serializers.ModelSerializer):
    """Write serializer for profile edits.

    Email is intentionally not editable here: changing the login identifier is
    a security-sensitive operation that should go through a verification flow,
    not a plain PATCH.
    """

    class Meta:
        model = User
        fields = ("first_name", "last_name", "display_name")

    def validate_first_name(self, value):
        return value.strip()

    def validate_last_name(self, value):
        return value.strip()

    def validate_display_name(self, value):
        return value.strip()


class RegisterSerializer(serializers.ModelSerializer):
    """Registration. Creates the user and their default categories."""

    password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={"input_type": "password"},
        error_messages={"min_length": "رمز عبور باید حداقل ۸ کاراکتر باشد."},
    )
    password_confirm = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )

    class Meta:
        model = User
        fields = ("email", "password", "password_confirm", "first_name", "last_name")

    def validate_email(self, value):
        email = value.lower().strip()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("این ایمیل قبلاً ثبت شده است.")
        return email

    def validate(self, attrs):
        if attrs.get("password") != attrs.get("password_confirm"):
            raise serializers.ValidationError(
                {"password_confirm": "رمز عبور و تکرار آن یکسان نیستند."}
            )
        # Validate against a throwaway user so similarity checks have context.
        provisional = User(
            email=attrs.get("email", ""),
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        _run_password_validators(attrs["password"], provisional)
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm", None)
        password = validated_data.pop("password")

        user = User.objects.create_user(password=password, **validated_data)

        # Seeding default categories here (rather than in a signal) keeps the
        # side effect visible at the one place users are created.
        from apps.categories.services import seed_default_categories

        seed_default_categories(user)
        return user


class ChangePasswordSerializer(serializers.Serializer):
    """Authenticated password change."""

    current_password = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )
    new_password = serializers.CharField(
        write_only=True, min_length=8, style={"input_type": "password"}
    )
    new_password_confirm = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("رمز عبور فعلی درست نیست.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "رمز عبور جدید و تکرار آن یکسان نیستند."}
            )
        if attrs["current_password"] == attrs["new_password"]:
            raise serializers.ValidationError(
                {"new_password": "رمز عبور جدید باید با رمز فعلی متفاوت باشد."}
            )
        _run_password_validators(attrs["new_password"], self.context["request"].user)
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    """Step 1 of password reset: request a reset for an email."""

    email = serializers.EmailField()

    def validate_email(self, value):
        return value.lower().strip()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Step 2 of password reset: supply uid/token and the new password."""

    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(
        write_only=True, min_length=8, style={"input_type": "password"}
    )
    new_password_confirm = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "رمز عبور جدید و تکرار آن یکسان نیستند."}
            )
        _run_password_validators(attrs["new_password"])
        return attrs
