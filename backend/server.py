"""
ViralForge v3 — FastAPI Backend
================================
AI-Powered Viral Content Generation Platform
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
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import time

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
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
EXP_DIR = os.path.join(DATA_DIR, "exports")
AUDIO_DIR = os.path.join(DATA_DIR, "audio")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(EXP_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

# API Key
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

# Video dimensions
W, H = 1080, 1920
FPS = 30

# Color Palettes
PALETTES = {
    "amber":   {"bg": (8, 6, 2),    "accent": (245, 166, 35),  "text": (255, 255, 255)},
    "crimson": {"bg": (8, 2, 4),    "accent": (220, 30, 60),   "text": (255, 255, 255)},
    "ice":     {"bg": (2, 6, 14),   "accent": (0, 200, 255),   "text": (255, 255, 255)},
    "void":    {"bg": (4, 0, 14),   "accent": (140, 0, 255),   "text": (255, 255, 255)},
    "forest":  {"bg": (2, 10, 4),   "accent": (0, 210, 80),    "text": (255, 255, 255)},
    "solar":   {"bg": (10, 6, 0),   "accent": (255, 140, 0),   "text": (255, 255, 255)},
}

# In-memory state
app_state = {
    "trends": [],
    "patterns": {},
    "last_fetch": None,
    "fetch_status": "idle",
    "active_jobs": {},
}

# ============ MODELS ============

class GenerateRequest(BaseModel):
    niche: str = "general"

class VideoRequest(BaseModel):
    script_id: str = ""
    script: dict
    palette: str = "amber"

class PerformanceRequest(BaseModel):
    script_id: str
    video_id: str = ""
    platform: str
    views: int
    likes: int = 0
    shares: int = 0

class FetchTrendsRequest(BaseModel):
    categories: list = ["trending", "entertainment", "gaming", "howto"]
    force: bool = False

# ============ HEALTH ============

@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "version": "3.0",
        "ts": datetime.now(timezone.utc).isoformat(),
        "fetch_status": app_state["fetch_status"],
        "has_key": bool(EMERGENT_LLM_KEY),
    }

# ============ TRENDS ============

YT_FEEDS = {
    "trending": "https://www.youtube.com/feeds/videos.xml?chart=trending&gl=US&hl=en",
    "music": "https://www.youtube.com/feeds/videos.xml?chart=trending&gl=US&hl=en&videoCategoryId=10",
    "gaming": "https://www.youtube.com/feeds/videos.xml?chart=trending&gl=US&hl=en&videoCategoryId=20",
    "entertainment": "https://www.youtube.com/feeds/videos.xml?chart=trending&gl=US&hl=en&videoCategoryId=24",
    "howto": "https://www.youtube.com/feeds/videos.xml?chart=trending&gl=US&hl=en&videoCategoryId=26",
}

HOOK_RULES = [
    ("number_hook", lambda t: bool(re.match(r"^\d+", t))),
    ("question_hook", lambda t: t.strip().endswith("?")),
    ("curiosity_gap", lambda t: any(w in t for w in ["secret", "truth", "revealed", "nobody", "hidden", "real reason"])),
    ("pattern_interrupt", lambda t: any(t.startswith(w) for w in ["pov", "stop", "wait", "story time", "hot take"])),
    ("transformation", lambda t: any(w in t for w in ["before", "after", "glow up", "changed", "transform"])),
    ("list_format", lambda t: any(w in t for w in ["things", "ways", "reasons", "tips", "mistakes", "signs"])),
    ("fear_hook", lambda t: any(w in t for w in ["warning", "danger", "never", "mistake", "wrong", "risk"])),
]

TRIGGERS = {
    "curiosity": ["secret", "truth", "revealed", "hidden", "why", "how", "what if"],
    "fear": ["danger", "warning", "never", "mistake", "wrong", "risk", "stop"],
    "aspiration": ["rich", "success", "dream", "goals", "motivation", "transform"],
    "humor": ["funny", "lol", "wait for it", "unexpected", "fail", "prank"],
    "relatability": ["pov", "when you", "that moment", "we all", "literally"],
    "controversy": ["hot take", "unpopular", "controversial", "nobody talks"],
}

def analyze_title(title: str) -> dict:
    t = title.lower().strip()
    hook = "neutral"
    for name, rule in HOOK_RULES:
        if rule(t):
            hook = name
            break
    trigs = [k for k, words in TRIGGERS.items() if any(w in t for w in words)]
    return {
        "hook_type": hook,
        "triggers": trigs,
        "has_number": bool(re.search(r"\d", title)),
        "has_question": "?" in title,
        "word_count": len(title.split()),
    }

def score_trend(video: dict, analysis: dict) -> float:
    s = 0.0
    views = max(video.get("views", 1), 1)
    s += min(25, math.log10(views) * 3.5)
    hook_scores = {
        "curiosity_gap": 28, "pattern_interrupt": 26, "fear_hook": 24,
        "number_hook": 22, "transformation": 20, "question_hook": 18,
        "list_format": 16, "neutral": 4,
    }
    s += hook_scores.get(analysis["hook_type"], 4)
    s += len(analysis["triggers"]) * 3.5
    if analysis["has_number"]: s += 4
    if analysis["has_question"]: s += 3
    if 5 <= analysis["word_count"] <= 13: s += 4
    return round(min(100, s), 1)

def fetch_url(url: str, retries: int = 3) -> bytes:
    headers = {"User-Agent": "ViralForge/3.0"}
    for attempt in range(retries):
        try:
            req = Request(url, headers=headers)
            return urlopen(req, timeout=12).read()
        except (URLError, HTTPError):
            if attempt == retries - 1:
                raise
            time.sleep(1.5)
    return b""

def parse_youtube_rss(data: bytes, label: str) -> list:
    results = []
    try:
        root = ET.fromstring(data)
        ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
        for entry in root.findall("a:entry", ns):
            vid_id = getattr(entry.find("yt:videoId", ns), "text", "") or ""
            title = getattr(entry.find("a:title", ns), "text", "") or ""
            if title and vid_id:
                results.append({
                    "id": vid_id,
                    "title": title,
                    "views": 100000,  # Estimated
                    "source": label,
                    "thumbnail": f"https://img.youtube.com/vi/{vid_id}/mqdefault.jpg",
                })
    except Exception as e:
        print(f"[YT parse:{label}] {e}")
    return results

def fetch_youtube_trends(categories: list) -> list:
    results = []
    for cat in categories:
        url = YT_FEEDS.get(cat)
        if not url:
            continue
        try:
            data = fetch_url(url)
            items = parse_youtube_rss(data, f"yt:{cat}")
            results.extend(items)
            print(f"[YT:{cat}] {len(items)} items")
        except Exception as e:
            print(f"[YT:{cat}] FAILED: {e}")
    return results

def pattern_report(trends: list) -> dict:
    hf, tf = {}, {}
    for t in trends:
        a = t.get("analysis", {})
        h = a.get("hook_type", "neutral")
        hf[h] = hf.get(h, 0) + 1
        for tr in a.get("triggers", []):
            tf[tr] = tf.get(tr, 0) + 1
    avg = sum(t.get("virality_score", 0) for t in trends) / max(len(trends), 1)
    top_t = sorted(tf.items(), key=lambda x: x[1], reverse=True)
    return {
        "total": len(trends),
        "avg_score": round(avg, 1),
        "top_hook": max(hf, key=hf.get) if hf else "neutral",
        "top_triggers": [x[0] for x in top_t[:5]],
        "hook_dist": hf,
        "trigger_dist": tf,
        "top_5": [{"title": t.get("title", ""), "score": t.get("virality_score", 0),
                   "source": t.get("source", ""), "hook": t.get("analysis", {}).get("hook_type", "")}
                  for t in trends[:5]],
    }

@app.post("/api/trends/fetch")
async def fetch_trends(req: FetchTrendsRequest, background_tasks: BackgroundTasks):
    if app_state["fetch_status"] == "fetching":
        return {"status": "already_running", "message": "Fetch in progress"}
    
    async def run_fetch():
        app_state["fetch_status"] = "fetching"
        try:
            raw = fetch_youtube_trends(req.categories)
            unique = []
            seen = set()
            for v in raw:
                if v["id"] in seen:
                    continue
                seen.add(v["id"])
                a = analyze_title(v["title"])
                v["analysis"] = a
                v["virality_score"] = score_trend(v, a)
                unique.append(v)
            unique.sort(key=lambda x: x["virality_score"], reverse=True)
            app_state["trends"] = unique
            app_state["patterns"] = pattern_report(unique)
            app_state["last_fetch"] = datetime.now(timezone.utc).isoformat()
            app_state["fetch_status"] = "done"
            
            # Save to MongoDB
            await db.trends.delete_many({})
            if unique:
                await db.trends.insert_many([{**t, "_id": t["id"]} for t in unique[:100]])
            
            print(f"[Fetch] Complete: {len(unique)} trends")
        except Exception as e:
            app_state["fetch_status"] = "error"
            print(f"[Fetch] ERROR: {e}")
    
    background_tasks.add_task(asyncio.to_thread, lambda: asyncio.run(run_fetch()))
    return {"status": "started"}

@app.get("/api/trends")
async def get_trends(limit: int = 50, hook: str = "", sort: str = "virality_score"):
    data = app_state["trends"]
    if not data:
        # Load from MongoDB
        cursor = db.trends.find({}, {"_id": 0}).sort("virality_score", -1).limit(limit)
        data = await cursor.to_list(length=limit)
    
    if hook:
        data = [t for t in data if t.get("analysis", {}).get("hook_type") == hook]
    
    return {
        "trends": data[:limit],
        "total": len(data),
        "last_fetch": app_state["last_fetch"],
        "status": app_state["fetch_status"],
    }

@app.get("/api/trends/patterns")
async def get_patterns():
    p = app_state["patterns"]
    if not p and app_state["trends"]:
        p = pattern_report(app_state["trends"])
    return p or {"error": "No data — fetch trends first"}

# ============ AI ENGINE ============

async def generate_with_ai(prompt: str, system: str = "", max_tokens: int = 2000) -> str:
    """Generate content using AI"""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="EMERGENT_LLM_KEY not configured")
    
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"viralforge-{uuid.uuid4()}",
        system_message=system or "You are a viral content expert."
    ).with_model("openai", "gpt-4o")
    
    response = await chat.send_message(UserMessage(text=prompt))
    return response

def parse_json_response(raw: str) -> dict | list:
    """Parse JSON from AI response"""
    clean = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    clean = re.sub(r"\s*```$", "", clean).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", clean)
        if m:
            return json.loads(m.group(1))
        raise ValueError(f"No JSON found")

async def generate_options(niche: str, trend_context: dict, n: int = 10) -> list:
    """Generate viral video options"""
    top_trends = trend_context.get("top_5", [])[:5]
    top_hook = trend_context.get("top_hook", "curiosity_gap")
    top_triggers = trend_context.get("top_triggers", ["curiosity", "aspiration"])[:3]
    
    prompt = f"""Generate exactly {n} DIFFERENT viral video options for this context.

