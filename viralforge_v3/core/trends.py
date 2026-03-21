"""ViralForge v3 — Trend Fetcher (YouTube RSS + Reddit JSON, retry + 10min cache)"""
import json, re, xml.etree.ElementTree as ET, math, time, os, sys
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.db import get_db, cache_get, cache_set, get_weights, init

YT_FEEDS = {
    "trending":      "https://www.youtube.com/feeds/videos.xml?chart=trending&gl=US&hl=en",
    "music":         "https://www.youtube.com/feeds/videos.xml?chart=trending&gl=US&hl=en&videoCategoryId=10",
    "gaming":        "https://www.youtube.com/feeds/videos.xml?chart=trending&gl=US&hl=en&videoCategoryId=20",
    "entertainment": "https://www.youtube.com/feeds/videos.xml?chart=trending&gl=US&hl=en&videoCategoryId=24",
    "science":       "https://www.youtube.com/feeds/videos.xml?chart=trending&gl=US&hl=en&videoCategoryId=28",
    "howto":         "https://www.youtube.com/feeds/videos.xml?chart=trending&gl=US&hl=en&videoCategoryId=26",
}

REDDIT_SUBS = ["videos", "interestingasfuck", "todayilearned", "nextfuckinglevel", "mildlyinteresting"]

HEADERS = {"User-Agent": "ViralForge/3.0 (content-research-tool; non-commercial)"}

def _fetch_url(url: str, retries: int = 3, timeout: int = 12) -> bytes:
    for attempt in range(retries):
        try:
            req = Request(url, headers=HEADERS)
            return urlopen(req, timeout=timeout).read()
        except (URLError, HTTPError) as e:
            if attempt == retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    return b""

# ── Pattern Analysis ──────────────────────────────────────────────────────────

HOOK_RULES = [
    ("number_hook",       lambda t: bool(re.match(r"^\d+", t))),
    ("question_hook",     lambda t: t.strip().endswith("?")),
    ("curiosity_gap",     lambda t: any(w in t for w in
        ["secret", "truth", "revealed", "nobody", "hidden", "real reason", "they don't", "what they", "won't tell"])),
    ("pattern_interrupt", lambda t: any(t.startswith(w) for w in
        ["pov", "stop", "wait", "story time", "hot take", "this is", "you need", "watch this", "i can't"])),
    ("transformation",    lambda t: any(w in t for w in
        ["before", "after", "glow up", "changed", "transform", "journey", " days", "weeks", "months"])),
    ("list_format",       lambda t: any(w in t for w in
        ["things", "ways", "reasons", "tips", "mistakes", "signs", "facts", "rules", "habits", "hacks"])),
    ("fear_hook",         lambda t: any(w in t for w in
        ["warning", "danger", "never", "mistake", "wrong", "risk", "worst", "avoid", "stop doing"])),
]

TRIGGERS = {
    "curiosity":    ["secret", "truth", "revealed", "hidden", "why", "how", "what if", "unknown"],
    "fear":         ["danger", "warning", "never", "mistake", "wrong", "risk", "stop", "losing"],
    "aspiration":   ["rich", "success", "dream", "goals", "motivation", "transform", "level up", "achieve"],
    "humor":        ["funny", "lol", "wait for it", "unexpected", "fail", "prank", "plot twist"],
    "relatability": ["pov", "when you", "that moment", "we all", "literally", "everyone does"],
    "controversy":  ["hot take", "unpopular", "controversial", "nobody talks", "fight me"],
    "nostalgia":    ["remember", "childhood", "throwback", "90s", "classic", "back when"],
}

def _analyze(title: str) -> dict:
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
        "has_emoji": bool(re.search(r"[^\x00-\x7F]", title)),
        "word_count": len(title.split()),
        "char_count": len(title),
    }

def _score(video: dict, analysis: dict, weights: dict) -> float:
    """Weighted virality score using learned pattern weights."""
    s = 0.0

    # View momentum (max 25 pts, log scale)
    views = max(video.get("views", 1), 1)
    s += min(25, math.log10(views) * 3.5)

    # Hook score (max 30 pts × learned weight)
    hook_base = {
        "curiosity_gap": 28, "pattern_interrupt": 26, "fear_hook": 24,
        "number_hook": 22, "transformation": 20, "question_hook": 18,
        "list_format": 16, "neutral": 4,
    }.get(analysis["hook_type"], 4)
    hook_w = weights.get(f"hook:{analysis['hook_type']}", 1.0)
    s += min(30, hook_base * hook_w)

    # Trigger score (max 22 pts × learned weights)
    for tr in analysis["triggers"]:
        tr_w = weights.get(f"trigger:{tr}", 1.0)
        s += min(4, 3.5 * tr_w)

    # Title optimization signals
    if analysis["has_number"]:   s += 4
    if analysis["has_question"]: s += 3
    if analysis["has_emoji"]:    s += 2
    if 5 <= analysis["word_count"] <= 13: s += 4
    if analysis["char_count"] <= 80:     s += 2

    return round(min(100, s), 1)

# ── YouTube RSS ───────────────────────────────────────────────────────────────

