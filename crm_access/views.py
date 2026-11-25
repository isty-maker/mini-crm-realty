from django.conf import settings
from django.contrib.auth import login
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from .invitations import consume


@never_cache
@csrf_protect
@require_http_methods(["GET", "POST"])
def staff_invitation(request):
    error, status = "", 200
    if request.method == "POST":
        if not request.is_secure() or not settings.CRM_REQUIRE_STAFF_LOGIN:
            error, status = "Вход по приглашению требует защищённого подключения и включённого входа CRM.", 403
        else:
            user, status = consume(request.POST.get("invitation", ""))
            if user:
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
                request.session.set_expiry(settings.CRM_STAFF_SESSION_DAYS * 86400)
                response = redirect("panel_list")
                response["Referrer-Policy"] = "no-referrer"
                return response
            error = "Вход не подтверждён. Запросите новое приглашение или повторите позже."
    response = render(request, "core/staff_login.html", {"error": error}, status=status)
    response["Referrer-Policy"] = "no-referrer"
    return response
