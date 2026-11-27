/* Leasing Compass — voluntary site sharing, no third-party SDK, no contact access. */
(function () {
  "use strict";
  const PREVIEW = "https://talysrus90-cmd.github.io/lizingkompas-unified/variant-5.html?v=508";
  const PRODUCTION = "https://leasingcompass.ru/";
  const TITLE = "Лизинг Компас";
  function shareData(locationHref, position) {
    let production = false;
    try { production = new URL(locationHref).origin === new URL(PRODUCTION).origin; } catch (_) {}
    const u = new URL(production ? PRODUCTION : PREVIEW);
    u.searchParams.set("utm_source", "site_share");
    u.searchParams.set("utm_medium", "referral");
    u.searchParams.set("utm_campaign", "recommendation");
    u.searchParams.set("utm_content", position === "floating" ? "floating" : "header");
    return { title: TITLE, text: production ? "Лизинг Компас — подбор лизинга для бизнеса и онлайн-калькулятор." : "Лизинг Компас — подбор лизинга для бизнеса и онлайн-калькулятор.", url: u.href };
  }
  function links(data) {
    return {
      max: "https://max.ru/:share?text=" + encodeURIComponent(data.text + "\n" + data.url),
      mail: "mailto:?subject=" + encodeURIComponent(data.title) + "&body=" + encodeURIComponent(data.text + "\n" + data.url)
    };
  }
  function mount(doc, nav, locationHref) {
    const buttons = [...doc.querySelectorAll("[data-lk-share]")];
    const dialog = doc.getElementById("lkShareDialog");
    if (!dialog || !buttons.length) return;
    const input = doc.getElementById("lkShareLink");
    const status = doc.getElementById("lkShareStatus");
    let active = null;
    function fallback(data) {
      input.value = data.url;
      status.textContent = "";
      const l = links(data);
      doc.getElementById("lkShareMax").href = l.max;
      doc.getElementById("lkShareMail").href = l.mail;
      if (!dialog.open) dialog.showModal();
      doc.getElementById("lkShareCopy").focus();
    }
    for (const button of buttons) {
      button.addEventListener("click", async () => {
        let data;
        try { data = button.dataset.lkShare === "calculation" ? window.LKGrowth.calculationShare(doc,locationHref) : shareData(locationHref, button.dataset.lkShare); } catch (e) { window.alert(e.message || "Проверьте параметры расчёта."); return; }
        active = button;
        if (typeof nav.share === "function") {
          try {
            if (typeof nav.canShare !== "function" || nav.canShare(data)) {
              await nav.share(data);
              return; // OS handoff, not evidence the recipient received it.
            }
          } catch (e) {
            if (e && e.name === "AbortError") return;
          }
        }
        fallback(data);
      });
    }
    doc.getElementById("lkShareClose").addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => { if (active) active.focus(); });
    doc.getElementById("lkShareCopy").addEventListener("click", async () => {
      try {
        if (nav.clipboard && nav.clipboard.writeText) {
          await nav.clipboard.writeText(input.value);
          status.textContent = "Ссылка скопирована.";
          return;
        }
      } catch (_) {}
      input.focus();
      input.select();
      try {
        if (doc.execCommand("copy")) {
          status.textContent = "Ссылка скопирована.";
          return;
        }
      } catch (_) {}
      status.textContent = "Ссылка выделена. Скопируйте её вручную.";
    });
    input.addEventListener("click", () => input.select());
  }
  if (typeof module === "object" && module.exports) module.exports = { shareData, links, mount };
  if (typeof document !== "undefined") mount(document, navigator, location.href);
})();
