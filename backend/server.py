"""
ViralForge v3 — The Independent Factory
========================================
Decentralized Architecture: Cloud AI + External APIs + Persistent Storage
Anti-Sleep Strategy: All heavy processing via external services
"""
import os
import json
import uuid
import asyncio
import aiohttp
import hashlib
import threading
import base64
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import feedparser

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

# Emergent AI integrations
from emergentintegrations.llm.chat import LlmChat, UserMessage
from emergentintegrations.llm.openai import OpenAITextToSpeech

app = FastAPI(title="ViralForge v3 — Independent Factory")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ CLOUD CONNECTIONS ============

# MongoDB Atlas (Persistent Cloud Storage)
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "viralforge")
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client[DB_NAME]

# AI Keys
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

# Thread Pool for background tasks
executor = ThreadPoolExecutor(max_workers=4)

# Task Queue (in-memory with MongoDB backup)
task_queue: Dict[str, Dict] = {}

# ============ MODELS ============

class GenerateRequest(BaseModel):
    prompt: Optional[str] = None
    niche: Optional[str] = "general"

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: int
    step: str
    result: Optional[Dict] = None

# ============ 2026 VIRAL INTELLIGENCE ============

HOOK_PATTERNS = {
    "curiosity_gap": {
        "weight": 1.4,
        "triggers": ["secret", "truth", "nobody", "hidden", "real reason", "what they"],
        "template": "The {topic} that {authority} don't want you to know"
    },
    "pattern_interrupt": {
        "weight": 1.35,
        "triggers": ["stop", "wait", "hold on", "listen", "before you"],
        "template": "Stop {action} if you want to {benefit}"
    },
    "fear_based": {
        "weight": 1.3,
        "triggers": ["mistake", "wrong", "danger", "warning", "never", "avoid"],
        "template": "{number} {topic} mistakes that keep you {negative_state}"
    },
    "transformation": {
        "weight": 1.25,
        "triggers": ["how i", "went from", "changed", "before after", "finally"],
        "template": "How I went from {before} to {after} in {timeframe}"
    },
    "controversy": {
        "weight": 1.2,
        "triggers": ["unpopular", "hot take", "controversial", "nobody agrees"],
        "template": "Unpopular opinion: {controversial_statement}"
    },
    "number_hook": {
        "weight": 1.15,
        "triggers": ["3 things", "5 ways", "7 secrets", "10 tips", "reasons"],
        "template": "{number} {topic} {benefit_word} you need to know"
    },
}

TIKTOK_SEO_2026 = [
    "ai", "chatgpt", "side hustle", "passive income", "productivity", "mental health",
    "self improvement", "dating", "gym", "crypto", "investing", "mindset", "motivation",
    "life hack", "cooking", "recipe", "fashion", "skincare", "travel", "storytime",
    "money", "rich", "success", "routine", "tips", "secrets", "hack", "transform"
]

# ============ HEALTH CHECK ============

