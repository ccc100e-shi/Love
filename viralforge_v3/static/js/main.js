// ViralForge v3 — Main App Orchestration

// ── Actions ────────────────────────────────────────────────────────────────────
const Actions = {
  // Navigation
  nav(page) { UI.showPage(page); },
  navGenerate() { UI.showPage("generate"); },

  // ── Trends ──────────────────────────────────────────────────────────────────
  async fetchTrends(force = false) {
    const btn = UI.$("fetch-btn");
    if (btn) { btn.disabled = true; btn.textContent = "⟳ Fetching..."; }
    UI.setStatus("fetching", "FETCHING");
    UI.toast("Fetching YouTube RSS + Reddit...", "info");

    const res = await API.fetchTrends(
      ["trending", "entertainment", "gaming", "howto"],
      force
    );
    if (!res.ok) {
      UI.toast("Fetch failed: " + res.error, "err");
      UI.setStatus("error");
      if (btn) { btn.disabled = false; btn.textContent = "⚡ Fetch Live Trends"; }
      return;
    }

    // Poll until done
    let tries = 0;
    const poll = setInterval(async () => {
      const h = await API.health();
      const status = h.data?.fetch_status || "idle";

      if (status === "done" || tries > 40) {
        clearInterval(poll);
        const tr = await API.getTrends({ limit: 60 });
        if (tr.ok) {
          State.set({
            trends: tr.data.trends || [],
            lastFetch: tr.data.last_fetch,
            fetchStatus: "done",
          });
        }
        const pt = await API.getPatterns();
        if (pt.ok) State.set({ patterns: pt.data });

        await Actions.loadStats();
        UI.setStatus("done", "READY");
        UI.toast(`Trends loaded`, "ok");
        if (btn) { btn.disabled = false; btn.textContent = "⚡ Fetch Live Trends"; }
        UI.refreshDashboard();
        UI.renderTrends(State.get("trends"), State.get("ui").hookFilter || "");
      } else if (status.startsWith("error")) {
        clearInterval(poll);
        UI.setStatus("error", "ERROR");
        UI.toast("Fetch failed on server", "err");
        if (btn) { btn.disabled = false; btn.textContent = "⚡ Fetch Live Trends"; }
      }
      tries++;
    }, 1800);
  },

  setHookFilter(hook, el) {
    document.querySelectorAll(".filter-pill").forEach(p => p.classList.remove("active"));
    if (el) el.classList.add("active");
    State.set({ hookFilter: hook });
    UI.renderTrends(State.get("trends"), hook);
  },

  sortTrends(by) {
    const sorted = [...State.get("trends")].sort((a, b) => (b[by] || 0) - (a[by] || 0));
    State.set({ trends: sorted });
    UI.renderTrends(sorted, State.get("hookFilter") || "");
  },

  scriptFromTrend(trend) {
    // Pre-fill niche from trend source, navigate to generate
    UI.showPage("generate");
    UI.toast(`Trend loaded: "${trend.title.slice(0, 40)}..."`, "info");
    State.set({ prefillTrend: trend });
  },

  // ── Generate (Decision Engine) ───────────────────────────────────────────────
  async runEngine() {
    const niche = UI.$("gen-niche")?.value || "general";
    const btn   = UI.$("generate-btn");

    if (btn) { btn.disabled = true; btn.textContent = "⟳ Generating..."; }
    UI.setStatus("processing", "THINKING");
    UI.toast("Running Decision Engine — generating 10 options...", "info");

    // Clear previous results
    State.set({ ideas: [], winner: null, decision: null, script: null });
    UI.renderIdeas([], null, null);
    const scriptEl = UI.$("script-container");
    if (scriptEl) scriptEl.innerHTML = `<div class="empty"><div class="empty-sub">Generating script...</div></div>`;

    const res = await API.generate(niche);

    if (btn) { btn.disabled = false; btn.textContent = "✦ Generate"; }
    UI.setStatus("done", "READY");

    if (!res.ok) {
      UI.toast("Generation failed: " + res.error, "err");
      return;
    }

    const d = res.data;
    State.set({
      ideas:    d.options || [],
      winner:   d.winner,
      decision: d.decision,
      script:   d.script,
      scriptId: d.script_id,
      batchId:  d.batch_id,
      activeNiche: niche,
    });

    UI.renderIdeas(d.options, d.winner, d.decision);
    UI.renderScript(d.script, d.decision);
    await Actions.loadStats();

    UI.toast(`Done — ${(d.options||[]).length} options scored, winner selected`, "ok");

    // Auto-navigate to script tab if on generate page
    const scriptTab = document.querySelector('[data-tab="script"]');
    if (scriptTab) scriptTab.click();
  },

  // ── Video Build ──────────────────────────────────────────────────────────────
  async buildVideo() {
    const script   = State.get("script");
    const scriptId = State.get("scriptId");
    const palette  = UI.$("palette-select")?.value || "amber";

    if (!script) { UI.toast("No script to build — generate content first", "err"); return; }

    const btn = UI.$("generate-video-btn");
    if (btn) { btn.disabled = true; btn.textContent = "⟳ Starting..."; }

    const res = await API.generateVideo(scriptId, script, palette);
    if (!res.ok) {
      UI.toast("Video start failed: " + res.error, "err");
      if (btn) { btn.disabled = false; btn.textContent = "⚡ Build Video"; }
      return;
    }

    const videoId = res.data.video_id;
    State.set({ video: { id: videoId, status: "processing", progress: 0 } });
    UI.toast("Building video — check progress...", "info");

    UI.pollVideoProgress(videoId, () => {
      State.set({ video: { id: videoId, status: "done", progress: 100 } });
      Actions.loadStats();
    });
  },

  // ── Publish ──────────────────────────────────────────────────────────────────
  openPublish(videoId) {
    State.set({ publishVideoId: videoId });
    UI.showPage("publish");
    UI.renderPublish();
  },

  async copyCaption(videoId) {
    const res = await API.getCaption(videoId);
    if (!res.ok) { UI.toast("Caption not found", "err"); return; }

    const caption = res.data.caption || "";
    if (!caption) { UI.toast("No caption available", "err"); return; }

    // Show preview
    const prev = UI.$(`caption-preview-${videoId}`);
    if (prev) {
      prev.style.display = "block";
      prev.textContent = caption;
    }

    try {
      await navigator.clipboard.writeText(caption);
      UI.toast("Caption copied to clipboard!", "ok");
    } catch (e) {
      UI.toast("Copy failed — caption shown below", "info");
    }
  },

  tiktokUpload(videoId) {
    UI.toast("Opening TikTok — download your video first, then upload", "info");
    window.open("https://www.tiktok.com/upload", "_blank");
    Actions.copyCaption(videoId);
  },

  // ── Performance Logging ───────────────────────────────────────────────────────
  async logPerf() {
    const scriptId = UI.$("perf-script-id")?.value?.trim();
    const platform = UI.$("perf-platform")?.value;
    const views    = parseInt(UI.$("perf-views")?.value || "0");
    const likes    = parseInt(UI.$("perf-likes")?.value || "0");

    if (!scriptId || !views) { UI.toast("Script ID and views required", "err"); return; }

    const res = await API.logPerformance({ script_id: scriptId, platform, views, likes });
    if (res.ok) {
      UI.toast("Performance logged — pattern weights updated!", "ok");
      const wr = await API.weights();
      if (wr.ok) {
        State.set({ weights: wr.data.weights || {} });
        UI.renderWeights(wr.data.weights || {});
      }
    } else {
      UI.toast("Log failed: " + res.error, "err");
    }
  },

  // ── Helpers ──────────────────────────────────────────────────────────────────
  async loadStats() {
    const res = await API.stats();
    if (res.ok) State.set({ stats: res.data });
    UI.refreshDashboard();
  },

  async loadWeights() {
    const res = await API.weights();
    if (res.ok) {
      State.set({ weights: res.data.weights || {} });
      UI.renderWeights(res.data.weights || {});
    }
  },
};

