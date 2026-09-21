"""Project test runner.

Why this exists
---------------
Django's stock discovery walks every package and imports each ``tests`` module.
Because this project has one ``tests`` subpackage per app
(``apps.budgets.tests``, ``apps.debts.tests``, ...), ``unittest``'s loader hits
a basename collision and aborts with::

    ImportError: 'tests' module incorrectly imported from
    'D:\\My-Money\\backend\\apps\\debts\\tests'.
    Expected 'D:\\My-Money\\backend\\apps\\debts'.

The usual workarounds are to run one app at a time, or to rename every
``tests`` directory — both of which are friction the next person would have to
rediscover. Instead this runner discovers the app test modules itself and
builds the suite from explicit dotted labels, so ``python manage.py test``
works as a single command and the conventional ``apps/<app>/tests/`` layout is
preserved.

``python manage.py test apps.budgets`` and ``... apps.budgets.tests`` both keep
working exactly as before.
"""

from __future__ import annotations

import importlib
import pkgutil
import unittest

from django.test.runner import DiscoverRunner


class AppAwareDiscoverRunner(DiscoverRunner):
    """Discover tests without tripping over repeated ``tests`` package names."""

    def build_suite(self, test_labels=None, **kwargs):
        if not test_labels:
            # No labels given: enumerate the test modules ourselves rather than
            # letting stock discovery scan every package (which is what hits
            # the basename collision).
            test_labels = self._discover_test_labels()
            if not test_labels:
                return super().build_suite(None, **kwargs)

        normalized = [self._normalize_label(label) for label in test_labels]

        # Build one suite per label and concatenate. Each label is an explicit
        # dotted path to a module, so the loader never resolves a bare `tests`
        # package under more than one parent.
        combined = unittest.TestSuite()
        for label in normalized:
            combined.addTests(super().build_suite([label], **kwargs))
        return combined

    def _discover_test_labels(self) -> list[str]:
        """Dotted paths to every test module under ``apps.*``."""
        labels: list[str] = []

        import apps

        for app_info in sorted(
            pkgutil.iter_modules(apps.__path__), key=lambda info: info.name
        ):
            app_name = app_info.name
            full_app = f"apps.{app_name}"
            try:
                app_module = importlib.import_module(full_app)
            except ImportError:
                continue

            tests_package_name = f"{full_app}.tests"
            try:
                tests_module = importlib.import_module(tests_package_name)
            except ImportError:
                continue

            if not hasattr(app_module, "tests"):
                continue

            # A `tests` entry can be an empty module rather than a package (no
            # __path__), in which case there is nothing to walk.
            tests_path = getattr(tests_module, "__path__", None)
            if tests_path is None:
                continue

            # Gather every module inside the tests package (test_*.py and any
            # subpackages), so adding a new test file needs no registration.
            for module_info in pkgutil.walk_packages(
                tests_path, prefix=f"{tests_package_name}."
            ):
                if module_info.name.rsplit(".", 1)[-1].startswith("test_"):
                    labels.append(module_info.name)

        return labels

    @staticmethod
    def _normalize_label(label: str) -> str:
        """Re-root ``<pkg>`` at ``<pkg>.tests`` when that package has tests.

        ``apps.debts`` -> ``apps.debts.tests`` so discovery starts inside the
        app's own tests directory rather than scanning from the app root.
        Labels that already name a module are left untouched.
        """
        try:
            module = importlib.import_module(label)
        except ImportError:
            return label

        tests_module_name = f"{label}.tests"
        try:
            importlib.import_module(tests_module_name)
        except ImportError:
            return label

        if hasattr(module, "tests"):
            return tests_module_name
        return label