@app.get("/api/health")
async def health():
    # Check MongoDB connection
    try:
        await db.command("ping")
        db_status = "connected"
    except:
        db_status = "disconnected"
    
    # Count tasks
    pending_tasks = sum(1 for t in task_queue.values() if t["status"] == "processing")
    
    return {
        "status": "operational",
        "version": "3.0-cloud",
        "architecture": "decentralized",
        "database": db_status,
        "ai_ready": bool(EMERGENT_LLM_KEY),
        "pending_tasks": pending_tasks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

# ============ TREND ENGINE (EXTERNAL FEEDS) ============

async def fetch_youtube_rss() -> List[Dict]:
    """Fetch trends from YouTube RSS feeds"""
    feeds = [
        "https://www.youtube.com/feeds/videos.xml?channel_id=UCBcRF18a7Qf58cCRy5xuWwQ",  # Popular
        "https://www.youtube.com/feeds/videos.xml?channel_id=UC-lHJZR3Gqxm24_Vd_AJ5Yw",  # Trending
    ]
    
    results = []
    for url in feeds:
        try:
            feed = await asyncio.to_thread(feedparser.parse, url)
            for entry in feed.entries[:8]:
                results.append({
                    "id": entry.get("yt_videoid", str(uuid.uuid4())[:8]),
                    "title": entry.get("title", ""),
                    "source": "youtube",
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                })
        except Exception as e:
            print(f"[RSS] Error: {e}")
    
    return results

def generate_viral_trends() -> List[Dict]:
    """Generate curated 2026 viral trend patterns"""
    patterns = [
        # Curiosity Gap
        "The Truth About {topic} Nobody Tells You",
        "What {authority} Don't Want You to Know About {topic}",
        "I Discovered the Real Reason Why {phenomenon}",
        # Pattern Interrupt
        "Stop Doing This If You Want to {benefit}",
        "Wait - Before You {action}, Watch This",
        "Hold On - This Changes Everything About {topic}",
        # Fear Based
        "{number} Mistakes That Keep You {negative_state} Forever",
        "Warning: These Habits Are Destroying Your {aspect}",
        "Why You're Failing at {topic} (And How to Fix It)",
        # Transformation
        "How I Went From {before} to {after} in {timeframe}",
        "My {timeframe} Transformation That Shocked Everyone",
        "POV: You Finally {positive_outcome}",
        # Number Hook
        "3 {topic} Secrets That Actually Work in 2026",
        "5 Ways to {benefit} Without {common_method}",
        "7 Signs You're {positive_trait} (Most People Miss #4)",
    ]
    
    topics = ["money", "fitness", "productivity", "relationships", "mindset", "success", "health"]
    
    results = []
    for i, pattern in enumerate(patterns):
        topic = topics[i % len(topics)]
        title = pattern.format(
            topic=topic,
            authority="experts",
            phenomenon="most people fail",
            benefit="get rich",
            action="invest",
            number="3",
            negative_state="broke",
            aspect="mental health",
            before="broke",
            after="$10K/month",
            timeframe="30 days",
            positive_outcome="understand wealth",
            common_method="working harder",
            positive_trait="smarter than average"
        )
        
        results.append({
            "id": f"trend_{i}",
            "title": title,
            "source": "viral_patterns",
            "score": 0,  # Will be scored
        })
    
    return results

def analyze_trend_2026(title: str) -> Dict:
    """2026 Algorithm: Analyze viral potential"""
    title_lower = title.lower()
    
    # Detect hook type
    detected_hook = "neutral"
    hook_weight = 1.0
    
    for hook_type, config in HOOK_PATTERNS.items():
        if any(trigger in title_lower for trigger in config["triggers"]):
            detected_hook = hook_type
            hook_weight = config["weight"]
            break
    
    # SEO keyword match
    seo_matches = [kw for kw in TIKTOK_SEO_2026 if kw in title_lower]
    
    # Word analysis
    word_count = len(title.split())
    has_number = any(c.isdigit() for c in title)
    has_question = "?" in title
    
    # Retention score (0-100)
    retention = 50
    if 6 <= word_count <= 14:
        retention += 15
    if has_number:
        retention += 12
    if has_question:
        retention += 8
    if len(seo_matches) > 0:
        retention += len(seo_matches) * 5
    
    return {
        "hook_type": detected_hook,
        "hook_weight": hook_weight,
        "seo_keywords": seo_matches,
        "retention_score": min(100, retention),
        "word_count": word_count,
        "has_number": has_number,
    }

def score_trend_2026(trend: Dict, analysis: Dict) -> float:
    """
    2026 Scoring Algorithm:
    - Hook Strength: 30%
    - Retention Pattern: 30%
    - SEO Demand: 20%
    - Viral Sentiment: 20%
    """
    hook_score = (50 + (analysis["hook_weight"] - 1.0) * 100) * 0.30
    retention_score = analysis["retention_score"] * 0.30
    seo_score = min(100, len(analysis["seo_keywords"]) * 20) * 0.20
    viral_score = 60 * 0.20  # Base viral sentiment
    
    if analysis["has_number"]:
        viral_score += 5
    
    return round(min(100, hook_score + retention_score + seo_score + viral_score), 1)

@app.post("/api/trends/fetch")
async def fetch_trends(background_tasks: BackgroundTasks):
    """Fetch and analyze trends from external sources"""
    
    async def process_trends():
        try:
            # Fetch from YouTube RSS
            yt_trends = await fetch_youtube_rss()
            
            # Generate viral patterns
            viral_patterns = generate_viral_trends()
            
            all_trends = yt_trends + viral_patterns
            
            # Analyze and score each trend
            scored_trends = []
            for trend in all_trends:
                analysis = analyze_trend_2026(trend["title"])
                trend["analysis"] = analysis
                trend["viral_score"] = score_trend_2026(trend, analysis)
                scored_trends.append(trend)
            
            # Sort by score
            scored_trends.sort(key=lambda x: x["viral_score"], reverse=True)
            
            # Store in MongoDB (persistent)
            await db.trends.delete_many({})
            if scored_trends:
                await db.trends.insert_many([
                    {**t, "_id": t["id"], "fetched_at": datetime.now(timezone.utc).isoformat()}
                    for t in scored_trends[:50]
                ])
            
            print(f"[TrendEngine] Stored {len(scored_trends)} trends")
            
        except Exception as e:
            print(f"[TrendEngine] Error: {e}")
    
    background_tasks.add_task(process_trends)
    return {"status": "fetching", "message": "Trends being fetched in background"}

@app.get("/api/trends")
async def get_trends(limit: int = 30):
    """Get analyzed trends from cloud storage"""
    try:
        cursor = db.trends.find({}, {"_id": 0}).sort("viral_score", -1).limit(limit)
        trends = await cursor.to_list(length=limit)
        
        return {
            "trends": trends,
            "total": len(trends),
            "source": "cloud_db",
        }
    except Exception as e:
        return {"trends": [], "error": str(e)}

@app.get("/api/trends/stats")
async def get_trend_stats():
    """Get trend statistics"""
    try:
        cursor = db.trends.find({}, {"_id": 0})
        trends = await cursor.to_list(length=100)
        
        if not trends:
            return {"message": "No trends available. Click 'Fetch Trends' first."}
        
        # Analyze patterns
        hook_dist = {}
        scores = []
        
        for t in trends:
            hook = t.get("analysis", {}).get("hook_type", "neutral")
            hook_dist[hook] = hook_dist.get(hook, 0) + 1
            scores.append(t.get("viral_score", 0))
        
        avg_score = sum(scores) / len(scores) if scores else 0
        top_hook = max(hook_dist, key=hook_dist.get) if hook_dist else "neutral"
        
        return {
            "total_trends": len(trends),
            "avg_score": round(avg_score, 1),
            "top_hook": top_hook,
            "hook_distribution": hook_dist,
            "top_5": [
                {"title": t["title"], "score": t["viral_score"], "hook": t.get("analysis", {}).get("hook_type")}
                for t in trends[:5]
            ]
        }
    except Exception as e:
        return {"error": str(e)}

# ============ AI ENGINE (CLOUD) ============

async def ai_generate_with_retry(prompt: str, system: str, max_tokens: int = 2000, retries: int = 3) -> str:
    """Generate with Gemini AI + retry logic"""
    if not EMERGENT_LLM_KEY:
        raise Exception("AI key not configured")
    
    last_error = None
    for attempt in range(retries):
        try:
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"vf-{uuid.uuid4()}",
                system_message=system
            ).with_model("gemini", "gemini-2.0-flash")
            
            response = await chat.send_message(UserMessage(text=prompt))
            return response
            
        except Exception as e:
            last_error = e
            print(f"[AI] Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    raise last_error or Exception("AI generation failed")

def parse_json_safe(raw: str) -> Dict:
    """Safely parse JSON from AI response"""
    import re
    
    # Clean markdown
    clean = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    clean = re.sub(r"\s*```$", "", clean).strip()
    
    try:
        return json.loads(clean)
    except:
        # Try to extract JSON object
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", clean)
        if match:
            return json.loads(match.group(1))
        raise ValueError("No valid JSON found")

async def generate_10_ideas(niche: str, trends: List[Dict]) -> List[Dict]:
    """Generate 10 viral ideas using AI"""
    
    trend_context = "\n".join([
        f"- \"{t['title']}\" (Score: {t['viral_score']}, Hook: {t.get('analysis', {}).get('hook_type', 'unknown')})"
        for t in trends[:8]
    ])
    
    prompt = f"""Generate exactly 10 DIFFERENT viral short-form video ideas for: {niche}

CURRENT VIRAL PATTERNS (2026):
{trend_context}

REQUIREMENTS:
- Each idea must use a DIFFERENT hook type
- Hooks must stop the scroll in 1.5 seconds
- Optimize for TikTok/YouTube Shorts retention
- Include SEO keywords: {', '.join(TIKTOK_SEO_2026[:8])}

OUTPUT JSON array only:
[
  {{
    "id": 1,
    "title": "Viral title (8-14 words)",
    "hook": "Exact first 3 seconds script",
    "hook_type": "curiosity_gap|pattern_interrupt|fear_based|transformation|controversy|number_hook",
    "concept": "2-sentence concept",
    "emotion": "primary emotion"
  }}
]"""

    system = "You are the world's top viral content strategist. Output ONLY valid JSON array."
    
    raw = await ai_generate_with_retry(prompt, system, 2500)
    ideas = parse_json_safe(raw)
    
    return ideas[:10] if isinstance(ideas, list) else []

async def score_ideas_with_ai(ideas: List[Dict], niche: str) -> List[Dict]:
    """Score ideas using 2026 algorithm"""
    
    ideas_text = "\n".join([
        f"IDEA {i['id']}: \"{i['title']}\"\nHook: \"{i['hook']}\""
        for i in ideas
    ])
    
    prompt = f"""Score these {len(ideas)} video ideas for {niche}.

{ideas_text}

SCORING (0-100 each):
- hook_strength: Scroll-stopping power
- retention: Watch-through likelihood
- viral_potential: Share/save likelihood
- seo_demand: 2026 search relevance

Be harsh and differentiate. Output JSON array:
[{{"id": 1, "hook_strength": 85, "retention": 70, "viral_potential": 80, "seo_demand": 75}}]"""

    system = "Score with precision. Output ONLY JSON array."
    
    raw = await ai_generate_with_retry(prompt, system, 1200)
    scores = parse_json_safe(raw)
    
    # Calculate final scores
    scored = []
    for idea, score_data in zip(ideas, scores if isinstance(scores, list) else [{}] * len(ideas)):
        if not isinstance(score_data, dict):
            score_data = {}
        
        final_score = (
            score_data.get("hook_strength", 50) * 0.30 +
            score_data.get("retention", 50) * 0.30 +
            score_data.get("viral_potential", 50) * 0.20 +
            score_data.get("seo_demand", 50) * 0.20
        )
        
        scored.append({
            **idea,
            "scores": score_data,
            "final_score": round(final_score, 1)
        })
    
    scored.sort(key=lambda x: x["final_score"], reverse=True)
    return scored

async def generate_script(idea: Dict, niche: str) -> Dict:
    """Generate full production script"""
    
    prompt = f"""Create a viral TikTok/Shorts script for:

IDEA: {idea['title']}
HOOK: {idea['hook']}
CONCEPT: {idea.get('concept', '')}

STRUCTURE (30-40 seconds total):
1. HOOK (0-3s): Pattern interrupt - stop the scroll
2. TENSION (3-12s): Build curiosity
3. VALUE (12-28s): Deliver the promise
4. CTA (28-32s): Call to action + loop trigger

OUTPUT JSON:
{{
  "title": "Final title",
  "hook": "Opening hook",
  "duration": 32,
  "scenes": [
    {{
      "id": 1,
      "phase": "hook",
      "start": 0,
      "end": 3,
      "spoken": "What narrator says",
      "caption": "ON-SCREEN TEXT",
      "visual": "Visual description"
    }}
  ],
  "hashtags": ["#fyp", "#viral"],
  "description": "Video description for SEO"
}}"""

    system = "Write viral scripts. Output ONLY valid JSON."
    
    raw = await ai_generate_with_retry(prompt, system, 2000)
    return parse_json_safe(raw)

# ============ VOICE GENERATION (CLOUD) ============

async def generate_voice_cloud(text: str, task_id: str) -> Optional[str]:
    """Generate voice using OpenAI TTS (Cloud API)"""
    if not EMERGENT_LLM_KEY:
        return None
    
    try:
        tts = OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY)
        audio_bytes = await tts.generate_speech(
            text=text,
            model="tts-1",
            voice="nova",
            speed=1.05
        )
        
        # Store in MongoDB as base64 (cloud persistent)
        audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
        
        await db.audio.update_one(
            {"task_id": task_id},
            {"$set": {"audio_b64": audio_b64, "created_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True
        )
        
        return task_id
        
    except Exception as e:
        print(f"[TTS] Error: {e}")
        return None

# ============ VIDEO METADATA (CLOUD STORAGE) ============

async def create_video_package(task_id: str, script: Dict, idea: Dict) -> Dict:
    """Create video metadata package (stored in cloud)"""
    
    # Since we're cloud-based, we store the "video instructions" 
    # that can be rendered by any video service
    
    video_package = {
        "task_id": task_id,
        "status": "ready",
        "title": script.get("title", idea.get("title", "")),
        "hook": script.get("hook", idea.get("hook", "")),
        "duration": script.get("duration", 30),
        "scenes": script.get("scenes", []),
        "hashtags": script.get("hashtags", []),
        "description": script.get("description", ""),
        "seo_metadata": {
            "title": script.get("title", ""),
            "tags": script.get("hashtags", []),
            "description": script.get("description", ""),
        },
        "render_instructions": {
            "resolution": "1080x1920",
            "fps": 30,
            "format": "mp4",
            "style": "tiktok_caption",
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    # Store in MongoDB
    await db.videos.update_one(
        {"task_id": task_id},
        {"$set": video_package},
        upsert=True
    )
    
    return video_package

# ============ TASK QUEUE SYSTEM ============

def update_task(task_id: str, status: str, progress: int, step: str, result: Dict = None):
    """Update task status"""
    task_queue[task_id] = {
        "task_id": task_id,
        "status": status,
        "progress": progress,
        "step": step,
        "result": result,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

async def save_task_to_cloud(task_id: str, data: Dict):
    """Persist task to MongoDB"""
    await db.tasks.update_one(
        {"task_id": task_id},
        {"$set": {**data, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )

# ============ MAIN GENERATION ENDPOINT ============

@app.post("/api/generate")
async def generate(req: GenerateRequest, background_tasks: BackgroundTasks):
    """
    Main generation endpoint - Returns immediately with task_id
    Heavy processing happens in background via cloud APIs
    """
    task_id = str(uuid.uuid4())[:12]
    niche = req.prompt or req.niche or "viral trending content"
    
    # Initialize task (immediate response < 1s)
    update_task(task_id, "processing", 0, "Initializing...")
    
    async def process_generation():
        """Background worker - all processing via cloud APIs"""
        try:
            # Step 1: Load trends from cloud DB
            update_task(task_id, "processing", 5, "Loading trend intelligence...")
            await save_task_to_cloud(task_id, {"step": "loading_trends"})
            
            cursor = db.trends.find({}, {"_id": 0}).sort("viral_score", -1).limit(15)
            trends = await cursor.to_list(length=15)
            
            if not trends:
                # Generate fallback trends
                trends = generate_viral_trends()
                for t in trends:
                    analysis = analyze_trend_2026(t["title"])
                    t["analysis"] = analysis
                    t["viral_score"] = score_trend_2026(t, analysis)
                trends.sort(key=lambda x: x["viral_score"], reverse=True)
            
            # Step 2: Generate 10 ideas via AI
            update_task(task_id, "processing", 15, "Generating 10 viral ideas...")
            await save_task_to_cloud(task_id, {"step": "generating_ideas"})
            
            ideas = await generate_10_ideas(niche, trends)
            
            # Step 3: Score ideas
            update_task(task_id, "processing", 35, "Scoring with 2026 algorithm...")
            await save_task_to_cloud(task_id, {"step": "scoring_ideas"})
            
            scored_ideas = await score_ideas_with_ai(ideas, niche)
            
            # Step 4: Auto-select winner
            update_task(task_id, "processing", 45, "Selecting best idea...")
            winner = scored_ideas[0] if scored_ideas else None
            
            if not winner:
                raise Exception("No ideas generated")
            
            # Step 5: Generate script
            update_task(task_id, "processing", 55, "Writing viral script...")
            await save_task_to_cloud(task_id, {"step": "writing_script"})
            
            script = await generate_script(winner, niche)
            
            # Step 6: Generate voice
            update_task(task_id, "processing", 70, "Generating AI voice...")
            await save_task_to_cloud(task_id, {"step": "generating_voice"})
            
            full_text = " ".join(s.get("spoken", "") for s in script.get("scenes", []))
            voice_id = await generate_voice_cloud(full_text, task_id)
            
            # Step 7: Create video package
            update_task(task_id, "processing", 85, "Creating video package...")
            await save_task_to_cloud(task_id, {"step": "creating_package"})
            
            video_package = await create_video_package(task_id, script, winner)
            
            # Step 8: Finalize
            update_task(task_id, "processing", 95, "Finalizing...")
            
            result = {
                "success": True,
                "task_id": task_id,
                "niche": niche,
                "all_ideas": scored_ideas,
                "winner": {
                    "title": winner.get("title", ""),
                    "hook": winner.get("hook", ""),
                    "concept": winner.get("concept", ""),
                    "hook_type": winner.get("hook_type", ""),
                    "final_score": winner.get("final_score", 0),
                    "scores": winner.get("scores", {}),
                },
                "script": script,
                "video": {
                    "task_id": task_id,
                    "status": "ready",
                    "has_voice": voice_id is not None,
                },
                "metadata": {
                    "title": script.get("title", ""),
                    "hashtags": script.get("hashtags", []),
                    "description": script.get("description", ""),
                    "duration": script.get("duration", 30),
                }
            }
            
            # Save complete result to cloud
            await db.generations.insert_one({
                "task_id": task_id,
                "prompt": niche,
                "winner": result["winner"],
                "script": script,
                "all_ideas": [{"title": i["title"], "score": i["final_score"]} for i in scored_ideas],
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            
            update_task(task_id, "complete", 100, "Complete!", result)
            await save_task_to_cloud(task_id, {"status": "complete", "result": result})
            
        except Exception as e:
            print(f"[Generation] Error: {e}")
            import traceback
            traceback.print_exc()
            update_task(task_id, "error", 0, f"Error: {str(e)[:100]}")
            await save_task_to_cloud(task_id, {"status": "error", "error": str(e)})
    
    # Run in background
    background_tasks.add_task(process_generation)
    
    # Return immediately with task_id
    return {"task_id": task_id, "status": "processing", "message": "Generation started"}

@app.get("/api/task/{task_id}")
async def get_task_status(task_id: str):
    """Poll endpoint for task status"""
    # Check in-memory first
    if task_id in task_queue:
        return task_queue[task_id]
    
    # Check cloud DB
    task = await db.tasks.find_one({"task_id": task_id}, {"_id": 0})
    if task:
        return task
    
    # Check generations
    gen = await db.generations.find_one({"task_id": task_id}, {"_id": 0})
    if gen:
        return {
            "task_id": task_id,
            "status": "complete",
            "progress": 100,
            "step": "Complete!",
            "result": {
                "success": True,
                "task_id": task_id,
                "winner": gen.get("winner"),
                "script": gen.get("script"),
                "metadata": {
                    "title": gen.get("script", {}).get("title", ""),
                    "hashtags": gen.get("script", {}).get("hashtags", []),
                }
            }
        }
    
    raise HTTPException(status_code=404, detail="Task not found")

# ============ VIDEO VAULT (CLOUD STORAGE) ============

@app.get("/api/vault")
async def get_video_vault():
    """Get all generated videos from cloud storage"""
    try:
        cursor = db.generations.find({}, {"_id": 0}).sort("created_at", -1).limit(20)
        videos = await cursor.to_list(length=20)
        
        return {
            "videos": [
                {
                    "task_id": v.get("task_id"),
                    "title": v.get("winner", {}).get("title", "Untitled"),
                    "hook": v.get("winner", {}).get("hook", ""),
                    "score": v.get("winner", {}).get("final_score", 0),
                    "duration": v.get("script", {}).get("duration", 30),
                    "hashtags": v.get("script", {}).get("hashtags", []),
                    "created_at": v.get("created_at"),
                }
                for v in videos
            ],
            "total": len(videos),
        }
    except Exception as e:
        return {"videos": [], "error": str(e)}

@app.get("/api/video/{task_id}")
async def get_video_details(task_id: str):
    """Get video details and script"""
    video = await db.videos.find_one({"task_id": task_id}, {"_id": 0})
    gen = await db.generations.find_one({"task_id": task_id}, {"_id": 0})
    
    if not video and not gen:
        raise HTTPException(status_code=404, detail="Video not found")
    
    return {
        "task_id": task_id,
        "video": video,
        "generation": gen,
    }

@app.get("/api/audio/{task_id}")
async def get_audio(task_id: str):
    """Get generated audio"""
    audio = await db.audio.find_one({"task_id": task_id}, {"_id": 0})
    if not audio:
        raise HTTPException(status_code=404, detail="Audio not found")
    
    # Return base64 audio
    return {"task_id": task_id, "audio_b64": audio.get("audio_b64")}

# ============ STARTUP ============

@app.on_event("startup")
async def startup():
    # Create indexes for performance
    try:
        await db.trends.create_index("viral_score")
        await db.generations.create_index("created_at")
        await db.tasks.create_index("task_id")
    except:
        pass
    
    print("=" * 60)
    print("  ViralForge v3 — The Independent Factory")
    print("  Architecture: Decentralized Cloud Processing")
    print("  Status: Operational")
    print("=" * 60)
