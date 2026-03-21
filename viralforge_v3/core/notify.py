"""
ViralForge v3 — Notification Service
=====================================
Three channels: Telegram bot, SMTP email, in-app Server-Sent Events (SSE).
All sends are fire-and-forget via a background queue thread.
The caller never waits. Failures are logged, not raised.

Configuration (environment variables):
  TELEGRAM_BOT_TOKEN   — from @BotFather
  TELEGRAM_CHAT_ID     — your personal chat or group ID
  NOTIFY_EMAIL_FROM    — sender address
  NOTIFY_EMAIL_TO      — recipient address
  NOTIFY_SMTP_HOST     — e.g. smtp.gmail.com
  NOTIFY_SMTP_PORT     — e.g. 587
  NOTIFY_SMTP_USER     — login username
  NOTIFY_SMTP_PASS     — app password / SMTP password
  NOTIFY_CHANNELS      — comma-separated: telegram,email,inapp  (default: inapp)
"""

import os
import json
import queue
import threading
import time
import smtplib
import ssl
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.request import urlopen, Request
from urllib.error import URLError
from urllib.parse import urlencode
from typing import Optional
from collections import deque

# ── Constants ─────────────────────────────────────────────────────────────────

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

EVENT_ICONS = {
    "success": "✅",
    "info":    "ℹ️",
    "warning": "⚠️",
    "error":   "❌",
    "trend":   "📈",
    "idea":    "🧠",
    "script":  "📝",
    "video":   "🎬",
    "report":  "📊",
    "publish": "📤",
}

# ── In-App Event Bus (SSE feed) ───────────────────────────────────────────────
# Holds the last 100 notifications for the dashboard live feed

