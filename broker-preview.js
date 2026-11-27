/* Compass Broker UI preview — ALL DATA SYNTHETIC.
 * This script never makes network requests, saves data, or accepts files.
 * Calculations are integer RUB cash outflows, not APR or lending offers.
 * Not a production CRM, identity service, or secure backend.
 */
(function (root) {
  'use strict';
  const AS_OF='2026-11-27';
  const COST_FIELDS=['monthly','buyout','upfrontFee','recurringMonthlyFee','insuranceTotal','otherCosts'];
  const cases=[
    {
      id:'DEMO-001',title:'Экскаватор · демонстрация',description:'Подбор финансирования для условной новой спецтехники.',
      status:'Сравнение',statusStyle:'',price:4500000,advance:900000,months:36,
      offers:[
        {id:'KP-001',lessor:'Компания А (пример)',doc:'DOC-DEMO-001',received:'2026-11-25',validUntil:'2026-12-20',verified:true,monthly:125000,buyout:1000,upfrontFee:5000,recurringMonthlyFee:500,insuranceTotal:30000,otherCosts:0},
        {id:'KP-002',lessor:'Компания Б (пример)',doc:'DOC-DEMO-002',received:'2026-11-25',validUntil:'2026-12-20',verified:true,monthly:121000,buyout:1000,upfrontFee:5000,recurringMonthlyFee:500,insuranceTotal:30000,otherCosts:0},
        {id:'KP-003',lessor:'Компания В (пример)',doc:'DOC-DEMO-003',received:'2026-11-25',validUntil:'2026-12-20',verified:true,monthly:119000,buyout:1000,upfrontFee:5000,recurringMonthlyFee:500,insuranceTotal:30000,otherCosts:0}
      ]
    },
    {
      id:'DEMO-002',title:'Грузовик · демонстрация',description:'Условная сделка: требуется проверить полноту второго КП.',
      status:'Сбор КП',statusStyle:'wait',price:8900000,advance:1780000,months:48,
      offers:[
        {id:'KP-004',lessor:'Компания Г (пример)',doc:'DOC-DEMO-004',received:'2026-11-25',validUntil:'2026-12-20',verified:true,monthly:175000,buyout:2000,upfrontFee:8500,recurringMonthlyFee:0,insuranceTotal:92000,otherCosts:0},
        {id:'KP-005',lessor:'Компания Д (пример)',doc:'DOC-DEMO-005',received:'2026-11-25',validUntil:'2026-12-20',verified:false,monthly:169000,buyout:2000,upfrontFee:8500,recurringMonthlyFee:0,insuranceTotal:null,otherCosts:0}
      ]
    },
    {
      id:'DEMO-003',title:'Станок · демонстрация',description:'Условное оборудование, заявка ещё на стадии черновика.',
      status:'Черновик',statusStyle:'draft',price:2100000,advance:420000,months:24,
      offers:[
        {id:'KP-006',lessor:'Компания Е (пример)',doc:'DOC-DEMO-006',received:'2026-11-25',validUntil:'2026-12-20',verified:true,monthly:81000,buyout:500,upfrontFee:1000,recurringMonthlyFee:0,insuranceTotal:25000,otherCosts:0},
        {id:'KP-007',lessor:'Компания Ж (пример)',doc:'DOC-DEMO-007',received:'2026-11-25',validUntil:'2026-12-20',verified:true,monthly:83000,buyout:500,upfrontFee:1000,recurringMonthlyFee:0,insuranceTotal:25000,otherCosts:0}
      ]
    }
  ];
  function formatRub(amount) {
    return typeof amount==='number' && Number.isFinite(amount)
      ? new Intl.NumberFormat('ru-RU',{maximumFractionDigits:0}).format(amount)+' ₽'
      : '—';
  }
  function evaluateOffer(deal,offer,asOf=AS_OF){
    const blockers=[];
    if(!offer.verified)blockers.push('Не проверено брокером');
    if(!offer.doc)blockers.push('Нет ссылки на исходное КП');
    if(!offer.received||offer.received>asOf)blockers.push('Дата получения не подтверждена');
    if(!offer.validUntil||offer.validUntil<asOf)blockers.push('Срок действия истёк');
    for(const name of COST_FIELDS){
      const value=offer[name];
      if(!Number.isSafeInteger(value)||value<0)blockers.push('Неизвестно: '+name);
    }
    if(!blockers.length){
      const sum=deal.advance+(offer.monthly+offer.recurringMonthlyFee)*deal.months+
                offer.buyout+offer.upfrontFee+offer.insuranceTotal+offer.otherCosts;
      if(!Number.isSafeInteger(sum)||sum<0)blockers.push('Ошибка диапазона суммы');
      else return {offer,total:sum,blockers,rank:null};
    }
    return {offer,total:null,blockers,rank:null};
  }
  function compare(deal,asOf=AS_OF){
    if(!deal||!Array.isArray(deal.offers))throw Error('Synthetic deal required');
    const rows=deal.offers.map(o=>evaluateOffer(deal,o,asOf));
    const valid=rows.filter(r=>r.total!==null).sort((a,b)=>a.total-b.total);
    if(valid.length>=2){
      valid.forEach(row=>{
        row.rank=1+valid.filter(other=>other.total<row.total).length;
      });
    }
    return {rows:rows.sort((a,b)=>(a.rank===null?999:a.rank)-(b.rank===null?999:b.rank)),comparableCount:valid.length};
  }
  function initialise(doc){
    let selected=0;
    const by=id=>doc.getElementById(id);
    const nav=Array.from(doc.querySelectorAll('[data-tab]'));
    function showTab(tab){
      nav.forEach(btn=>btn.setAttribute('aria-current',btn.dataset.tab===tab?'page':'false'));
      Array.from(doc.querySelectorAll('main .section')).forEach(el=>el.classList.toggle('active',el.id==='view-'+tab));
    }
    function make(tag,txt,css){
      const node=doc.createElement(tag);
      if(txt!==undefined&&txt!==null)node.textContent=String(txt);
      if(css)node.className=css;
      return node;
    }
    function renderCases(){
      const list=by('caseList');list.replaceChildren();
      cases.forEach((deal,index)=>{
        const btn=make('button',null,'case');
        btn.type='button';btn.setAttribute('aria-pressed',String(index===selected));
        const line=make('span',null,'case-line');
        line.append(make('small',deal.id),make('span',deal.status,'status '+deal.statusStyle));
        btn.append(line,make('strong',deal.title),make('small',formatRub(deal.price)+' · '+deal.months+' мес.'));
        btn.addEventListener('click',()=>{selected=index;renderCases();renderDetail();});
        list.append(btn);
      });
    }
    function renderDetail(){
      const deal=cases[selected];
      by('caseCode').textContent=deal.id+' / ИСКУССТВЕННЫЕ ДАННЫЕ';
      by('caseTitle').textContent=deal.title;
      by('caseDescription').textContent=deal.description;
      by('factPrice').textContent=formatRub(deal.price);
      by('factAdvance').textContent=formatRub(deal.advance);
      by('factTerm').textContent=deal.months+' мес.';
      by('factOffers').textContent=deal.offers.length;
      by('factStatus').textContent=deal.status;
    }
    function renderOffers(){
      const deal=cases[selected],out=compare(deal),body=by('comparisonRows');body.replaceChildren();
      by('comparisonLabel').textContent=deal.id+' · '+deal.title+' · '+deal.months+' месяцев';
      out.rows.forEach(row=>{
        const tr=make('tr'),rank=make('td');
        rank.append(make('span',row.rank===null?'—':row.rank,'rank'));
        const lessor=make('td');
        lessor.append(make('strong',row.offer.lessor),make('span',row.offer.id,'table-meta'));
        const monthly=make('td',formatRub(row.offer.monthly),'number');
        const total=make('td',row.total===null?'Не сопоставимо':formatRub(row.total),'number');
        const source=make('td');
        source.append(make('strong',row.offer.doc||'Нет исходного документа'),
                      make('span',row.blockers.length?row.blockers.join('; '):'Условно подтверждено · до '+row.offer.validUntil,'table-meta'));
        tr.append(rank,lessor,monthly,total,source);body.append(tr);
      });
      by('comparisonFootnote').textContent=
        'Сопоставимых КП: '+out.comparableCount+' из '+out.rows.length+
        '. Рейтинг доступен только при двух и более полноценных КП. Все лизингодатели и документы вымышлены.';
    }
    function renderDocuments(){
      const list=by('documentList');list.replaceChildren();
      const deal=cases[selected];
      const examples=[
        {label:'Карточка сделки '+deal.id,description:'Тестовая запись; реально не загружена',state:'Пример'},
        {label:'Коммерческие предложения · '+deal.offers.length,description:'Только демонстрационные строки, оригиналов файлов нет',state:'Нет файлов'},
        {label:'Compass Legal / OCR',description:'Анализ договоров не запущен',state:'Неактивен'}
      ];
      for(const item of examples){
        const node=make('div',null,'list-item'),info=make('div');
        info.append(make('strong',item.label),make('small',item.description));
        node.append(info,make('span',item.state,'status draft'));list.append(node);
      }
    }
    nav.forEach(btn=>btn.addEventListener('click',()=>{
      const tab=btn.dataset.tab;
      if(tab==='offers')renderOffers();
      if(tab==='documents')renderDocuments();
      showTab(tab);
    }));
    by('compareNow').addEventListener('click',()=>{renderOffers();showTab('offers');});
    by('openDocs').addEventListener('click',()=>{renderDocuments();showTab('documents');});
    by('backToDeals').addEventListener('click',()=>showTab('deals'));
    renderCases();renderDetail();showTab('deals');
  }
  if(typeof module==='object'&&module.exports)module.exports={cases,formatRub,evaluateOffer,compare,AS_OF};
  if(typeof document!=='undefined')initialise(document);
})(typeof globalThis==='object'?globalThis:this);
