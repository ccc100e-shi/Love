// ViralForge v3 — UI Rendering Layer

const UI = (() => {
  // ── Utilities ───────────────────────────────────────────────────────────────
  const $ = id => document.getElementById(id);
  const qs = sel => document.querySelector(sel);
  const fmtN = n => n > 1e6 ? `${(n/1e6).toFixed(1)}M` : n > 1e3 ? `${Math.round(n/1e3)}K` : `${n||0}`;
  const fmtSrc = s => s ? s.replace("yt:", "YT/").replace("reddit:", "r/") : "";
  const fmtDate = s => s ? new Date(s).toLocaleString([], {dateStyle:"short",timeStyle:"short"}) : "—";
  const clamp = (n,a,b) => Math.max(a,Math.min(b,n));

  const HOOK_COLORS = {
    curiosity_gap:     "#f5a623",
    pattern_interrupt: "#ff7043",
    fear_hook:         "#ef5350",
    number_hook:       "#66bb6a",
    transformation:    "#ab47bc",
    question_hook:     "#42a5f5",
    list_format:       "#ec407a",
    neutral:           "#546e7a",
  };

  function scoreColor(s) {
    return s >= 75 ? "var(--green)" : s >= 50 ? "var(--amber)" : "var(--red)";
  }

  // ── SVG Ring Score ──────────────────────────────────────────────────────────
  function ring(score, size = 56, strokeW = 5) {
    const s = score || 0;
    const r = (size - strokeW * 2) / 2;
    const circ = 2 * Math.PI * r;
    const fill = circ * (1 - s / 100);
    const col = scoreColor(s);
    const cx = size / 2, cy = size / 2;
    return `<svg width="${size}" height="${size}" style="transform:rotate(-90deg);flex-shrink:0">
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--bg3)" stroke-width="${strokeW}"/>
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${col}"
        stroke-width="${strokeW}" stroke-dasharray="${circ.toFixed(2)}"
        stroke-dashoffset="${fill.toFixed(2)}" stroke-linecap="round"
        style="transition:stroke-dashoffset .8s ease"/>
      <text x="${cx}" y="${cy}" dominant-baseline="middle" text-anchor="middle"
        fill="${col}" font-size="${(size*.22).toFixed(1)}" font-weight="bold"
        font-family="var(--font-mono)"
        style="transform:rotate(90deg);transform-origin:${cx}px ${cy}px">${s}</text>
    </svg>`;
  }

  // ── Toast ───────────────────────────────────────────────────────────────────
  function toast(msg, type = "info") {
    const z = $("toast-zone");
    if (!z) return;
    const el = document.createElement("div");
    el.className = `toast toast-${type}`;
    el.textContent = ({ ok:"✓ ", err:"✗ ", info:"→ " }[type] || "→ ") + msg;
    z.appendChild(el);
    setTimeout(() => el.classList.add("toast-fade"), 3200);
    setTimeout(() => el.remove(), 3700);
  }

  // ── Bar Chart ───────────────────────────────────────────────────────────────
  function barChart(data, colorFn = () => "var(--amber)") {
    const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
    const max = entries[0]?.[1] || 1;
    return entries.map(([k, v]) => {
      const pct = Math.round((v / max) * 100);
      const col = typeof colorFn === "function" ? colorFn(k) : colorFn;
      return `<div class="bar-row">
        <div class="bar-meta">
          <span class="bar-name" style="color:${col}">${k.replace(/_/g," ")}</span>
          <span class="bar-val">${v}</span>
        </div>
        <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${col}"></div></div>
      </div>`;
    }).join("");
  }

  // ── Tag ─────────────────────────────────────────────────────────────────────
  function tag(label, color = "var(--amber)") {
    return `<span class="tag" style="color:${color};border-color:${color}30;background:${color}12">${label}</span>`;
  }

  // ── Pages ───────────────────────────────────────────────────────────────────
  function showPage(name) {
    document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
    document.querySelectorAll(".nav-btn").forEach(b => b.classList.toggle("active", b.dataset.page === name));
    const pg = $(`page-${name}`);
    if (pg) pg.classList.add("active");
    State.setUi({ page: name });
    if (name === "videos")   renderVideos();
    if (name === "publish")  renderPublish();
    if (name === "dashboard") refreshDashboard();
  }

  // ── Dashboard ───────────────────────────────────────────────────────────────
  function refreshDashboard() {
    const s = State.get("stats");
    const p = State.get("patterns");

    const set = (id, val) => { const el = $(id); if (el) el.textContent = val; };
    set("stat-trends",  s.trends_count || 0);
    set("stat-scripts", s.scripts_count || 0);
    set("stat-videos",  s.videos_count || 0);
    set("stat-score",   s.avg_score ? s.avg_score + "/100" : "—");
    set("stat-hook",    (s.top_hook || "—").replace(/_/g," "));
    set("stat-learned", (s.top_learned_pattern || "—").replace("hook:","").replace("trigger:","").replace(/_/g," "));

    // Hook chart
    const hc = $("dash-hook-chart");
    if (hc && p.hook_dist) {
      hc.innerHTML = barChart(p.hook_dist, k => HOOK_COLORS[k] || "var(--text3)");
    }

    // Trigger chart
    const tc = $("dash-trigger-chart");
    if (tc && p.trigger_dist) {
      tc.innerHTML = barChart(p.trigger_dist, () => "var(--purple)");
    }

    // Top 5 trends
    const trends = State.get("trends").slice(0, 6);
    const tt = $("dash-top-trends");
    if (tt) {
      if (!trends.length) {
        tt.innerHTML = `<div class="empty"><div class="empty-icon">↑</div>
          <div class="empty-title">No data yet</div>
          <div class="empty-sub">Go to Trends and click Fetch Live Trends</div></div>`;
      } else {
        tt.innerHTML = trends.map((t, i) => {
          const a = t.analysis || {};
          const hc = HOOK_COLORS[a.hook_type] || "var(--text3)";
          return `<div class="top-trend-row" onclick="Actions.scriptFromTrend(${JSON.stringify(t).replace(/"/g,"&quot;")})">
            <span class="rank">${i + 1}</span>
            <div class="flex-1">
              <div class="trend-title-sm">${t.title}</div>
              ${tag((a.hook_type||"neutral").replace(/_/g," "), hc)}
            </div>
            <span class="score-sm" style="color:${scoreColor(t.virality_score)}">${t.virality_score||0}</span>
          </div>`;
        }).join("");
      }
    }
  }

  // ── Trend List ───────────────────────────────────────────────────────────────
  function renderTrends(trends, hookFilter = "") {
    const el = $("trends-list");
    if (!el) return;

    let data = [...trends];
    if (hookFilter) data = data.filter(t => t.analysis?.hook_type === hookFilter);

    const meta = $("trends-meta");
    if (meta) meta.textContent = `${data.length} trends · sorted by virality score`;

    if (!data.length) {
      el.innerHTML = `<div class="empty">
        <div class="empty-icon">↑</div>
        <div class="empty-title">No trends ${hookFilter ? "match filter" : "loaded"}</div>
        <div class="empty-sub">${hookFilter ? "Try a different filter" : "Click Fetch Live Trends"}</div>
      </div>`;
      return;
    }

    el.innerHTML = `<div class="trends-grid">${data.map(t => {
      const a = t.analysis || {};
      const hc = HOOK_COLORS[a.hook_type] || "#546e7a";
      const triggers = (a.triggers || []).slice(0, 2).map(tr => tag(tr, "var(--purple)")).join("");
      return `<div class="trend-card" onclick="Actions.scriptFromTrend(${JSON.stringify(t).replace(/"/g,"&quot;")})">
        <div class="trend-title">${t.title}</div>
        <div class="trend-tags">
          ${tag((a.hook_type||"neutral").replace(/_/g," "), hc)}
          ${triggers}
        </div>
        <div class="trend-footer">
          <span class="trend-views">${fmtN(t.views)} · ${fmtSrc(t.source)}</span>
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-family:var(--mono);font-weight:800;color:${scoreColor(t.virality_score)}">${t.virality_score||0}</span>
            <button class="btn btn-xs btn-primary" onclick="event.stopPropagation();Actions.navGenerate()">Use →</button>
          </div>
        </div>
      </div>`;
    }).join("")}</div>`;
  }

  // ── Ideas Grid (Decision Engine output) ─────────────────────────────────────
  function renderIdeas(options, winner, decision) {
    const el = $("ideas-container");
    if (!el) return;

    if (!options?.length) {
      el.innerHTML = `<div class="empty"><div class="empty-icon">✦</div>
        <div class="empty-title">No ideas generated yet</div>
        <div class="empty-sub">Select a niche and click Generate</div></div>`;
      return;
    }

    const winnerIdx = winner?.idx ?? options[0]?.idx ?? 0;

    el.innerHTML = options.map((opt, i) => {
      const isWinner = opt.idx === winnerIdx;
      const sc = opt.scores || {};
      const dims = ["hook_strength","curiosity_gap","emotional_trigger","trend_alignment","retention_arc","clarity"];
      const dimBars = dims.map(d => {
        const v = sc[d] || 0;
        return `<div class="dim-row">
          <span class="dim-name">${d.replace(/_/g," ")}</span>
          <div class="dim-track"><div class="dim-fill" style="width:${v*10}%;background:${v>=7?"var(--green)":v>=5?"var(--amber)":"var(--red)"}"></div></div>
          <span class="dim-val">${v}/10</span>
        </div>`;
      }).join("");

      return `<div class="idea-card ${isWinner ? "idea-winner" : ""}">
        ${isWinner ? `<div class="winner-badge">🏆 AI SELECTED</div>` : ""}
        <div class="idea-rank">#${i + 1} · Score: <span style="color:${scoreColor(opt.virality_score)};font-weight:800">${opt.virality_score}</span></div>
        <div class="idea-title">${opt.title || ""}</div>
        <div class="idea-hook">"${opt.hook || ""}"</div>
        <div class="idea-tags">
          ${tag((opt.hook_type||"").replace(/_/g," "), HOOK_COLORS[opt.hook_type]||"var(--text3)")}
          ${tag(opt.primary_trigger||"", "var(--purple)")}
          ${tag(opt.structure||"", "var(--blue)")}
        </div>
        <div class="idea-dims">${dimBars}</div>
        ${isWinner && decision ? `<div class="why-wins">
          <div class="why-label">WHY THIS WINS</div>
          <div class="why-text">${decision.why_wins || ""}</div>
          <div class="why-meta">
            <span>🎯 ${decision.predicted_views_range||""}</span>
            <span>⚡ ${decision.strongest_element||""}</span>
          </div>
        </div>` : ""}
      </div>`;
    }).join("");
  }

  // ── Script View ──────────────────────────────────────────────────────────────
  function renderScript(script, decision) {
    const el = $("script-container");
    if (!el || !script) return;

    const scenes = script.scenes || script.script || [];
    const cs = script.captions_style || {};

    el.innerHTML = `
      <div class="script-header">
        <div>
          <div class="script-title">${script.title || ""}</div>
          <div class="script-hook">"${script.hook || ""}"</div>
        </div>
        <div class="script-meta-right">
          <div class="script-meta-item"><span class="meta-label">DURATION</span><span class="meta-val">${script.total_duration||"?"}s</span></div>
          <div class="script-meta-item"><span class="meta-label">SCENES</span><span class="meta-val">${scenes.length}</span></div>
        </div>
      </div>

      <div class="scene-timeline">
        ${scenes.map((sc, i) => `
          <div class="scene-block phase-${sc.phase||"body"}">
            <div class="scene-header">
              <span class="scene-phase">${(sc.phase||"").toUpperCase()}</span>
              <span class="scene-time">${sc.start_time||0}s–${sc.end_time||"?"}s</span>
              <span class="scene-trans">${sc.transition||"cut"}</span>
            </div>
            <div class="scene-spoken">${sc.spoken_text||""}</div>
            <div class="scene-caption">📺 "${sc.caption_text||""}"</div>
            <div class="scene-visual">📽 ${sc.visual_direction||sc.visual||""}</div>
          </div>`).join("")}
      </div>

      <div class="script-footer-grid">
        <div class="card">
          <div class="card-header">MUSIC</div>
          <div class="card-body">${script.music_direction||"—"}</div>
        </div>
        <div class="card">
          <div class="card-header">THUMBNAIL CONCEPT</div>
          <div class="card-body">${script.thumbnail_concept||"—"}</div>
        </div>
      </div>

      <div class="hashtag-row">${(script.hashtags||[]).map(h=>tag(h,"var(--blue)")).join("")}</div>

      ${decision?.critical_execution_tip ? `
      <div class="execution-tip">
        <span class="tip-icon">⚡</span>
        <span><strong>Critical execution tip:</strong> ${decision.critical_execution_tip}</span>
      </div>` : ""}
    `;
  }

  // ── Video Library ────────────────────────────────────────────────────────────
  function renderVideos() {
    API.getVideos().then(res => {
      if (!res.ok) return;
      const vids = res.data.videos || [];
      State.set({ videos: vids });
      const el = $("videos-list");
      if (!el) return;

      if (!vids.length) {
        el.innerHTML = `<div class="empty"><div class="empty-icon">▶</div>
          <div class="empty-title">No videos yet</div>
          <div class="empty-sub">Generate a script and click ⚡ Build Video</div></div>`;
        return;
      }

      el.innerHTML = vids.map(v => `
        <div class="video-card">
          <div class="video-thumb-wrap">
            ${v.has_thumb
              ? `<img src="${API.thumbnailUrl(v.id)}" class="video-thumb" alt="thumb" onerror="this.parentElement.innerHTML='🎬'">`
              : `<div class="video-thumb-placeholder">🎬</div>`}
          </div>
          <div class="video-info">
            <div class="video-title">${v.title||"Untitled"}</div>
            <div class="video-badges">
              <span class="badge badge-${v.status==="done"?"green":v.status==="processing"?"amber":"red"}">${v.status}</span>
              ${v.has_video ? `<span class="badge badge-blue">9:16 READY</span>` : ""}
              ${v.file_size_mb ? `<span class="badge badge-dim">${v.file_size_mb}MB</span>` : ""}
            </div>
            ${v.status==="processing" ? `
              <div class="progress-wrap">
                <div class="progress-fill" id="vprog-${v.id}" style="width:0%"></div>
              </div>` : ""}
            <div class="video-date">${fmtDate(v.created_at)}</div>
            <div class="video-actions">
              ${v.has_video ? `<a class="btn btn-sm btn-primary" href="${API.downloadUrl(v.id)}">⬇ Download MP4</a>` : ""}
              ${v.has_export ? `<button class="btn btn-sm btn-ghost" onclick="Actions.openPublish('${v.id}')">📤 Publish</button>` : ""}
            </div>
          </div>
          <div>${ring(v.virality_score||0, 52)}</div>
        </div>`).join("");
    });
  }

  // ── Publish Panel ─────────────────────────────────────────────────────────
  function renderPublish() {
    const el = $("publish-container");
    if (!el) return;
    const vids = State.get("videos").filter(v => v.has_video);
    if (!vids.length) {
      el.innerHTML = `<div class="empty"><div class="empty-icon">📤</div>
        <div class="empty-title">No videos ready to publish</div>
        <div class="empty-sub">Build a video first</div></div>`;
      return;
    }
    el.innerHTML = `<div class="publish-grid">${vids.map(v => `
      <div class="publish-card" id="pub-${v.id}">
        <div class="pub-title">${v.title||"Untitled"}</div>
        <div class="pub-platforms">
          <div class="platform-block">
            <div class="platform-name">📱 TikTok</div>
            <div class="platform-note">Manual upload — automated TikTok uploads require verified business API access.</div>
            <button class="btn btn-sm btn-primary" onclick="Actions.tiktokUpload('${v.id}')">Open TikTok Upload</button>
            <button class="btn btn-sm btn-ghost" onclick="Actions.copyCaption('${v.id}')">📋 Copy Caption</button>
          </div>
          <div class="platform-block">
            <div class="platform-name">▶ YouTube Shorts</div>
            <div class="platform-note">Manual upload via YouTube Studio. Title, description, and hashtags prepared.</div>
            <a class="btn btn-sm btn-primary" href="https://studio.youtube.com" target="_blank">Open YouTube Studio</a>
            <button class="btn btn-sm btn-ghost" onclick="Actions.copyCaption('${v.id}')">📋 Copy Caption</button>
          </div>
        </div>
        <div id="caption-preview-${v.id}" class="caption-preview" style="display:none"></div>
      </div>`).join("")}</div>`;
  }

  // ── Weight Learner display ───────────────────────────────────────────────────
  function renderWeights(weights) {
    const el = $("weights-display");
    if (!el) return;
    const sorted = Object.entries(weights).sort((a,b) => b[1]-a[1]);
    el.innerHTML = sorted.map(([k, w]) => {
      const pct = Math.round(clamp((w - 0.2) / 2.3 * 100, 0, 100));
      const col = w > 1.2 ? "var(--green)" : w < 0.8 ? "var(--red)" : "var(--amber)";
      return `<div class="bar-row">
        <div class="bar-meta">
          <span class="bar-name" style="color:${col}">${k.replace(/_/g," ")}</span>
          <span class="bar-val">${w.toFixed(3)}</span>
        </div>
        <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${col}"></div></div>
      </div>`;
    }).join("");
  }

  // ── Status bar update ────────────────────────────────────────────────────────
  function setStatus(status, message = "") {
    const dot  = $("status-dot");
    const text = $("status-text");
    if (!dot || !text) return;

    dot.className = "status-dot";
    if (status === "fetching" || status === "processing") {
      dot.classList.add("busy");
      text.textContent = message || "PROCESSING";
    } else if (status === "done" || status === "ready") {
      text.textContent = message || "READY";
    } else if (status === "error") {
      dot.classList.add("error-dot");
      text.textContent = message || "ERROR";
    } else {
      dot.classList.add("idle");
      text.textContent = "IDLE";
    }
  }

  // ── Video progress polling ────────────────────────────────────────────────────
  function pollVideoProgress(videoId, onDone) {
    let tries = 0;
    const interval = setInterval(async () => {
      const res = await API.videoStatus(videoId);
      if (!res.ok || tries > 120) {
        clearInterval(interval);
        return;
      }
      const d = res.data;
      const pct = d.progress || 0;
      const bar = $(`vprog-${videoId}`);
      if (bar) bar.style.width = pct + "%";

      const genBtn = $("generate-video-btn");
      if (genBtn) genBtn.textContent = `⟳ Building... ${pct}%`;

      if (d.status === "done" || d.video_ready) {
        clearInterval(interval);
        if (genBtn) { genBtn.textContent = "⚡ Build Video"; genBtn.disabled = false; }
        toast("Video ready! Check Videos tab.", "ok");
        if (onDone) onDone(d);
      } else if (d.status === "failed" || d.status === "error") {
        clearInterval(interval);
        if (genBtn) { genBtn.textContent = "⚡ Build Video"; genBtn.disabled = false; }
        toast("Video generation failed: " + (d.message || ""), "err");
      }
      tries++;
    }, 2000);
  }

  return {
    $, toast, ring, tag, barChart, fmtN, fmtDate,
    showPage, refreshDashboard,
    renderTrends, renderIdeas, renderScript,
    renderVideos, renderPublish, renderWeights,
    setStatus, pollVideoProgress,
    HOOK_COLORS, scoreColor,
  };
})();
