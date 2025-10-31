/* scheduler/static/scheduler/client_typeahead.js
 * Progressive enhancement: adds a "Search clients…" box above the existing <select>.
 * On input, fetches /service/api/clients/search, rebuilds <select> options, and preserves selection.
 * Works alongside your autofill script (select change still fires).
 */

(function () {
  const DEBUG = !!window.__AUTO_DEBUG__;
  const API = "/service/api/clients/search/";

  function log(...a){ if (DEBUG) console.log("[TYPEAHEAD]", ...a); }
  function $(s, r){ return (r||document).querySelector(s); }
  function h(tag, props = {}, children = []) {
    const el = document.createElement(tag);
    Object.entries(props).forEach(([k, v]) => {
      if (k === "class") el.className = v;
      else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
      else el.setAttribute(k, v);
    });
    (Array.isArray(children) ? children : [children]).forEach(ch => {
      if (ch == null) return;
      if (typeof ch === "string") el.appendChild(document.createTextNode(ch));
      else el.appendChild(ch);
    });
    return el;
  }

  function debounce(fn, ms){
    let t;
    return function(...args){
      clearTimeout(t);
      t = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  async function searchClients(q, limit = 20){
    const url = new URL(API, window.location.origin);
    if (q) url.searchParams.set("q", q);
    if (limit) url.searchParams.set("limit", String(limit));
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) return { results: [], has_more: false };
    const ct = (res.headers.get("content-type") || "").toLowerCase();
    if (!ct.includes("application/json")) return { results: [], has_more: false };
    return res.json();
  }

  function rebuildOptions(select, results, keepValue) {
    const old = keepValue ?? select.value;
    // Clear
    while (select.firstChild) select.removeChild(select.firstChild);

    // Optional placeholder
    select.appendChild(h("option", { value: "" }, ["— Select client —"]));

    // New options
    for (const r of results) {
      const label = r.name || `Client #${r.id}`;
      select.appendChild(h("option", { value: String(r.id) }, [label]));
    }

    // Try to restore previous selection if still present
    if (old) {
      const opt = Array.from(select.options).find(o => o.value === String(old));
      if (opt) {
        opt.selected = true;
      }
    }

    // Emit change/input so downstream listeners (autofill) can react
    select.dispatchEvent(new Event("input", { bubbles: true }));
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function injectUI(select) {
    // Build wrapper: Search input above the select
    const wrap = h("div", { class: "space-y-2", style: { width: "100%" } }, []);
    const search = h("input", {
      type: "search",
      placeholder: "Search clients…",
      id: "id_client_search",
      class: "block w-full border rounded-md px-3 py-2",
      autocomplete: "off",
      "aria-label": "Search clients"
    });

    // Put wrapper before select, and move select inside for neat grouping
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(search);
    wrap.appendChild(select);

    // Status line (optional)
    const status = h("div", { class: "text-xs text-gray-500", style: { minHeight: "1em" } }, []);
    wrap.appendChild(status);

    // Debounced handler
    const run = debounce(async function(){
      const q = search.value.trim();
      status.textContent = q ? "Searching…" : "";
      try {
        const { results, has_more } = await searchClients(q, 20);
        rebuildOptions(select, results);
        status.textContent = (q && has_more)
          ? `Showing ${results.length}+ results… refine your search`
          : (q ? `Found ${results.length}` : "");
      } catch (e) {
        status.textContent = "Search failed";
      }
    }, 250);

    // Events
    search.addEventListener("input", run);
    search.addEventListener("keydown", (e) => {
      // Enter: focus select to quickly pick
      if (e.key === "Enter") {
        e.preventDefault();
        select.focus();
      }
    });

    // Initial load: leave select as-is (no surprises).
    return { search, status };
  }

  function ready(fn){ if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }

  ready(function(){
    const select =
      document.getElementById("id_client") ||
      document.getElementById("id_client_select") ||
      $('select[name$="client"]') || $('select[id*="client"]');

    if (!select) { return; }
    log("Enhancing client select with type-ahead");

    injectUI(select);
    // We do NOT auto-search on load—keeps current UX intact.
    // Users can type to search; the select options refresh and your autofill continues to work.
  });
})();
