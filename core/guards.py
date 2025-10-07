from functools import wraps

from django.conf import settings
from django.http import HttpResponseForbidden


def shared_key_required(view):
    """Проверка общего ключа: заголовок X-Shared-Key или параметр ?key=..."""

    @wraps(view)
    def _wrap(request, *args, **kwargs):
        provided = (
            request.headers.get("X-Shared-Key")
            or request.GET.get("key")
            or request.POST.get("key")
        )
        expected = getattr(settings, "SHARED_KEY", "")
        if not provided or provided != expected:
            return HttpResponseForbidden("forbidden")
        return view(request, *args, **kwargs)

    return _wrap

