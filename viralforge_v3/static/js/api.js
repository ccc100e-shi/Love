// ViralForge v3 — API Layer
const API = (() => {
  const BASE = "";

  async function _req(path, opts = {}) {
    try {
      const r = await fetch(BASE + path, {
        headers: { "Content-Type": "application/json" },
        ...opts,
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
      return { ok: true, data };
    } catch (e) {
      console.error(`[API] ${path}:`, e.message);
      return { ok: false, error: e.message };
    }
  }

  const get  = (path)        => _req(path);
  const post = (path, body)  => _req(path, { method: "POST", body: JSON.stringify(body) });

  return {
    health:        ()      => get("/api/health"),
    stats:         ()      => get("/api/stats"),
    weights:       ()      => get("/api/weights"),

    fetchTrends:   (cats, force) => post("/api/trends/fetch", { categories: cats, force }),
    getTrends:     (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return get(`/api/trends${q ? "?" + q : ""}`);
    },
    getPatterns:   ()      => get("/api/trends/patterns"),

    generate:      (niche) => post("/api/generate", { niche }),
    getScripts:    ()      => get("/api/scripts"),

    generateVideo: (scriptId, script, palette) =>
      post("/api/video/generate", { script_id: scriptId, script, palette }),
    videoStatus:   (id)    => get(`/api/video/status/${id}`),
    getVideos:     ()      => get("/api/videos"),
    getCaption:    (id)    => get(`/api/publish/caption/${id}`),
    getExport:     (id)    => get(`/api/video/${id}/export`),

    logPerformance: (data) => post("/api/performance", data),

    downloadUrl:   (id)    => `/api/video/${id}/download`,
    thumbnailUrl:  (id)    => `/api/video/${id}/thumbnail`,
  };
})();
