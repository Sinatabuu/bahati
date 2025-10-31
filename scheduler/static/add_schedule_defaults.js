(function(){
  function qs(s, root){ return (root||document).querySelector(s); }

  async function fetchClientDefaults(clientId) {
    if (!clientId) return null;
    const resp = await fetch(`/service/ajax/client/${clientId}/defaults/`, { credentials: 'same-origin' });
    if (!resp.ok) return null;
    const json = await resp.json();
    return json.ok ? json.client : null;
  }

  function ensureDatalist(input, id, values) {
    if (!input) return;
    let list = document.getElementById(id);
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

  async function onClientChange() {
    const clientInput = qs('#id_client');            // assuming your form has id_client for the FK
    const clientName = qs('#id_client_name');        // if you keep a parallel client_name field
    const pickupAddr  = qs('#id_pickup_address');
    const pickupCity  = qs('#id_pickup_city');
    const pickupState = qs('#id_pickup_state');
    const dropAddr    = qs('#id_dropoff_address');
    const dropCity    = qs('#id_dropoff_city');
    const dropState   = qs('#id_dropoff_state');

    const clientId = clientInput && clientInput.value && /^\d+$/.test(clientInput.value) ? clientInput.value : null;
    if (!clientId) return;

    const c = await fetchClientDefaults(clientId);
    if (!c) return;

    // Only fill if empty; allow manual edits
    if (pickupAddr && !pickupAddr.value)   pickupAddr.value = c.pickup_address || '';
    if (pickupCity && !pickupCity.value)   pickupCity.value = c.pickup_city || '';
    if (pickupState && !pickupState.value) pickupState.value = c.pickup_state || '';
    if (dropAddr && !dropAddr.value)       dropAddr.value = c.dropoff_address || '';
    if (dropCity && !dropCity.value)       dropCity.value = c.dropoff_city || '';
    if (dropState && !dropState.value)     dropState.value = c.dropoff_state || '';

    // Suggestions via datalist
    if (pickupAddr)  ensureDatalist(pickupAddr,  'dl_pickup_addr_'  + clientId, [c.pickup_address]);
    if (pickupCity)  ensureDatalist(pickupCity,  'dl_pickup_city_'  + clientId, [c.pickup_city]);
    if (pickupState) ensureDatalist(pickupState, 'dl_pickup_state_' + clientId, [c.pickup_state]);
    if (dropAddr)    ensureDatalist(dropAddr,    'dl_drop_addr_'    + clientId, [c.dropoff_address]);
    if (dropCity)    ensureDatalist(dropCity,    'dl_drop_city_'    + clientId, [c.dropoff_city]);
    if (dropState)   ensureDatalist(dropState,   'dl_drop_state_'   + clientId, [c.dropoff_state]);
  }

  document.addEventListener('DOMContentLoaded', function(){
    const clientInput = qs('#id_client');
    if (!clientInput) return;
    clientInput.addEventListener('change', onClientChange);

    // Run once on load in case client is preselected
    onClientChange();
  });
})();
