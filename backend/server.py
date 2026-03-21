"""
ViralForge v3 — Simplified Single-Endpoint Backend
===================================================
One prompt → Full viral video pipeline
"""
import os
import json
import uuid
import asyncio
import shutil
import tempfile
import subprocess
import math
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import time

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

# PIL for image generation
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_OK = True
except ImportError:
    PIL_OK = False

# Emergent AI integrations
from emergentintegrations.llm.chat import LlmChat, UserMessage
from emergentintegrations.llm.openai import OpenAITextToSpeech

app = FastAPI(title="ViralForge v3 API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "viralforge")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# Directories
DATA_DIR = "/app/backend/data"
OUT_DIR = os.path.join(DATA_DIR, "outputs")
AUDIO_DIR = os.path.join(DATA_DIR, "audio")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

# API Key
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

# Video dimensions
W, H = 1080, 1920
FPS = 30

# Color Palettes
PALETTES = {
    "indigo": {"bg": (15, 23, 42), "accent": (99, 102, 241), "text": (255, 255, 255)},
    "emerald": {"bg": (6, 32, 28), "accent": (16, 185, 129), "text": (255, 255, 255)},
    "amber": {"bg": (30, 20, 8), "accent": (245, 158, 11), "text": (255, 255, 255)},
    "rose": {"bg": (30, 10, 15), "accent": (244, 63, 94), "text": (255, 255, 255)},
}

# In-memory job tracking
jobs = {}

# ============ MODELS ============

class GenerateAllRequest(BaseModel):
    prompt: str

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    step: str
    result: Optional[dict] = None

# ============ HEALTH ============

@app.get("/api/health")
async def health():
    return {"ok": True, "version": "3.0", "has_key": bool(EMERGENT_LLM_KEY)}

# ============ AI FUNCTIONS ============

async def ai_generate(prompt: str, system: str = "", max_tokens: int = 2000) -> str:
    """Generate content using AI"""
    if not EMERGENT_LLM_KEY:
        raise Exception("AI key not configured")
    
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"vf-{uuid.uuid4()}",
        system_message=system or "You are a viral content expert."
    ).with_model("openai", "gpt-4o")
    
    response = await chat.send_message(UserMessage(text=prompt))
    return response

def parse_json(raw: str) -> dict:
    """Parse JSON from AI response"""
    clean = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    clean = re.sub(r"\s*```$", "", clean).strip()
    try:
        return json.loads(clean)
    except:
        m = re.search(r"(\{[\s\S]*\})", clean)
        if m:
            return json.loads(m.group(1))
        raise ValueError("No JSON found")

# ============ TREND ANALYSIS ============

def fetch_youtube_trends() -> list:
    """Quick trend fetch for context"""
    results = []
    url = "https://www.youtube.com/feeds/videos.xml?chart=trending&gl=US&hl=en"
    headers = {"User-Agent": "ViralForge/3.0"}
    try:
        req = Request(url, headers=headers)
        data = urlopen(req, timeout=10).read()
        root = ET.fromstring(data)
        ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
        for entry in root.findall("a:entry", ns)[:10]:
            title = getattr(entry.find("a:title", ns), "text", "") or ""
            if title:
                results.append(title)
    except:
        pass
    return results

# ============ VIDEO GENERATION ============

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
_font_cache = {}

def get_font(size: int):
    if size in _font_cache:
        return _font_cache[size]
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, size)
                _font_cache[size] = f
                return f
            except:
                pass
    f = ImageFont.load_default()
    _font_cache[size] = f
    return f

def wrap_text(text: str, max_chars: int = 18) -> list:
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
    return lines[:4]

