"""ViralForge v3 — Flask API Routes"""
import json, os, sys, threading, uuid
from datetime import datetime
from flask import Flask, jsonify, request, send_file, abort, render_template

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from core.db import init, get_weights, update_weight, cache_get, cache_set
from core.trends import fetch_all, get_cached_trends, pattern_report
from core.engine import run_decision_engine, get_scripts, get_batch, record_performance
from core.videos import (assemble_video, make_thumbnail, build_export,
                          save_video_record, update_video_status, get_videos,
                          OUT_DIR, EXP_DIR)
from core.notify import (send_notification, send_error, send_report,
                          get_event_bus, notification_history)

app = Flask(
    __name__,
    template_folder=os.path.join(ROOT, "templates"),
    static_folder=os.path.join(ROOT, "static"),
)

# ── CORS ──────────────────────────────────────────────────────────────────────
@app.after_request
def cors(r):
    r.headers.update({
        "Access-Control-Allow-Origin":  "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS,DELETE",
    })
    return r

@app.route("/<path:p>", methods=["OPTIONS"])
@app.route("/",          methods=["OPTIONS"])
def opts(p=""): return "", 204

# ── App State (in-memory, supplements DB) ────────────────────────────────────
_state = {
    "trends":       [],
    "patterns":     {},
    "last_fetch":   None,
    "fetch_status": "idle",  # idle|fetching|done|error
    "active_jobs":  {},      # video_id → {status, progress, message}
}

# ── Frontend ──────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

# ── Health ────────────────────────────────────────────────────────────────────
@app.route("/api/health")
def health():
    return jsonify({
        "ok":           True,
        "version":      "3.0",
        "ts":           datetime.now().isoformat(),
        "fetch_status": _state["fetch_status"],
        "has_key":      bool(os.environ.get("ANTHROPIC_API_KEY")),
    })

# ── Trends ────────────────────────────────────────────────────────────────────
@app.route("/api/trends/fetch", methods=["POST"])
def trigger_fetch():
    if _state["fetch_status"] == "fetching":
        return jsonify({"status": "already_running", "message": "Fetch in progress"})

    body = request.json or {}
    cats  = body.get("categories", ["trending", "entertainment", "gaming", "howto"])
    force = bool(body.get("force", False))

    def _run():
        _state["fetch_status"] = "fetching"
        try:
            trends   = fetch_all(cats, force=force)
            patterns = pattern_report(trends)
            _state["trends"]       = trends
            _state["patterns"]     = patterns
            _state["last_fetch"]   = datetime.now().isoformat()
            _state["fetch_status"] = "done"
            print(f"[Fetch] Complete: {len(trends)} trends")
        except Exception as e:
            _state["fetch_status"] = f"error"
            print(f"[Fetch] ERROR: {e}")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started"})

@app.route("/api/trends")
def get_trends():
    limit  = int(request.args.get("limit", 50))
    hook   = request.args.get("hook", "")
    source = request.args.get("source", "")
    sort   = request.args.get("sort", "virality_score")

    data = _state["trends"] or get_cached_trends(limit * 2)

    if hook:   data = [t for t in data if t.get("analysis", {}).get("hook_type") == hook]
    if source: data = [t for t in data if source in t.get("source", "")]
    if sort in ("virality_score", "views"):
        data = sorted(data, key=lambda x: x.get(sort, 0), reverse=True)

    return jsonify({
        "trends":      data[:limit],
        "total":       len(data),
        "last_fetch":  _state["last_fetch"],
        "status":      _state["fetch_status"],
    })

@app.route("/api/trends/patterns")
def get_patterns():
    p = _state["patterns"]
    if not p:
        cached = get_cached_trends(80)
        p = pattern_report(cached) if cached else {}
    return jsonify(p or {"error": "No data — fetch trends first"})

# ── Decision Engine (the core v3 feature) ─────────────────────────────────────
@app.route("/api/generate", methods=["POST"])
def generate():
    """
    Full pipeline: trends → 10 options → score → select → script
    This is the main v3 endpoint.
    """
    body  = request.json or {}
    niche = body.get("niche", "general")

    # Build trend context
    trends = _state["trends"] or get_cached_trends(60)
    ctx    = pattern_report(trends) if trends else {
        "top_hook":      "curiosity_gap",
        "top_triggers":  ["curiosity", "aspiration"],
        "avg_score":     60,
        "top_5":         [],
    }

    try:
        result = run_decision_engine(niche, ctx)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/scripts")
def list_scripts():
    return jsonify({"scripts": get_scripts(30)})

