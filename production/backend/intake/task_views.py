"""Case-bound manual task management; no external messaging or PII."""
from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .models import Lead, BrokerTask, AuditEvent
from .workspace import allowed, scoped_leads, layout_context

class TaskForm(forms.Form):
    kind=forms.ChoiceField(label="Действие",choices=BrokerTask.Kind.choices)
    priority=forms.TypedChoiceField(label="Приоритет",choices=BrokerTask.Priority.choices,coerce=int,initial=2)
    due_on=forms.DateField(label="Выполнить до",widget=forms.DateInput(attrs={"type":"date"}))

class UpdateTaskForm(forms.Form):
    state=forms.ChoiceField(label="Действие",choices=[("done","Выполнено"),("cancelled","Отменено"),("open","Перенести срок")])
    due_on=forms.DateField(label="Новый срок (при переносе)",required=False,widget=forms.DateInput(attrs={"type":"date"}))
    version=forms.IntegerField(min_value=0,widget=forms.HiddenInput)
    def clean(self):
        data=super().clean()
        if data.get("state")=="open" and not data.get("due_on"):
            self.add_error("due_on","Укажите новый срок.")
        return data

@admin.site.admin_view
@never_cache
@require_http_methods(["GET","POST"])
def task_case(request,layout,case_id):
    design=layout_context(layout)
    user=request.user
    if not (allowed(user,"view_brokertask") or allowed(user,"change_brokertask")):
        raise PermissionDenied
    lead=get_object_or_404(scoped_leads(user),pk=case_id)
    can_create=allowed(user,"add_brokertask") and allowed(user,"change_lead") and lead.stage!=Lead.Stage.CLOSED
    can_update=allowed(user,"change_brokertask") and allowed(user,"change_lead")
    create=TaskForm(initial={"due_on":timezone.localdate()})
    bound=None
    bound_id=None
    status=200
    if request.method=="POST":
        action=request.POST.get("action")
        if action=="create":
            if not can_create: raise PermissionDenied
            create=TaskForm(request.POST)
            if create.is_valid():
                try:
                    with transaction.atomic():
                        locked=get_object_or_404(scoped_leads(user).select_for_update(),pk=lead.pk)
                        if locked.stage==Lead.Stage.CLOSED: raise PermissionDenied
                        if locked.broker_tasks.count()>=200:
                            create.add_error(None,"Достигнут лимит задач по сделке.")
                        else:
                            task=BrokerTask.objects.create(lead=locked,**create.cleaned_data)
                            AuditEvent.objects.create(lead=locked,action="task.created",actor=str(user.pk),details=str(task.pk))
                            return redirect("broker-task-case",layout=layout,case_id=lead.pk)
                except IntegrityError:
                    create.add_error("kind","Такая открытая задача уже существует.")
        elif action=="update":
            if not can_update: raise PermissionDenied
            import uuid
            try: bound_id=uuid.UUID(request.POST.get("task_id",""))
            except ValueError: raise Http404
            bound=UpdateTaskForm(request.POST)
            with transaction.atomic():
                locked=get_object_or_404(scoped_leads(user).select_for_update(),pk=lead.pk)
                task=get_object_or_404(BrokerTask.objects.select_for_update(),pk=bound_id,lead=locked)
                if task.state!=BrokerTask.State.OPEN or request.POST.get("version")!=str(task.version):
                    bound.is_valid()
                    bound.add_error(None,"Задача уже изменилась. Обновите страницу.")
                    status=409
                elif bound.is_valid():
                    state=bound.cleaned_data["state"]
                    if state=="open" and locked.stage==Lead.Stage.CLOSED: raise PermissionDenied
                    if state=="open":
                        task.due_on=bound.cleaned_data["due_on"]
                    else:
                        task.state=state
                        task.completed_at=timezone.now()
                    task.version+=1
                    task.save()
                    AuditEvent.objects.create(lead=locked,action="task.changed",actor=str(user.pk),details=str(task.pk)+" "+state)
                    return redirect("broker-task-case",layout=layout,case_id=lead.pk)
        else: raise Http404
    rows=[]
    for task in lead.broker_tasks.all():
        form=None
        if can_update and task.state==BrokerTask.State.OPEN:
            form=bound if task.pk==bound_id else UpdateTaskForm(initial={"version":task.version})
        rows.append((task,form))
    return render(request,"intake/task_case.html",{**design,"lead":lead,"rows":rows,"create":create,"can_create":can_create,"today":timezone.localdate(),"error":"Задача изменилась. Обновите страницу." if status==409 else ""},status=status)
