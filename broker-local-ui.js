/* Compass Broker local operator UI.
 * Runs ONLY when served from http://127.0.0.1, never on GitHub Pages.
 * Password/CSRF stay in transient browser memory; no tokens in localStorage.
 * No client PII, document uploads, external APIs or background sending.
 */
(() => {
  "use strict";
  if (typeof document === "undefined" || location.protocol !== "http:" ||
      location.hostname !== "127.0.0.1") return;

  document.body.dataset.localActive = "true";
  const by = id => document.getElementById(id);
  const loginForm=by("localLoginForm"),caseForm=by("localCaseForm"),
        offerForm=by("localOfferForm"),status=by("localStatus");
  if (!loginForm || !caseForm || !offerForm) return;
  let csrf="",cases=[],selected=null,busy=false;

  const today=new Date();
  const iso=d=>[d.getFullYear(),String(d.getMonth()+1).padStart(2,"0"),String(d.getDate()).padStart(2,"0")].join("-");
  const future=new Date(today.getFullYear(),today.getMonth(),today.getDate()+30);
  offerForm.elements.received_on.value=iso(today);
  offerForm.elements.valid_until.value=iso(future);

  function say(message,error=false){
    status.textContent=message;
    status.classList.toggle("error",!!error);
  }
  const setBusy=flag=>{
    busy=flag;
    for(const form of [loginForm,caseForm,offerForm]){
      for(const element of form.elements){
        // Keep fields editable if backend responds after a failed request.
        if(element.tagName==="BUTTON")element.disabled=flag;
      }
    }
    for(const id of ["localNextStage","localCompare","localAudit","localLogout"])
      by(id).disabled=flag;
  };
  async function api(path,options={}){
    const headers={"Accept":"application/json"};
    if(options.method==="POST"){
      headers["Content-Type"]="application/json";
      if(csrf)headers["X-CSRF-Token"]=csrf;
    }
    const res=await fetch(path,{
      method:options.method||"GET",headers,credentials:"same-origin",
      cache:"no-store",
      body:options.json ? JSON.stringify(options.json) : undefined
    });
    const payload=await res.json().catch(()=>({error:"invalid_server_response"}));
    if(!res.ok)throw Error("HTTP "+res.status+": "+(payload.error||"operation_failed"));
    return payload;
  }
  const formData=form=>Object.fromEntries(new FormData(form).entries());
  function setLoggedIn(isLogged){
    by("localAuth").hidden=isLogged;
    by("localWorkArea").hidden=!isLogged;
    by("localLogout").hidden=!isLogged;
    by("modeBadge").textContent=isLogged?"● ЛОКАЛЬНЫЙ РЕЖИМ • СДЕЛКИ В БАЗЕ":"● ПРИМЕР • ЛОКАЛЬНЫЙ ВХОД";
    if(isLogged)document.querySelector('[data-tab="workspace"]')?.click();
  }
  function make(tag,text,cls){
    const el=document.createElement(tag);
    if(text!==undefined)el.textContent=String(text);
    if(cls)el.className=cls;
    return el;
  }
  function money(raw){
    const n=Number(raw);
    return Number.isFinite(n)?new Intl.NumberFormat("ru-RU",{maximumFractionDigits:2}).format(n)+" ₽":String(raw);
  }
  function renderCases(){
    const list=by("localCaseList");list.replaceChildren();
    if(!cases.length)list.append(make("p","Сохранённых сделок пока нет. Создайте первую.","muted"));
    for(const item of cases){
      const button=make("button",
        "Сделка "+item.case_id.slice(0,8)+" · "+money(item.asset_price)+
        " · "+item.term_months+" мес. · "+item.stage+
        " · "+item.offer_count+" КП");
      button.type="button";
      button.setAttribute("aria-pressed",String(selected?.case_id===item.case_id));
      button.addEventListener("click",()=>{
        selected=item;renderCases();renderSelected();by("localResults").replaceChildren();
      });
      list.append(button);
    }
    renderSelected();
  }
  function renderSelected(){
    const box=by("localSelectedCase");
    box.hidden=!selected;
    if(!selected)return;
    by("localSelectedTitle").textContent="Сделка "+selected.case_id.slice(0,8);
    by("localSelectedDescription").textContent=
      "Стоимость "+money(selected.asset_price)+
      " · аванс "+money(selected.advance)+
      " · "+selected.term_months+" месяцев · этап: "+selected.stage+
      " · версия "+selected.version;
    const next={draft:["collecting","Начать сбор КП"],
                collecting:["comparing","Перейти к сравнению"],
                comparing:["closed","Завершить сделку"]}[selected.stage];
    by("localNextStage").hidden=!next;
    if(next){by("localNextStage").dataset.next=next[0];by("localNextStage").textContent=next[1];}
    offerForm.hidden=!["draft","collecting"].includes(selected.stage);
  }
  async function refresh(selectId=null){
    const out=await api("/api/cases");
    cases=out.cases||[];
    if(selectId)selected=cases.find(x=>x.case_id===selectId)||null;
    else if(selected)selected=cases.find(x=>x.case_id===selected.case_id)||null;
    else selected=cases[0]||null;
    renderCases();
  }
  async function execute(action){
    if(busy)return;
    setBusy(true);
    try{await action();say("Действие выполнено и сохранено.");}
    catch(error){say(error.message||"Ошибка подключения",true);}
    finally{setBusy(false);}
  }
  loginForm.addEventListener("submit",e=>{
    e.preventDefault();
    execute(async()=>{
      const password=loginForm.elements.password.value;
      const response=await api("/api/login",{method:"POST",json:{password}});
      csrf=response.csrf;
      loginForm.reset();
      setLoggedIn(true);
      await refresh();
      say("Локальная база открыта. Контактные данные клиентов не вводить.");
    });
  });
  caseForm.addEventListener("submit",e=>{
    e.preventDefault();
    execute(async()=>{
      const data=formData(caseForm);
      data.term_months=Number(data.term_months);
      const result=await api("/api/cases",{method:"POST",json:data});
      await refresh(result.case_id);
      say("Сделка сохранена в локальной базе: "+result.case_id.slice(0,8));
    });
  });
  offerForm.addEventListener("submit",e=>{
    e.preventDefault();
    if(!selected){say("Выберите сделку",true);return;}
    execute(async()=>{
      const data=formData(offerForm);
      data.expected_version=selected.version;
      data.verified_by_broker=data.verified_by_broker==="true";
      const caseId=selected.case_id;
      await api("/api/cases/"+caseId+"/offers",{method:"POST",json:data});
      await refresh(caseId);
      offerForm.reset();
      offerForm.elements.received_on.value=iso(today);
      offerForm.elements.valid_until.value=iso(future);
      say("Условия КП сохранены. Исходный документ здесь не загружается.");
    });
  });
  by("localNextStage").addEventListener("click",()=>execute(async()=>{
    if(!selected)return;
    const caseId=selected.case_id;
    await api("/api/cases/"+caseId+"/stage",
      {method:"POST",json:{target:by("localNextStage").dataset.next,expected_version:selected.version}});
    await refresh(caseId);
  }));
  function renderRows(headers,rows){
    const box=by("localResults");box.replaceChildren();
    const wrap=make("div",undefined,"table-scroll");
    const table=make("table",undefined,"local-table");
    const thead=make("thead"),head=make("tr");
    headers.forEach(label=>head.append(make("th",label)));
    thead.append(head);table.append(thead);
    const tbody=make("tbody");
    rows.forEach(values=>{
      const tr=make("tr");values.forEach(v=>tr.append(make("td",v===null?"—":String(v))));
      tbody.append(tr);
    });
    table.append(tbody);wrap.append(table);box.append(wrap);
  }
  by("localCompare").addEventListener("click",()=>execute(async()=>{
    if(!selected)return;
    const out=await api("/api/cases/"+selected.case_id+"/comparison");
    renderRows(["Ранг","КП","Лизингодатель","Сумма выплат","Проверка"],
      out.rows.map(r=>[r.rank,r.offer_id,r.lessor,
        r.total_cash_outflow?money(r.total_cash_outflow):"Не сопоставимо",
        r.blockers.length?r.blockers.join(", "):"Проверено"]));
    say("Сопоставимых предложений: "+out.comparable_count+". Не является решением о финансировании.");
  }));
  by("localAudit").addEventListener("click",()=>execute(async()=>{
    if(!selected)return;
    const out=await api("/api/cases/"+selected.case_id+"/audit");
    renderRows(["Версия","Действие","Дата"],out.events.map(e=>[e.version,e.action,e.at]));
    say("Загружен журнал действий выбранной сделки.");
  }));
  by("localLogout").addEventListener("click",()=>execute(async()=>{
    await api("/api/logout",{method:"POST",json:{}});
    csrf="";cases=[];selected=null;
    setLoggedIn(false);by("localResults").replaceChildren();
    say("Вы вышли из локального рабочего режима.");
  }));
  (async()=>{
    try{
      const session=await api("/api/session");
      csrf=session.csrf||"";
      setLoggedIn(session.authenticated);
      if(session.authenticated)await refresh();
      else say("Для работы с локальной базой введите пароль оператора.");
    }catch(error){
      setLoggedIn(false);
      say("Не удалось связаться с локальным сервером: "+error.message,true);
    }
  })();
})();
