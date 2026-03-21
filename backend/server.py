"""
ViralForge v3 — Production-Grade Viral Video Generator
=======================================================
Premium quality: Dynamic visuals, TikTok-style captions, AI voice
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
import random
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional, List, Dict
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

# PIL for image generation
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
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

# Video dimensions (9:16 vertical)
W, H = 1080, 1920
FPS = 30

# Premium color themes
THEMES = {
    "midnight": {
        "bg_start": (10, 10, 25),
        "bg_end": (25, 15, 45),
        "accent": (138, 43, 226),  # Purple
        "accent2": (255, 105, 180),  # Pink
        "text": (255, 255, 255),
        "subtitle_bg": (0, 0, 0, 180),
    },
    "ocean": {
        "bg_start": (5, 20, 35),
        "bg_end": (10, 40, 60),
        "accent": (0, 212, 255),  # Cyan
        "accent2": (50, 255, 150),  # Green
        "text": (255, 255, 255),
        "subtitle_bg": (0, 0, 0, 180),
    },
    "fire": {
        "bg_start": (30, 10, 5),
        "bg_end": (50, 20, 10),
        "accent": (255, 100, 50),  # Orange
        "accent2": (255, 200, 50),  # Yellow
        "text": (255, 255, 255),
        "subtitle_bg": (0, 0, 0, 180),
    },
    "emerald": {
        "bg_start": (5, 25, 15),
        "bg_end": (10, 45, 25),
        "accent": (16, 185, 129),  # Green
        "accent2": (52, 211, 153),  # Light green
        "text": (255, 255, 255),
        "subtitle_bg": (0, 0, 0, 180),
    },
}

# In-memory job tracking
jobs = {}

# ============ MODELS ============

class GenerateAllRequest(BaseModel):
    prompt: str

# ============ HEALTH ============

@app.get("/api/health")
async def health():
    return {"ok": True, "version": "3.1-pro", "has_key": bool(EMERGENT_LLM_KEY)}

# ============ AI ENGINE ============

async def ai_generate(prompt: str, system: str = "", max_tokens: int = 2000, retries: int = 3) -> str:
    """Generate content using AI with retry logic"""
    if not EMERGENT_LLM_KEY:
        raise Exception("AI key not configured")
    
    last_error = None
    for attempt in range(retries):
        try:
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"vf-{uuid.uuid4()}",
                system_message=system or "You are a viral content expert."
            ).with_model("openai", "gpt-4o")
            
            response = await chat.send_message(UserMessage(text=prompt))
            return response
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                await asyncio.sleep(1)
    
    raise last_error

def parse_json(raw: str) -> dict:
    """Parse JSON from AI response with fallback"""
    clean = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    clean = re.sub(r"\s*```$", "", clean).strip()
    try:
        return json.loads(clean)
    except:
        m = re.search(r"(\{[\s\S]*\})", clean)
        if m:
            return json.loads(m.group(1))
        raise ValueError("No JSON found in response")

# ============ TREND INTELLIGENCE ============

def fetch_trends() -> List[str]:
    """Quick trend fetch for context"""
    results = []
    url = "https://www.youtube.com/feeds/videos.xml?chart=trending&gl=US&hl=en"
    headers = {"User-Agent": "ViralForge/3.1"}
    try:
        req = Request(url, headers=headers)
        data = urlopen(req, timeout=8).read()
        root = ET.fromstring(data)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("a:entry", ns)[:8]:
            title = getattr(entry.find("a:title", ns), "text", "") or ""
            if title:
                results.append(title)
    except:
        pass
    return results

# ============ PREMIUM VIDEO GENERATION ============

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
_font_cache = {}

def get_font(size: int):
    if size in _font_cache:
        return _font_cache[size]
    for p in FONT_PATHS:
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

def create_gradient_background(width: int, height: int, theme: dict, variation: float = 0) -> Image.Image:
    """Create animated gradient background"""
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    
    start = theme["bg_start"]
    end = theme["bg_end"]
    
    # Add variation for animation effect
    var = math.sin(variation * math.pi * 2) * 0.1
    
    for y in range(height):
        ratio = y / height + var
        ratio = max(0, min(1, ratio))
        r = int(start[0] + (end[0] - start[0]) * ratio)
        g = int(start[1] + (end[1] - start[1]) * ratio)
        b = int(start[2] + (end[2] - start[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    return img

def add_particle_effects(img: Image.Image, theme: dict, frame_num: int, total_frames: int) -> Image.Image:
    """Add subtle floating particles for dynamic feel"""
    draw = ImageDraw.Draw(img, "RGBA")
    
    random.seed(42)  # Consistent particles
    num_particles = 15
    
    for i in range(num_particles):
        # Base position
        base_x = random.randint(0, W)
        base_y = random.randint(0, H)
        
        # Animate position
        progress = frame_num / max(total_frames, 1)
        offset_y = math.sin(progress * math.pi * 2 + i) * 30
        offset_x = math.cos(progress * math.pi * 2 + i * 0.5) * 20
        
        x = int(base_x + offset_x) % W
        y = int((base_y + offset_y + frame_num * 0.5) % H)
        
        # Particle size and alpha
        size = random.randint(2, 6)
        alpha = random.randint(30, 80)
        
        color = (*theme["accent"][:3], alpha)
        draw.ellipse([x - size, y - size, x + size, y + size], fill=color)
    
    return img

def wrap_text_smart(text: str, max_width: int, font) -> List[str]:
    """Smart text wrapping"""
    words = text.split()
    lines = []
    current_line = []
    
    dummy_img = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy_img)
    
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        width = bbox[2] - bbox[0]
        
        if width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(" ".join(current_line))
    
    return lines[:4]  # Max 4 lines

def draw_tiktok_subtitle(img: Image.Image, text: str, theme: dict, 
                         progress: float = 1.0, emphasis_words: List[str] = None) -> Image.Image:
    """Draw TikTok-style animated subtitle with word emphasis"""
    draw = ImageDraw.Draw(img, "RGBA")
    
    # Font sizes
    font_size = 72
    font = get_font(font_size)
    
    # Wrap text
    max_width = W - 120
    lines = wrap_text_smart(text.upper(), max_width, font)
    
    # Calculate total height
    line_height = font_size + 20
    total_height = len(lines) * line_height
    
    # Position (lower third of screen)
    start_y = int(H * 0.68) - total_height // 2
    
    # Draw each line
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x = (W - text_width) // 2
        y = start_y + i * line_height
        
        # Animate entrance
        line_progress = min(1.0, progress * len(lines) - i)
        if line_progress <= 0:
            continue
        
        # Scale effect
        scale = 0.8 + 0.2 * min(1.0, line_progress)
        alpha = int(255 * min(1.0, line_progress))
        
        # Background pill
        padding_x, padding_y = 30, 12
        bg_rect = [
            x - padding_x,
            y - padding_y,
            x + text_width + padding_x,
            y + font_size + padding_y
        ]
        
        # Rounded rectangle background
        draw.rounded_rectangle(bg_rect, radius=20, fill=(0, 0, 0, min(200, alpha)))
        
        # Draw text with glow effect
        glow_color = (*theme["accent"], 60)
        for offset in [(2, 2), (-2, -2), (2, -2), (-2, 2)]:
            draw.text((x + offset[0], y + offset[1]), line, font=font, fill=glow_color)
        
        # Main text - highlight emphasis words
        if emphasis_words:
            # Draw word by word for emphasis
            words = line.split()
            word_x = x
            for word in words:
                word_bbox = draw.textbbox((0, 0), word + " ", font=font)
                word_width = word_bbox[2] - word_bbox[0]
                
                # Check if this word should be emphasized
                is_emphasis = any(ew.upper() in word.upper() for ew in (emphasis_words or []))
                
                if is_emphasis:
                    # Draw with accent color
                    draw.text((word_x, y), word, font=font, fill=theme["accent2"])
                else:
                    draw.text((word_x, y), word, font=font, fill=(255, 255, 255, alpha))
                
                word_x += word_width
        else:
            draw.text((x, y), line, font=font, fill=(255, 255, 255, alpha))
    
    return img

def draw_hook_frame(img: Image.Image, text: str, theme: dict, progress: float) -> Image.Image:
    """Special hook frame with maximum impact"""
    draw = ImageDraw.Draw(img, "RGBA")
    
    # Large impactful text
    font_size = 110
    font = get_font(font_size)
    
    # Wrap text
    max_width = W - 100
    lines = wrap_text_smart(text.upper(), max_width, font)
    
    line_height = font_size + 25
    total_height = len(lines) * line_height
    start_y = (H - total_height) // 2 - 50
    
    # Pulsing background effect
    pulse = 0.9 + 0.1 * math.sin(progress * math.pi * 4)
    
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x = (W - text_width) // 2
        y = start_y + i * line_height
        
        # Glow effect
        glow_size = int(8 * pulse)
        for g in range(glow_size, 0, -2):
            glow_alpha = int(40 * (1 - g / glow_size))
            glow_color = (*theme["accent"], glow_alpha)
            draw.text((x, y), line, font=font, fill=glow_color,
                     stroke_width=g, stroke_fill=glow_color)
        
        # Main text with accent color
        draw.text((x, y), line, font=font, fill=theme["accent"],
                 stroke_width=3, stroke_fill=(0, 0, 0))
    
    # Add "WATCH THIS" or similar hook indicator
    small_font = get_font(32)
    indicator = "👇 WATCH THIS"
    ind_bbox = draw.textbbox((0, 0), indicator, font=small_font)
    ind_x = (W - (ind_bbox[2] - ind_bbox[0])) // 2
    ind_y = start_y + total_height + 60
    
    draw.rounded_rectangle(
        [ind_x - 20, ind_y - 10, ind_x + (ind_bbox[2] - ind_bbox[0]) + 20, ind_y + 40],
        radius=25, fill=theme["accent"]
    )
    draw.text((ind_x, ind_y), indicator, font=small_font, fill=(255, 255, 255))
    
    return img

def draw_progress_indicator(img: Image.Image, current: int, total: int, theme: dict) -> Image.Image:
    """Draw scene progress indicator"""
    draw = ImageDraw.Draw(img, "RGBA")
    
    # Progress bar at bottom
    bar_height = 6
    bar_y = H - 20
    
    # Background
    draw.rectangle([0, bar_y, W, bar_y + bar_height], fill=(255, 255, 255, 40))
    
    # Progress
    progress_width = int(W * current / max(total, 1))
    draw.rectangle([0, bar_y, progress_width, bar_y + bar_height], fill=theme["accent"])
    
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
    """Generate high-quality TTS"""
    if not EMERGENT_LLM_KEY:
        return None
    try:
        tts = OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY)
        audio_bytes = await tts.generate_speech(
            text=text,
            model="tts-1-hd",  # HD quality
            voice="nova",  # Energetic voice
            speed=1.05  # Slightly faster for engagement
        )
        audio_path = os.path.join(AUDIO_DIR, f"voice_{video_id}.mp3")
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)
        return audio_path
    except Exception as e:
        print(f"[TTS] Error: {e}")
        return None

async def build_premium_video(script: dict, video_id: str, update_progress) -> Optional[str]:
    """Build premium quality video with TikTok-style captions"""
    if not PIL_OK:
        return None
    
    scenes = script.get("scenes", [])
    if not scenes:
        return None
    
    # Select random theme
    theme_name = random.choice(list(THEMES.keys()))
    theme = THEMES[theme_name]
    
    ff = get_ffmpeg()
    tmp = tempfile.mkdtemp(prefix="vf_pro_")
    
    try:
        all_frames = []
        total_scenes = len(scenes)
        
        # Calculate total frames
        total_duration = sum(s.get("duration", 3) for s in scenes)
        
        frame_count = 0
        for si, scene in enumerate(scenes):
            await update_progress(
                55 + int((si / total_scenes) * 30),
                f"Rendering scene {si+1}/{total_scenes}"
            )
            
            caption = scene.get("caption_text") or scene.get("spoken_text", "")
            duration = scene.get("duration", 3)
            phase = scene.get("phase", "body")
            emphasis = scene.get("emphasis_words", [])
            
            n_frames = int(duration * FPS)
            
            for fi in range(n_frames):
                # Progress within scene
                scene_progress = fi / max(n_frames - 1, 1)
                global_progress = frame_count / (total_duration * FPS)
                
                # Create base frame with gradient
                frame = create_gradient_background(W, H, theme, global_progress)
                
                # Add particle effects
                frame = add_particle_effects(frame, theme, frame_count, int(total_duration * FPS))
                
                # Draw content based on phase
                if phase == "hook":
                    frame = draw_hook_frame(frame, caption, theme, scene_progress)
                else:
                    # Subtitle animation
                    text_progress = min(1.0, scene_progress * 3)  # Quick entrance
                    frame = draw_tiktok_subtitle(frame, caption, theme, text_progress, emphasis)
                
                # Progress indicator
                frame = draw_progress_indicator(frame, si + 1, total_scenes, theme)
                
                all_frames.append(frame)
                frame_count += 1
        
        await update_progress(85, "Saving frames...")
        
        # Save frames
        frame_paths = []
        for fi, frame in enumerate(all_frames):
            p = os.path.join(tmp, f"f{fi:07d}.jpg")
            frame.save(p, "JPEG", quality=92)
            frame_paths.append(p)
        
        await update_progress(88, "Generating AI voice...")
        
        # Generate TTS
        full_text = " ".join(s.get("spoken_text", "") for s in scenes)
        audio_path = await generate_tts(full_text, video_id)
        
        await update_progress(92, "Encoding video...")
        
        # Create frame list
        lst = os.path.join(tmp, "frames.txt")
        with open(lst, "w") as fh:
            for fp in frame_paths:
                fh.write(f"file '{fp}'\nduration {1/FPS:.6f}\n")
            if frame_paths:
                fh.write(f"file '{frame_paths[-1]}'\n")
        
        out_path = os.path.join(OUT_DIR, f"viral_{video_id}.mp4")
        
        # FFmpeg encoding with high quality
        if audio_path and os.path.exists(audio_path):
            cmd = [
                ff, "-y",
                "-f", "concat", "-safe", "0", "-i", lst,
                "-i", audio_path,
                "-vf", "scale=1080:1920,setsar=1",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                "-r", str(FPS), "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                out_path
            ]
        else:
            cmd = [
                ff, "-y",
                "-f", "concat", "-safe", "0", "-i", lst,
                "-vf", "scale=1080:1920,setsar=1",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-r", str(FPS), "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                out_path
            ]
        
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
    Premium viral video generation pipeline
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
            
            # Step 1: Fetch trends for context
            await update_progress(8, "Fetching viral trends...")
            trends = fetch_trends()
            trend_context = "\n".join(f"- {t}" for t in trends[:5]) if trends else "General viral trends"
            
            # Step 2: Generate optimized viral idea with strong hook
            await update_progress(15, "Creating viral idea...")
            
            idea_prompt = f"""You are the world's best viral content strategist. Based on this request:

