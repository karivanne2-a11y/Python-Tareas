# Precalcula la caché de ASR (mismo código y formato que la celda del notebook 01)
import json, sys
from pathlib import Path
import torch  # antes que cualquier otra librería nativa (Windows)
import pandas as pd

raiz = Path(sys.argv[1])
sys.path.insert(0, str(raiz))
import os; os.chdir(raiz)
import voz

RAW = Path("datos/raw"); CACHE = RAW / "cache"; CACHE.mkdir(parents=True, exist_ok=True)
sal_dir = RAW / "audio" / "salidas"; sal_dir.mkdir(exist_ok=True)
man = pd.read_csv(RAW / "audio" / "manifiesto.csv")
for r in man.itertuples():
    cache = CACHE / f"asr_{r.id}.json"
    if cache.exists():
        continue
    segs, meta = voz.transcribir(r.archivo, "small", vad=True)
    if r.tipo == "entrevista_commons" and segs:
        n_h = voz.diarizar(r.archivo, segs)
    else:
        n_h = 1
        for s in segs:
            s.hablante = None
    voz.exportar(segs, sal_dir / r.id)
    d = {"id": r.id, "duracion_seg": round(meta["duracion"], 1), "duracion_voz": round(meta["duracion_voz"], 1),
         "seg_proceso": round(meta["segundos_proceso"], 1), "idioma": meta["idioma"], "n_segmentos": len(segs),
         "texto_asr_crudo": voz.texto_con_hablantes(segs) if n_h > 1 else " ".join(s.texto for s in segs),
         "n_hablantes": n_h}
    cache.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    print(r.id, d["duracion_seg"], n_h, round(d["seg_proceso"] / max(d["duracion_seg"], 1), 2), flush=True)
print("ASR_DONE")
