// كيخلي التطبيق يخدم بلا أنترنت. النسخة كتبدل مع كل بناء باش التحديثات يوصلو.
const CACHE = "aula-63e1906662";
const SHELL = ["./", "index.html", "manifest.webmanifest", "audio/manifest.json", "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png"];
self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith("aula-") && k !== CACHE && k !== "aula-audio").map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  // الصوت: من الكاش إلا كان، وإلا كنجيبوه ونخبيوه
  if (url.pathname.endsWith(".mp3")) {
    e.respondWith(caches.open("aula-audio").then(async c => {
      const hit = await c.match(e.request);
      if (hit) return hit;
      const res = await fetch(e.request);
      if (res.ok) c.put(e.request, res.clone());
      return res;
    }));
    return;
  }
  // الباقي: الأنترنت الأول (باش التحديثات يبانو)، والكاش إلا ماكانش الأنترنت
  e.respondWith(fetch(e.request).then(res => {
    if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); }
    return res;
  }).catch(() => caches.match(e.request).then(r => r || caches.match("index.html"))));
});
