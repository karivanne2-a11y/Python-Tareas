# Precalienta la caché de OCR (mismo código y formato que la celda del notebook 01)
import json, sys, time
from pathlib import Path
import torch  # importar torch antes que paddle evita un conflicto de DLL en Windows
import numpy as np
from paddleocr import PaddleOCR

raiz = Path(sys.argv[1])
ocr_dir = raiz / "datos/raw/documentos/ocr_paddle"; ocr_dir.mkdir(exist_ok=True)
ocr = PaddleOCR(lang="es", use_doc_orientation_classify=False, use_doc_unwarping=False,
                use_textline_orientation=False, enable_mkldnn=False,
                text_detection_model_name="PP-OCRv5_mobile_det",
                text_recognition_model_name="latin_PP-OCRv5_mobile_rec")
for ruta in sorted((raiz / "datos/raw/documentos").glob("doc_*.jpg")):
    salida = ocr_dir / (ruta.stem + ".json")
    if salida.exists():
        continue
    t0 = time.perf_counter()
    res = ocr.predict(str(ruta))[0]
    textos, confs = list(res["rec_texts"]), [float(c) for c in res["rec_scores"]]
    d = {"texto": "\n".join(textos), "conf_media": float(np.mean(confs)) if confs else 0.0,
         "segundos": time.perf_counter() - t0, "lineas": textos, "scores": confs,
         "cajas": [np.asarray(b).tolist() for b in res["rec_polys"]]}
    salida.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    print(ruta.stem, len(d["texto"]), round(d["segundos"], 1), flush=True)
print("OCR_DONE")