@app.route("/api/scripts/<script_id>")
def get_script(script_id: str):
    scripts = get_scripts(100)
    s = next((x for x in scripts if x["id"] == script_id), None)
    if not s:
        abort(404)
    return jsonify(s)

@app.route("/api/batch/<batch_id>")
def get_batch_endpoint(batch_id: str):
    b = get_batch(batch_id)
    if not b:
        abort(404)
    return jsonify(b)

# ── Video Generation ──────────────────────────────────────────────────────────
@app.route("/api/video/generate", methods=["POST"])
def gen_video():
    body      = request.json or {}
    script    = body.get("script", {})
    script_id = body.get("script_id", "")
    palette   = body.get("palette", "amber")

    if not script:
        return jsonify({"error": "script required"}), 400

    video_id = str(uuid.uuid4())[:12]

    # Check not already running
    if video_id in _state["active_jobs"] and _state["active_jobs"][video_id].get("status") == "processing":
        return jsonify({"status": "already_running", "video_id": video_id})

    _state["active_jobs"][video_id] = {"status": "queued", "progress": 0, "message": "Queued"}
    save_video_record(script_id, video_id, palette)

    def _build():
        def progress_cb(pct: int, msg: str):
            _state["active_jobs"][video_id] = {
                "status":   "processing" if pct < 100 else "done",
                "progress": pct,
                "message":  msg,
            }
            update_video_status(video_id, "processing" if pct < 100 else "done", pct)

        try:
            path = assemble_video(script, video_id, palette, progress_cb=progress_cb)
            export_dir = os.path.join(EXP_DIR, video_id)

            if path and os.path.exists(path):
                _state["active_jobs"][video_id] = {
                    "status": "done", "progress": 100,
                    "message": "Video ready",
                    "video_id": video_id,
                }
                update_video_status(video_id, "done", 100, path, export_dir)
            else:
                _state["active_jobs"][video_id] = {
                    "status": "failed", "progress": 0,
                    "message": "Assembly returned no output",
                }
                update_video_status(video_id, "failed", 0)

        except Exception as e:
            msg = str(e)[:200]
            _state["active_jobs"][video_id] = {
                "status": "error", "progress": 0, "message": msg
            }
            update_video_status(video_id, "error", 0)
            print(f"[video_gen:{video_id}] {e}")

    threading.Thread(target=_build, daemon=True).start()
    return jsonify({"status": "started", "video_id": video_id})

@app.route("/api/video/status/<video_id>")
def video_status(video_id: str):
    if not video_id.replace("-", "").replace("_", "").isalnum():
        abort(400)
    job   = _state["active_jobs"].get(video_id, {"status": "unknown", "progress": 0})
    vpath = os.path.join(OUT_DIR, f"vf3_{video_id}.mp4")
    tpath = os.path.join(OUT_DIR, f"thumb_{video_id}.jpg")
    epath = os.path.join(EXP_DIR, video_id, "caption.txt")
    return jsonify({
        **job,
        "video_id":    video_id,
        "video_ready": os.path.exists(vpath),
        "thumb_ready": os.path.exists(tpath),
        "export_ready": os.path.exists(epath),
        "size_mb":     round(os.path.getsize(vpath) / 1024 / 1024, 2) if os.path.exists(vpath) else 0,
    })

@app.route("/api/videos")
def list_videos():
    return jsonify({"videos": get_videos(30)})

@app.route("/api/video/<video_id>/download")
def download_video(video_id: str):
    if not video_id.replace("-", "").replace("_", "").isalnum():
        abort(400)
    path = os.path.join(OUT_DIR, f"vf3_{video_id}.mp4")
    if not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True, download_name=f"viralforge_{video_id}.mp4")

@app.route("/api/video/<video_id>/thumbnail")
def video_thumbnail(video_id: str):
    if not video_id.replace("-", "").replace("_", "").isalnum():
        abort(400)
    path = os.path.join(OUT_DIR, f"thumb_{video_id}.jpg")
    if not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="image/jpeg")

@app.route("/api/video/<video_id>/export")
def video_export(video_id: str):
    """Return export package contents."""
    if not video_id.replace("-", "").replace("_", "").isalnum():
        abort(400)
    edir = os.path.join(EXP_DIR, video_id)
    result = {}
    for fname in ("caption.txt", "metadata.json"):
        fpath = os.path.join(edir, fname)
        if os.path.exists(fpath):
            with open(fpath) as f:
                result[fname] = f.read() if fname.endswith(".txt") else json.load(f)
    if not result:
        abort(404)
    return jsonify(result)

