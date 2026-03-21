"""
ViralForge v3 — Decision Engine
Generates 10 options, scores each on 6 dimensions, selects the best, explains why.
This is the core intelligence that makes v3 different from v2.
"""
import json, os, re, sys, uuid, sqlite3
from datetime import datetime
from urllib.request import urlopen, Request

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.db import get_db, get_weights, init

API_URL = "https://api.anthropic.com/v1/messages"
MODEL   = "claude-sonnet-4-20250514"

# ── Claude API ────────────────────────────────────────────────────────────────

def _claude(prompt: str, system: str = "", max_tokens: int = 2000) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = Request(API_URL, data=payload, method="POST", headers={
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    })
    resp = json.loads(urlopen(req, timeout=40).read())
    return resp["content"][0]["text"]

def _parse(raw: str) -> dict | list:
    clean = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    clean = re.sub(r"\s*```$", "", clean).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", clean)
        if m:
            return json.loads(m.group(1))
        raise ValueError(f"No JSON found in:\n{raw[:300]}")

# ── Dimension Definitions ─────────────────────────────────────────────────────

SCORING_DIMENSIONS = {
    "hook_strength":     {"weight": 0.30, "desc": "Does the opening grab attention in 2 seconds?"},
    "curiosity_gap":     {"weight": 0.20, "desc": "Does it create an unanswered question that demands resolution?"},
    "emotional_trigger": {"weight": 0.20, "desc": "Does it activate a strong emotion (fear, aspiration, humor)?"},
    "trend_alignment":   {"weight": 0.15, "desc": "Does it match current trending patterns and topics?"},
    "retention_arc":     {"weight": 0.10, "desc": "Will viewers watch to the end? Is there a payoff?"},
    "clarity":           {"weight": 0.05, "desc": "Is the premise immediately understood?"},
}

# ── Step 1: Generate 10 Options ───────────────────────────────────────────────

SYS_OPTIONS = """You are the world's best viral short-form content strategist.
You generate video concepts that consistently exceed 1M views.
Output ONLY valid JSON arrays. No commentary, no markdown, no preamble."""

def generate_options(niche: str, trend_context: dict, n: int = 10) -> list[dict]:
    """Generate N video options with title, hook, concept, and structure."""

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
- Each title must be immediately compelling (no generic outputs)
- Hook = exact first 1-2 sentences the creator says on camera
- Vary the structure across options: list, story, transformation, tutorial, hot take
- Think platform-native: TikTok, YouTube Shorts, Reels

OUTPUT exactly {n} items in this JSON array format:
[
  {{
    "title": "SEO-optimized video title with power words",
    "hook": "Exact opening words — must stop scroll in 2 seconds",
    "concept": "2-sentence summary of the video content",
    "structure": "list|story|transformation|tutorial|hot_take|problem_solve|reaction",
    "hook_type": "curiosity_gap|number_hook|question_hook|pattern_interrupt|fear_hook|transformation|list_format",
    "primary_trigger": "curiosity|fear|aspiration|humor|relatability|controversy",
    "target_platform": "tiktok|youtube_shorts|both",
    "estimated_duration": 30
  }}
]"""

    raw = _claude(prompt, SYS_OPTIONS, max_tokens=2400)
    options = _parse(raw)
    if not isinstance(options, list):
        raise ValueError("Expected list of options")
    return options[:n]

# ── Step 2: Score Each Option ─────────────────────────────────────────────────

SYS_SCORER = """You are a data-driven viral content analyst.
You score video concepts with surgical precision.
NEVER give every option the same score — differentiate ruthlessly.
Output ONLY valid JSON. No commentary."""

def score_options(options: list[dict], niche: str, weights: dict) -> list[dict]:
    """Score each option on 6 dimensions, compute weighted total, apply learned weights."""

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
- curiosity_gap: Creates unanswered question that demands resolution?
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

    raw = _claude(prompt, SYS_SCORER, max_tokens=1200)
    scores = _parse(raw)
    if not isinstance(scores, list):
        raise ValueError("Expected list of scores")

    # Compute weighted total + apply learned weights
    scored = []
    for i, (option, raw_score) in enumerate(zip(options, scores)):
        dims = {
            "hook_strength":     raw_score.get("hook_strength", 5),
            "curiosity_gap":     raw_score.get("curiosity_gap", 5),
            "emotional_trigger": raw_score.get("emotional_trigger", 5),
            "trend_alignment":   raw_score.get("trend_alignment", 5),
            "retention_arc":     raw_score.get("retention_arc", 5),
            "clarity":           raw_score.get("clarity", 5),
        }

        # Weighted base score (0-100)
        base = sum(dims[d] * SCORING_DIMENSIONS[d]["weight"] * 10 for d in dims)

        # Apply learned pattern weights
        hook_boost = weights.get(f"hook:{option.get('hook_type','neutral')}", 1.0)
        trigger_boost = weights.get(f"trigger:{option.get('primary_trigger','curiosity')}", 1.0)
        learned_multiplier = (hook_boost * 0.6 + trigger_boost * 0.4)  # blend
        final = round(min(100, base * learned_multiplier), 1)

        scored.append({
            **option,
            "idx": i,
            "scores": dims,
            "base_score": round(base, 1),
            "learned_multiplier": round(learned_multiplier, 3),
            "virality_score": final,
        })

    return sorted(scored, key=lambda x: x["virality_score"], reverse=True)

# ── Step 3: Select Best + Explain ─────────────────────────────────────────────

SYS_SELECTOR = """You are a viral content expert making a final recommendation.
Be direct and specific about WHY the winner wins.
Output ONLY valid JSON."""

def select_best(scored_options: list[dict], niche: str) -> dict:
    """Select the winner and provide detailed reasoning."""

    top3 = scored_options[:3]
    comparison = "\n".join(
        f'OPTION {o["idx"]+1} (Score: {o["virality_score"]}): "{o["title"]}"\n'
        f'  Hook: "{o["hook"]}"\n'
        f'  Scores: Hook={o["scores"]["hook_strength"]}, Curiosity={o["scores"]["curiosity_gap"]}, '
        f'Emotion={o["scores"]["emotional_trigger"]}, Trend={o["scores"]["trend_alignment"]}'
        for o in top3
    )

    prompt = f"""Select the single BEST viral video option and explain precisely why it wins.