"{req.prompt}"

Current trending topics for context:
{trend_context}

Generate ONE perfect viral video concept optimized for TikTok/Shorts.

CRITICAL: The HOOK must be incredibly strong - it has 1.5 seconds to stop the scroll.

Hook techniques that work:
- Pattern interrupt ("Stop scrolling if...")
- Controversial take ("Nobody talks about this...")
- Curiosity gap ("The real reason why...")
- Fear/urgency ("You're making this mistake...")
- Transformation ("How I went from X to Y...")

OUTPUT JSON only:
{{
  "niche": "detected niche",
  "title": "Scroll-stopping title (8-12 words, power words)",
  "idea": "2-sentence video concept",
  "hook": "EXACT opening words - must create instant curiosity in 1.5 seconds",
  "hook_type": "pattern_interrupt|curiosity_gap|fear|transformation|controversy",
  "emotion": "primary emotion triggered",
  "why_viral": "1 sentence on the psychological trigger",
  "emphasis_words": ["key", "words", "to", "highlight"]
}}"""
            
            idea_raw = await ai_generate(idea_prompt, 
                "You create viral concepts that get millions of views. Output ONLY valid JSON.", 1000)
            idea_data = parse_json(idea_raw)
            
            # Step 3: Generate premium script
            await update_progress(30, "Writing viral script...")
            
            script_prompt = f"""Create a PREMIUM viral video script. This must be SHORT, PUNCHY, and ADDICTIVE.

