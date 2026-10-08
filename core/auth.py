from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

from .models import User


class UsernameOrEmailBackend(ModelBackend):
    """Log in with either the username or the e-mail address."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None
        user = User.objects.filter(Q(username__iexact=username) | Q(email__iexact=username)).order_by("id").first()
        if user is None:
            User().set_password(password)  # equalise timing
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