NICHE: {niche}
TOP 3 OPTIONS BY SCORE:
{comparison}

Consider:
1. Which hook is most psychologically compelling?
2. Which creates the strongest need to watch to the end?
3. Which is most differentiated from typical content in this niche?
4. Which has the best platform fit for TikTok/Shorts?

OUTPUT JSON:
{{
  "winner_idx": 0,
  "winner_title": "...",
  "winner_hook": "...",
  "why_wins": "2-3 specific sentences explaining the psychological mechanism that makes this the best choice",
  "predicted_views_range": "100K-500K",
  "strongest_element": "The single most powerful element",
  "critical_execution_tip": "The one thing that will make or break this video",
  "alternatives": [
    {{"idx": 1, "why_viable": "brief note on why option 2 could work", "best_for": "audience segment"}}
  ]
}}"""

    raw = _claude(prompt, SYS_SELECTOR, max_tokens=800)
    return _parse(raw)

# ── Step 4: Generate Full Script ──────────────────────────────────────────────

SYS_SCRIPT = """You are an elite short-form video scriptwriter.
Every word must earn its place. Every scene transition = a reason to keep watching.
Output ONLY valid JSON. Zero preamble."""

def generate_script(winner: dict, decision: dict, niche: str) -> dict:
    """Generate a production-ready script for the selected winner."""

    prompt = f"""Write a complete, production-ready script for this viral video.

SELECTED CONCEPT:
- Title: "{winner['title']}"
- Hook: "{winner['hook']}"
- Structure: {winner.get('structure','story')}
- Primary trigger: {winner.get('primary_trigger','curiosity')}
- Niche: {niche}

EXECUTION TIP: {decision.get('critical_execution_tip', '')}

SCRIPT STRUCTURE:
- Hook (0-3s): The exact opening that stops the scroll
- Build (3-15s): Establish stakes, add context, deepen curiosity
- Payoff (15-45s): Deliver the value, surprising insight, or resolution
- Loop (last 2s): An ending that makes viewers rewatch from the start