CONCEPT:
- Title: {idea_data.get('title', '')}
- Hook: {idea_data.get('hook', '')}
- Idea: {idea_data.get('idea', '')}
- Emotion: {idea_data.get('emotion', 'curiosity')}

RULES FOR VIRAL SCRIPTS:
1. HOOK (0-3s): Pattern interrupt, stop the scroll IMMEDIATELY
2. TENSION (3-15s): Build curiosity, create "I need to know" feeling
3. PAYOFF (15-30s): Deliver value, create "aha" moment
4. LOOP (last 2s): End that makes viewers rewatch

WRITING STYLE:
- Short sentences. Punchy. Direct.
- Conversational, not robotic
- Each word must EARN its place
- Create rhythm and flow

OUTPUT JSON:
{{
  "title": "final optimized title",
  "hook": "exact hook line",
  "total_duration": 30,
  "scenes": [
    {{
      "id": 1,
      "phase": "hook",
      "duration": 3,
      "spoken_text": "Natural spoken words",
      "caption_text": "SHORT ON-SCREEN TEXT",
      "emphasis_words": ["KEY", "WORDS"]
    }},
    {{
      "id": 2,
      "phase": "build",
      "duration": 8,
      "spoken_text": "...",
      "caption_text": "...",
      "emphasis_words": []
    }},
    {{
      "id": 3,
      "phase": "payoff",
      "duration": 12,
      "spoken_text": "...",
      "caption_text": "...",
      "emphasis_words": []
    }},
    {{
      "id": 4,
      "phase": "loop",
      "duration": 4,
      "spoken_text": "...",
      "caption_text": "...",
      "emphasis_words": []
    }}
  ],
  "hashtags": ["#viral", "#fyp", "#niche"],
  "caption": "Video caption for posting"
}}