class _InAppBus:
    def __init__(self, maxlen: int = 100):
        self._history: deque = deque(maxlen=maxlen)
        self._listeners: list = []
        self._lock = threading.Lock()

    def publish(self, event: dict):
        with self._lock:
            self._history.appendleft(event)
            dead = []
            for q in self._listeners:
                try:
                    q.put_nowait(event)
                except Exception:
                    dead.append(q)
            for q in dead:
                try:
                    self._listeners.remove(q)
                except ValueError:
                    pass

    def subscribe(self) -> queue.Queue:
        """Returns a queue that will receive all future events."""
        q = queue.Queue(maxsize=50)
        with self._lock:
            self._listeners.append(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        with self._lock:
            try:
                self._listeners.remove(q)
            except ValueError:
                pass

    def history(self, limit: int = 50) -> list:
        with self._lock:
            return list(self._history)[:limit]


_bus = _InAppBus()

# ── Background Worker ─────────────────────────────────────────────────────────

_send_queue: queue.Queue = queue.Queue(maxsize=200)
_worker_started = False
_worker_lock = threading.Lock()


def _worker():
    """Single background thread — drains the send queue without blocking callers."""
    while True:
        try:
            task = _send_queue.get(timeout=5)
            if task is None:
                break
            fn, args, kwargs, retries = task
            for attempt in range(retries):
                try:
                    fn(*args, **kwargs)
                    break
                except Exception as e:
                    if attempt < retries - 1:
                        time.sleep(1.5 * (attempt + 1))
                    else:
                        print(f"[Notify] Permanent failure after {retries} tries: {e}")
            _send_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            print(f"[Notify:worker] {e}")


def _ensure_worker():
    global _worker_started
    with _worker_lock:
        if not _worker_started:
            t = threading.Thread(target=_worker, daemon=True, name="notify-worker")
            t.start()
            _worker_started = True


def _enqueue(fn, *args, retries: int = 3, **kwargs):
    """Put a send task on the queue. Never blocks."""
    _ensure_worker()
    try:
        _send_queue.put_nowait((fn, args, kwargs, retries))
    except queue.Full:
        print("[Notify] Queue full — dropping notification")


# ── Channel: Telegram ─────────────────────────────────────────────────────────

def _send_telegram(text: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return  # silently skip if not configured

    url = TELEGRAM_API.format(token=token)
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()
    req = Request(url, data=payload, method="POST",
                  headers={"Content-Type": "application/json"})
    resp = urlopen(req, timeout=10)
    result = json.loads(resp.read())
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API error: {result.get('description','unknown')}")


# ── Channel: Email ────────────────────────────────────────────────────────────

def _send_email(subject: str, body_text: str, body_html: str = ""):
    smtp_host = os.environ.get("NOTIFY_SMTP_HOST", "").strip()
    smtp_port = int(os.environ.get("NOTIFY_SMTP_PORT", "587"))
    smtp_user = os.environ.get("NOTIFY_SMTP_USER", "").strip()
    smtp_pass = os.environ.get("NOTIFY_SMTP_PASS", "").strip()
    from_addr = os.environ.get("NOTIFY_EMAIL_FROM", smtp_user).strip()
    to_addr   = os.environ.get("NOTIFY_EMAIL_TO", "").strip()

    if not all([smtp_host, smtp_user, smtp_pass, to_addr]):
        return  # silently skip if not configured

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"ViralForge <{from_addr}>"
    msg["To"]      = to_addr

    msg.attach(MIMEText(body_text, "plain"))
    if body_html:
        msg.attach(MIMEText(body_html, "html"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
        server.ehlo()
        server.starttls(context=ctx)
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_addr, to_addr, msg.as_string())


# ── Channel: In-App ───────────────────────────────────────────────────────────

def _publish_inapp(event: dict):
    _bus.publish(event)


# ── Active channels resolver ──────────────────────────────────────────────────

def _active_channels() -> list[str]:
    raw = os.environ.get("NOTIFY_CHANNELS", "inapp").strip()
    return [c.strip().lower() for c in raw.split(",") if c.strip()]


# ── Public API ────────────────────────────────────────────────────────────────

def send_notification(
    message: str,
    event_type: str = "info",
    title: str = "",
    metadata: Optional[dict] = None,
):
    """
    Fire-and-forget notification to all configured channels.

    Args:
        message:    Human-readable description of what happened.
        event_type: One of: success, info, warning, error, trend, idea, script, video, report, publish
        title:      Optional short title (used in Telegram header, email subject)
        metadata:   Optional dict of extra data stored in in-app event
    """
    icon = EVENT_ICONS.get(event_type, "ℹ️")
    ts   = datetime.now().strftime("%H:%M:%S")
    subject = title or f"ViralForge — {event_type.capitalize()}"
    full_text = f"{icon} {message}"

    # ── In-app event (always, regardless of channel setting) ──
    event = {
        "id":        f"{int(time.time()*1000)}",
        "type":      event_type,
        "icon":      icon,
        "title":     title or message[:60],
        "message":   message,
        "ts":        ts,
        "metadata":  metadata or {},
    }
    _enqueue(_publish_inapp, event, retries=1)

    channels = _active_channels()

    # ── Telegram ──
    if "telegram" in channels:
        tg_text = (
            f"<b>ViralForge</b> [{ts}]\n"
            f"{icon} <b>{subject}</b>\n\n"
            f"{message}"
        )
        if metadata:
            tg_text += "\n\n" + "\n".join(f"• <i>{k}:</i> {v}" for k, v in metadata.items())
        _enqueue(_send_telegram, tg_text, retries=3)

    # ── Email ──
    if "email" in channels:
        plain = f"ViralForge [{ts}]\n{'='*40}\n{full_text}"
        if metadata:
            plain += "\n\nDetails:\n" + "\n".join(f"  {k}: {v}" for k, v in metadata.items())
        html = _build_email_html(icon, subject, message, ts, metadata)
        _enqueue(_send_email, subject, plain, html, retries=2)


def send_error(
    error_message: str,
    context: str = "",
    exc: Optional[Exception] = None,
):
    """Shortcut for error notifications — always treated as high priority."""
    detail = str(exc) if exc else ""
    full   = f"{error_message}" + (f" — {context}" if context else "") + (f"\n{detail}" if detail else "")
    send_notification(
        message    = full,
        event_type = "error",
        title      = "ViralForge Error",
        metadata   = {"context": context, "detail": detail[:200]} if (context or detail) else None,
    )


def send_report(summary: dict):
    """
    Send a full workflow summary.

    Expected summary keys (all optional):
        trends, ideas, scripts, videos, errors, niche, duration_s
    """
    lines = ["📊 <b>ViralForge Workflow Report</b>\n"]
    display = {
        "trends":     "📈 Trends fetched",
        "ideas":      "🧠 Ideas generated",
        "scripts":    "📝 Scripts created",
        "videos":     "🎬 Videos built",
        "niche":      "🎯 Niche",
        "duration_s": "⏱ Duration",
        "errors":     "❌ Errors",
    }
    plain_lines = ["ViralForge Workflow Report", "=" * 36]
    for key, label in display.items():
        if key in summary:
            val = summary[key]
            if key == "duration_s":
                val = f"{val:.1f}s"
            lines.append(f"{label}: <b>{val}</b>")
            plain_lines.append(f"{label}: {val}")

    message = "\n".join(plain_lines[2:])
    tg_body = "\n".join(lines)

    # In-app + email use the message string; Telegram gets the formatted version
    event = {
        "id":      f"{int(time.time()*1000)}",
        "type":    "report",
        "icon":    "📊",
        "title":   "Workflow Complete",
        "message": message,
        "ts":      datetime.now().strftime("%H:%M:%S"),
        "metadata": summary,
    }
    _enqueue(_publish_inapp, event, retries=1)

    channels = _active_channels()
    if "telegram" in channels:
        _enqueue(_send_telegram, tg_body, retries=3)
    if "email" in channels:
        html = _build_email_html("📊", "ViralForge Report", message,
                                  datetime.now().strftime("%H:%M:%S"), summary)
        plain = "\n".join(plain_lines)
        _enqueue(_send_email, "ViralForge — Workflow Report", plain, html, retries=2)


# ── SSE helpers (used by Flask route) ────────────────────────────────────────

def get_event_bus() -> _InAppBus:
    return _bus


def notification_history(limit: int = 50) -> list:
    return _bus.history(limit)


# ── HTML email template ───────────────────────────────────────────────────────

def _build_email_html(icon: str, title: str, body: str,
                       ts: str, metadata: Optional[dict] = None) -> str:
    rows = ""
    if metadata:
        rows = "".join(
            f"<tr><td style='padding:4px 12px 4px 0;color:#888;font-size:12px'>{k}</td>"
            f"<td style='padding:4px 0;font-size:12px'>{v}</td></tr>"
            for k, v in metadata.items()
        )
        rows = f"<table style='margin-top:12px;border-collapse:collapse'>{rows}</table>"

    return f"""<!DOCTYPE html>
<html><body style="background:#0b0b0f;color:#e2e2f0;font-family:sans-serif;padding:24px;margin:0">
  <div style="max-width:480px;margin:0 auto">
    <div style="background:#16161d;border:1px solid #28283a;border-radius:10px;padding:24px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
        <span style="font-size:22px">{icon}</span>
        <div>
          <div style="font-size:16px;font-weight:800;color:#f5a623">ViralForge</div>
          <div style="font-size:11px;color:#52526a;font-family:monospace">{ts}</div>
        </div>
      </div>
      <div style="font-size:15px;font-weight:700;margin-bottom:10px">{title}</div>
      <div style="font-size:13px;color:#8a8aaa;line-height:1.6;white-space:pre-wrap">{body}</div>
      {rows}
    </div>
  </div>
</body></html>"""
