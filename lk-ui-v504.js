/* Leasing Compass V5 — mobile menu history + existing install/QR UI.
   Android Back closes the open menu before navigating away from the site.
   No URL/hash or visual change is made merely by opening the menu. */
(()=>{"use strict";
  const by=id=>document.getElementById(id);
  const menu=by("mobileMenu"),trigger=by("burgerBtn");
  if(!menu||!trigger)return;
  let installEvent=null,tracked=false,backPending=false,previousState=null,pendingAnchor=null;
  const token="lk-v5-menu-"+Math.random().toString(36).slice(2);

  function ownsHistoryEntry(){
    return tracked && history.state && history.state.__lkMobileMenu===token;
  }
  function hideMenu(){
    menu.classList.remove("open");
    trigger.setAttribute("aria-expanded","false");
  }
  function restoreMenuHistoryWithoutNavigation(){
    if(ownsHistoryEntry()){
      try { history.replaceState(previousState,"",location.href); } catch(_){}
    }
    tracked=false;
    backPending=false;
    pendingAnchor=null;
  }
  function closeMenu(mode="back"){
    hideMenu();
    if(!ownsHistoryEntry()){
      if(!backPending)tracked=false;
      return;
    }
    if(mode==="replace"){
      restoreMenuHistoryWithoutNavigation();
      return;
    }
    if(!backPending){
      backPending=true;
      history.back();
    }
  }
  function onMenuOpened(){
    if(backPending){hideMenu();return;}
    previousState=history.state;
    try{
      const state=previousState&&typeof previousState==="object"&&!Array.isArray(previousState)
        ? {...previousState}:{};
      state.__lkMobileMenu=token;
      history.pushState(state,"",location.href);
      tracked=true;
    }catch(_){tracked=false;}
  }
  // This listener follows V5's existing button toggle in variant-5.html.
  // Read the resulting state to avoid a second toggle and preserve the design.
  trigger.addEventListener("click",()=>{
    if(menu.classList.contains("open"))onMenuOpened();
    else closeMenu();
  });

  window.addEventListener("popstate",()=>{
    const hash=pendingAnchor;
    pendingAnchor=null;
    tracked=false;
    backPending=false;
    hideMenu();
    // For a section link, consume the temporary menu history entry first,
    // then navigate normally to the requested section.
    if(hash){
      if(location.hash!==hash)location.hash=hash;
      else{
        try{document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView({block:"start"});}catch(_){}
      }
    }
  });

  // Capture runs before the legacy inline closing handler. Same-page links
  // become one ordinary anchor navigation rather than a duplicate Back step.
  menu.querySelectorAll("a").forEach(anchor=>anchor.addEventListener("click",event=>{
    const href=anchor.getAttribute("href")||"";
    if(href.startsWith("#")&&href.length>1&&ownsHistoryEntry()){
      event.preventDefault();
      pendingAnchor=href;
      closeMenu("back");
    }else{
      // tel:, downloads and other pages must retain their native user gesture.
      closeMenu("replace");
    }
  },{capture:true}));

  window.addEventListener("beforeinstallprompt",e=>{e.preventDefault();installEvent=e;});
  window.addEventListener("appinstalled",()=>{installEvent=null;});

  by("lkQrOpen")?.addEventListener("click",()=>{
    // A dialog opened by a click should not be immediately closed by a
    // pending history.back() from a previously opened menu.
    closeMenu("replace");
    by("lkQrDialog")?.showModal();
  });
  for(const id of ["lkInstallMenu","lkInstallFooter"]){
    by(id)?.addEventListener("click",async()=>{
      closeMenu("replace");
      if(installEvent){
        try{
          const event=installEvent;
          installEvent=null;
          await event.prompt();
          await event.userChoice;
          return;
        }catch(_){}
      }
      by("lkInstallDialog")?.showModal();
    });
  }
  document.querySelectorAll("[data-close-dialog]").forEach(btn=>
    btn.addEventListener("click",()=>by(btn.dataset.closeDialog)?.close()));
  by("lkQrDialog")?.addEventListener("close",()=>by("lkQrOpen")?.focus());

  document.addEventListener("keydown",e=>{
    if(e.key==="Escape"&&menu.classList.contains("open")){
      closeMenu();
      trigger.focus();
    }
  });
  document.addEventListener("click",e=>{
    if(!menu.classList.contains("open")||menu.contains(e.target)||trigger.contains(e.target))return;
    const element=e.target;
    // Avoid interrupting native navigation, phone calls, PWA prompts or dialogs.
    const interactive=typeof element?.closest==="function"&&element.closest(
      "a,button,input,select,textarea,[role=button]"
    );
    closeMenu(interactive?"replace":"back");
  });
})();
