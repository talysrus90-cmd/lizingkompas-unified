"""Optional, read-only client status portal. No automatic grants or self-registration."""
from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from .models import ClientPortalControl, ClientCaseAccess, Lead
from .services import count_attempt


def active_revision():
    if not settings.CLIENT_PORTAL_READY or not settings.LIVE_INTAKE or settings.SSH_OPERATOR:
        return None
    try:
        return ClientPortalControl.objects.filter(pk=1,enabled=True).values_list("revision",flat=True).first()
    except DatabaseError:
        return None


def require_revision():
    revision=active_revision()
    if revision is None:
        raise Http404
    return str(revision)


def access_rows(user):
    return ClientCaseAccess.objects.filter(user=user,active=True,lead__source="site").exclude(lead__consent_version="").exclude(lead__consent_text_sha256="")


class ClientLoginForm(AuthenticationForm):
    def confirm_login_allowed(self,user):
        super().confirm_login_allowed(user)
        if user.is_staff or user.is_superuser or not access_rows(user).exists():
            raise ValidationError("Вход недоступен. Обратитесь к брокеру.",code="invalid_login")


@never_cache
@require_GET
def client_status(request):
    return JsonResponse({"enabled":active_revision() is not None})


@never_cache
@require_http_methods(["GET","POST"])
def client_login(request):
    revision=require_revision()
    form=ClientLoginForm(request,data=request.POST if request.method=="POST" else None)
    if request.method=="POST":
        if not count_attempt(request):
            return HttpResponse("Превышен лимит попыток. Повторите позже.",status=429)
        if form.is_valid():
            if require_revision()!=revision:
                raise Http404
            login(request,form.get_user())
            request.session["client_portal_revision"]=revision
            request.session.set_expiry(1800)
            return redirect("client-home")
    return render(request,"intake/client_portal.html",{"form":form})


@never_cache
@require_GET
def client_home(request):
    revision=require_revision()
    user=request.user
    if not user.is_authenticated or user.is_staff or user.is_superuser or not user.is_active or request.session.get("client_portal_revision")!=revision:
        return redirect("client-login")
    grants=access_rows(user)
    cases=list(Lead.objects.filter(pk__in=grants.values("lead_id")).values("id","stage","created_at","updated_at").order_by("-created_at")[:100])
    labels=dict(Lead.Stage.choices)
    for item in cases:
        item["status_label"]=labels.get(item["stage"],"Уточняется")
    return render(request,"intake/client_portal.html",{"cases":cases,"portal_authenticated":True})


@never_cache
@require_POST
def client_logout(request):
    require_revision()
    if request.user.is_authenticated and not request.user.is_staff and not request.user.is_superuser:
        logout(request)
    return redirect("client-login")
