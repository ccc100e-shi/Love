// كيطلع جميع الجمل والكلمات الإسبانية اللي خاصهم صوت مسجل، مجموعين حسب الملف.
// الاستعمال: node tools/list-audio.js > audio-list.json
const fs = require("fs");
const html = fs.readFileSync(__dirname + "/../index.html", "utf8");
const data = html.split("<script>")[1].split("/* ============ التخزين")[0];
const { LESSONS, ASK, TEXTS } = new Function(data + "; return { LESSONS, ASK, TEXTS };")();
const groups = [];
for (const l of LESSONS) {
  const n = [];
  (l.vocab || []).forEach(v => n.push(v[0]));
  (l.build || []).forEach(b => n.push(b[0]));
  (l.fill || []).forEach(f => n.push(f[0].replace("___", f[1])));
  (ASK[l.id] || []).forEach(a => { n.push(a[0]); n.push(a[2]); });
  groups.push({ file: l.id, normal: n, slow: [] });
}
for (const t of TEXTS) {
  const s = t.sentences.map(x => x[0]);
  const q = t.questions.flatMap(x => [x[0], x[1], ...x[2]]);
  groups.push({ file: t.id, normal: s.concat(q), slow: s });
}
groups.push({ file: "common", normal: ["Hola, ¿cómo estás? Me llamo Lucía y vivo en Madrid.", "Hola, ¿qué tal?", "Hola, ¿qué tal? Encantado de conocerte."], slow: [] });
process.stdout.write(JSON.stringify(groups));
