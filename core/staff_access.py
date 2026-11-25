"""The staff boundary for Django-served CRM routes."""

from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden
from django.urls import reverse
from django.utils.cache import add_never_cache_headers
from django.utils.deprecation import MiddlewareMixin

from .property_writes import can_use_staff_card


READ_ONLY_PUBLIC = {"healthz", "export_cian", "export_domklik"}
SESSION_VIEWS = {"crm_staff_login", "crm_staff_logout"}


class StaffAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not can_use_staff_card(user):
            raise ValidationError("Эта учётная запись не имеет доступа к CRM.", code="not_staff")


class StaffAccessMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        request.crm_staff_login_required = settings.CRM_REQUIRE_STAFF_LOGIN
        if not settings.CRM_REQUIRE_STAFF_LOGIN:
            return None
        path = request.path_info
        if not path.startswith(("/panel/", "/healthz/", "/crm/")) and not path.startswith(
            (f"{settings.MEDIA_URL}logs/", f"{settings.MEDIA_URL}tmp/")
        ):
            return None
        name = request.resolver_match.url_name
        if name in SESSION_VIEWS or name in READ_ONLY_PUBLIC and request.method in {"GET", "HEAD"}:
            return None
        request.crm_private_response = True
        if can_use_staff_card(request.user):
            return None
        if request.user.is_authenticated or request.method not in {"GET", "HEAD"}:
            return HttpResponseForbidden("Требуется вход сотрудника.")
        return redirect_to_login(request.get_full_path(), reverse("crm_staff_login"))

    def process_response(self, request, response):
        if getattr(request, "crm_private_response", False):
            add_never_cache_headers(response)
        return response
