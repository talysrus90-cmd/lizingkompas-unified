/* Public growth tools; no cookies, contact access, or network submission. */
(function(){
"use strict";
const PREVIEW="https://talysrus90-cmd.github.io/lizingkompas-unified/variant-5.html", PROD="https://leasingcompass.ru/";
const TYPES=["Новое легковое авто","Авто с пробегом","Оборудование","Коммерческая недвижимость","Спецтехника / Грузовой","Рефинансирование / Возвратный лизинг","Иное"];
const RATES=Object.freeze([18,20,22,24,26]);
function valid(x){
 return x && Number.isSafeInteger(x.price)&&x.price>=500000&&x.price<=150000000&&Number.isSafeInteger(x.advance)&&x.advance>=Math.ceil(x.price*.05)&&x.advance<=Math.floor(x.price*.49)&&Number.isInteger(x.term)&&x.term>=12&&x.term<=84&&x.term%6===0&&Number.isInteger(x.type)&&x.type>=0&&x.type<TYPES.length;
}
function estimate(x,rate=18){
 if(!valid(x)||!RATES.includes(rate))throw new RangeError("Invalid parameters");
 const r=rate/1200,principal=x.price-x.advance,power=(1+r)**x.term;
 const monthly=principal*r*power/(power-1);
 return {monthly,total:x.advance+monthly*x.term,overpay:x.advance+monthly*x.term-x.price};
}
function root(href){try{return new URL(href).origin===new URL(PROD).origin?PROD:PREVIEW}catch(_){return PREVIEW}}
function calcLink(x,href){
 if(!valid(x))throw new RangeError("Invalid parameters");
 const u=new URL(root(href));u.searchParams.set("utm_source","calc_share");u.searchParams.set("utm_medium","referral");u.searchParams.set("utm_campaign","calculation");
 u.hash="calc=v1,"+[x.price,x.advance,x.term,x.type].join(",");return u.href;
}
function decode(hash){
 const m=/^#calc=v1,(\d{6,9}),(\d{1,9}),(\d{2}),(\d)$/.exec(hash||"");
 if(!m)return null;const [price,advance,term,type]=m.slice(1).map(Number);const x={price,advance,term,type};return valid(x)?x:null;
}
function partnerCode(raw){const p=String(raw||"").trim().toLowerCase();return /^[a-z0-9][a-z0-9_-]{2,31}$/.test(p)?p:null;}
function partnerLink(code,href){const p=partnerCode(code);if(!p)throw new RangeError("Invalid partner code");const u=new URL(root(href));u.searchParams.set("utm_source","partner");u.searchParams.set("utm_medium","referral");u.searchParams.set("utm_campaign","partner_widget");u.searchParams.set("utm_content",p);return u.href}
function embedCode(code,href){const p=partnerCode(code);if(!p)throw new RangeError("Invalid partner code");const u=new URL("partner-calculator.html",root(href));u.searchParams.set("partner",p);return '<iframe src="'+u.href+'" title="Лизинг Компас — калькулятор" width="100%" height="680" loading="lazy" sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox" referrerpolicy="strict-origin-when-cross-origin" style="border:0;max-width:560px"></iframe>'}
const rub=n=>Math.round(n).toLocaleString("ru-RU")+" ₽";
function calculationShare(doc,href){
 const x={price:Number(doc.getElementById("cPriceNum").value.replace(/\s/g,"")),advance:Number(doc.getElementById("cAdvInput").value.replace(/\s/g,"")),term:Number(doc.getElementById("cTerm").value),type:TYPES.indexOf(doc.getElementById("cType").value)};
 if(!valid(x))throw new RangeError("Проверьте стоимость, аванс и срок расчёта.");
 return {title:"Лизинг Компас — параметры расчёта",text:"Ориентировочный расчёт: "+TYPES[x.type]+", стоимость "+rub(x.price)+", аванс "+rub(x.advance)+", срок "+x.term+" мес. Условные ставки; не оферта. Откройте ссылку для пересчёта.",url:calcLink(x,href)};
}
function restore(doc,hash){
 const x=decode(hash);if(!x)return false;
 const type=doc.getElementById("cType");if(!type||typeof syncPrice!=="function"||typeof syncAdvInput!=="function"||typeof setFinance!=="function")return false;
 type.value=TYPES[x.type];syncPrice(x.price,true);setFinance(doc.getElementById("cAdvInput"),x.advance);syncAdvInput(true);doc.getElementById("cTerm").value=String(x.term);recalc();if(typeof refreshFinance==="function")refreshFinance();
 const notice=doc.getElementById("lkCalcRestored");notice.hidden=false;
 requestAnimationFrame(()=>doc.getElementById("calc-section").scrollIntoView({block:"start"}));return true;
}
function mount(doc,href){
 const p=doc.getElementById("lkPartnerCode");if(!p)return;
 const link=doc.getElementById("lkPartnerLink"),embed=doc.getElementById("lkPartnerEmbed"),status=doc.getElementById("lkPartnerStatus");
 doc.getElementById("lkPartnerGenerate").addEventListener("click",()=>{
 const code=partnerCode(p.value);if(!code){status.textContent="Используйте 3–32 латинских символа, цифры, дефис или подчёркивание.";link.value="";embed.value="";return}
 link.value=partnerLink(code,href);embed.value=embedCode(code,href);status.textContent="Готово. Это демонстрационные метки, не регистрация партнёра и не договор о вознаграждении.";
 });
 for(const [btn,field] of [["lkPartnerCopyLink",link],["lkPartnerCopyEmbed",embed]])doc.getElementById(btn).addEventListener("click",async()=>{if(!field.value){status.textContent="Сначала создайте ссылку.";return}try{await navigator.clipboard.writeText(field.value);status.textContent="Скопировано."}catch(_){field.focus();field.select();status.textContent="Текст выделен для ручного копирования."}});
 if(location.hash.startsWith("#calc="))restore(doc,location.hash);
}
const api={TYPES,RATES,valid,estimate,calcLink,decode,partnerCode,partnerLink,embedCode,calculationShare,restore,mount,rub,root};
if(typeof module==="object"&&module.exports)module.exports=api;
if(typeof window!=="undefined"){window.LKGrowth=api;if(document.getElementById("lkPartnerCode"))mount(document,location.href);}
})();
