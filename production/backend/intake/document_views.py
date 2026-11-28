"""Private PDF originals. Disabled by default until production approvals.

Only the approved staff process can upload/download; every retrieval is
authorized, authenticated, integrity checked and scanned again.
"""
import hashlib
import hmac
import uuid

from cryptography.fernet import InvalidToken
from django.conf import settings
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .crypto import cipher
from .document_security import MAX_PDF, looks_like_pdf, scan_pdf
from .models import AuditEvent, Lead, Quote, OriginalDocument
from .workspace import allowed, layout_context, scoped_leads


def binding(doc):
    return ("compass-document-v1:" + str(doc.pk) + ":" + str(doc.lead_id) + ":" + str(doc.quote_id) + ":").encode("ascii")


def can_view_documents(user):
    return ((allowed(user,"view_quote") or allowed(user,"change_quote"))
            and allowed(user,"view_originaldocument"))


def can_add_documents(user):
    return (can_view_documents(user) and allowed(user,"change_quote")
            and allowed(user,"add_originaldocument"))


@admin.site.admin_view
@never_cache
@require_http_methods(["GET","POST"])
def original_document(request,layout,case_id,quote_id):
    design=layout_context(layout)
    if not settings.DOCUMENT_VAULT_ENABLED:
        raise Http404
    user=request.user
    if not can_view_documents(user):
        raise PermissionDenied
    # Internal financial-only records cannot acquire a personal document by
    # accident. Only consented customer-case workflow is supported initially.
    lead=get_object_or_404(scoped_leads(user).exclude(source="broker_internal"),pk=case_id)
    quote=get_object_or_404(Quote,pk=quote_id,lead=lead)
    doc=OriginalDocument.objects.filter(lead=lead,quote=quote).defer("ciphertext").first()
    error=""
    status=200
    may_add=can_add_documents(user) and lead.stage!=Lead.Stage.CLOSED
    if request.method=="POST":
        action=request.POST.get("action")
        if action=="download":
            if not doc:
                raise Http404
            # Fetch ciphertext only for a permitted, explicitly requested file.
            current=get_object_or_404(OriginalDocument,pk=doc.pk,lead=lead,quote=quote)
            try:
                raw=cipher().decrypt(bytes(current.ciphertext))
                prefix=binding(current)
                if not raw.startswith(prefix):
                    raise InvalidToken
                data=raw[len(prefix):]
                if not looks_like_pdf(data) or len(data)!=current.byte_count or not hmac.compare_digest(hashlib.sha256(data).hexdigest(),current.sha256):
                    raise InvalidToken
            except (InvalidToken,ImproperlyConfigured,ValueError,TypeError):
                return HttpResponse("Проверка целостности не пройдена.",status=503)
            if not scan_pdf(data):
                return HttpResponse("Выдача заблокирована: проверка безопасности не пройдена.",status=503)
            with transaction.atomic():
                get_object_or_404(scoped_leads(user).select_for_update().exclude(source="broker_internal"),pk=case_id)
                AuditEvent.objects.create(lead=lead,action="document.downloaded",actor=str(user.pk),details=str(current.pk))
            response=HttpResponse(data,content_type="application/pdf")
            response["Content-Disposition"]='attachment; filename="compass-original-'+str(current.pk)+'.pdf"'
            response["X-Content-Type-Options"]="nosniff"
            return response
        if action!="upload":
            raise Http404
        if not may_add:
            raise PermissionDenied
        if doc:
            error,status="Оригинал уже зарегистрирован. Замена запрещена.",409
        else:
            files=request.FILES.getlist("original")
            if getattr(request,"_compass_upload_rejected",False) or len(files)!=1 or len(request.FILES)!=1 or not 0<files[0].size<=MAX_PDF:
                error,status="Выберите один PDF не более 5 МиБ.",400
            else:
                data=files[0].read(MAX_PDF+1)
                if not looks_like_pdf(data):
                    error,status="Файл не соответствует формату PDF.",400
                elif not scan_pdf(data):
                    error,status="Файл не принят: проверка безопасности не пройдена.",503
                else:
                    try:
                        with transaction.atomic():
                            locked=get_object_or_404(scoped_leads(user).select_for_update().exclude(source="broker_internal"),pk=case_id)
                            if locked.stage==Lead.Stage.CLOSED:
                                raise PermissionDenied
                            locked_quote=get_object_or_404(Quote.objects.select_for_update(),pk=quote_id,lead=locked)
                            new=OriginalDocument(id=uuid.uuid4(),lead=locked,quote=locked_quote,uploaded_by=user,
                                sha256=hashlib.sha256(data).hexdigest(),byte_count=len(data))
                            new.ciphertext=cipher().encrypt(binding(new)+data)
                            new.save(force_insert=True)
                            AuditEvent.objects.create(lead=locked,action="document.uploaded",actor=str(user.pk),details=str(new.pk))
                        return redirect("broker-original-document",layout=layout,case_id=case_id,quote_id=quote_id)
                    except IntegrityError:
                        error,status="Оригинал или идентичный файл уже зарегистрирован.",409
                    except ImproperlyConfigured:
                        error,status="Хранилище недоступно.",503
    return render(request,"intake/original_document.html",{**design,"lead":lead,"quote":quote,
        "document":doc,"may_add":may_add and not doc,"error":error},status=status)