REQUIREMENTS:
- Each scene: spoken text + visual instruction + on-screen caption text
- Fast pacing: short sentences, clear cuts
- Captions are DIFFERENT from spoken text (shorter, punchier)
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
      "caption_text": "ON-SCREEN TEXT (shorter, punchier)",
      "visual_direction": "what the viewer sees — camera angle, action, graphic",
      "pacing": "fast",
      "transition": "cut|zoom_in|zoom_out|fade"
    }}
  ],
  "captions_style": {{
    "font": "bold",
    "color": "yellow",
    "position": "center",
    "size": "large",
    "shadow": true
  }},
  "music_direction": "describe ideal background track energy",
  "hashtags": ["#tag1","#tag2","#tag3","#tag4","#tag5","#tag6"],
  "description": "YouTube/TikTok description (2-3 sentences)",
  "thumbnail_concept": "describe ideal thumbnail image"
}}"""

    raw = _claude(prompt, SYS_SCRIPT, max_tokens=2000)
    return _parse(raw)

# ── Full Pipeline ─────────────────────────────────────────────────────────────

def run_decision_engine(niche: str, trend_context: dict) -> dict:
    """
    Full pipeline: generate → score → select → script.
    Returns complete decision package.
    """
    weights = get_weights()

    # Step 1: Generate 10 options
    print(f"[Engine] Generating 10 options for niche={niche}...")
    options = generate_options(niche, trend_context, n=10)

    # Step 2: Score each
    print(f"[Engine] Scoring {len(options)} options...")
    scored = score_options(options, niche, weights)

    # Step 3: Select best
    print(f"[Engine] Selecting winner...")
    decision = select_best(scored, niche)
    winner_idx = decision.get("winner_idx", 0)
    winner = scored[0] if winner_idx >= len(scored) else scored[winner_idx]

    # Step 4: Generate script
    print(f"[Engine] Building script for: {winner.get('title', '')}")
    script = generate_script(winner, decision, niche)

    # Persist batch
    batch_id = str(uuid.uuid4())[:12]
    init()
    conn = get_db()
    conn.execute(
        "INSERT INTO idea_batches VALUES (?,?,?,?,?,?)",
        (batch_id, niche, json.dumps(trend_context),
         json.dumps(scored), winner_idx, datetime.now().isoformat())
    )
    script_id = str(uuid.uuid4())[:12]
    conn.execute(
        "INSERT INTO scripts VALUES (?,?,?,?,?,?,?,?,?,?)",
        (script_id, batch_id, winner_idx,
         script.get("title", ""), script.get("hook", ""),
         json.dumps(script), json.dumps(decision),
         decision.get("predicted_views_range", ""),
         datetime.now().isoformat(), niche)
    )
    conn.commit()
    conn.close()

    # Notify: ideas generated
    from core.notify import send_notification, send_report, send_error
    send_notification(
        message    = f"Generated {len(scored)} ideas for niche '{niche}', winner scored {winner.get('virality_score',0)}",
        event_type = "idea",
        title      = "Ideas Generated",
        metadata   = {
            "niche":          niche,
            "options":        len(scored),
            "winner_title":   winner.get("title","")[:60],
            "winner_score":   winner.get("virality_score", 0),
            "winner_hook":    winner.get("hook","")[:80],
        },
    )
    send_notification(
        message    = f"Script ready — {script.get('title','')[:60]}",
        event_type = "script",
        title      = "Script Generated",
        metadata   = {
            "title":    script.get("title","")[:60],
            "hook":     script.get("hook","")[:80],
            "scenes":   len(script.get("scenes") or script.get("script") or []),
            "duration": script.get("total_duration", 0),
        },
    )

    return {
        "batch_id":    batch_id,
        "script_id":   script_id,
        "niche":       niche,
        "options":     scored,
        "winner":      winner,
        "decision":    decision,
        "script":      script,
        "total_options": len(scored),
    }

# ── Script CRUD ───────────────────────────────────────────────────────────────

def get_scripts(limit: int = 20) -> list[dict]:
    try:
        init()
        conn = get_db()
        rows = conn.execute(
            "SELECT id,batch_id,title,hook,virality_score,created_at,niche,script_json,decision_json "
            "FROM scripts ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        result = []
        for r in rows:
            try: s = json.loads(r["script_json"] or "{}")
            except: s = {}
            try: d = json.loads(r["decision_json"] or "{}")
            except: d = {}
            result.append({
                "id": r["id"], "batch_id": r["batch_id"],
                "title": r["title"], "hook": r["hook"],
                "virality_score": r["virality_score"],
                "created_at": r["created_at"], "niche": r["niche"],
                "script": s, "decision": d,
            })
        return result
    except Exception as e:
        print(f"[get_scripts] {e}")
        return []

def get_batch(batch_id: str) -> dict | None:
    try:
        init()
        conn = get_db()
        row = conn.execute("SELECT * FROM idea_batches WHERE id=?", (batch_id,)).fetchone()
        conn.close()
        if not row: return None
        return {
            "id": row["id"], "niche": row["niche"],
            "ideas": json.loads(row["ideas_json"] or "[]"),
            "selected_idx": row["selected_idx"],
            "created_at": row["created_at"],
        }
    except: return None

def record_performance(script_id: str, video_id: str, platform: str,
                        views: int, likes: int, shares: int):
    """Record real performance data and trigger weight learning."""
    init()
    conn = get_db()
    conn.execute(
        "INSERT INTO performance (script_id,video_id,platform,views,likes,shares,recorded_at) VALUES (?,?,?,?,?,?,?)",
        (script_id, video_id, platform, views, likes, shares, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

    # Compute normalized performance score (0-100)
    # Views: 1M = 100, 100K = 70, 10K = 40, 1K = 20
    import math
    perf_score = min(100, math.log10(max(views, 1)) * 20)

    # Update weights for the patterns used in this script
    try:
        conn2 = get_db()
        row = conn2.execute("SELECT script_json FROM scripts WHERE id=?", (script_id,)).fetchone()
        conn2.close()
        if row:
            script = json.loads(row["script_json"] or "{}")
            # Find the winner's hook and trigger from the batch
            batch_row_conn = get_db()
            batch = batch_row_conn.execute(
                "SELECT ideas_json, selected_idx FROM idea_batches WHERE id=(SELECT batch_id FROM scripts WHERE id=?)",
                (script_id,)
            ).fetchone()
            batch_row_conn.close()
            if batch:
                ideas = json.loads(batch["ideas_json"] or "[]")
                idx = batch["selected_idx"]
                if 0 <= idx < len(ideas):
                    winner = ideas[idx]
                    from core.db import update_weight
                    update_weight(f"hook:{winner.get('hook_type','neutral')}", perf_score)
                    update_weight(f"trigger:{winner.get('primary_trigger','curiosity')}", perf_score)
    except Exception as e:
        print(f"[record_performance] weight update failed: {e}")