# ── Performance / Learning ────────────────────────────────────────────────────
@app.route("/api/performance", methods=["POST"])
def log_performance():
    """
    Log real performance data to trigger weight learning.
    Body: {script_id, video_id, platform, views, likes, shares}
    """
    body = request.json or {}
    required = ["script_id", "platform", "views"]
    if not all(k in body for k in required):
        return jsonify({"error": f"Required: {required}"}), 400
    try:
        record_performance(
            body["script_id"], body.get("video_id", ""),
            body["platform"], int(body["views"]),
            int(body.get("likes", 0)), int(body.get("shares", 0))
        )
        return jsonify({"ok": True, "message": "Recorded and weights updated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/weights")
def get_pattern_weights():
    return jsonify({"weights": get_weights()})

# ── Publish Helpers ───────────────────────────────────────────────────────────
@app.route("/api/publish/caption/<video_id>")
def get_caption(video_id: str):
    """Return caption for clipboard copy (TikTok upload helper)."""
    if not video_id.replace("-", "").replace("_", "").isalnum():
        abort(400)
    cap_path = os.path.join(EXP_DIR, video_id, "caption.txt")
    if not os.path.exists(cap_path):
        # Try to regenerate from DB
        videos = get_videos(50)
        v = next((x for x in videos if x["id"] == video_id), None)
        if not v:
            abort(404)
        return jsonify({"caption": "", "message": "Caption file not found — regenerate video"})
    with open(cap_path) as f:
        return jsonify({"caption": f.read(), "video_id": video_id})

@app.route("/api/publish/tiktok_url")
def tiktok_url():
    """Return TikTok upload URL (no API automation — opens browser)."""
    return jsonify({
        "url":     "https://www.tiktok.com/upload",
        "message": "TikTok does not allow automated uploads. Open the URL and upload manually.",
    })

# ── Stats ─────────────────────────────────────────────────────────────────────
@app.route("/api/stats")
def stats():
    trends  = _state["trends"] or get_cached_trends(80)
    scripts = get_scripts(100)
    videos  = get_videos(100)
    pats    = _state["patterns"] or (pattern_report(trends) if trends else {})
    weights = get_weights()

    # Most learned pattern
    top_w = max(weights.items(), key=lambda x: x[1]) if weights else ("—", 1.0)

    return jsonify({
        "trends_count":   len(trends),
        "scripts_count":  len(scripts),
        "videos_count":   len([v for v in videos if v.get("has_video")]),
        "avg_score":      pats.get("avg_score", 0),
        "top_hook":       pats.get("top_hook", "—"),
        "top_triggers":   pats.get("top_triggers", [])[:3],
        "last_fetch":     _state["last_fetch"],
        "fetch_status":   _state["fetch_status"],
        "top_learned_pattern": top_w[0],
        "pattern_count":  len(weights),
    })

# ── Notifications ─────────────────────────────────────────────────────────────

@app.route("/api/notify", methods=["POST"])
def manual_notify():
    """Manually trigger a notification (for testing or external hooks)."""
    body = request.json or {}
    msg  = body.get("message", "")
    kind = body.get("type", "info")
    if not msg:
        return jsonify({"error": "message required"}), 400
    send_notification(msg, event_type=kind, title=body.get("title",""),
                      metadata=body.get("metadata"))
    return jsonify({"ok": True})

@app.route("/api/notifications")
def get_notifications():
    """Return recent in-app notification history."""
    limit = int(request.args.get("limit", 50))
    return jsonify({"notifications": notification_history(limit)})

@app.route("/api/notifications/stream")
def notification_stream():
    """
    Server-Sent Events endpoint.
    Client: const es = new EventSource('/api/notifications/stream');
            es.onmessage = e => console.log(JSON.parse(e.data));
    """
    import time as _time
    from flask import Response, stream_with_context

    bus = get_event_bus()
    q   = bus.subscribe()

    def _generate():
        # Send buffered history first (last 20)
        for event in reversed(notification_history(20)):
            yield f"data: {json.dumps(event)}\n\n"

        # Then stream live events
        while True:
            try:
                event = q.get(timeout=25)
                yield f"data: {json.dumps(event)}\n\n"
            except Exception:
                # Heartbeat to keep connection alive
                yield f": heartbeat\n\n"

    def _cleanup():
        bus.unsubscribe(q)

    import atexit
    atexit.register(_cleanup)

    return Response(
        stream_with_context(_generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":  "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

@app.route("/api/notify/test")
def test_notify():
    """Send a test notification to all configured channels."""
    send_notification(
        "ViralForge notification system is working correctly.",
        event_type = "success",
        title      = "Test Notification",
        metadata   = {"source": "test endpoint", "ts": datetime.now().isoformat()},
    )
    return jsonify({"ok": True, "message": "Test notification sent"})