// ── Initialization ─────────────────────────────────────────────────────────────
async function init() {
  // Load cached data
  const [tr, pt, st, wt] = await Promise.all([
    API.getTrends({ limit: 60 }),
    API.getPatterns(),
    API.stats(),
    API.weights(),
  ]);

  if (tr.ok && tr.data.trends?.length) {
    State.set({ trends: tr.data.trends, lastFetch: tr.data.last_fetch, fetchStatus: tr.data.status });
  }
  if (pt.ok) State.set({ patterns: pt.data });
  if (st.ok) State.set({ stats: st.data });
  if (wt.ok) State.set({ weights: wt.data.weights || {} });

  UI.refreshDashboard();
  UI.renderTrends(State.get("trends"), "");
  UI.renderWeights(State.get("weights"));

  // Health check
  const h = await API.health();
  if (h.ok && !h.data.has_key) {
    UI.toast("⚠️ ANTHROPIC_API_KEY not set — script generation will fail", "err");
  }

  UI.setStatus(tr.data?.status || "idle");

  // Refresh stats every 20s
  setInterval(Actions.loadStats, 20000);
}

// ── Tab switching (sub-tabs in Generate page) ──────────────────────────────────
function switchTab(tab, el) {
  document.querySelectorAll(".subtab-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".subtab-pane").forEach(p => p.classList.remove("active"));
  if (el) el.classList.add("active");
  const pane = document.getElementById(`tab-${tab}`);
  if (pane) pane.classList.add("active");
}

document.addEventListener("DOMContentLoaded", init);