MARKET INTELLIGENCE:
- Niche: {niche}
- Currently dominating hook type: {top_hook}
- Top emotional triggers right now: {', '.join(top_triggers)}
- Trending titles for inspiration (DO NOT copy):
{chr(10).join(f'  {i+1}. "{t["title"]}" ({t["hook"]})' for i, t in enumerate(top_trends))}

RULES:
- Each option must use a DIFFERENT hook type
- Each title must be immediately compelling
- Hook = exact first 1-2 sentences the creator says
- Vary the structure: list, story, transformation, tutorial, hot take
- Think platform-native: TikTok, YouTube Shorts, Reels

OUTPUT exactly {n} items in this JSON array format:
[
  {{
    "title": "SEO-optimized video title with power words",
    "hook": "Exact opening words — must stop scroll in 2 seconds",
    "concept": "2-sentence summary of the video content",
    "structure": "list|story|transformation|tutorial|hot_take|problem_solve",
    "hook_type": "curiosity_gap|number_hook|question_hook|pattern_interrupt|fear_hook|transformation|list_format",
    "primary_trigger": "curiosity|fear|aspiration|humor|relatability|controversy",
    "target_platform": "tiktok|youtube_shorts|both",
    "estimated_duration": 30
  }}
]"""
    
    system = """You are the world's best viral short-form content strategist.