def make_frame(caption: str, scene_n: int, total: int, pal_name: str, phase: str) -> Image.Image:
    pal = PALETTES.get(pal_name, PALETTES["indigo"])
    img = Image.new("RGB", (W, H), pal["bg"])
    draw = ImageDraw.Draw(img)
    acc = pal["accent"]
    
    # Gradient
    for y in range(H):
        p = y / H
        r = int(pal["bg"][0] + (acc[0] - pal["bg"][0]) * p * 0.12)
        g = int(pal["bg"][1] + (acc[1] - pal["bg"][1]) * p * 0.08)
        b = int(pal["bg"][2] + (acc[2] - pal["bg"][2]) * p * 0.10)
        draw.line([(0, y), (W, y)], fill=(max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))))
    
    if phase == "hook":
        # Bold hook frame
        draw.rectangle([0, 0, W, H], fill=acc)
        lines = wrap_text(caption.upper(), 14)
        fs = 100 if len(lines) == 1 else 85
        font = get_font(fs)
        total_h = len(lines) * (fs + 16)
        y = (H - total_h) // 2
        for ln in lines:
            bbox = draw.textbbox((0, 0), ln, font=font)
            tw = bbox[2] - bbox[0]
            x = (W - tw) // 2
            draw.text((x + 4, y + 4), ln, fill=(0, 0, 0), font=font)
            draw.text((x, y), ln, fill=(255, 255, 255), font=font)
            y += fs + 16
    else:
        # Progress bar
        prog = int(W * scene_n / max(total, 1))
        draw.rectangle([0, H - 8, W, H], fill=tuple(c // 4 for c in acc))
        draw.rectangle([0, H - 8, prog, H], fill=acc)
        
        # Caption
        lines = wrap_text(caption.upper(), 16)
        fs = 90 if len(lines) == 1 else 75
        font = get_font(fs)
        base_y = int(H * 0.70)
        total_h = len(lines) * (fs + 14)
        y = base_y - total_h // 2
        
        for ln in lines:
            bbox = draw.textbbox((0, 0), ln, font=font)
            tw = bbox[2] - bbox[0]
            x = (W - tw) // 2
            for ox, oy in [(4, 4), (6, 6)]:
                draw.text((x + ox, y + oy), ln, fill=(0, 0, 0), font=font)
            for ox, oy in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
                draw.text((x + ox, y + oy), ln, fill=acc, font=font)
            draw.text((x, y), ln, fill=pal["text"], font=font)
            y += fs + 14
    
    return img

def get_ffmpeg() -> str:
    r = subprocess.run(["which", "ffmpeg"], capture_output=True)
    if r.returncode == 0:
        return r.stdout.decode().strip()
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except:
        return "ffmpeg"

async def generate_tts(text: str, video_id: str) -> Optional[str]:
    """Generate TTS audio"""
    if not EMERGENT_LLM_KEY:
        return None
    try:
        tts = OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY)
        audio_bytes = await tts.generate_speech(
            text=text,
            model="tts-1",
            voice="nova",
            speed=1.1
        )
        audio_path = os.path.join(AUDIO_DIR, f"voice_{video_id}.mp3")
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)
        return audio_path
    except Exception as e:
        print(f"[TTS] Error: {e}")
        return None