Keep total duration 25-35 seconds. 4-5 scenes max."""
            
            script_raw = await ai_generate(script_prompt,
                "You write viral scripts that keep viewers hooked. Output ONLY valid JSON.", 1800)
            script_data = parse_json(script_raw)
            
            # Step 4: Build premium video
            await update_progress(50, "Building video...")
            
            video_path = await build_premium_video(script_data, job_id, update_progress)
            
            await update_progress(96, "Finalizing...")
            
            # Prepare result
            video_url = f"/api/video/{job_id}" if video_path and os.path.exists(video_path) else None
            
            result = {
                "success": True,
                "idea": {
                    "niche": idea_data.get("niche", "general"),
                    "title": idea_data.get("title", script_data.get("title", "")),
                    "concept": idea_data.get("idea", ""),
                    "hook": idea_data.get("hook", script_data.get("hook", "")),
                    "hook_type": idea_data.get("hook_type", "curiosity_gap"),
                    "emotion": idea_data.get("emotion", "curiosity"),
                    "why_viral": idea_data.get("why_viral", ""),
                },
                "script": {
                    "title": script_data.get("title", ""),
                    "hook": script_data.get("hook", ""),
                    "duration": script_data.get("total_duration", 30),
                    "scenes": script_data.get("scenes", []),
                    "hashtags": script_data.get("hashtags", []),
                    "caption": script_data.get("caption", ""),
                },
                "video": {
                    "id": job_id,
                    "url": video_url,
                    "ready": video_url is not None,
                }
            }
            
            # Save to MongoDB for learning
            await db.generations.insert_one({
                "job_id": job_id,
                "prompt": req.prompt,
                "idea": result["idea"],
                "script": result["script"],
                "video_ready": result["video"]["ready"],
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
            import traceback
            traceback.print_exc()
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
        # Check MongoDB
        doc = await db.generations.find_one({"job_id": job_id}, {"_id": 0})
        if doc:
            return {
                "status": "complete",
                "progress": 100,
                "step": "Done!",
                "result": {
                    "success": True,
                    "idea": doc.get("idea"),
                    "script": doc.get("script"),
                    "video": {
                        "id": job_id,
                        "url": f"/api/video/{job_id}",
                        "ready": doc.get("video_ready", False)
                    }
                }
            }
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]

@app.get("/api/video/{video_id}")
async def get_video(video_id: str):
    """Download video"""
    path = os.path.join(OUT_DIR, f"viral_{video_id}.mp4")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(path, media_type="video/mp4", filename=f"viral_{video_id}.mp4")

@app.get("/api/history")
async def get_history():
    """Get generation history"""
    cursor = db.generations.find({}, {"_id": 0}).sort("created_at", -1).limit(20)
    items = await cursor.to_list(length=20)
    return {"history": items}

# ============ STARTUP ============

@app.on_event("startup")
async def startup():
    print("✓ ViralForge v3.1 Pro — Production Ready")
