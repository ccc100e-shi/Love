#!/usr/bin/env python3
"""
ViralForge v3 — Single Entry Point
=====================================
Local:  python run.py          → http://localhost:5000
Cloud:  gunicorn run:app       (PORT env var respected)
"""
import os, sys, threading, time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# ── Env check ─────────────────────────────────────────────────────────────────
missing_warn = []
if not os.environ.get("ANTHROPIC_API_KEY"):
    missing_warn.append("ANTHROPIC_API_KEY  ← required for AI script generation")
if missing_warn:
    print("\n⚠️  Warning — missing environment variables:")
    for m in missing_warn:
        print(f"   • {m}")
    print("   The app will start but AI features won't work without the key.\n")

# ── Init DB ────────────────────────────────────────────────────────────────────
from core.db import init as init_db
init_db()
print("✓ Database initialised")

# ── Startup notification ───────────────────────────────────────────────────────
from core.notify import send_notification
send_notification(
    "ViralForge v3 started successfully",
    event_type="success",
    title="System Online",
    metadata={"port": os.environ.get("PORT", "5000"),
              "channels": os.environ.get("NOTIFY_CHANNELS", "inapp")},
)
print("✓ Notification system ready")

# ── Import app (also exposed as module-level for gunicorn) ─────────────────────
from api.routes import app  # noqa — used by gunicorn as run:app

PORT = int(os.environ.get("PORT", 5000))

# ── Auto-open browser only when running locally (not on a server) ─────────────
def _open_browser():
    time.sleep(1.4)
    try:
        import webbrowser
        webbrowser.open(f"http://localhost:{PORT}")
    except Exception:
        pass

if __name__ == "__main__":
    print(f"\n{'─'*50}")
    print(f"  ⚡ ViralForge v3")
    print(f"  → http://localhost:{PORT}")
    print(f"  Notification channels: {os.environ.get('NOTIFY_CHANNELS','inapp')}")
    print(f"{'─'*50}\n")

    is_local = not os.environ.get("RENDER") and not os.environ.get("RAILWAY_ENVIRONMENT")
    if is_local:
        threading.Thread(target=_open_browser, daemon=True).start()

    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