async def build_video(script: dict, video_id: str, update_progress) -> Optional[str]:
    """Build the video from script"""
    if not PIL_OK:
        return None
    
    scenes = script.get("scenes", [])
    if not scenes:
        return None
    
    ff = get_ffmpeg()
    tmp = tempfile.mkdtemp(prefix="vf_")
    
    try:
        all_frames = []
        total_scenes = len(scenes)
        palette = "indigo"
        
        for si, scene in enumerate(scenes):
            await update_progress(60 + int((si / total_scenes) * 20), f"Rendering scene {si+1}/{total_scenes}")
            
            caption = scene.get("caption_text") or scene.get("spoken_text", "")
            duration = scene.get("duration", 3)
            phase = scene.get("phase", "body")
            
            base = make_frame(caption, si + 1, total_scenes, palette, phase)
            n_frames = max(int(duration * FPS), FPS // 2)
            
            for i in range(n_frames):
                frame = base.copy()
                if i < 4:
                    fade = Image.new("RGB", (W, H), (0, 0, 0))
                    frame = Image.blend(fade, frame, i / 4)
                all_frames.append(frame)
        
        await update_progress(80, "Saving frames...")
        
        frame_paths = []
        for fi, frame in enumerate(all_frames):
            p = os.path.join(tmp, f"f{fi:07d}.jpg")
            frame.save(p, "JPEG", quality=88)
            frame_paths.append(p)
        
        await update_progress(85, "Generating AI voice...")
        
        full_text = " ".join(s.get("spoken_text", "") for s in scenes)
        audio_path = await generate_tts(full_text, video_id)
        
        await update_progress(90, "Encoding video...")
        
        lst = os.path.join(tmp, "frames.txt")
        with open(lst, "w") as fh:
            for fp in frame_paths:
                fh.write(f"file '{fp}'\nduration {1/FPS:.6f}\n")
            if frame_paths:
                fh.write(f"file '{frame_paths[-1]}'\n")
        
        out_path = os.path.join(OUT_DIR, f"viral_{video_id}.mp4")
        
        if audio_path and os.path.exists(audio_path):
            cmd = [ff, "-y", "-f", "concat", "-safe", "0", "-i", lst, "-i", audio_path,
                   "-vf", "scale=1080:1920,setsar=1", "-c:v", "libx264", "-preset", "fast",
                   "-crf", "22", "-c:a", "aac", "-b:a", "128k", "-shortest",
                   "-r", str(FPS), "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path]
        else:
            cmd = [ff, "-y", "-f", "concat", "-safe", "0", "-i", lst,
                   "-vf", "scale=1080:1920,setsar=1", "-c:v", "libx264", "-preset", "fast",
                   "-crf", "22", "-r", str(FPS), "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path]
        
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode != 0:
            print(f"[FFmpeg] Error: {result.stderr.decode()[:500]}")
            return None
        
        return out_path
    
    except Exception as e:
        print(f"[build_video] {e}")
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

# ============ MAIN ENDPOINT ============

@app.post("/api/generate-all")
async def generate_all(req: GenerateAllRequest, background_tasks: BackgroundTasks):
    """
    ONE endpoint to rule them all.
    User prompt → Idea + Hook + Script + Voice + Video
    """
    if not req.prompt or len(req.prompt.strip()) < 3:
        raise HTTPException(status_code=400, detail="Please enter a valid prompt")
    
    job_id = str(uuid.uuid4())[:12]
    jobs[job_id] = {
        "status": "processing",
        "progress": 0,
        "step": "Starting...",
        "result": None
    }
    
    async def process():
        try:
            async def update_progress(pct: int, step: str):
                jobs[job_id]["progress"] = pct
                jobs[job_id]["step"] = step
            
            await update_progress(5, "Analyzing your request...")
            
            # Step 1: Get trending context
            await update_progress(10, "Fetching viral trends...")
            trends = fetch_youtube_trends()
            trend_context = "\n".join(f"- {t}" for t in trends[:5]) if trends else "General viral content"
            
            # Step 2: Generate the perfect viral idea
            await update_progress(20, "Creating viral idea...")
            
            idea_prompt = f"""Based on this user request: "{req.prompt}"

And these current trending topics:
{trend_context}

Generate ONE perfect viral video idea.

OUTPUT JSON only:
{{
  "niche": "detected niche (e.g., fitness, finance, motivation)",
  "title": "Viral video title (scroll-stopping, 8-12 words)",
  "idea": "2-sentence description of the video concept",
  "hook": "Exact opening line (first 3 seconds) - must create instant curiosity",
  "hook_type": "curiosity_gap|fear|transformation|question|number",
  "primary_emotion": "curiosity|fear|aspiration|humor|shock",
  "predicted_engagement": "high|very_high|viral",
  "why_viral": "1 sentence explaining the psychological trigger"
}}"""
            
            idea_system = """You are the world's top viral content strategist. 
You create concepts that get millions of views.
Output ONLY valid JSON. No explanation."""
            
            idea_raw = await ai_generate(idea_prompt, idea_system, 800)
            idea_data = parse_json(idea_raw)
            
            # Step 3: Generate full script
            await update_progress(35, "Writing viral script...")
            
            script_prompt = f"""Create a complete TikTok/Shorts script for this viral idea:

TITLE: {idea_data.get('title', '')}
HOOK: {idea_data.get('hook', '')}
CONCEPT: {idea_data.get('idea', '')}
EMOTION: {idea_data.get('primary_emotion', 'curiosity')}

Generate a 30-45 second script with 4-6 scenes.

OUTPUT JSON only:
{{
  "title": "final title",
  "hook": "opening hook line",
  "total_duration": 35,
  "scenes": [
    {{
      "id": 1,
      "phase": "hook",
      "duration": 3,
      "spoken_text": "what the creator says",
      "caption_text": "ON-SCREEN TEXT (shorter, punchier)",
      "visual_direction": "what viewer sees"
    }}
  ],
  "hashtags": ["#tag1", "#tag2", "#tag3"],
  "music_style": "describe ideal background music"
}}

RULES:
- Hook phase: 0-3 seconds, must stop the scroll
- Build phase: 3-20 seconds, create tension
- Payoff phase: 20-35 seconds, deliver value
- Keep spoken text natural, conversational
- Caption text should be DIFFERENT from spoken (shorter, punchier)"""
            
            script_system = """You are an elite short-form video scriptwriter.
Every word must earn its place. Maximum engagement.
Output ONLY valid JSON."""
            
            script_raw = await ai_generate(script_prompt, script_system, 1500)
            script_data = parse_json(script_raw)
            
            # Step 4: Build the video
            await update_progress(50, "Building video...")
            
            video_id = job_id
            video_path = await build_video(script_data, video_id, update_progress)
            
            await update_progress(95, "Finalizing...")
            
            # Prepare result
            video_url = f"/api/video/{video_id}" if video_path and os.path.exists(video_path) else None
            
            result = {
                "success": True,
                "idea": {
                    "niche": idea_data.get("niche", "general"),
                    "title": idea_data.get("title", script_data.get("title", "")),
                    "concept": idea_data.get("idea", ""),
                    "hook": idea_data.get("hook", script_data.get("hook", "")),
                    "hook_type": idea_data.get("hook_type", "curiosity_gap"),
                    "emotion": idea_data.get("primary_emotion", "curiosity"),
                    "why_viral": idea_data.get("why_viral", ""),
                },
                "script": {
                    "title": script_data.get("title", ""),
                    "hook": script_data.get("hook", ""),
                    "duration": script_data.get("total_duration", 35),
                    "scenes": script_data.get("scenes", []),
                    "hashtags": script_data.get("hashtags", []),
                    "music": script_data.get("music_style", ""),
                },
                "video": {
                    "id": video_id,
                    "url": video_url,
                    "ready": video_url is not None,
                }
            }
            
            # Save to DB
            await db.generations.insert_one({
                "job_id": job_id,
                "prompt": req.prompt,
                "result": result,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            
            jobs[job_id] = {
                "status": "complete",
                "progress": 100,
                "step": "Done!",
                "result": result
            }
            
        except Exception as e:
            print(f"[generate_all] Error: {e}")
            jobs[job_id] = {
                "status": "error",
                "progress": 0,
                "step": f"Error: {str(e)[:100]}",
                "result": None
            }
    
    background_tasks.add_task(process)
    return {"job_id": job_id, "status": "processing"}

@app.get("/api/job/{job_id}")
async def get_job_status(job_id: str):
    """Check job status"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]

@app.get("/api/video/{video_id}")
async def get_video(video_id: str):
    """Download video"""
    path = os.path.join(OUT_DIR, f"viral_{video_id}.mp4")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(path, media_type="video/mp4", filename=f"viral_{video_id}.mp4")

# ============ STARTUP ============

@app.on_event("startup")
async def startup():
    print("✓ ViralForge v3 - Simplified Edition Ready")
