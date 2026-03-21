// ViralForge v3 — State Management
const State = (() => {
  let _s = {
    trends:       [],
    patterns:     {},
    ideas:        [],        // scored options from engine
    winner:       null,      // selected best idea
    decision:     null,      // decision reasoning
    script:       null,      // generated script
    scriptId:     null,
    batchId:      null,
    video:        null,      // {id, status, progress}
    videos:       [],        // library
    stats:        {},
    weights:      {},
    fetchStatus:  "idle",
    lastFetch:    null,
    activeNiche:  "general",
    ui: {
      page:         "dashboard",
      scriptPanelOpen: false,
      publishPanelOpen: false,
    }
  };

  const _listeners = {};

  function on(event, fn) {
    if (!_listeners[event]) _listeners[event] = [];
    _listeners[event].push(fn);
  }

  function emit(event, data) {
    (_listeners[event] || []).forEach(fn => fn(data));
  }

  function get(key) {
    return key ? _s[key] : { ..._s };
  }

  function set(updates) {
    const changed = {};
    for (const [k, v] of Object.entries(updates)) {
      if (JSON.stringify(_s[k]) !== JSON.stringify(v)) {
        _s[k] = v;
        changed[k] = v;
      }
    }
    if (Object.keys(changed).length) {
      emit("change", changed);
      for (const k of Object.keys(changed)) {
        emit(`change:${k}`, changed[k]);
      }
    }
  }

  function setUi(updates) {
    set({ ui: { ..._s.ui, ...updates } });
  }

  return { on, emit, get, set, setUi };
})();