You generate video concepts that consistently exceed 1M views.
Output ONLY valid JSON arrays. No commentary, no markdown, no preamble."""
    
    raw = await generate_with_ai(prompt, system, max_tokens=2400)
    options = parse_json_response(raw)
    return options[:n] if isinstance(options, list) else []

async def score_options(options: list, niche: str) -> list:
    """Score each option on 6 dimensions"""
    options_text = "\n".join(
        f'{i+1}. Title: "{o["title"]}"\n   Hook: "{o["hook"]}"\n   Structure: {o.get("structure","")}'
        for i, o in enumerate(options)
    )
    
    prompt = f"""Score these {len(options)} video concepts on 6 dimensions (each 0-10).

NICHE: {niche}

OPTIONS:
{options_text}

SCORING DIMENSIONS (score 0-10, be harsh, differentiate):
- hook_strength: Does the opening grab in 2 seconds?
- curiosity_gap: Creates unanswered question?
- emotional_trigger: Activates strong emotion?
- trend_alignment: Matches current viral patterns?
- retention_arc: Will viewers watch to the end?
- clarity: Premise immediately understood?

OUTPUT JSON array with one object per option (maintain order):
[
  {{
    "option_idx": 0,
    "hook_strength": 8,
    "curiosity_gap": 7,
    "emotional_trigger": 9,
    "trend_alignment": 6,
    "retention_arc": 7,
    "clarity": 9
  }}
]"""
    
    system = """You are a data-driven viral content analyst.
