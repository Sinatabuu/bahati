// Works in Django Admin including inlines.
(function () {
  function ready(fn){ if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }
  async function fetchMini(id) {
    try {
      const r = await fetch(`/service/api/client/${id}/mini/`, { credentials: "same-origin" });
      if (!r.ok) return null;
      const ct = (r.headers.get("content-type")||"").toLowerCase();
      if (!ct.includes("application/json")) return null;
      return await r.json();
    } catch { return null; }
  }
  function findField(root, suffixes) {
    for (const suf of suffixes) {
      let el = root.querySelector(`[id$="${suf}"]`); if (el) return el;
      el = root.querySelector(`[name$="${suf}"]`);    if (el) return el;
    }
    return null;
  }
  function set(el, v){ if (!el) return; el.value = v || ""; el.dispatchEvent(new Event("input", {bubbles:true})); el.dispatchEvent(new Event("change", {bubbles:true})); }
  ready(function () {
    document.body.addEventListener("change", async function (e) {
      const el = e.target;
      const isClient = el.tagName === "SELECT" && ((el.id && el.id.endsWith("client")) || (el.name && el.name.endsWith("client")));
      if (!isClient) return;
      const id = /^\d+$/.test(el.value) ? el.value : null;
      if (!id) return;

      const row = el.closest(".inline-related, .form-row, .form-group, fieldset, form") || document;
      const d = await fetchMini(id); if (!d) return;
      set(findField(row, ["pickup_address"]),  d.pickup_address);
      set(findField(row, ["dropoff_address"]), d.dropoff_address);
      set(findField(row, ["start_time","pickup_time"]), d.pickup_time || d.start_time);
      set(findField(row, ["notes"]), d.notes);
    });
  });
})();
