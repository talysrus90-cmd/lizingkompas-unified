"""Security headers for Django operator and intake responses.

Public V5 static pages are served separately by Caddy and must pass their own
Content-Security-Policy regression tests before CSP can be tightened there.
"""
class SecurityHeadersMiddleware:
    def __init__(self,get_response):
        self.get_response=get_response

    def __call__(self,request):
        response=self.get_response(request)
        response["Content-Security-Policy"] = (
            "default-src 'none'; img-src 'self' data:; font-src 'self'; "
            "script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; form-action 'self'; "
            "base-uri 'none'; frame-ancestors 'none'; object-src 'none'"
        )
        response["Permissions-Policy"]="camera=(), microphone=(), geolocation=()"
        if request.path.startswith(("/apply/","/admin/")):
            response["Cache-Control"]="no-store, private"
        return response
