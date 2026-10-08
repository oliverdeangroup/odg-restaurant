from django import forms

from core.forms import StyledMixin
from core.i18n import _

from .models import Category, Customer, PosSettings, Product, Reservation, Table


class CategoryForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "parent", "station", "order", "active", "show_on_website"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Category.objects.all()
        if self.instance.pk:
            # A category cannot be placed inside itself or one of its children.
            bad = {self.instance.pk}
            changed = True
            while changed:
                kids = set(Category.objects.filter(parent_id__in=bad).values_list("pk", flat=True)) - bad
                changed = bool(kids)
                bad |= kids
            qs = qs.exclude(pk__in=bad)
        self.fields["parent"].queryset = qs
        self.fields["parent"].label_from_instance = lambda c: c.path


class ProductForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "category", "price", "code", "description", "image", "station", "prep_minutes",
                  "options_text", "available", "active", "show_on_website", "order"]
        widgets = {"options_text": forms.Textarea(attrs={"rows": 3, "placeholder": "*Doneness: Rare | Medium rare | Medium | Well done\nSide: Fries | Rice | Salad"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.all()
        self.fields["category"].label_from_instance = lambda c: c.path
        self.fields["price"].widget.attrs.update({"step": "0.01", "min": "0"})


class CustomerForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["first_name", "last_name", "email", "phone", "whatsapp", "notes", "marketing"]

    def __init__(self, *args, require_email=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = require_email

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if email and Customer.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("A customer with this e-mail address already exists."))
        return email


class ReservationForm(StyledMixin, forms.ModelForm):
    date = forms.DateField(widget=forms.DateInput())
    time = forms.TimeField(widget=forms.TimeInput())

    class Meta:
        model = Reservation
        fields = ["guests", "table", "duration_minutes", "status", "source", "notes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["table"].queryset = Table.objects.filter(active=True)
        self.fields["table"].required = False
        self.fields["table"].empty_label = _("Choose automatically")
        self.fields["table"].label_from_instance = lambda t: f"#{t.number} · {t.seats} {_('seats')}" + (f" · {t.section}" if t.section else "")
        if self.instance.pk:
            from django.utils import timezone

            local = timezone.localtime(self.instance.start)
            self.fields["date"].initial = local.date()
            self.fields["time"].initial = local.time().replace(second=0, microsecond=0)


class PosSettingsForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = PosSettings
        fields = [
            "currency_code", "currency_symbol", "tax_name", "tax_rate", "prices_include_tax", "service_charge_percent",
            "tip_suggestions", "default_bill_format", "bill_prefix", "next_bill_number", "bill_header_text",
            "bill_footer_text", "crib_number", "kvk_number", "order_history_days", "manager_history_days",
            "live_refresh_seconds", "late_after_minutes", "sound_alerts", "floor_width", "floor_height", "grid_size",
        ]

    def clean_next_bill_number(self):
        n = self.cleaned_data["next_bill_number"]
        if self.instance.pk and n < self.instance.next_bill_number:
            raise forms.ValidationError(_("Bill numbers can only go up (no gaps or doubles are allowed)."))
        return n

    def clean_live_refresh_seconds(self):
        return min(max(self.cleaned_data["live_refresh_seconds"], 2), 30)


class ReservationSettingsForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = PosSettings
        fields = ["online_reservations", "slot_minutes", "dining_minutes", "min_hours_ahead", "max_days_ahead",
                  "max_guests_online", "auto_confirm", "no_show_minutes"]