Score with surgical precision. NEVER give every option the same score.
Output ONLY valid JSON."""
    
    raw = await generate_with_ai(prompt, system, max_tokens=1200)
    scores = parse_json_response(raw)
    
    dims = ["hook_strength", "curiosity_gap", "emotional_trigger", "trend_alignment", "retention_arc", "clarity"]
    weights = [0.30, 0.20, 0.20, 0.15, 0.10, 0.05]
    
    scored = []
    for i, (opt, raw_score) in enumerate(zip(options, scores)):
        dim_scores = {d: raw_score.get(d, 5) for d in dims}
        base = sum(dim_scores[d] * weights[j] * 10 for j, d in enumerate(dims))
        scored.append({
            **opt,
            "idx": i,
            "scores": dim_scores,
            "virality_score": round(min(100, base), 1),
        })
    
    return sorted(scored, key=lambda x: x["virality_score"], reverse=True)

async def select_best(scored_options: list, niche: str) -> dict:
    """Select the best option with reasoning"""
    top3 = scored_options[:3]
    comparison = "\n".join(
        f'OPTION {o["idx"]+1} (Score: {o["virality_score"]}): "{o["title"]}"\n'
        f'  Hook: "{o["hook"]}"'
        for o in top3
    )
    
    prompt = f"""Select the single BEST viral video option and explain why.

NICHE: {niche}
TOP 3 OPTIONS:
{comparison}

OUTPUT JSON:
{{
  "winner_idx": 0,
  "winner_title": "...",
  "winner_hook": "...",
  "why_wins": "2-3 specific sentences explaining why this wins",
  "predicted_views_range": "100K-500K",
  "strongest_element": "The single most powerful element",
  "critical_execution_tip": "One thing that makes or breaks this video"
}}"""
    
    system = """You are a viral content expert making a final recommendation.
Be direct and specific about WHY the winner wins. Output ONLY valid JSON."""
    
    raw = await generate_with_ai(prompt, system, max_tokens=800)
    return parse_json_response(raw)

async def generate_script(winner: dict, decision: dict, niche: str) -> dict:
    """Generate a full production-ready script"""
    prompt = f"""Write a complete, production-ready script for this viral video.

SELECTED CONCEPT:
- Title: "{winner['title']}"
- Hook: "{winner['hook']}"
- Structure: {winner.get('structure','story')}
- Niche: {niche}

EXECUTION TIP: {decision.get('critical_execution_tip', '')}

SCRIPT STRUCTURE:
- Hook (0-3s): Exact opening that stops scroll
- Build (3-15s): Establish stakes, deepen curiosity
- Payoff (15-45s): Deliver value, resolution
- Loop (last 2s): Ending that makes viewers rewatch

REQUIREMENTS:
- Each scene: spoken text + visual instruction + caption text
- Fast pacing: short sentences, clear cuts
- Captions DIFFERENT from spoken text (shorter, punchier)
- Total duration: 30-55 seconds

