/* scheduler/static/scheduler/add_schedule_defaults.js
 * UX polish: spinner + disabled state while fetching client defaults.
 * Safe, no behavior change other than visuals and preventing mid-fetch edits.
 */

(function () {
  const DEBUG = !!window.__AUTO_DEBUG__;

  function log(...a){ if (DEBUG) console.log("[AUTOFILL]", ...a); }
  function warn(...a){ console.warn("[AUTOFILL]", ...a); }
  function $1(s, r){ return (r||document).querySelector(s); }
  function emit(el, type){ try{ el && el.dispatchEvent(new Event(type, {bubbles:true})); }catch{} }

  // --- Spinner helpers (auto-inject a small inline spinner near the client select)
  function ensureSpinnerFor(el){
    if (!el) return null;
    let holder = el.parentElement;
    if (!holder) return null;

    let wrap = holder.querySelector(".auto-spinner-wrap");
    if (!wrap) {
      wrap = document.createElement("span");
      wrap.className = "auto-spinner-wrap";
      wrap.style.display = "inline-flex";
      wrap.style.alignItems = "center";
      wrap.style.gap = "6px";
      wrap.style.marginLeft = "8px";
      holder.appendChild(wrap);
    }

    let sp = wrap.querySelector(".auto-spinner");
    if (!sp) {
      sp = document.createElement("span");
      sp.className = "auto-spinner";
      sp.setAttribute("aria-hidden", "true");
      sp.style.display = "none";
      sp.style.width = "16px";
      sp.style.height = "16px";
      sp.style.border = "2px solid #e5e7eb";        // light gray
      sp.style.borderTopColor = "#3b82f6";          // blue
      sp.style.borderRadius = "50%";
      sp.style.animation = "auto-spin 0.8s linear infinite";
      wrap.appendChild(sp);

      // inject keyframes once
      if (!document.getElementById("auto-spinner-style")) {
        const st = document.createElement("style");
        st.id = "auto-spinner-style";
        st.textContent = "@keyframes auto-spin{to{transform:rotate(360deg)}}";
        document.head.appendChild(st);
      }
    }
    return sp;
  }
  function showSpinner(sp){ if (sp) sp.style.display = "inline-block"; }
  function hideSpinner(sp){ if (sp) sp.style.display = "none"; }

  function forceSet(el, value){
    if (!el) return false;
    const v = value == null ? "" : String(value);
    el.value = v;
    emit(el, "input");
    emit(el, "change");
    try {
      el.style.transition = "background 150ms";
      el.style.background = "#fff7ed"; // light orange flash
      setTimeout(() => (el.style.background = ""), 220);
    } catch {}
    return true;
  }

  async function fetchJSON(url){
    try{
      const res = await fetch(url, { credentials: "same-origin" });
      if (!res.ok) { warn("HTTP", res.status, url); return null; }
      const ct = (res.headers.get("content-type")||"").toLowerCase();
      if (!ct.includes("application/json")) { warn("non-JSON (maybe login redirect?)", url, ct); return null; }
      const data = await res.json();
      log("OK", url, data);
      return data;
    }catch(e){ warn("fetch error", url, e); return null; }
  }

  async function getClientDefaults(clientId){
    const d = await fetchJSON(`/service/api/client/${clientId}/mini/`);
    if (!d) return null;
    return {
      pickup_address: d.pickup_address || "",
      dropoff_address: d.dropoff_address || "",
      pickup_time: d.pickup_time || d.start_time || "",
      notes: d.notes || "",
      pickup_city: d.pickup_city || "",
      pickup_state: d.pickup_state || "",
      dropoff_city: d.dropoff_city || "",
      dropoff_state: d.dropoff_state || "",
      _source: "mini"
    };
  }

  function findClientSelect(){
    return (
      document.getElementById("id_client") ||
      document.getElementById("id_client_select") ||
      $1('select[name$="client"]') ||
      $1('select[id*="client"]')
    );
  }

  function locateFields(){
    return {
      pickup:  document.getElementById("id_pickup_address")  || $1('[name$="pickup_address"]'),
      dropoff: document.getElementById("id_dropoff_address") || $1('[name$="dropoff_address"]'),
      start:   document.getElementById("id_start_time")      || $1('[name$="start_time"],[name$="pickup_time"]'),
      notes:   document.getElementById("id_notes")           || $1('[name$="notes"]'),
      pCity:   document.getElementById("id_pickup_city")     || $1('[name$="pickup_city"]'),
      pState:  document.getElementById("id_pickup_state")    || $1('[name$="pickup_state"]'),
      dCity:   document.getElementById("id_dropoff_city")    || $1('[name$="dropoff_city"]'),
      dState:  document.getElementById("id_dropoff_state")   || $1('[name$="dropoff_state"]'),
    };
  }

  function setDisabled(fields, flag){
    Object.values(fields).forEach(el => { if (el && "disabled" in el) el.disabled = flag; });
  }

  async function handleClientChange(clientSelect){
    const raw = (clientSelect.value || "").trim();
    if (!/^\d+$/.test(raw)) { warn("client id not numeric:", raw); return; }
    const clientId = raw;

    const sp = ensureSpinnerFor(clientSelect);
    const fields = locateFields();

    try{
      showSpinner(sp);
      setDisabled(fields, true);
      log("fetching defaults for", clientId);
      const d = await getClientDefaults(clientId);
      if (!d) return;

      const filled = [];
      if (forceSet(fields.pickup,  d.pickup_address)) filled.push("pickup_address");
      if (forceSet(fields.dropoff, d.dropoff_address)) filled.push("dropoff_address");
      if (forceSet(fields.start,   d.pickup_time))     filled.push("start_time/pickup_time");
      if (forceSet(fields.notes,   d.notes))           filled.push("notes");
      if (d.pickup_city   && forceSet(fields.pCity,  d.pickup_city))   filled.push("pickup_city");
      if (d.pickup_state  && forceSet(fields.pState, d.pickup_state))  filled.push("pickup_state");
      if (d.dropoff_city  && forceSet(fields.dCity,  d.dropoff_city))  filled.push("dropoff_city");
      if (d.dropoff_state && forceSet(fields.dState, d.dropoff_state)) filled.push("dropoff_state");
      log("filled:", filled.join(", ") || "(none)");
    } finally {
      hideSpinner(sp);
      setDisabled(fields, false);
    }
  }

  function ready(fn){ if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }

  ready(function(){
    const clientSelect = findClientSelect();
    if (!clientSelect) { warn("No client <select> found. Expected #id_client or name$='client'."); return; }

    const onChange = () => handleClientChange(clientSelect);
    clientSelect.addEventListener("change", onChange);
    clientSelect.addEventListener("input", onChange);

    if (clientSelect.value) onChange(); // prefill on edit
  });
})();

// --- Mobile: gently scroll first empty field into view after autofill
(function(){
  const isSmall = () => window.matchMedia("(max-width: 640px)").matches;
  const firstFocusableEmpty = () => {
    const sel = [
      "#id_pickup_address", "#id_dropoff_address", "#id_start_time", "#id_notes",
      "[name$='pickup_address']", "[name$='dropoff_address']", "[name$='start_time']", "[name$='pickup_time']", "[name$='notes']"
    ].join(",");
    return Array.from(document.querySelectorAll(sel)).find(el => el && !el.value);
  };
  document.addEventListener("autofill:done", () => {
    if (!isSmall()) return;
    const el = firstFocusableEmpty();
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.focus({ preventScroll: true });
    }
  });
})();
