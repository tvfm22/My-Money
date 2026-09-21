"""Classify every expense as ضروری / انعطاف‌پذیر / هدر رفته.

The field is new, so existing rows have nothing to classify them. Rather than
leave every past expense unclassified — which would make the reports read as if
the user had spent nothing on essentials — the data step backfills from the one
signal that already exists: the budget plan. A category the user flagged as
essential when planning the month is a fair guess for the expenses filed under
it, and everything else defaults to flexible.

`wasted` is deliberately **not** backfilled. It is a judgement about a specific
purchase, and inventing it from a category would put a value in the user's
mouth that they never chose.
"""

from django.db import migrations, models


def backfill_spending_type(apps, schema_editor):
    Transaction = apps.get_model("transactions", "Transaction")
    BudgetItem = apps.get_model("budgets", "BudgetItem")

    expenses = Transaction.objects.filter(transaction_type="expense")

    essential_category_ids = list(
        BudgetItem.objects.filter(is_essential=True)
        .values_list("category_id", flat=True)
        .distinct()
    )

    if essential_category_ids:
        expenses.filter(category_id__in=essential_category_ids).update(
            spending_type="essential"
        )

    expenses.exclude(category_id__in=essential_category_ids).update(
        spending_type="flexible"
    )


def unclassify(apps, schema_editor):
    """Reversing the data step only clears what this migration set.

    The column is dropped by the `RemoveField` that follows, so there is
    nothing to restore — but leaving the values in place would make the
    reverse look like a no-op that silently kept the guesses.
    """
    Transaction = apps.get_model("transactions", "Transaction")
    Transaction.objects.update(spending_type="")


class Migration(migrations.Migration):

    dependencies = [
        ("budgets", "0001_initial"),
        ("transactions", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="spending_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("essential", "ضروری"),
                    ("flexible", "انعطاف‌پذیر"),
                    ("wasted", "هدر رفته"),
                ],
                default="",
                max_length=10,
                verbose_name="نوع هزینه",
            ),
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(
                fields=["user", "spending_type", "occurred_on"],
                name="tx_user_spend_date_idx",
            ),
        ),
        migrations.RunPython(backfill_spending_type, unclassify),
    ]
