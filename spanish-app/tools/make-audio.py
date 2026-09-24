"""كيسجل الصوت الإسباني ديال التطبيق وكيجمعو فملفات mp3.

الصوت: Piper es_ES-sharvard-medium، المتكلم M (صوت ديال سبانيا، castellano) عبر sherpa-onnx.
اخترناه بعد ما قارنا الأصوات بـ Whisper: أحسن واحد فالجمل (5.5% غلط) وفالكلمات بوحدها.
الكلمات القصيرة (كلمة ولا جوج) كتتقال بشوية وبنقطة فالخر باش تكون واضحة.

الاستعمال:
    pip install sherpa-onnx num2words imageio-ffmpeg soundfile
    node tools/list-audio.js > /tmp/audio-list.json
    python3 tools/make-audio.py /tmp/audio-list.json MODEL_DIR CACHE_DIR

MODEL_DIR = vits-piper-es_ES-sharvard-medium من
https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-es_ES-sharvard-medium.tar.bz2
كيكتب audio/*.mp3 و audio/manifest.json حدا index.html.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from multiprocessing import Pool

import numpy as np
import soundfile as sf

VOICE = "piper-es_ES-sharvard-medium-M"
SPEAKER = 0  # M
LENGTH = {"n": 1.05, "s": 1.45, "w": 1.2}  # جملة عادية / بشوية / كلمة بوحدها
SR = 22050
PAD_BEFORE, PAD_AFTER = 0.15, 0.35

list_path, model_dir, cache_dir = sys.argv[1:4]
out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "audio")
os.makedirs(cache_dir, exist_ok=True)
os.makedirs(out_dir, exist_ok=True)


def spoken(text):
    from num2words import num2words
    t = re.sub(r"\([^)]*\)", "", text)
    t = re.sub(r"\d+", lambda m: num2words(int(m.group()), lang="es"), t)
    t = t.replace("—", "").replace("€", " euros").replace("___", "")
    return re.sub(r"\s+", " ", t).strip()


def kind(text, mode):
    return "w" if mode == "n" and len(spoken(text).split()) <= 2 else mode


def spoken_for(text, mode):
    t = spoken(text)
    return t.rstrip(".") + "." if kind(text, mode) == "w" and not re.search(r"[?!.]$", t) else t


def cache_file(text, mode):
    h = hashlib.sha1(f"{VOICE}|{kind(text, mode)}|{spoken_for(text, mode)}".encode()).hexdigest()[:16]
    return os.path.join(cache_dir, f"{h}.wav")


_k = None


def synth(job):
    global _k
    text, mode = job
    path = cache_file(text, mode)
    if os.path.exists(path):
        return
    if _k is None:
        import sherpa_onnx
        name = os.path.basename(os.path.normpath(model_dir))[len("vits-piper-"):]
        _k = {k: sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=os.path.join(model_dir, name + ".onnx"),
                                                       tokens=os.path.join(model_dir, "tokens.txt"),
                                                       data_dir=os.path.join(model_dir, "espeak-ng-data"),
                                                       length_scale=ls),
            num_threads=1))) for k, ls in LENGTH.items()}  # 4 عمليات × خيط واحد
    out = _k[kind(text, mode)].generate(spoken_for(text, mode), sid=SPEAKER)
    samples, sr = np.array(out.samples, dtype="float32"), out.sample_rate
    assert sr == SR
    sf.write(path, samples, sr)


def main():
    groups = json.load(open(list_path, encoding="utf-8"))
    # كل جملة كتسجل مرة وحدة، وكتمشي للملف الأول اللي فيه
    owner = {}
    for g in groups:
        for mode, key in (("n", "normal"), ("s", "slow")):
            for t in g[key]:
                owner.setdefault((t, mode), g["file"])
    jobs = sorted(owner)
    with Pool(4) as p:
        for i, _ in enumerate(p.imap_unordered(synth, jobs, chunksize=4)):
            if i % 100 == 0:
                print(f"{i}/{len(jobs)}", flush=True)

    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    manifest = {"f": [], "n": {}, "s": {}}
    for g in groups:
        items = [(t, m) for (t, m), f in owner.items() if f == g["file"]]
        if not items:
            continue
        fi = len(manifest["f"])
        name = f"{g['file']}.mp3"
        manifest["f"].append(name)
        parts, pos = [], 0.0
        for t, m in items:
            a, _ = sf.read(cache_file(t, m), dtype="float32")
            pre, post = np.zeros(int(PAD_BEFORE * SR), "float32"), np.zeros(int(PAD_AFTER * SR), "float32")
            start = pos + PAD_BEFORE - 0.05
            manifest[m][t] = [fi, round(start, 3), round(len(a) / SR + 0.12, 3)]
            parts += [pre, a, post]
            pos += PAD_BEFORE + len(a) / SR + PAD_AFTER
        wav = os.path.join(cache_dir, "_sprite.wav")
        sf.write(wav, np.concatenate(parts), SR)
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", wav, "-ac", "1", "-codec:a", "libmp3lame", "-b:a", "48k",
                        os.path.join(out_dir, name)], check=True)
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, separators=(",", ":"))
    print("files:", len(manifest["f"]), "clips:", len(manifest["n"]) + len(manifest["s"]))


if __name__ == "__main__":
    main()
