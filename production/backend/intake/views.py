"""Same-origin, CSRF-protected applicant entry and one-time acknowledgement."""
import uuid
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache
from django.utils import timezone
from .forms import ApplicationForm, CallbackForm
from .services import count_attempt, consent_text, save_application, callback_consent_text, save_callback

UNAVAILABLE = (
    "Приём заявок ещё не подключён к защищённому серверу. "
    "Отправка персональных данных недоступна."
)

def _render_form(request, form, status=200):
    return render(request, "intake/apply.html", {
        "form": form, "consent_text": consent_text(),
        "operator_name": settings.OPERATOR_NAME,
        "consent_version": settings.CONSENT_VERSION,
    }, status=status)

@never_cache
def apply(request):
    if not settings.LIVE_INTAKE:
        return HttpResponse(UNAVAILABLE, status=503, content_type="text/plain; charset=utf-8")
    if request.method == "GET":
        nonce = str(uuid.uuid4())
        request.session["apply_nonce"] = nonce
        request.session["apply_started_at"] = timezone.now().timestamp()
        return _render_form(request, ApplicationForm(initial={"request_key": nonce}))
    if request.method != "POST":
        return HttpResponse(status=405)
    if not count_attempt(request):
        return HttpResponse("Превышен лимит запросов. Попробуйте позже.",status=429)
    form = ApplicationForm(request.POST)
    if not form.is_valid():
        return _render_form(request, form, 400)
    nonce = request.session.get("apply_nonce")
    started = request.session.get("apply_started_at", 0)
    if (not nonce or nonce != str(form.cleaned_data["request_key"])
            or timezone.now().timestamp()-started > 24*3600):
        return HttpResponse("Сессия формы устарела. Откройте страницу заново.", status=409)
    lead, created = save_application(form.cleaned_data, request)
    request.session.pop("apply_nonce", None)
    request.session.pop("apply_started_at", None)
    request.session["apply_success"] = True
    return redirect("intake:success")

@never_cache
def success(request):
    if not settings.LIVE_INTAKE:
        return HttpResponse(UNAVAILABLE,status=503)
    if request.method != "GET" or not request.session.pop("apply_success",False):
        return redirect("intake:apply")
    return render(request,"intake/success.html")

@never_cache
def callback(request):
    """Separate protected callback entry, no leasing-case fields needed."""
    if not settings.LIVE_INTAKE:
        return HttpResponse(UNAVAILABLE, status=503,
                            content_type="text/plain; charset=utf-8")
    if request.method == "GET":
        nonce=str(uuid.uuid4())
        request.session["callback_nonce"]=nonce
        request.session["callback_started_at"]=timezone.now().timestamp()
        form=CallbackForm(initial={"request_key":nonce})
        return render(request,"intake/callback.html",{
            "form":form,"consent_text":callback_consent_text(),
            "consent_version":settings.CONSENT_VERSION,
            "operator_name":settings.OPERATOR_NAME,
        })
    if request.method!="POST":
        return HttpResponse(status=405)
    if not count_attempt(request):
        return HttpResponse("Превышен лимит запросов. Попробуйте позже.",status=429)
    form=CallbackForm(request.POST)
    if not form.is_valid():
        return render(request,"intake/callback.html",{
            "form":form,"consent_text":callback_consent_text(),
            "consent_version":settings.CONSENT_VERSION,
            "operator_name":settings.OPERATOR_NAME,
        },status=400)
    nonce=request.session.get("callback_nonce")
    started=request.session.get("callback_started_at",0)
    if (not nonce or nonce!=str(form.cleaned_data["request_key"])
            or timezone.now().timestamp()-started>24*3600):
        return HttpResponse("Сессия устарела. Откройте форму заново.",status=409)
    save_callback(form.cleaned_data,request)
    request.session.pop("callback_nonce",None)
    request.session.pop("callback_started_at",None)
    request.session["callback_success"]=True
    return redirect("intake:callback_success")

@never_cache
def callback_success(request):
    if not settings.LIVE_INTAKE:
        return HttpResponse(UNAVAILABLE,status=503)
    if request.method!="GET" or not request.session.pop("callback_success",False):
        return redirect("intake:callback")
    return render(request,"intake/callback_success.html")
