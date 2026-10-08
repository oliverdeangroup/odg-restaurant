from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .i18n import _
from .models import Role, SystemSettings, User


class StyledMixin:
    """Adds dashboard CSS classes and HTML5 input types to every field."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            w = field.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs.setdefault("class", "chk")
                continue
            if isinstance(w, forms.DateInput):
                w.input_type = "date"
                w.format = "%Y-%m-%d"
            if isinstance(w, forms.TimeInput):
                w.input_type = "time"
                w.format = "%H:%M"
            if isinstance(w, forms.DateTimeInput):
                w.input_type = "datetime-local"
                w.format = "%Y-%m-%dT%H:%M"
            if isinstance(w, forms.Textarea):
                w.attrs.setdefault("rows", 3)
            w.attrs["class"] = (w.attrs.get("class", "") + " inp").strip()


PERSON_FIELDS = ["first_name", "last_name", "email", "phone", "address", "birthdate", "id_number", "photo"]


class UserForm(StyledMixin, forms.ModelForm):
    """Contact details shared by every user type + login details."""

    password = forms.CharField(
        label="Password", required=False, widget=forms.PasswordInput(render_value=False),
        help_text="Leave empty to keep the current password (new users get a generated one).",
    )
    role_choices = ()

    class Meta:
        model = User
        fields = ["role"] + PERSON_FIELDS + ["username", "language", "is_active"]
        widgets = {"birthdate": forms.DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ("first_name", "last_name"):
            self.fields[f].required = True
        if self.role_choices:
            self.fields["role"].choices = [(r.value, r.label) for r in self.role_choices]
        else:
            self.fields.pop("role", None)
        self.fields["language"].required = False

    def clean_password(self):
        pw = self.cleaned_data.get("password")
        if pw:
            if len(pw) < SystemSettings.load().password_min_length:
                raise ValidationError(_("The password is too short."))
            validate_password(pw, self.instance)
        return pw

    def save(self, commit=True):
        user = super().save(commit=False)
        pw = self.cleaned_data.get("password")
        if pw:
            user.set_password(pw)
        elif not user.pk:
            user.set_unusable_password()
        if commit:
            user.save()
        return user


class SystemUserForm(UserForm):
    role_choices = (Role.ADMIN, Role.MODERATOR)


class StaffUserForm(UserForm):
    role_choices = (Role.WAITER, Role.BARTENDER, Role.CHEF, Role.MANAGER, Role.OWNER)

    def clean_role(self):
        role = self.cleaned_data["role"]
        s = SystemSettings.load()
        limits = {Role.OWNER: 1, Role.MANAGER: s.max_managers}
        if role in limits:
            others = User.objects.filter(role=role, is_active=True).exclude(pk=self.instance.pk).count()
            if others >= limits[role]:
                raise ValidationError(
                    _("The maximum number of {0} accounts ({1}) is reached.").format(_(Role(role).label).lower(), limits[role])
                    + ("" if role == Role.OWNER else " " + _("You can change the limit in Settings."))
                )
        return role


class SystemSettingsForm(StyledMixin, forms.ModelForm):
    smtp_password = forms.CharField(
        label="SMTP password", required=False, widget=forms.PasswordInput,
        help_text="Leave empty to keep the saved password.",
    )

    class Meta:
        model = SystemSettings
        fields = "__all__"

    def clean_smtp_password(self):
        return self.cleaned_data.get("smtp_password") or self.instance.smtp_password


class ProfileForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = PERSON_FIELDS + ["language", "bio"]
        widgets = {"birthdate": forms.DateInput()}


class UpdateUploadForm(forms.Form):
    package = forms.FileField(label="Update package (.zip)")
    allow_destructive = forms.BooleanField(
        label="I understand this update removes database fields/tables (a full backup is made first)", required=False
    )
