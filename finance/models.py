"""Expenses for the Profit & Loss overview. Sales come from paid POS orders."""
from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class Expense(models.Model):
    class Category(models.TextChoices):
        FOOD = "food", "Food purchases"
        DRINKS = "drinks", "Drink purchases"
        WAGES = "wages", "Wages & salaries"
        RENT = "rent", "Rent"
        UTILITIES = "utilities", "Water, electricity & internet"
        MAINTENANCE = "maintenance", "Maintenance & repairs"
        MARKETING = "marketing", "Marketing"
        FEES = "fees", "Bank & card fees"
        TAXES = "taxes", "Taxes & licences"
        OTHER = "other", "Other"

    class Method(models.TextChoices):
        BANK = "bank", "Bank transfer"
        CASH = "cash", "Cash"
        CARD = "card", "Card"

    date = models.DateField(default=timezone.localdate, db_index=True)
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.FOOD)
    description = models.CharField(max_length=200)
    supplier = models.CharField(max_length=120, blank=True)
    invoice_number = models.CharField(max_length=60, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Total paid, including OB")
    tax_amount = models.DecimalField("OB included", max_digits=12, decimal_places=2, default=0)
    method = models.CharField(max_length=5, choices=Method.choices, default=Method.BANK)
    receipt = models.FileField(upload_to="private/receipts/%Y/%m/", blank=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return self.description

    @property
    def net(self):
        return self.amount - self.tax_amount
