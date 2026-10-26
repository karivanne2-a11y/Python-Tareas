# Muestra texto fuente + JSON del LLM para auditar a mano las 20 extracciones sorteadas
import json, sys
from pathlib import Path
import pandas as pd
docs = pd.read_csv("datos/documentos.csv").set_index("id"); aud = pd.read_csv("datos/transcripciones.csv").set_index("id")
for i in sys.argv[1:]:
    p = Path(f"datos/raw/cache/llm_{i}.json")
    if not p.exists():
        print("==", i, "PENDIENTE"); continue
    texto = docs.loc[i, "texto_ocr"] if i.startswith("doc") else aud.loc[i, "texto_asr"]
    extra = f" tipo={docs.loc[i, 'tipo']}" if i.startswith("doc") else f" hablantes={aud.loc[i, 'n_hablantes']}"
    print("==", i, extra, "\nTEXTO:", str(texto)[:700].replace("\n", " | "), "\nLLM:", p.read_text(encoding="utf-8"), "\n")
