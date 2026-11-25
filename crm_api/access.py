import hashlib
import re
import secrets
from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.utils.cache import add_never_cache_headers
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt

from .models import AccessKey


def digest(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def issue_key(user, label, can_write=False, can_identify=False):
    secret = secrets.token_urlsafe(32)
    key = AccessKey.objects.create(user=user, label=label, digest=digest(secret), can_write=can_write,
                                   can_identify=can_identify, issued_for=user.get_session_auth_hash())
    return key, secret


class APIError(Exception):
    def __init__(self, status, code, message, **details):
        self.status = status
        self.payload = {"error": {"code": code, "message": message, **details}}


def api_view(methods):
    def decorate(view):
        @csrf_exempt
        @wraps(view)
        def serve(request, *args, **kwargs):
            try:
                if not settings.CRM_REQUIRE_STAFF_LOGIN or not request.is_secure():
                    raise APIError(403, "https_required", "API requires HTTPS and enabled staff access.")
                match = re.fullmatch(r"Bearer ([A-Za-z0-9_-]{43})", request.headers.get("Authorization", ""))
                key = None
                if match:
                    key = AccessKey.objects.select_related("user").filter(
                        digest=digest(match[1]), revoked_at__isnull=True, user__is_active=True, user__is_staff=True,
                    ).first()
                if key is None or not constant_time_compare(key.issued_for, key.user.get_session_auth_hash()):
                    raise APIError(401, "invalid_key", "A valid Bearer key is required.")
                if request.method not in methods:
                    raise APIError(405, "method_not_allowed", "Method not allowed.")
                if request.method not in {"GET", "HEAD"} and not key.can_write:
                    raise APIError(403, "read_only", "The key does not permit modifications.")
                response = view(request, key, *args, **kwargs)
            except APIError as error:
                response = JsonResponse(error.payload, status=error.status)
                if error.status == 401:
                    response["WWW-Authenticate"] = "Bearer"
                if error.status == 405:
                    response["Allow"] = ", ".join(methods)
            add_never_cache_headers(response)
            response["X-Content-Type-Options"] = "nosniff"
            return response
        return serve
    return decorate
