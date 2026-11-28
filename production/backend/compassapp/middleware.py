"""Security headers for Django operator and intake responses.

Public V5 static pages are served separately by Caddy and must pass their own
Content-Security-Policy regression tests before CSP can be tightened there.
"""
from django.conf import settings
from django.http import HttpResponseNotFound, HttpResponse
from intake.document_security import BoundedMemoryUploadHandler, MAX_REQUEST


class SecurityHeadersMiddleware:
    def __init__(self,get_response):
        self.get_response=get_response

    def __call__(self,request):
        # The public process never serves staff routes, even if the proxy is misconfigured.
        path = request.path_info
        if not settings.SSH_OPERATOR and (path == "/admin" or path.startswith("/admin/")):
            response = HttpResponseNotFound("Not found")
        elif path.startswith("/admin/workspace/v/") and path.endswith("/original/"):
            if not settings.DOCUMENT_VAULT_ENABLED:
                response = HttpResponseNotFound("Not found")
            elif request.method == "POST" and request.content_type == "multipart/form-data":
                try:
                    size = int(request.META.get("CONTENT_LENGTH", ""))
                except (ValueError, TypeError):
                    size = -1
                if not 0 < size <= MAX_REQUEST:
                    response = HttpResponse("Request too large or missing length",status=413)
                else:
                    request.upload_handlers = [BoundedMemoryUploadHandler(request)]
                    response = self.get_response(request)
            else:
                response = self.get_response(request)
        else:
            response = self.get_response(request)
        response["Content-Security-Policy"] = (
            "default-src 'none'; img-src 'self' data:; font-src 'self'; "
            "script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; form-action 'self'; "
            "base-uri 'none'; frame-ancestors 'none'; object-src 'none'"
        )
        response["Permissions-Policy"]="camera=(), microphone=(), geolocation=()"
        if path in ("/apply", "/callback", "/admin") or path.startswith(("/apply/", "/callback/", "/admin/")):
            response["Cache-Control"]="no-store, private"
        return response
