(function() {
  function byId(id){ return document.getElementById(id); }

  // Build or reuse a datalist and attach it to an input
  function ensureDatalist(input, id, values) {
    let list = byId(id);
    if (!list) {
      list = document.createElement('datalist');
      list.id = id;
      document.body.appendChild(list);
    }
    list.innerHTML = '';
    (values || []).forEach(v => {
      if (v && String(v).trim() !== '') {
        const opt = document.createElement('option');
        opt.value = v;
        list.appendChild(opt);
      }
    });
    input.setAttribute('list', id);
  }

  // Apply client defaults to a row/form
  async function applyClientDefaults(rootEl, clientId) {
    if (!clientId) return;
    try {
      const resp = await fetch(`/service/admin/ajax/client/${clientId}/defaults/`, { credentials: 'same-origin' });
      const json = await resp.json();
      if (!json.ok) return;
      const c = json.client;

      // Find inputs by their name attribute within this inline/form row
      const fields = {
        pickup_address:   rootEl.querySelector('[name$="pickup_address"]'),
        pickup_city:      rootEl.querySelector('[name$="pickup_city"]'),
        pickup_state:     rootEl.querySelector('[name$="pickup_state"]'),
        dropoff_address:  rootEl.querySelector('[name$="dropoff_address"]'),
        dropoff_city:     rootEl.querySelector('[name$="dropoff_city"]'),
        dropoff_state:    rootEl.querySelector('[name$="dropoff_state"]'),
      };

      // Auto-fill where empty
      if (fields.pickup_address && !fields.pickup_address.value) fields.pickup_address.value = c.pickup_address || '';
      if (fields.pickup_city && !fields.pickup_city.value)       fields.pickup_city.value = c.pickup_city || '';
      if (fields.pickup_state && !fields.pickup_state.value)     fields.pickup_state.value = c.pickup_state || '';
      if (fields.dropoff_address && !fields.dropoff_address.value) fields.dropoff_address.value = c.dropoff_address || '';
      if (fields.dropoff_city && !fields.dropoff_city.value)       fields.dropoff_city.value = c.dropoff_city || '';
      if (fields.dropoff_state && !fields.dropoff_state.value)     fields.dropoff_state.value = c.dropoff_state || '';

      // Provide suggestions (datalist). Here we just give the client's default;
      // you can expand to include prior values too.
      if (fields.pickup_address)  ensureDatalist(fields.pickup_address,  'dl_pickup_addr_'  + clientId, [c.pickup_address]);
      if (fields.pickup_city)     ensureDatalist(fields.pickup_city,     'dl_pickup_city_'  + clientId, [c.pickup_city]);
      if (fields.pickup_state)    ensureDatalist(fields.pickup_state,    'dl_pickup_state_' + clientId, [c.pickup_state]);
      if (fields.dropoff_address) ensureDatalist(fields.dropoff_address, 'dl_drop_addr_'    + clientId, [c.dropoff_address]);
      if (fields.dropoff_city)    ensureDatalist(fields.dropoff_city,    'dl_drop_city_'    + clientId, [c.dropoff_city]);
      if (fields.dropoff_state)   ensureDatalist(fields.dropoff_state,   'dl_drop_state_'   + clientId, [c.dropoff_state]);

    } catch (e) {
      console.warn('Client defaults fetch failed', e);
    }
  }

  function bindRow(rootEl) {
    // Admin autocomplete renders a hidden input that stores client PK.
    // We target both raw_id and admin-autocomplete widgets.
    const clientPkInput = rootEl.querySelector('input[name$="client"]'); // raw_id case
    const autoHidden = rootEl.querySelector('input[name$="client"][type="hidden"]'); // autocomplete hidden
    const widgetEl = rootEl.querySelector('.related-widget-wrapper, .admin-autocomplete');

    function currentClientId() {
      if (autoHidden && autoHidden.value) return autoHidden.value;
      if (clientPkInput && clientPkInput.value && /^\d+$/.test(clientPkInput.value)) return clientPkInput.value;
      return null;
    }

    // initial apply (e.g., when editing an existing row)
    const initialId = currentClientId();
    if (initialId) applyClientDefaults(rootEl, initialId);

    // Listen to change events on the autocomplete/select
    rootEl.addEventListener('change', (ev) => {
      if (!ev.target) return;
      // For admin autocomplete, the hidden input [name$="client"] gets updated.
      if (ev.target.matches('select, input, .admin-autocomplete')) {
        const cid = currentClientId();
        if (cid) applyClientDefaults(rootEl, cid);
      }
    });

    // For inline "Add another" rows, re-bind after they appear
  }

  // Bind on DOM ready + after inline forms are added
  function bindAll() {
    // Each inline row or single form
    document.querySelectorAll('.inline-related, .change-form').forEach(bindRow);
  }

  document.addEventListener('DOMContentLoaded', bindAll);
  document.addEventListener('formset:added', function(event, $row, formsetName) {
    // Django Admin triggers this when new inline rows are added
    bindAll();
  });
})();