OUTPUT JSON:
{{
  "title": "final optimized title",
  "hook": "hook line",
  "total_duration": 42,
  "scenes": [
    {{
      "id": 1,
      "phase": "hook",
      "start_time": 0,
      "end_time": 3,
      "spoken_text": "exact words creator says",
      "caption_text": "ON-SCREEN TEXT (shorter)",
      "visual_direction": "what viewer sees",
      "pacing": "fast",
      "transition": "cut|zoom_in|fade"
    }}
  ],
  "music_direction": "describe ideal background track",
  "hashtags": ["#tag1","#tag2","#tag3","#tag4","#tag5"],
  "description": "YouTube/TikTok description",
  "thumbnail_concept": "describe ideal thumbnail"
}}"""
    
    system = """You are an elite short-form video scriptwriter.
Every word must earn its place. Output ONLY valid JSON. Zero preamble."""
    
    raw = await generate_with_ai(prompt, system, max_tokens=2000)
    return parse_json_response(raw)

@app.post("/api/generate")
async def generate(req: GenerateRequest):
    """Full AI pipeline: generate → score → select → script"""
    niche = req.niche
    
    # Build trend context
    trends = app_state["trends"]
    ctx = pattern_report(trends) if trends else {
        "top_hook": "curiosity_gap",
        "top_triggers": ["curiosity", "aspiration"],
        "avg_score": 60,
        "top_5": [],
    }
    
    try:
        print(f"[Engine] Generating 10 options for niche={niche}...")
        options = await generate_options(niche, ctx, n=10)
        
        print(f"[Engine] Scoring {len(options)} options...")
        scored = await score_options(options, niche)
        
        print(f"[Engine] Selecting winner...")
        decision = await select_best(scored, niche)
        winner_idx = decision.get("winner_idx", 0)
        winner = scored[0] if winner_idx >= len(scored) else scored[winner_idx]
        
        print(f"[Engine] Building script for: {winner.get('title', '')}")
        script = await generate_script(winner, decision, niche)
        
        # Save to DB
        batch_id = str(uuid.uuid4())[:12]
        script_id = str(uuid.uuid4())[:12]
        
        await db.idea_batches.insert_one({
            "id": batch_id,
            "niche": niche,
            "trend_context": ctx,
            "ideas": scored,
            "selected_idx": winner_idx,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        
        await db.scripts.insert_one({
            "id": script_id,
            "batch_id": batch_id,
            "title": script.get("title", ""),
            "hook": script.get("hook", ""),
            "script": script,
            "decision": decision,
            "virality_score": winner.get("virality_score", 0),
            "niche": niche,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        
        return {
            "batch_id": batch_id,
            "script_id": script_id,
            "niche": niche,
            "options": scored,
            "winner": winner,
            "decision": decision,
            "script": script,
            "total_options": len(scored),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/scripts")
async def list_scripts():
    cursor = db.scripts.find({}, {"_id": 0}).sort("created_at", -1).limit(30)
    scripts = await cursor.to_list(length=30)
    return {"scripts": scripts}

@app.get("/api/stats")
async def stats():
    trends = app_state["trends"]
    scripts_count = await db.scripts.count_documents({})
    videos_count = await db.videos.count_documents({"status": "done"})
    pats = app_state["patterns"] or (pattern_report(trends) if trends else {})
    
    return {
        "trends_count": len(trends),
        "scripts_count": scripts_count,
        "videos_count": videos_count,
        "avg_score": pats.get("avg_score", 0),
        "top_hook": pats.get("top_hook", "—"),
        "top_triggers": pats.get("top_triggers", [])[:3],
        "last_fetch": app_state["last_fetch"],
        "fetch_status": app_state["fetch_status"],
    }

# ============ VIDEO GENERATION ============

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
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
    return lines[:3]

def make_frame(caption: str, visual: str, scene_n: int, total: int, pal_name: str, phase: str) -> Image.Image:
    pal = PALETTES.get(pal_name, PALETTES["amber"])
    img = Image.new("RGB", (W, H), pal["bg"])
    draw = ImageDraw.Draw(img)
    
    # Gradient background
    for y in range(H):
        p = y / H
        r = int(pal["bg"][0] + (pal["accent"][0] - pal["bg"][0]) * p * 0.15)
        g = int(pal["bg"][1] + (pal["accent"][1] - pal["bg"][1]) * p * 0.10)
        b = int(pal["bg"][2] + (pal["accent"][2] - pal["bg"][2]) * p * 0.12)
        draw.line([(0, y), (W, y)], fill=(max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))))
    
    acc = pal["accent"]
    
    if phase == "hook":
        # Full accent background for hook
        draw.rectangle([0, 0, W, H], fill=acc)
        lines = wrap_text(caption.upper(), 15)
        fs = 110 if len(lines) == 1 else 90
        font = get_font(fs)
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
        # Scene progress bar
        prog = int(W * scene_n / max(total, 1))
        draw.rectangle([0, H - 9, W, H], fill=tuple(c // 5 for c in acc))
        draw.rectangle([0, H - 9, prog, H], fill=acc)
        
        # Scene counter
        sf = get_font(30)
        draw.text((36, 38), f"{scene_n}/{total}", fill=acc, font=sf)
        
        # Caption
        lines = wrap_text(caption.upper(), 16)
        fs = 100 if len(lines) == 1 else 85
        font = get_font(fs)
        base_y = int(H * 0.72)
        total_h = len(lines) * (fs + 14)
        y = base_y - total_h // 2
        
        for ln in lines:
            bbox = draw.textbbox((0, 0), ln, font=font)
            tw = bbox[2] - bbox[0]
            x = (W - tw) // 2
            # Shadow
            for ox, oy in [(5, 5), (8, 8)]:
                draw.text((x + ox, y + oy), ln, fill=(0, 0, 0), font=font)
            # Accent outline
            for ox, oy in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
                draw.text((x + ox, y + oy), ln, fill=acc, font=font)
            # Main text
            draw.text((x, y), ln, fill=pal["text"], font=font)
            y += fs + 14
    
    return img

def scene_frames(scene: dict, scene_n: int, total_scenes: int, pal_name: str, fps: int = FPS) -> list:
    caption = scene.get("caption_text") or scene.get("spoken_text", "")
    visual = scene.get("visual_direction", "")
    duration = scene.get("end_time", 3) - scene.get("start_time", 0)
    if duration <= 0:
        duration = 3
    phase = scene.get("phase", "body")
    
    n_frames = max(int(duration * fps), fps // 2)
    base = make_frame(caption, visual, scene_n, total_scenes, pal_name, phase)
    
    frames = []
    for i in range(n_frames):
        frame = base.copy()
        # Fade in on first frames
        if i < 4:
            fade = Image.new("RGB", (W, H), (0, 0, 0))
            frame = Image.blend(fade, frame, i / 4)
        frames.append(frame)
    
    return frames

def get_ffmpeg() -> str:
    r = subprocess.run(["which", "ffmpeg"], capture_output=True)
    if r.returncode == 0:
        return r.stdout.decode().strip()
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except:
        return "ffmpeg"

async def generate_tts_audio(text: str, video_id: str) -> Optional[str]:
    """Generate TTS audio for the script"""
    if not EMERGENT_LLM_KEY:
        return None
    
    try:
        tts = OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY)
        audio_bytes = await tts.generate_speech(
            text=text,
            model="tts-1",
            voice="nova",  # Energetic, upbeat voice
            speed=1.1
        )
        
        audio_path = os.path.join(AUDIO_DIR, f"voice_{video_id}.mp3")
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)
        
        return audio_path
    except Exception as e:
        print(f"[TTS] Error: {e}")
        return None

async def assemble_video(script: dict, video_id: str, palette: str, progress_cb=None) -> Optional[str]:
    """Full pipeline: scenes → PIL frames → TTS audio → FFmpeg MP4"""
    if not PIL_OK:
        if progress_cb: progress_cb(0, "PIL not available")
        return None
    
    scenes = script.get("scenes") or []
    if not scenes:
        if progress_cb: progress_cb(0, "No scenes in script")
        return None
    
    ff = get_ffmpeg()
    tmp = tempfile.mkdtemp(prefix="vf3_")
    
    try:
        all_frames = []
        total_scenes = len(scenes)
        
        # Generate frames
        for si, scene in enumerate(scenes):
            pct = int(10 + (si / total_scenes) * 40)
            if progress_cb:
                progress_cb(pct, f"Rendering scene {si+1}/{total_scenes}...")
            
            frames = scene_frames(scene, si + 1, total_scenes, palette)
            all_frames.extend(frames)
        
        if progress_cb:
            progress_cb(50, f"Saving {len(all_frames)} frames...")
        
        # Save frames
        frame_paths = []
        for fi, frame in enumerate(all_frames):
            p = os.path.join(tmp, f"f{fi:07d}.jpg")
            frame.save(p, "JPEG", quality=90)
            frame_paths.append(p)
        
        # Generate TTS audio
        if progress_cb:
            progress_cb(60, "Generating voice narration...")
        
        full_text = " ".join(s.get("spoken_text", "") for s in scenes)
        audio_path = await generate_tts_audio(full_text, video_id)
        
        if progress_cb:
            progress_cb(75, "Encoding video with FFmpeg...")
        
        # Build frame list for FFmpeg
        lst = os.path.join(tmp, "frames.txt")
        with open(lst, "w") as fh:
            for fp in frame_paths:
                fh.write(f"file '{fp}'\nduration {1/FPS:.6f}\n")
            if frame_paths:
                fh.write(f"file '{frame_paths[-1]}'\n")
        
        out_path = os.path.join(OUT_DIR, f"vf3_{video_id}.mp4")
        
        # FFmpeg command with or without audio
        if audio_path and os.path.exists(audio_path):
            cmd = [
                ff, "-y",
                "-f", "concat", "-safe", "0", "-i", lst,
                "-i", audio_path,
                "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
                       "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1",
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                "-r", str(FPS), "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                out_path,
            ]
        else:
            cmd = [
                ff, "-y",
                "-f", "concat", "-safe", "0", "-i", lst,
                "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
                       "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1",
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-r", str(FPS), "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                out_path,
            ]
        
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode != 0:
            err = result.stderr.decode()[:600]
            print(f"[FFmpeg] Error:\n{err}")
            if progress_cb: progress_cb(0, f"FFmpeg failed")
            return None
        
        if progress_cb: progress_cb(90, "Building export package...")
        
        # Build export package
        export_dir = os.path.join(EXP_DIR, video_id)
        os.makedirs(export_dir, exist_ok=True)
        
        hashtags = " ".join(script.get("hashtags", []))
        caption_text = f"{script.get('title', '')}\n\n{script.get('description', '')}\n\n{hashtags}"
        with open(os.path.join(export_dir, "caption.txt"), "w") as f:
            f.write(caption_text)
        
        meta = {
            "title": script.get("title", ""),
            "description": script.get("description", ""),
            "hashtags": script.get("hashtags", []),
            "hook": script.get("hook", ""),
            "total_duration": script.get("total_duration", 0),
            "scenes": len(scenes),
            "video_id": video_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(os.path.join(export_dir, "metadata.json"), "w") as f:
            json.dump(meta, f, indent=2)
        
        if progress_cb: progress_cb(100, "Complete!")
        
        return out_path
    
    except Exception as e:
        print(f"[assemble_video] {e}")
        if progress_cb: progress_cb(0, f"Error: {str(e)}")
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

@app.post("/api/video/generate")
async def gen_video(req: VideoRequest, background_tasks: BackgroundTasks):
    script = req.script
    script_id = req.script_id
    palette = req.palette
    
    if not script:
        raise HTTPException(status_code=400, detail="script required")
    
    video_id = str(uuid.uuid4())[:12]
    
    app_state["active_jobs"][video_id] = {"status": "queued", "progress": 0, "message": "Queued"}
    
    # Save video record
    await db.videos.insert_one({
        "id": video_id,
        "script_id": script_id,
        "status": "queued",
        "progress": 0,
        "palette": palette,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    
    async def build():
        def progress_cb(pct: int, msg: str):
            app_state["active_jobs"][video_id] = {
                "status": "processing" if pct < 100 else "done",
                "progress": pct,
                "message": msg,
            }
        
        try:
            path = await assemble_video(script, video_id, palette, progress_cb)
            
            if path and os.path.exists(path):
                app_state["active_jobs"][video_id] = {
                    "status": "done", "progress": 100,
                    "message": "Video ready", "video_id": video_id,
                }
                await db.videos.update_one(
                    {"id": video_id},
                    {"$set": {"status": "done", "progress": 100, "file_path": path}}
                )
            else:
                app_state["active_jobs"][video_id] = {
                    "status": "failed", "progress": 0, "message": "Assembly failed",
                }
                await db.videos.update_one(
                    {"id": video_id},
                    {"$set": {"status": "failed", "progress": 0}}
                )
        except Exception as e:
            app_state["active_jobs"][video_id] = {
                "status": "error", "progress": 0, "message": str(e)[:200],
            }
            await db.videos.update_one(
                {"id": video_id},
                {"$set": {"status": "error", "progress": 0}}
            )
    
    background_tasks.add_task(build)
    return {"status": "started", "video_id": video_id}

@app.get("/api/video/status/{video_id}")
async def video_status(video_id: str):
    job = app_state["active_jobs"].get(video_id, {"status": "unknown", "progress": 0})
    vpath = os.path.join(OUT_DIR, f"vf3_{video_id}.mp4")
    epath = os.path.join(EXP_DIR, video_id, "caption.txt")
    
    return {
        **job,
        "video_id": video_id,
        "video_ready": os.path.exists(vpath),
        "export_ready": os.path.exists(epath),
        "size_mb": round(os.path.getsize(vpath) / 1024 / 1024, 2) if os.path.exists(vpath) else 0,
    }

@app.get("/api/videos")
async def list_videos():
    cursor = db.videos.find({}, {"_id": 0}).sort("created_at", -1).limit(30)
    videos = await cursor.to_list(length=30)
    
    result = []
    for v in videos:
        vid = v.get("id", "")
        vpath = os.path.join(OUT_DIR, f"vf3_{vid}.mp4")
        result.append({
            **v,
            "has_video": os.path.exists(vpath),
            "has_export": os.path.exists(os.path.join(EXP_DIR, vid, "caption.txt")),
            "file_size_mb": round(os.path.getsize(vpath) / 1024 / 1024, 2) if os.path.exists(vpath) else 0,
        })
    
    return {"videos": result}

@app.get("/api/video/{video_id}/download")
async def download_video(video_id: str):
    path = os.path.join(OUT_DIR, f"vf3_{video_id}.mp4")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(path, media_type="video/mp4", filename=f"viralforge_{video_id}.mp4")

@app.get("/api/publish/caption/{video_id}")
async def get_caption(video_id: str):
    cap_path = os.path.join(EXP_DIR, video_id, "caption.txt")
    if not os.path.exists(cap_path):
        raise HTTPException(status_code=404, detail="Caption not found")
    with open(cap_path) as f:
        return {"caption": f.read(), "video_id": video_id}

@app.get("/api/video/{video_id}/export")
async def video_export(video_id: str):
    edir = os.path.join(EXP_DIR, video_id)
    result = {}
    for fname in ("caption.txt", "metadata.json"):
        fpath = os.path.join(edir, fname)
        if os.path.exists(fpath):
            with open(fpath) as f:
                result[fname] = f.read() if fname.endswith(".txt") else json.load(f)
    if not result:
        raise HTTPException(status_code=404, detail="Export not found")
    return result

# ============ WEIGHTS ============

@app.get("/api/weights")
async def get_weights():
    weights = await db.weights.find({}, {"_id": 0}).to_list(length=100)
    return {"weights": {w["key"]: w["weight"] for w in weights}}

@app.post("/api/performance")
async def log_performance(req: PerformanceRequest):
    await db.performance.insert_one({
        "script_id": req.script_id,
        "video_id": req.video_id,
        "platform": req.platform,
        "views": req.views,
        "likes": req.likes,
        "shares": req.shares,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"ok": True, "message": "Performance logged"}

# ============ STARTUP ============

@app.on_event("startup")
async def startup():
    # Seed default weights
    count = await db.weights.count_documents({})
    if count == 0:
        defaults = [
            ("hook:curiosity_gap", 1.4), ("hook:pattern_interrupt", 1.3),
            ("hook:fear_hook", 1.2), ("hook:number_hook", 1.1),
            ("hook:transformation", 1.0), ("hook:question_hook", 0.9),
            ("trigger:curiosity", 1.3), ("trigger:fear", 1.2),
            ("trigger:aspiration", 1.1), ("trigger:humor", 0.9),
        ]
        await db.weights.insert_many([{"key": k, "weight": w} for k, w in defaults])
    
    print("✓ ViralForge v3 Backend Ready")
