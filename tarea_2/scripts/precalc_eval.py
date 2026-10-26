# Precalcula EasyOCR y wav2vec2 sobre las muestras de evaluación (mismo sorteo, código y caché que el notebook 02)
import json, random, sys, time
from pathlib import Path
import torch
import pandas as pd

raiz = Path(sys.argv[1]); qué = sys.argv[2]
import os; os.chdir(raiz)
RAW = Path("datos/raw"); CACHE = RAW / "cache"; CACHE.mkdir(parents=True, exist_ok=True)
man_doc = pd.read_csv(RAW / "documentos" / "manifiesto.csv").drop_duplicates("sha256")
man_doc = man_doc[man_doc.id != "doc_009"]  # descartado en el notebook 01 (pintura sin texto)
CUOTA = {"impreso": 8, "foto": 8, "manuscrito": 9}
docs = pd.concat([g.iloc[:CUOTA[t]] for t, g in man_doc.groupby("tipo")]).sort_values("id")
man_aud = pd.read_csv(RAW / "audio" / "manifiesto.csv")

rng = random.Random(2026)
muestra_doc = []
for tipo, k in [("impreso", 4), ("foto", 3), ("manuscrito", 3)]:
    muestra_doc += sorted(rng.sample(sorted(docs[docs.tipo == tipo].id), k))
openslr = man_aud[man_aud.tipo == "openslr73"]
fem = sorted(openslr[openslr.titulo.str.contains("female")].id)
mas = sorted(openslr[~openslr.titulo.str.contains("female")].id)
muestra_aud = sorted(rng.sample(fem, 5) + rng.sample(mas, 5))
print(muestra_doc, muestra_aud, flush=True)

if qué == "easyocr":
    import easyocr
    lector = easyocr.Reader(["es"], gpu=False, verbose=False)
    for i in muestra_doc:
        cache = CACHE / f"easyocr_{i}.json"
        if cache.exists():
            continue
        t0 = time.perf_counter()
        texto = "\n".join(lector.readtext(str(RAW / "documentos" / f"{i}.jpg"), detail=0, paragraph=True))
        cache.write_text(json.dumps({"texto": texto, "segundos": time.perf_counter() - t0}, ensure_ascii=False), encoding="utf-8")
        print(i, len(texto), flush=True)
elif qué == "w2v":
    import soundfile as sf
    from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
    torch.set_num_threads(4)
    W2V = "jonatasgrosman/wav2vec2-large-xlsr-53-spanish"
    proc = Wav2Vec2Processor.from_pretrained(W2V)
    w2v = Wav2Vec2ForCTC.from_pretrained(W2V).eval()
    for i in muestra_aud:
        cache = CACHE / f"w2v_{i}.json"
        if cache.exists():
            continue
        y, sr = sf.read(str(RAW / "audio" / f"{i}.wav"))
        t0 = time.perf_counter()
        trozos = []
        for ini in range(0, len(y), 20 * sr):
            x = proc(y[ini: ini + 20 * sr], sampling_rate=sr, return_tensors="pt").input_values
            with torch.no_grad():
                ids = w2v(x).logits.argmax(-1)
            trozos.append(proc.batch_decode(ids)[0])
        d = {"texto": " ".join(trozos), "segundos": time.perf_counter() - t0, "duracion": len(y) / sr}
        cache.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        print(i, round(d["segundos"] / d["duracion"], 2), flush=True)
print("EVAL_DONE", qué)
