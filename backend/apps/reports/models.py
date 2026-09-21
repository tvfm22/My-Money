"""The reports app is stateless.

Every figure it returns is derived from transactions, budgets, debts and assets
at request time. There is nothing to persist, so there are no models here —
reports cannot go stale or need a cache-invalidation strategy.
"""
