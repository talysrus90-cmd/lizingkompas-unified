'use strict';
/* Synthetic sandbox; no network, real identity, storage, or legally effective consent. */
const $=id=>document.getElementById(id);
const names=['Заявка','Документы','Предложение','Договор','Сделка'];
const labels={company:'ООО / организация',ip:'ИП',person:'Физическое лицо'};
const docs={company:['Реквизиты организации','Полномочия представителя','Финансовые сведения','Предложение поставщика'],ip:['Регистрационные сведения','Учебный документ личности','Сведения об оборотах','Предложение поставщика'],person:['Учебный документ личности','Сведения о доходах','Предложение поставщика']};
const money=n=>Math.round(n).toLocaleString('ru-RU')+' ₽';
const rates=[{id:'A',rate:18},{id:'B',rate:22}];
function initial(){return {step:0,furthest:0,kind:'company',asset:'Оборудование',price:4500000,advance:900000,advanceMode:'pct',term:36,inn:'',pd:false,documents:[],creditConsent:false,credit:'idle',selected:null,signed:false,submitted:false,closed:false,history:['Открыт учебный кабинет']}}
let state=initial();
const entry=t=>state.history.push(t);
function el(tag,txt,cls){const x=document.createElement(tag);if(txt!==undefined)x.textContent=txt;if(cls)x.className=cls;return x}
function button(t,fn,primary=false,disabled=false,id=''){const b=el('button',t,'btn'+(primary?' primary':''));b.type='button';b.disabled=disabled;if(id)b.id=id;b.addEventListener('click',fn);return b}
function choice(t,checked,fn,id){const l=el('label',undefined,'choice'),c=el('input');c.type='checkbox';c.checked=checked;if(id)c.id=id;c.addEventListener('change',()=>fn(c.checked));l.append(c,document.createTextNode(t));return l}
function select(label,values,value,fn,id){const d=el('div',undefined,'field'),l=el('label',label),s=el('select');s.id=id;l.htmlFor=id;Object.entries(values).forEach(([v,t])=>{let o=el('option',t);o.value=v;s.append(o)});s.value=value;s.onchange=()=>fn(s.value);d.append(l,s);return d}
function heading(v,title,sub){v.append(el('h2',title),el('p',sub,'muted'))}
function buttons(v,...items){const d=el('div',undefined,'buttons');d.append(...items);v.append(d)}
function msg(t){$('status').textContent=t;$('status').hidden=!t}
function go(n){if(n<0||n>4)return;state.step=n;render();$('view').scrollIntoView({block:'start',behavior:'instant'})}
function advance(n){state.furthest=Math.max(state.furthest,n);go(n)}
function saveFile(title,text){const blob=new Blob([text],{type:'text/plain;charset=utf-8'});const url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download=title;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
function reset(){state=initial();render();msg('Учебная сессия очищена.')}
function clearAfterApplication(){state.submitted=false;state.creditConsent=false;state.credit='idle';state.selected=null;state.signed=false;state.closed=false;state.furthest=0}
function clearAfterDocs(){state.creditConsent=false;state.credit='idle';state.selected=null;state.signed=false;state.closed=false;state.furthest=1}
function validNumbers(){return Number.isFinite(state.price)&&state.price>=100000&&state.price<=150000000&&Number.isFinite(state.advance)&&state.advance>=0&&state.advance<=state.price*.49+.001&&Number.isInteger(state.term)&&state.term>=12&&state.term<=84}
function quote(rate){const m=rate/1200,principal=state.price-state.advance,payment=principal*m/(1-Math.pow(1+m,-state.term));return {payment,total:state.advance+payment*state.term}}
function renderRoute(){
 $('steps').replaceChildren(...names.map((t,i)=>{const li=el('li'),b=button('',()=>go(i),false);b.className=i<state.furthest||state.closed?'done':i>state.furthest?'upcoming':'';b.title=i>state.furthest?'Посмотреть этап':'Открыть этап';const icon=el('span',i===4?'🤝':i<state.furthest||state.closed?'✓':String(i+1),'num'+(i===4?' handshake':''));icon.setAttribute('aria-hidden','true');b.append(icon,el('span',t,'step-name'));if(i===state.step)b.setAttribute('aria-current','step');li.append(b);return li}));
 const completed=state.closed?5:state.furthest;
 $('progress').style.width=(completed/5*100)+'%';$('progress').parentElement.setAttribute('aria-valuenow',String(completed));$('progressText').textContent='Выполнено '+completed+' из 5 этапов';$('history').replaceChildren(...state.history.map(t=>el('li',t)));$('reset').hidden=state.step===0&&!state.submitted&&state.history.length===1;
}
function numField(label,id,min,max,step,value){const d=el('div',undefined,'field'),l=el('label',label),n=el('input');n.id=id;n.type='number';n.min=min;n.max=max;n.step=step;n.value=value;n.inputMode=step<1?'decimal':'numeric';l.htmlFor=id;d.append(l,n);return {d,n,l}}
function range(id,min,max,step,value,label){const n=el('input');n.id=id;n.type='range';n.min=min;n.max=max;n.step=step;n.value=value;n.setAttribute('aria-label',label);return n}
function application(v){
 heading(v,'Ваша заявка','Выберите имущество и измените параметры. Расчёт обновляется сразу.');
 v.append(select('Категория клиента',labels,state.kind,x=>{state.kind=x;state.documents=[];state.inn='';state.pd=false;clearAfterApplication();entry('Изменена категория клиента');render()},'kind'),select('Тип имущества',{'Оборудование':'Оборудование','Автомобиль':'Легковой автомобиль','Спецтехника':'Спецтехника','Грузовой транспорт':'Грузовой транспорт','Недвижимость':'Коммерческая недвижимость','Иное':'Иное'},state.asset,x=>{state.asset=x;state.documents=[];clearAfterApplication();render()},'asset'));
 const price=numField('Стоимость имущества, ₽','price',100000,150000000,1,state.price);
 const pr=range('priceRange',100000,150000000,10000,state.price,'Стоимость имущества');
 price.d.append(pr);v.append(price.d);
 const adv=numField('Аванс','advance',0,state.advanceMode==='pct'?49:Math.floor(state.price*.49),state.advanceMode==='pct'?.01:1,state.advanceMode==='pct'?Math.round(state.advance/state.price*10000)/100:Math.round(state.advance));
 adv.d.classList.add('advance-field');const mode=el('div',undefined,'mode-row'),pct=button('%',()=>setMode('pct'),false,false,'pctMode'),rub=button('₽',()=>setMode('rub'),false,false,'rubMode');mode.append(pct,rub);adv.d.insertBefore(mode,adv.n);
 const ar=range('advanceRange',0,49,.1,state.advance/state.price*100,'Аванс в процентах');adv.d.append(ar);const avText=el('p','','legal');adv.d.append(avText);v.append(adv.d);
 const term=numField('Срок лизинга, месяцев','term',12,84,1,state.term),tr=range('termRange',12,84,1,state.term,'Срок лизинга');term.d.append(tr);const presets=el('div',undefined,'presets');[24,36,48,60].forEach(n=>{const b=button(n+' мес.',()=>{term.n.value=n;readTerm();sync()});b.dataset.term=n;presets.append(b)});term.d.append(presets);v.append(term.d);
 const result=el('div',undefined,'stats live-stats');for(const [id,title] of [['payment','Платёж в месяц'],['total','Всего с авансом']]){const d=el('div'),val=el('strong','—');val.id=id;d.append(el('small',title),val);result.append(d)}result.setAttribute('aria-live','polite');v.append(result,el('p','Условная ставка 18% годовых. Равные платежи; без отдельного выкупа, страховки, комиссий и налогового эффекта. Не предложение ЛК.','legal'));
 const innD=el('div',undefined,'field'),innL=el('label','Учебный ИНН (необязательно)'),inn=el('input');inn.id='demoInn';innL.htmlFor=inn.id;inn.type='text';inn.inputMode='numeric';inn.autocomplete='off';inn.maxLength=state.kind==='company'?10:12;inn.placeholder='Только тестовые цифры';inn.value=state.inn;innD.append(innL,inn);v.append(innD);
 inn.oninput=()=>{inn.value=inn.value.replace(/\D/g,'');state.inn=inn.value;clearAfterApplication();sync()};
 v.append(choice('Даю согласие на обработку персональных данных (тест)',state.pd,x=>{state.pd=x;if(!x)clearAfterApplication();sync()},'pd'));
 const link=el('a','Текст согласия');link.href='./consent.html';link.target='_blank';link.rel='noopener';v.append(link,el('p','Демонстрация: сведения не отправляются и не сохраняются.','legal'));
 const err=el('p','','error');err.id='appError';err.setAttribute('role','status');v.append(err);
 const save=button('Продолжить →',()=>{if(!validNumbers()||!state.pd||!price.n.checkValidity()||!adv.n.checkValidity()||!term.n.checkValidity())return;state.submitted=true;entry('Учебная заявка подготовлена');advance(1)},true,true,'saveApplication');buttons(v,save);
 function setMode(m){if(!Number.isFinite(state.advance)||!Number.isFinite(state.price)||state.price<=0)return;state.advanceMode=m;adv.n.max=m==='pct'?49:Math.floor(state.price*.49);adv.n.step=m==='pct'?.01:1;adv.n.value=m==='pct'?Math.round(state.advance/state.price*10000)/100:Math.round(state.advance);sync()}
 function readPrice(){const old=state.price,share=Number.isFinite(old)&&old>0?state.advance/old:0.2;state.price=price.n.value===''?NaN:Number(price.n.value);if(Number.isFinite(state.price)&&state.price>=100000&&state.price<=150000000){state.advance=state.advanceMode==='pct'?Math.round(state.price*share):Math.min(state.advance,state.price*.49);adv.n.max=state.advanceMode==='pct'?49:Math.floor(state.price*.49);adv.n.value=state.advanceMode==='pct'?Math.round(state.advance/state.price*10000)/100:Math.round(state.advance);pr.value=state.price}clearAfterApplication()}
 function readAdvance(){state.advance=adv.n.value===''?NaN:state.advanceMode==='pct'?Math.round(state.price*Number(adv.n.value)/100):Number(adv.n.value);clearAfterApplication()}
 function readTerm(){state.term=term.n.value===''?NaN:Number(term.n.value);if(Number.isFinite(state.term))tr.value=state.term;clearAfterApplication()}
 function sync(){const ok=validNumbers()&&price.n.checkValidity()&&adv.n.checkValidity()&&term.n.checkValidity();pct.setAttribute('aria-pressed',String(state.advanceMode==='pct'));rub.setAttribute('aria-pressed',String(state.advanceMode==='rub'));avText.textContent=ok?Math.round(state.advance/state.price*10000)/100+'% · '+money(state.advance):'Допустимый аванс — от 0 до 49%';if(ok)ar.value=state.advance/state.price*100;presets.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.term)===state.term)));const q=ok?quote(rates[0].rate):null;$('payment').textContent=q?money(q.payment):'—';$('total').textContent=q?money(q.total):'—';err.textContent=ok?'':'Проверьте стоимость, аванс и срок (12–84 месяца).';save.disabled=!ok||!state.pd;renderRoute()}
 price.n.oninput=()=>{readPrice();sync()};pr.oninput=()=>{price.n.value=pr.value;readPrice();sync()};
 adv.n.oninput=()=>{readAdvance();sync()};ar.oninput=()=>{state.advance=Math.round(state.price*Number(ar.value)/100);adv.n.value=state.advanceMode==='pct'?ar.value:Math.round(state.advance);clearAfterApplication();sync()};
 term.n.oninput=()=>{readTerm();sync()};tr.oninput=()=>{term.n.value=tr.value;readTerm();sync()};
 sync();
}
function render(){
 const v=$('view');v.replaceChildren();renderRoute();msg('');
 if(state.step>state.furthest){
 const previews=[
 null,
 ['Документы','Подготовка документов для рассмотрения заявки.',docs[state.kind].map(t=>[t,'Добавление учебного образца после заявки.'])],
 ['Предложение','Сравнение вариантов финансирования.',[['Условия лизинга','Аванс, ежемесячный платёж, срок и общая сумма.'],['Сравнение сценариев','Выбор наиболее подходящего варианта.'],['Выбор предложения','Переход к проекту договора.']]],
 ['Договор','Проверка условий перед заключением сделки.',[['Проект договора','Просмотр и скачивание учебного проекта.'],['График и выкуп','Проверка платежей и условий выбранного сценария.'],['Подтверждение','Учебное подтверждение, не электронная подпись.']]],
 ['Сделка','Завершение и сопровождение лизинга.',[['Передача имущества','Проверка готовности к завершению сделки.'],['Сопровождение','Изменение графика, досрочный выкуп, страховой случай.'],['История','Просмотр учебных действий.']]]
 ];
 const [title,sub,items]=previews[state.step];heading(v,title,sub);
 v.append(el('p','Предварительный просмотр. Чтобы выполнить этот этап, завершите предыдущие шаги.','status'));
 items.forEach(([title,desc])=>{const d=el('div',undefined,'preview-item');d.append(el('strong',title),el('p',desc,'muted'));v.append(d)});
 buttons(v,button('Продолжить: '+names[state.furthest]+' →',()=>go(state.furthest),true));return;
 }
 if(state.step===0)application(v);
 else if(state.step===1){
 heading(v,'Документы','Добавьте учебные образцы. Реальные файлы не принимаются.');
 docs[state.kind].forEach((t,i)=>{const d=el('div',undefined,'document'),a=el('div');a.append(el('strong',t),el('small',state.documents.includes(i)?'Учебный файл добавлен':'Ожидается'));d.append(a,button(state.documents.includes(i)?'Удалить':'Добавить образец',()=>{if(state.documents.includes(i)){state.documents=state.documents.filter(x=>x!==i);clearAfterDocs()}else state.documents.push(i);entry('Учебный документ: '+t);render()},false,false,'doc'+i));v.append(d)});
 buttons(v,button('Скачать образец',()=>saveFile('LK_DEMO_document.txt','УЧЕБНЫЙ ОБРАЗЕЦ\nНе является документом клиента.')));
 const d=el('details'),sum=el('summary','Проверка сведений и кредитная история');d.open=state.documents.length===docs[state.kind].length||state.creditConsent;d.append(sum,el('p','Отдельное согласие на учебный запрос БКИ. Получатель — планируемый пользователь лизинговый брокер, цель — рассмотрение заявки. Юридической силы нет.','legal'),choice('Согласие на получение кредитного отчёта (тест)',state.creditConsent,x=>{state.creditConsent=x;if(!x){clearAfterDocs();entry('Тестовое согласие отозвано')}render()},'creditConsent'));
 const complete=state.documents.length===docs[state.kind].length;
 if(state.credit==='idle')buttons(d,button('Передать на проверку (тест)',()=>{if(!complete||!state.creditConsent||!state.pd||!state.submitted)return;state.credit='pending';entry('Учебный запрос создан');render()},true,!complete||!state.creditConsent,'requestCredit'));
 if(state.credit==='pending')buttons(d,button('Получить учебный ответ',()=>{state.credit='review';entry('Учебные сведения получены');render()},true,false,'receiveCredit'));
 if(state.credit==='review')d.append(el('p','Учебная проверка завершена. Решение о финансировании не принято.','status'));v.append(d);
 buttons(v,button('К предложениям →',()=>{if(complete&&state.credit==='review'&&state.creditConsent)advance(2)},true,!complete||state.credit!=='review'||!state.creditConsent,'toOffers'));
 }else if(state.step===2){
 heading(v,'Предложения','Условные сценарии рассчитаны по вашим параметрам, не котировки лизингодателей.');
 rates.forEach((o,i)=>{const q=quote(o.rate),d=el('div',undefined,'offer'+(state.selected===o.id?' selected':''));d.append(el('h3','Сценарий '+(i+1)+' · '+o.rate+'% годовых'),el('div',money(q.payment)+' / мес.','amount'),el('p','Аванс: '+money(state.advance)+' · '+state.term+' мес.'),el('p','Всего с авансом: '+money(q.total)),button(state.selected===o.id?'Выбрано':'Выбрать',()=>{if(state.selected!==o.id){state.selected=o.id;state.signed=false;state.closed=false;state.furthest=2;entry('Выбран учебный сценарий '+(i+1));render()}},state.selected!==o.id,false,'offer'+o.id));v.append(d)});
 buttons(v,button('К договору →',()=>{if(state.selected)advance(3)},true,!state.selected,'toContract'));
 }else if(state.step===3){
 heading(v,'Договор','Ознакомьтесь с учебным проектом. Подтверждение не является электронной подписью.');
 const o=rates.find(x=>x.id===state.selected),q=quote(o.rate);v.append(el('p',state.asset+' · '+money(state.price)+' · '+state.term+' мес.','status'),el('p','Платёж: '+money(q.payment)+' в месяц. Аванс: '+money(state.advance)+'.'));
 buttons(v,button('Скачать учебный проект',()=>saveFile('LK_DEMO_contract.txt','УЧЕБНЫЙ ПРОЕКТ\nИмущество: '+state.asset+'\nСтоимость: '+money(state.price)+'\nАванс: '+money(state.advance)+'\nСрок: '+state.term+' мес.\nУсловный платёж: '+money(q.payment)+'\nНе договор и не подпись.')),button('Подтвердить и к сделке →',()=>{if(!state.selected||!state.pd||!state.creditConsent||state.credit!=='review')return;state.signed=true;entry('Учебное подтверждение договора');advance(4)},true,false,'demoSign'));
 }else{
 heading(v,'Сделка 🤝','Завершающий этап и сопровождение действующего договора.');
 v.append(el('p',state.closed?'Учебная сделка завершена.':'Учебный договор подтверждён.','status'));
 buttons(v,button(state.closed?'Сделка завершена':'Завершить учебную сделку',()=>{state.closed=true;entry('Учебная сделка завершена');render();msg('Учебный маршрут пройден.')},true,state.closed,'finishDeal'));
 if(state.closed){v.append(el('h3','Сопровождение'));buttons(v,...[['Изменить график','Изменение графика'],['Досрочный выкуп','Досрочный выкуп'],['Страховой случай','Страховой случай']].map(([a,b])=>button(a,()=>{entry('Учебное обращение: '+b);render();msg('Учебное обращение добавлено. Не отправлено брокеру.')})))}
 }
 if(state.step>0)buttons(v,button('← Назад',()=>go(state.step-1)));
}
$('reset').onclick=reset;render();
