"""
ViralForge v3 — Video Assembly
PIL frames with per-scene zoom motion + FFmpeg H.264 encode
9:16 TikTok/Shorts-ready output with progress callbacks
"""
import os, sys, json, shutil, subprocess, tempfile, uuid, math
from datetime import datetime
from typing import Callable, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.db import get_db, init

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    PIL_OK = True
except ImportError:
    PIL_OK = False

W, H = 1080, 1920
FPS = 30
OUT_DIR = os.path.join(os.path.dirname(__file__), "../outputs")
EXP_DIR = os.path.join(os.path.dirname(__file__), "../exports")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(EXP_DIR, exist_ok=True)

PALETTES = {
    "amber":   {"bg": (8,6,2),    "accent": (245,166,35),  "text": (255,255,255), "dim": (120,80,10)},
    "crimson": {"bg": (8,2,4),    "accent": (220,30,60),   "text": (255,255,255), "dim": (100,10,20)},
    "ice":     {"bg": (2,6,14),   "accent": (0,200,255),   "text": (255,255,255), "dim": (0,80,140)},
    "void":    {"bg": (4,0,14),   "accent": (140,0,255),   "text": (255,255,255), "dim": (60,0,120)},
    "forest":  {"bg": (2,10,4),   "accent": (0,210,80),    "text": (255,255,255), "dim": (0,100,40)},
    "solar":   {"bg": (10,6,0),   "accent": (255,140,0),   "text": (255,255,255), "dim": (140,60,0)},
}

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
]
_font_cache = {}

def _font(size: int) -> ImageFont.ImageFont:
    if size in _font_cache:
        return _font_cache[size]
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, size)
                _font_cache[size] = f
                return f
            except Exception:
                pass
    f = ImageFont.load_default()
    _font_cache[size] = f
    return f

def _wrap(text: str, max_chars: int = 18) -> list[str]:
    words, lines, cur = text.split(), [], []
    for w in words:
        cur.append(w)
        if len(" ".join(cur)) > max_chars:
            if len(cur) > 1:
                lines.append(" ".join(cur[:-1]))
                cur = [w]
            else:
                lines.append(" ".join(cur))
                cur = []
    if cur:
        lines.append(" ".join(cur))
    return lines[:3]

def _lerp(a, b, t):
    return a + (b - a) * t

def _ease_in_out(t):
    return t * t * (3 - 2 * t)

# ── Frame Generators ──────────────────────────────────────────────────────────

def _draw_gradient(draw: ImageDraw.ImageDraw, pal: dict, alpha: float = 1.0):
    """Draw full-height gradient background."""
    bg, acc = pal["bg"], pal["accent"]
    for y in range(H):
        p = y / H
        r = int(bg[0] + (acc[0] - bg[0]) * p * 0.20)
        g = int(bg[1] + (acc[1] - bg[1]) * p * 0.10)
        b = int(bg[2] + (acc[2] - bg[2]) * p * 0.15)
        draw.line([(0, y), (W, y)], fill=(
            max(0, min(255, r)),
            max(0, min(255, g)),
            max(0, min(255, b)),
        ))

