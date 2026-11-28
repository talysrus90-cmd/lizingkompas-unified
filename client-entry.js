/* Production-only optional client portal entry. No credentials or user data. */
(() => {
  "use strict";
  if (location.protocol !== "https:" || !["leasingcompass.ru","www.leasingcompass.ru"].includes(location.hostname)) return;
  let sequence = 0;
  function remove() {
    document.querySelectorAll("[data-compass-client-entry]").forEach(node => node.remove());
  }
  async function refresh() {
    const ticket = ++sequence;
    remove();
    try {
      const response = await fetch("/client/status/", {cache:"no-store",credentials:"same-origin",redirect:"error"});
      if (!response.ok) return;
      const status = await response.json();
      if (ticket !== sequence || status.enabled !== true) return;
      for (const menu of [document.querySelector(".desktop-nav"),document.querySelector("#mobileMenu .lk-menu-group")]) {
        if (!menu) continue;
        const link = document.createElement("a");
        link.href = "/client/";
        link.textContent = "Личный кабинет";
        link.dataset.compassClientEntry = "1";
        menu.append(link);
      }
    } catch (_) { /* Fail closed: leave navigation unchanged. */ }
  }
  refresh();
  window.addEventListener("pageshow",refresh);
  document.addEventListener("visibilitychange",() => { if (!document.hidden) refresh(); });
})();
