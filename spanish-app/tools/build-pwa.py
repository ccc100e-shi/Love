"""كيبني نسخة التطبيق اللي كتتانستالا فالتيليفون (PWA) فـ docs/ باش تتنشر على GitHub Pages.

الاستعمال (من الدوسي ديال الـ repo):
    python3 spanish-app/tools/build-pwa.py

كيكتب:
    docs/index.html            الصفحة كاملة (head + manifest + service worker)
    docs/manifest.webmanifest  المعلومات ديال التطبيق (السمية، الأيقونة، الألوان)
    docs/sw.js                 باش يخدم بلا أنترنت
    docs/icons/*.png           الأيقونات
    docs/audio/                الصوت المسجل
"""
import hashlib
import json
import os
import shutil

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
APP = os.path.join(ROOT, "spanish-app")
OUT = os.path.join(ROOT, "docs")
BLUE, SUN, WHITE = "#1F4FA8", "#E8A817", "#FFFFFF"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def icon(size, maskable=False, path=None):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if maskable:
        d.rectangle([0, 0, size, size], fill=BLUE)
    else:
        d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=BLUE)
    # «ñ» فالوسط، ونقطة صفرا بحال الشعار
    scale = 0.52 if maskable else 0.62
    f = ImageFont.truetype(FONT, int(size * scale))
    box = d.textbbox((0, 0), "ñ", font=f)
    w, h = box[2] - box[0], box[3] - box[1]
    x, y = (size - w) / 2 - box[0] - size * 0.04, (size - h) / 2 - box[1]
    d.text((x, y), "ñ", font=f, fill=WHITE)
    r = size * (0.055 if maskable else 0.065)
    cx, cy = x + box[2] + r * 1.4, y + box[3] - r
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=SUN)
    img.save(path)


def main():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, "icons"))
    for s in (192, 512):
        icon(s, path=os.path.join(OUT, "icons", f"icon-{s}.png"))
        icon(s, maskable=True, path=os.path.join(OUT, "icons", f"maskable-{s}.png"))
    icon(180, maskable=True, path=os.path.join(OUT, "icons", "apple-touch-icon.png"))
    shutil.copytree(os.path.join(APP, "audio"), os.path.join(OUT, "audio"))

    body = open(os.path.join(APP, "index.html"), encoding="utf-8").read()
    # الـ title والخطوط كيمشيو للـ head
    head_bits = []
    for line in body.split("\n"):
        if line.startswith(("<title>", "<meta name=\"description\"", "<link rel=\"preconnect\"", "<link rel=\"stylesheet\"")):
            head_bits.append(line)
    rest = "\n".join(l for l in body.split("\n") if l not in head_bits)
    version = hashlib.sha1(body.encode()).hexdigest()[:10]

    html = f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
{chr(10).join(head_bits)}
<meta name="theme-color" content="{BLUE}">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icons/icon-192.png">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Aula">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<style>:root {{ padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px); }} body {{ margin: 0; }} [hidden] {{ display: none !important; }} img {{ max-width: 100%; }}</style>
</head>
<body>
{rest}
<script>
if ("serviceWorker" in navigator) {{
  window.addEventListener("load", () => {{ navigator.serviceWorker.register("sw.js").catch(() => {{}}); }});
}}
</script>
</body>
</html>
"""
    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(html)

    manifest = {
        "name": "Aula de Español",
        "short_name": "Aula",
        "description": "تمارين الإسبانية من A1 حتى C1، بالشرح بالدارجة",
        "lang": "ar", "dir": "rtl",
        "start_url": "./", "scope": "./", "display": "standalone", "orientation": "portrait",
        "background_color": "#EEF2F8", "theme_color": BLUE,
        "icons": [
            {"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "icons/maskable-192.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
            {"src": "icons/maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    json.dump(manifest, open(os.path.join(OUT, "manifest.webmanifest"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    shell = ["./", "index.html", "manifest.webmanifest", "audio/manifest.json",
             "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png"]
    sw = f"""// كيخلي التطبيق يخدم بلا أنترنت. النسخة كتبدل مع كل بناء باش التحديثات يوصلو.
const CACHE = "aula-{version}";
const SHELL = {json.dumps(shell)};
self.addEventListener("install", e => {{
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
}});
self.addEventListener("activate", e => {{
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith("aula-") && k !== CACHE && k !== "aula-audio").map(k => caches.delete(k)))).then(() => self.clients.claim()));
}});
self.addEventListener("fetch", e => {{
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  // الصوت: من الكاش إلا كان، وإلا كنجيبوه ونخبيوه
  if (url.pathname.endsWith(".mp3")) {{
    e.respondWith(caches.open("aula-audio").then(async c => {{
      const hit = await c.match(e.request);
      if (hit) return hit;
      const res = await fetch(e.request);
      if (res.ok) c.put(e.request, res.clone());
      return res;
    }}));
    return;
  }}
  // الباقي: الأنترنت الأول (باش التحديثات يبانو)، والكاش إلا ماكانش الأنترنت
  e.respondWith(fetch(e.request).then(res => {{
    if (res.ok) {{ const copy = res.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); }}
    return res;
  }}).catch(() => caches.match(e.request).then(r => r || caches.match("index.html"))));
}});
"""
    open(os.path.join(OUT, "sw.js"), "w", encoding="utf-8").write(sw)
    open(os.path.join(OUT, ".nojekyll"), "w").close()
    print("built", OUT, "version", version)


if __name__ == "__main__":
    main()
