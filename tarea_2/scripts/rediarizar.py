# Rehace la diarización de las entrevistas a partir de los SRT exportados (sin repetir el ASR).
# Motivo: con umbral 0.55 todas las entrevistas salían con el tope de 4 hablantes (sobresegmentación evidente).
import json, re, sys
from pathlib import Path
import torch
import pandas as pd

raiz = Path(sys.argv[1]); umbral = float(sys.argv[2]) if len(sys.argv) > 2 else 0.70
sys.path.insert(0, str(raiz))
import os; os.chdir(raiz)
import voz

RAW = Path("datos/raw"); CACHE = RAW / "cache"; SAL = RAW / "audio" / "salidas"
man = pd.read_csv(RAW / "audio" / "manifiesto.csv")


def leer_srt(ruta):
    segs = []
    for bloque in ruta.read_text(encoding="utf-8").strip().split("\n\n"):
        lineas = bloque.splitlines()
        if len(lineas) < 3:
            continue
        a, b = [sum(float(x) * f for x, f in zip(t.replace(",", ".").split(":"), (3600, 60, 1))) for t in lineas[1].split(" --> ")]
        texto = re.sub(r"^\[HABLANTE_\d+\]\s*", "", " ".join(lineas[2:]))
        segs.append(voz.Segmento(a, b, texto))
    return segs


for r in man[man.tipo == "entrevista_commons"].itertuples():
    segs = leer_srt(SAL / f"{r.id}.srt")
    n_h = voz.diarizar(r.archivo, segs, umbral=umbral) if segs else 1
    voz.exportar(segs, SAL / r.id)
    cache = CACHE / f"asr_{r.id}.json"
    d = json.loads(cache.read_text(encoding="utf-8"))
    d["texto_asr_crudo"] = voz.texto_con_hablantes(segs) if n_h > 1 else " ".join(s.texto for s in segs)
    d["n_hablantes"] = n_h
    d["umbral_diarizacion"] = umbral
    cache.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    print(r.id, n_h, flush=True)
print("REDIAR_DONE")