def _draw_caption(draw: ImageDraw.ImageDraw, text: str, pal: dict,
                  phase: str = "body", scale: float = 1.0):
    """Draw centered caption with shadow and accent outline."""
    acc = pal["accent"]
    base_y = int(H * 0.72)

    lines = _wrap(text.upper(), max_chars=16 if phase == "hook" else 19)
    fs = int((108 if len(lines) == 1 else 90 if len(lines) == 2 else 76) * scale)
    font = _font(fs)

    total_h = len(lines) * (fs + 14)
    y = base_y - total_h // 2

    for ln in lines:
        bbox = draw.textbbox((0, 0), ln, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (W - tw) // 2

        # Drop shadow (3 layers)
        for ox, oy in [(5, 5), (8, 8), (11, 11)]:
            draw.text((x + ox, y + oy), ln, fill=(0, 0, 0), font=font)
        # Accent outline
        for ox, oy in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
            draw.text((x + ox, y + oy), ln, fill=acc, font=font)
        # Main white text
        draw.text((x, y), ln, fill=pal["text"], font=font)
        y += fs + 14

def _make_base_frame(caption: str, visual: str, scene_n: int, total: int,
                     pal_name: str, phase: str, scale: float = 1.0) -> Image.Image:
    pal = PALETTES.get(pal_name, PALETTES["amber"])
    img = Image.new("RGB", (W, H), pal["bg"])
    draw = ImageDraw.Draw(img)
    _draw_gradient(draw, pal)
    acc = pal["accent"]

    if phase == "hook":
        # Full-bleed hook frame: accent color background
        draw.rectangle([0, 0, W, H], fill=acc)
        # Dark vignette at edges
        for margin in range(0, 100, 20):
            alpha = int(180 * (1 - margin / 100))
            draw.rectangle([margin, margin, W - margin, H - margin],
                           outline=(0, 0, 0), width=1)
        # Caption in black on accent
        lines = _wrap(caption.upper(), 15)
        fs = int((110 if len(lines) == 1 else 92 if len(lines) == 2 else 78) * scale)
        font = _font(fs)
        total_h = len(lines) * (fs + 16)
        y = (H - total_h) // 2 - 30
        for ln in lines:
            bbox = draw.textbbox((0, 0), ln, font=font)
            tw = bbox[2] - bbox[0]
            x = (W - tw) // 2
            draw.text((x + 5, y + 5), ln, fill=(0, 0, 0), font=font)
            draw.text((x, y), ln, fill=(0, 0, 0), font=font)
            y += fs + 16
    else:
        # Visual label (small, dimmed)
        vf = _font(28)
        vlabel = visual.upper()[:52]
        bbox = draw.textbbox((0, 0), vlabel, font=vf)
        vw = bbox[2] - bbox[0]
        draw.text(((W - vw) // 2, 68), vlabel, fill=pal["dim"], font=vf)

        # Scene progress bar
        prog = int(W * scene_n / max(total, 1))
        draw.rectangle([0, H - 9, W, H], fill=tuple(c // 5 for c in acc))
        draw.rectangle([0, H - 9, prog, H], fill=acc)

        # Scene counter
        sf = _font(30)
        draw.text((36, 38), f"{scene_n}/{total}", fill=acc, font=sf)

        # Caption
        _draw_caption(draw, caption, pal, phase, scale)

    return img

def _apply_zoom(base: Image.Image, zoom_factor: float) -> Image.Image:
    """Apply Ken Burns zoom effect by cropping and upscaling."""
    if abs(zoom_factor - 1.0) < 0.001:
        return base
    new_w = int(W / zoom_factor)
    new_h = int(H / zoom_factor)
    x0 = (W - new_w) // 2
    y0 = (H - new_h) // 2
    cropped = base.crop((x0, y0, x0 + new_w, y0 + new_h))
    return cropped.resize((W, H), Image.LANCZOS)

# ── Scene to Frames ───────────────────────────────────────────────────────────

def _scene_frames(scene: dict, scene_n: int, total_scenes: int,
                  pal_name: str, fps: int = FPS) -> list[Image.Image]:
    """Generate all frames for a single scene with motion effects."""
    caption  = scene.get("caption_text") or scene.get("text") or scene.get("spoken_text", "")
    visual   = scene.get("visual_direction") or scene.get("visual", "")
    duration = scene.get("end_time", 3) - scene.get("start_time", 0)
    if duration <= 0:
        duration = scene.get("duration", 3)
    pacing   = scene.get("pacing", "medium")
    phase    = scene.get("phase", "body")
    trans    = scene.get("transition", "cut")

    # For fast pacing, use fewer source frames (simulate quick cuts)
    n_frames = max(int(duration * fps), fps // 2)
    if pacing == "fast":
        n_frames = max(int(n_frames * 0.65), fps // 3)

    # Generate base frame once (expensive)
    base = _make_base_frame(caption, visual, scene_n, total_scenes, pal_name, phase)

    frames = []

    # Zoom effect: slow zoom in for body scenes, zoom out for hook, static for payoff
    if phase == "hook":
        zoom_start, zoom_end = 1.08, 1.0   # zoom out reveal
    elif phase in ("build", "body"):
        zoom_start, zoom_end = 1.0, 1.05   # gentle zoom in
    else:
        zoom_start, zoom_end = 1.0, 1.0    # static

    for i in range(n_frames):
        t = _ease_in_out(i / max(n_frames - 1, 1))
        zoom = _lerp(zoom_start, zoom_end, t)

        if zoom != 1.0:
            frame = _apply_zoom(base, zoom)
        else:
            frame = base.copy()

        # Fade in on first 6 frames
        if i < 6 and trans in ("fade", "zoom_in", "zoom_out"):
            fade = Image.new("RGB", (W, H), (0, 0, 0))
            frame = Image.blend(fade, frame, i / 6)

        frames.append(frame)

    return frames

# ── FFmpeg Assembly ───────────────────────────────────────────────────────────

def _get_ffmpeg() -> str:
    r = subprocess.run(["which", "ffmpeg"], capture_output=True)
    if r.returncode == 0:
        return r.stdout.decode().strip()
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except:
        return "ffmpeg"

def assemble_video(script: dict, video_id: str, palette: str = "amber",
                   fps: int = FPS,
                   progress_cb: Optional[Callable[[int, str], None]] = None) -> Optional[str]:
    """
    Full pipeline: scenes → PIL frames → temp JPEG files → FFmpeg MP4
    progress_cb(percent: int, message: str)
    """
    if not PIL_OK:
        if progress_cb: progress_cb(0, "PIL not available")
        return None

    scenes = script.get("scenes") or script.get("script") or []
    if not scenes:
        if progress_cb: progress_cb(0, "No scenes in script")
        return None

    ff = _get_ffmpeg()
    tmp = tempfile.mkdtemp(prefix="vf3_")

    try:
        all_frames = []
        total_scenes = len(scenes)

        for si, scene in enumerate(scenes):
            pct = int(10 + (si / total_scenes) * 55)
            if progress_cb:
                progress_cb(pct, f"Rendering scene {si+1}/{total_scenes}...")

            frames = _scene_frames(scene, si + 1, total_scenes, palette, fps)
            all_frames.extend(frames)

        if progress_cb:
            progress_cb(65, f"Saving {len(all_frames)} frames to disk...")

        # Save frames as JPEG
        frame_paths = []
        for fi, frame in enumerate(all_frames):
            p = os.path.join(tmp, f"f{fi:07d}.jpg")
            frame.save(p, "JPEG", quality=92, optimize=False)
            frame_paths.append(p)

        if progress_cb:
            progress_cb(72, "Encoding video with FFmpeg...")

        # Build FFmpeg concat list
        lst = os.path.join(tmp, "frames.txt")
        with open(lst, "w") as fh:
            for fp in frame_paths:
                fh.write(f"file '{fp}'\nduration {1/fps:.6f}\n")
            # Duplicate last frame to avoid truncation
            if frame_paths:
                fh.write(f"file '{frame_paths[-1]}'\n")

        out_path = os.path.join(OUT_DIR, f"vf3_{video_id}.mp4")
        cmd = [
            ff, "-y",
            "-f", "concat", "-safe", "0", "-i", lst,
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
                   "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
                   "setsar=1",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-r", str(fps), "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            out_path,
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode != 0:
            err = result.stderr.decode()[:600]
            print(f"[FFmpeg] Error:\n{err}")
            if progress_cb: progress_cb(0, f"FFmpeg failed: {err[:80]}")
            return None

        if progress_cb: progress_cb(92, "Generating thumbnail...")
        make_thumbnail(script, video_id, palette)

        if progress_cb: progress_cb(98, "Building export package...")
        build_export(script, video_id)

        if progress_cb: progress_cb(100, "Complete!")

        # Notify: video ready
        from core.notify import send_notification, send_error
        size_mb = round(os.path.getsize(out_path) / 1024 / 1024, 2) if os.path.exists(out_path) else 0
        send_notification(
            message    = f"Video built: vf3_{video_id}.mp4 ({size_mb} MB)",
            event_type = "video",
            title      = "Video Created",
            metadata   = {
                "video_id":  video_id,
                "file":      f"vf3_{video_id}.mp4",
                "size_mb":   size_mb,
                "palette":   palette,
                "scenes":    len(scenes),
            },
        )
        return out_path

    except Exception as e:
        from core.notify import send_error
        send_error(f"Video assembly failed for {video_id}", context="assemble_video", exc=e)
        print(f"[assemble_video] {e}")
        if progress_cb: progress_cb(0, f"Error: {str(e)}")
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def make_thumbnail(script: dict, video_id: str, palette: str = "amber") -> Optional[str]:
    if not PIL_OK: return None
    hook = (script.get("hook") or script.get("title") or "VIDEO")[:70]
    pal = PALETTES.get(palette, PALETTES["amber"])

    img = Image.new("RGB", (W, H), pal["accent"])
    draw = ImageDraw.Draw(img)
    # Dark vignette
    for margin in range(0, 200, 15):
        alpha_val = int(255 * (margin / 200) * 0.7)
        c = tuple(max(0, int(x * (1 - margin / 200 * 0.7))) for x in pal["accent"])
        draw.rectangle([margin, margin, W - margin, H - margin], outline=c, width=1)

    lines = _wrap(hook.upper(), 14)
    fs = 112 if len(lines) == 1 else 95 if len(lines) == 2 else 80
    font = _font(fs)
    total_h = len(lines) * (fs + 16)
    y = (H - total_h) // 2 - 60

    for ln in lines:
        bbox = draw.textbbox((0, 0), ln, font=font)
        tw = bbox[2] - bbox[0]
        x = (W - tw) // 2
        draw.text((x + 5, y + 5), ln, fill=(0, 0, 0), font=font)
        draw.text((x, y), ln, fill=(0, 0, 0), font=font)
        y += fs + 16

    # Title bar
    title = (script.get("title") or "")[:80]
    if title:
        tf = _font(42)
        tlines = _wrap(title, 30)[-2:]
        ty = H - 200
        for tl in tlines:
            bbox = draw.textbbox((0, 0), tl, font=tf)
            tw = bbox[2] - bbox[0]
            draw.rectangle([0, ty - 8, W, ty + 54], fill=(0, 0, 0))
            draw.text(((W - tw) // 2, ty), tl, fill=(255, 255, 255), font=tf)
            ty += 58

    path = os.path.join(OUT_DIR, f"thumb_{video_id}.jpg")
    img.save(path, "JPEG", quality=90)
    return path

def build_export(script: dict, video_id: str) -> str:
    """Build /exports/<video_id>/ with video.mp4, caption.txt, metadata.json"""
    export_dir = os.path.join(EXP_DIR, video_id)
    os.makedirs(export_dir, exist_ok=True)

    # Caption file
    hashtags = " ".join(script.get("hashtags", []))
    desc = script.get("description", "")
    title = script.get("title", "")
    caption_text = f"{title}\n\n{desc}\n\n{hashtags}"
    with open(os.path.join(export_dir, "caption.txt"), "w") as f:
        f.write(caption_text)

    # Metadata JSON
    meta = {
        "title": title,
        "description": desc,
        "hashtags": script.get("hashtags", []),
        "hook": script.get("hook", ""),
        "total_duration": script.get("total_duration", 0),
        "scenes": len(script.get("scenes") or script.get("script") or []),
        "music_direction": script.get("music_direction", ""),
        "thumbnail_concept": script.get("thumbnail_concept", ""),
        "generated_at": datetime.now().isoformat(),
        "video_id": video_id,
    }
    with open(os.path.join(export_dir, "metadata.json"), "w") as f:
        json.dump(meta, f, indent=2)

    # Copy video file if it exists
    vpath = os.path.join(OUT_DIR, f"vf3_{video_id}.mp4")
    if os.path.exists(vpath):
        shutil.copy2(vpath, os.path.join(export_dir, "video.mp4"))

    return export_dir

# ── DB helpers ────────────────────────────────────────────────────────────────

def save_video_record(script_id: str, video_id: str, palette: str) -> None:
    init()
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO videos (id,script_id,status,progress,created_at,palette) VALUES (?,?,?,?,?,?)",
        (video_id, script_id, "queued", 0, datetime.now().isoformat(), palette)
    )
    conn.commit()
    conn.close()

def update_video_status(video_id: str, status: str, progress: int,
                        file_path: str = "", export_dir: str = ""):
    init()
    conn = get_db()
    size = os.path.getsize(file_path) if file_path and os.path.exists(file_path) else 0
    conn.execute(
        "UPDATE videos SET status=?,progress=?,file_path=?,file_size=?,export_dir=? WHERE id=?",
        (status, progress, file_path, size, export_dir, video_id)
    )
    conn.commit()
    conn.close()

def get_videos(limit: int = 20) -> list[dict]:
    try:
        init()
        conn = get_db()
        rows = conn.execute(
            "SELECT v.id,v.script_id,v.status,v.progress,v.file_path,v.thumb_path,"
            "v.created_at,v.file_size,v.palette,v.export_dir,"
            "s.title,s.virality_score "
            "FROM videos v LEFT JOIN scripts s ON v.script_id=s.id "
            "ORDER BY v.created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [{
            "id": r["id"], "script_id": r["script_id"],
            "status": r["status"], "progress": r["progress"],
            "has_video": bool(r["file_path"] and os.path.exists(r["file_path"])),
            "has_thumb": bool(r["thumb_path"] and os.path.exists(r["thumb_path"])),
            "has_export": os.path.exists(os.path.join(EXP_DIR, r["id"], "caption.txt")),
            "created_at": r["created_at"],
            "file_size_mb": round(r["file_size"] / 1024 / 1024, 2) if r["file_size"] else 0,
            "palette": r["palette"], "export_dir": r["export_dir"],
            "title": r["title"] or "Untitled",
            "virality_score": r["virality_score"] or 0,
        } for r in rows]
    except Exception as e:
        print(f"[get_videos] {e}")
        return []
