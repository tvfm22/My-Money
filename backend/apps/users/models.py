"""Custom user model.

A custom user is defined from day one because swapping it after migrations
exist is painful. Even though this app needs few extra fields today, having
the hook in place is cheap insurance.

Financial isolation
-------------------
`User` is the root of every ownership chain. Every financial model below it
carries a non-nullable `user` ForeignKey, so "a user can only see their own
data" is enforced structurally, not by convention.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """Manager for the email-based user model."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("ایمیل الزامی است.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("مدیر کل باید is_staff=True باشد.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("مدیر کل باید is_superuser=True باشد.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Application user, identified by email address.

    Email is the login identifier rather than a username: it is memorable, and
    it avoids asking Persian-speaking users to invent a Latin username.
    """

    email = models.EmailField("ایمیل", unique=True, db_index=True)

    first_name = models.CharField("نام", max_length=60, blank=True)
    last_name = models.CharField("نام خانوادگی", max_length=60, blank=True)

    # Free-text display name so the UI can greet the user naturally
    # ("سلام رضا") without guessing how first/last should be combined.
    display_name = models.CharField("نام نمایشی", max_length=80, blank=True)

    is_active = models.BooleanField("فعال", default=True)
    is_staff = models.BooleanField("دسترسی مدیریت", default=False)

    date_joined = models.DateTimeField("تاریخ عضویت", default=timezone.now)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = "کاربر"
        verbose_name_plural = "کاربران"
        ordering = ("-date_joined",)

    def __str__(self) -> str:
        return self.email

    @property
    def full_name(self) -> str:
        """Best available human-readable name, in Persian-appropriate order."""
        if self.display_name:
            return self.display_name
        combined = f"{self.first_name} {self.last_name}".strip()
        return combined or self.email.split("@")[0]

    def get_short_name(self) -> str:
        return self.first_name or self.full_name

    def get_full_name(self) -> str:
        return self.full_name