def _parse_yt(data: bytes, label: str) -> list[dict]:
    out = []
    try:
        root = ET.fromstring(data)
        ns = {
            "a":  "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015",
        }
        for entry in root.findall("a:entry", ns):
            vid_id = getattr(entry.find("yt:videoId", ns), "text", "") or ""
            title  = getattr(entry.find("a:title", ns), "text", "") or ""
            link   = (entry.find("a:link", ns) or entry).get("href", "")
            stats  = entry.find(".//yt:statistics", ns)
            views  = int(stats.get("viewCount", 0)) if stats is not None else 0
            if title and vid_id:
                out.append({
                    "id": vid_id, "title": title, "url": link,
                    "views": views, "source": label,
                    "thumbnail": f"https://img.youtube.com/vi/{vid_id}/mqdefault.jpg",
                })
    except ET.ParseError as e:
        print(f"[YT parse:{label}] {e}")
    return out

def fetch_youtube(categories: list | None = None, use_cache: bool = True) -> list[dict]:
    cats = categories or ["trending", "entertainment", "gaming", "howto"]
    cache_key = f"yt:{'_'.join(sorted(cats))}"

    if use_cache:
        cached = cache_get(cache_key)
        if cached:
            print(f"[YT] Cache hit ({len(cached)} items)")
            return cached

    results = []
    for cat in cats:
        url = YT_FEEDS.get(cat)
        if not url:
            continue
        try:
            data = _fetch_url(url)
            items = _parse_yt(data, f"yt:{cat}")
            results.extend(items)
            print(f"[YT:{cat}] {len(items)} items")
        except Exception as e:
            print(f"[YT:{cat}] FAILED: {e}")

    cache_set(cache_key, results, ttl_seconds=600)
    return results

# ── Reddit JSON ───────────────────────────────────────────────────────────────

def fetch_reddit(subs: list | None = None, use_cache: bool = True) -> list[dict]:
    targets = subs or REDDIT_SUBS
    cache_key = f"reddit:{'_'.join(sorted(targets))}"

    if use_cache:
        cached = cache_get(cache_key)
        if cached:
            print(f"[Reddit] Cache hit ({len(cached)} items)")
            return cached

    results = []
    for sub in targets:
        try:
            data = _fetch_url(f"https://www.reddit.com/r/{sub}/hot.json?limit=25&raw_json=1")
            parsed = json.loads(data)
            for post in parsed.get("data", {}).get("children", []):
                p = post["data"]
                if p.get("score", 0) < 200 or p.get("stickied"):
                    continue
                thumb = p.get("thumbnail", "")
                results.append({
                    "id": f"rd_{p['id']}", "title": p.get("title", ""),
                    "views": p.get("score", 0) * 40,
                    "source": f"reddit:{sub}",
                    "url": p.get("url", ""),
                    "thumbnail": thumb if str(thumb).startswith("http") else "",
                })
            print(f"[Reddit:{sub}] {len([p for p in parsed.get('data',{}).get('children',[]) if p['data'].get('score',0)>=200])} items")
        except Exception as e:
            print(f"[Reddit:{sub}] FAILED: {e}")

    cache_set(cache_key, results, ttl_seconds=600)
    return results

# ── Aggregate + Score ─────────────────────────────────────────────────────────

def fetch_all(yt_cats: list | None = None, reddit_subs: list | None = None,
              force: bool = False) -> list[dict]:
    """Fetch from all sources, deduplicate, score with learned weights."""
    from core.notify import send_notification, send_error
    weights = get_weights()

    try:
        raw = fetch_youtube(yt_cats, use_cache=not force) + fetch_reddit(reddit_subs, use_cache=not force)
    except Exception as e:
        send_error("Trend fetch failed", context="fetch_all", exc=e)
        raise

    seen, unique = set(), []
    for v in raw:
        vid_id = v.get("id", "")
        if not vid_id or vid_id in seen:
            continue
        seen.add(vid_id)
        a = _analyze(v["title"])
        v["analysis"] = a
        v["virality_score"] = _score(v, a, weights)
        unique.append(v)

    unique.sort(key=lambda x: x["virality_score"], reverse=True)
    _persist(unique)

    # Notify
    yt_count = len([v for v in unique if v.get("source","").startswith("yt:")])
    rd_count = len([v for v in unique if v.get("source","").startswith("reddit:")])
    top = unique[0] if unique else {}
    send_notification(
        message    = f"Fetched {len(unique)} trends ({yt_count} YouTube, {rd_count} Reddit)",
        event_type = "trend",
        title      = "Trends Fetched",
        metadata   = {
            "total":     len(unique),
            "youtube":   yt_count,
            "reddit":    rd_count,
            "top_score": top.get("virality_score", 0),
            "top_title": top.get("title","")[:60],
        },
    )
    return unique

def _persist(trends: list[dict]):
    init()
    conn = get_db()
    now = datetime.now().isoformat()
    for t in trends:
        a = t.get("analysis", {})
        try:
            conn.execute(
                "INSERT OR REPLACE INTO trends VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (t["id"], t["title"], t.get("views", 0), t.get("source", ""),
                 a.get("hook_type", ""), json.dumps(a.get("triggers", [])),
                 t.get("virality_score", 0), now,
                 t.get("url", ""), t.get("thumbnail", ""), "")
            )
        except Exception as e:
            print(f"[persist] {e}")
    conn.commit()
    conn.close()

def get_cached_trends(limit: int = 80) -> list[dict]:
    try:
        init()
        conn = get_db()
        rows = conn.execute(
            "SELECT id,title,views,source,hook_type,triggers,virality_score,url,thumbnail,niche "
            "FROM trends ORDER BY virality_score DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) | {"analysis": {"hook_type": r["hook_type"], "triggers": json.loads(r["triggers"] or "[]")}}
                for r in rows]
    except Exception as e:
        print(f"[get_cached] {e}")
        return []

def pattern_report(trends: list[dict]) -> dict:
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
