# Precalcula la extracción con LLM (mismos prompts, parámetros y caché que el notebook 02)
import json, sys, re
from pathlib import Path
import pandas as pd
from llama_cpp import Llama

raiz = Path(sys.argv[1])
import os; os.chdir(raiz)
CACHE = Path("datos/raw/cache")
src = Path("notebooks_src/02_evaluacion.py").read_text(encoding="utf-8")
PROMPT_DOC = re.search(r'PROMPT_DOC = """(.*?)"""', src, re.S).group(1)
PROMPT_AUD = re.search(r'PROMPT_AUD = """(.*?)"""', src, re.S).group(1)
llm = Llama(model_path="modelos/qwen2.5-1.5b-instruct-q4_k_m.gguf", n_ctx=4096, n_threads=4, verbose=False)


def extraer(texto, plantilla):
    texto = (texto if isinstance(texto, str) else "")[:2500]
    out = llm.create_chat_completion(
        messages=[{"role": "user", "content": plantilla.format(texto=texto)}],
        response_format={"type": "json_object"}, temperature=0, max_tokens=250)
    try:
        return json.loads(out["choices"][0]["message"]["content"])
    except json.JSONDecodeError:
        return {"error": "json_invalido", "crudo": out["choices"][0]["message"]["content"]}


docs = pd.read_csv("datos/documentos.csv"); aud = pd.read_csv("datos/transcripciones.csv")
for df, col, plantilla in [(docs, "texto_ocr", PROMPT_DOC), (aud, "texto_asr", PROMPT_AUD)]:
    for r in df.itertuples():
        cache = CACHE / f"llm_{r.id}.json"
        if cache.exists():
            continue
        campos = extraer(getattr(r, col), plantilla)
        cache.write_text(json.dumps(campos, ensure_ascii=False), encoding="utf-8")
        print(r.id, flush=True)
print("LLM_DONE")
