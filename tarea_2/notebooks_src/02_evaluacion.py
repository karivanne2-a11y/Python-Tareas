# %% [markdown]
# # Tarea 2 · Parte 2 — Evaluación (CER/WER), extracción estructurada con LLM y comparación de modelos
#
# Reglas que sigo en este notebook:
# 1. La muestra de evaluación (10 documentos, 10 clips) se elige **con semilla fija antes de correr cualquier modelo alternativo** y se usa la misma para todos.
# 2. Las configuraciones de todos los modelos se fijan en la celda de configuración; **no se ajustan** después de ver las métricas.
# 3. Referencia y salida automática se normalizan con el mismo criterio (`voz.normalizar`: minúsculas, sin tildes ni puntuación) y en WER se eliminan las marcas `[HABLANTE_n]`.

# %%
import json, time, random, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.io as pio
import jiwer
import voz
pio.renderers.default = "notebook_connected"
warnings.filterwarnings("ignore")
pd.set_option("display.max_colwidth", 100)

DATOS = Path("datos"); RAW = DATOS / "raw"; CACHE = RAW / "cache"
docs = pd.read_csv(DATOS / "documentos.csv")
aud = pd.read_csv(DATOS / "transcripciones.csv")
man_aud = pd.read_csv(RAW / "audio" / "manifiesto.csv")

CONFIG = {
    "ocr_base": "PaddleOCR 3 PP-OCRv5 mobile (latin) lang=es (sin personalización)",
    "ocr_alt": "EasyOCR 1.7 lang=['es'] paragraph=True",
    "asr_base": "faster-whisper small int8 CPU, VAD on, greedy",
    "asr_alt": "wav2vec2-large-xlsr-53-spanish (CTC, greedy) CPU",
    "llm": "Qwen2.5-1.5B-Instruct Q4_K_M (llama.cpp, CPU, temperatura 0)",
}
CONFIG

# %% [markdown]
# ## 1. Muestra de evaluación (sin nuevos datos)
# - **Documentos:** 4 impresos + 3 fotos + 3 manuscritos, sorteados con semilla 2026 entre los 25 de la Parte 1.
# - **Audio:** 10 clips de la Parte 1 con **transcripción humana disponible**: los clips de OpenSLR 73 traen la transcripción manual de cada enunciado
#   hecha y validada por anotadores humanos (no es una salida automática). Se sortean 5 de voces femeninas y 5 masculinas (hablantes distintos).
#   Las entrevistas de calle de Commons no tienen referencia publicada; se analizan como caso difícil en la sección 5.
# - Las referencias de documentos están en `datos/referencias_documentos.json` (transcripción manual de la imagen, conservando ortografía original).

# %%
rng = random.Random(2026)
muestra_doc = []
for tipo, k in [("impreso", 4), ("foto", 3), ("manuscrito", 3)]:
    muestra_doc += sorted(rng.sample(sorted(docs[docs.tipo == tipo].id), k))
openslr = man_aud[man_aud.tipo == "openslr73"]
fem = sorted(openslr[openslr.titulo.str.contains("female")].id)
mas = sorted(openslr[~openslr.titulo.str.contains("female")].id)
muestra_aud = sorted(rng.sample(fem, 5) + rng.sample(mas, 5))
print("Documentos:", muestra_doc)
print("Clips:", muestra_aud)

# %%
ref_doc = json.loads((DATOS / "referencias_documentos.json").read_text(encoding="utf-8"))
ref_aud = man_aud.set_index("id").texto_referencia_fuente.to_dict()
docs["texto_referencia"] = docs.id.map(lambda i: ref_doc.get(i, "") if i in muestra_doc else "")
aud["texto_referencia"] = aud.id.map(lambda i: ref_aud.get(i, "") if i in muestra_aud else "")
docs.to_csv(DATOS / "documentos.csv", index=False)
aud.to_csv(DATOS / "transcripciones.csv", index=False)
print("Referencias cargadas:", (docs.texto_referencia.fillna("") != "").sum(), "documentos |",
      (aud.texto_referencia.fillna("") != "").sum(), "clips")

# %% [markdown]
# ## 2. Línea base sin ajuste
# - OCR: salida cruda de PaddleOCR de la Parte 1 (mismo modelo, sin cambios).
# - ASR: faster-whisper `small` en CPU (salida de la Parte 1; el tiempo de proceso medido allí da el factor de tiempo real, RTF).

# %%
def cer(ref, hip):
    r, h = voz.normalizar(ref), voz.normalizar(hip)
    return jiwer.cer(r, h) if r else np.nan

def wer(ref, hip):
    r, h = voz.normalizar(ref), voz.normalizar(hip)
    return jiwer.wer(r, h) if r else np.nan

def leer_ocr_paddle(i):
    return json.loads((RAW / "documentos" / "ocr_paddle" / f"{i}.json").read_text(encoding="utf-8"))

ev_doc = docs[docs.id.isin(muestra_doc)].set_index("id")
filas_doc = []
for i in muestra_doc:
    d = leer_ocr_paddle(i)
    filas_doc.append({"id": i, "modelo": "PaddleOCR (base)", "cer": cer(ref_doc[i], d["texto"]), "segundos": d["segundos"], "hipotesis": d["texto"]})

filas_aud = []
for i in muestra_aud:
    d = json.loads((CACHE / f"asr_{i}.json").read_text(encoding="utf-8"))
    filas_aud.append({"id": i, "modelo": "faster-whisper small (base)", "wer": wer(ref_aud[i], d["texto_asr_crudo"]),
                      "rtf": d["seg_proceso"] / d["duracion_seg"], "hipotesis": d["texto_asr_crudo"]})
base_doc, base_aud = pd.DataFrame(filas_doc), pd.DataFrame(filas_aud)
print(f"Línea base  CER PaddleOCR = {base_doc.cer.mean():.3f}   WER faster-whisper small = {base_aud.wer.mean():.3f}")
base_doc.merge(docs[["id", "tipo"]]).groupby("tipo").cer.mean().round(3)

# %% [markdown]
# ## 3. Modelos alternativos sobre las mismas muestras
# ### 3.1 OCR alternativo: EasyOCR
# Justificación: Tesseract requiere instalar un binario del sistema (no disponible sin permisos de administrador en mi laptop);
# EasyOCR es un OCR abierto con otra arquitectura (detector CRAFT + reconocedor CRNN), instalable con `pip` y con modelo latino que cubre el español.

# %%
import easyocr
lector = easyocr.Reader(["es"], gpu=False, verbose=False)
for i in muestra_doc:
    cache = CACHE / f"easyocr_{i}.json"
    if cache.exists():
        d = json.loads(cache.read_text(encoding="utf-8"))
    else:
        t0 = time.perf_counter()
        texto = "\n".join(lector.readtext(ev_doc.loc[i, "archivo"], detail=0, paragraph=True))
        d = {"texto": texto, "segundos": time.perf_counter() - t0}
        cache.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    filas_doc.append({"id": i, "modelo": "EasyOCR (alternativo)", "cer": cer(ref_doc[i], d["texto"]), "segundos": d["segundos"], "hipotesis": d["texto"]})

# %% [markdown]
# ### 3.2 ASR alternativo: wav2vec2 XLSR-53 español (familia CTC de MMS)
# Justificación: Qwen3-ASR y Parakeet no corren de forma práctica en CPU de 4 núcleos y 10 GB de RAM; MMS-1B ocupa ~4 GB en fp32.
# `jonatasgrosman/wav2vec2-large-xlsr-53-spanish` es un modelo CTC de 300 M parámetros (misma base wav2vec2/XLS-R que MMS) afinado en Common Voice español.
# Se procesa en ventanas de 20 s sobre el audio a 16 kHz.

# %%
import torch, soundfile as sf
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
torch.set_num_threads(4)
W2V = "jonatasgrosman/wav2vec2-large-xlsr-53-spanish"
proc = Wav2Vec2Processor.from_pretrained(W2V)
w2v = Wav2Vec2ForCTC.from_pretrained(W2V).eval()

def asr_w2v(ruta):
    y, sr = sf.read(ruta)
    t0 = time.perf_counter()
    trozos = []
    for ini in range(0, len(y), 20 * sr):
        x = proc(y[ini: ini + 20 * sr], sampling_rate=sr, return_tensors="pt").input_values
        with torch.no_grad():
            ids = w2v(x).logits.argmax(-1)
        trozos.append(proc.batch_decode(ids)[0])
    return " ".join(trozos), time.perf_counter() - t0, len(y) / sr

ev_aud = aud.set_index("id")
for i in muestra_aud:
    cache = CACHE / f"w2v_{i}.json"
    if cache.exists():
        d = json.loads(cache.read_text(encoding="utf-8"))
    else:
        texto, seg, dur = asr_w2v(ev_aud.loc[i, "archivo_audio"])
        d = {"texto": texto, "segundos": seg, "duracion": dur}
        cache.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    filas_aud.append({"id": i, "modelo": "wav2vec2-xlsr-es (alternativo)", "wer": wer(ref_aud[i], d["texto"]),
                      "rtf": d["segundos"] / d["duracion"], "hipotesis": d["texto"]})

# %% [markdown]
# ## 4. Métricas finales sobre la muestra de evaluación

# %%
comp_doc = pd.DataFrame(filas_doc).merge(docs[["id", "tipo"]], on="id")
comp_aud = pd.DataFrame(filas_aud)
comp_doc.to_csv(DATOS / "comparacion_ocr.csv", index=False)
comp_aud.to_csv(DATOS / "comparacion_asr.csv", index=False)

tabla_doc = comp_doc.groupby("modelo").agg(CER=("cer", "mean"), seg_por_doc=("segundos", "mean")).round(3)
tabla_tipo = comp_doc.pivot_table(index="modelo", columns="tipo", values="cer", aggfunc="mean").round(3)
tabla_aud = comp_aud.groupby("modelo").agg(WER=("wer", "mean"), RTF=("rtf", "mean")).round(3)
display(tabla_doc.join(tabla_tipo.add_prefix("CER_")))
display(tabla_aud)

# %%
fig = px.box(comp_doc, x="tipo", y="cer", color="modelo", points="all",
             title="Ambos OCR funcionan en impresos; en manuscritos el CER se acerca o supera 1 (texto casi inservible)",
             labels={"cer": "CER (menor es mejor)"})
fig.show()
fig = px.bar(comp_aud, x="id", y="wer", color="modelo", barmode="group",
             title="faster-whisper small comete menos errores que wav2vec2 en casi todos los clips",
             labels={"wer": "WER (menor es mejor)"})
fig.show()

# %% [markdown]
# ## 5. Extracción estructurada con LLM local
# Prompt estructurado con salida JSON forzada por gramática (`response_format` JSON de llama.cpp), temperatura 0. Se pide `null` para datos ausentes.

# %%
from llama_cpp import Llama
# Pesos descargados de https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF (no versionados)
llm = Llama(model_path="modelos/qwen2.5-1.5b-instruct-q4_k_m.gguf", n_ctx=4096, n_threads=4, verbose=False)

PROMPT_DOC = """Eres un archivista. Lee el texto OCR de un documento peruano (puede tener errores de OCR) y devuelve SOLO un JSON con estas claves:
"modalidad": "documento", "tema": frase corta, "resumen": una oración, "emisor": quién emite el documento o null,
"fecha": fecha que aparezca literalmente en el texto o null, "monto": monto de dinero que aparezca literalmente o null.
Si un dato no aparece en el texto, usa null. No inventes información.

TEXTO OCR:
{texto}"""
PROMPT_AUD = """Lee la transcripción automática de un audio en español peruano y devuelve SOLO un JSON con estas claves:
"modalidad": "audio", "tema": frase corta, "resumen": una oración, "numero_hablantes": número de hablantes distintos si hay marcas [HABLANTE_n], si no null,
"citas_clave": lista de máximo 2 frases copiadas literalmente de la transcripción.
No inventes información.

TRANSCRIPCIÓN:
{texto}"""

def extraer(texto, plantilla):
    texto = (texto or "")[:2500]  # límite por costo en CPU (contexto y latencia)
    out = llm.create_chat_completion(
        messages=[{"role": "user", "content": plantilla.format(texto=texto)}],
        response_format={"type": "json_object"}, temperature=0, max_tokens=250)
    try:
        return json.loads(out["choices"][0]["message"]["content"])
    except json.JSONDecodeError:
        return {"error": "json_invalido", "crudo": out["choices"][0]["message"]["content"]}

filas = []
for modalidad, df, col, plantilla in [("documento", docs, "texto_ocr", PROMPT_DOC), ("audio", aud, "texto_asr", PROMPT_AUD)]:
    for r in df.itertuples():
        cache = CACHE / f"llm_{r.id}.json"
        if cache.exists():
            campos = json.loads(cache.read_text(encoding="utf-8"))
        else:
            campos = extraer(getattr(r, col), plantilla)
            cache.write_text(json.dumps(campos, ensure_ascii=False), encoding="utf-8")
        filas.append({"id": r.id, "modalidad": modalidad, "campos_json": json.dumps(campos, ensure_ascii=False),
                      "modelo_llm": CONFIG["llm"], "fecha": "2026-10-25"})
extraccion = pd.DataFrame(filas)
extraccion.to_csv(DATOS / "extraccion_llm.csv", index=False)
print(extraccion.shape)
extraccion.head(6)

# %% [markdown]
# ## 6. Auditoría humana de 20 extracciones al azar (10 documentos + 10 audios)
# **Criterios de corrección (fijados antes de revisar):** una extracción es *completamente correcta* si
# (a) el JSON es válido y tiene las claves pedidas; (b) `tema` y `resumen` son fieles al texto; (c) los campos factuales
# (`emisor`, `fecha`, `monto`, `numero_hablantes`, `citas_clave`) son correctos **o** `null` cuando el dato no aparece; (d) no hay datos inventados.
# Un solo campo erróneo o inventado ⇒ incorrecta. La revisión se registró en `datos/auditoria_llm.csv` comparando cada JSON con el texto fuente y la imagen/audio.

# %%
rng = random.Random(20)
muestra_auditoria = sorted(rng.sample(sorted(docs.id), 10)) + sorted(rng.sample(sorted(aud.id), 10))
auditoria = pd.read_csv(DATOS / "auditoria_llm.csv")
assert sorted(auditoria.id) == sorted(muestra_auditoria), "La auditoría debe cubrir exactamente la muestra sorteada"
ok = int(auditoria.correcto.sum())
print(f"Extracciones completamente correctas: {ok}/20 = {ok/20:.0%}")
display(auditoria.groupby("modalidad").correcto.agg(["sum", "count"]))
print("Tipos de error:"); display(auditoria[~auditoria.correcto].tipo_error.value_counts())
display(auditoria[~auditoria.correcto][["id", "tipo_error", "nota"]])

# %% [markdown]
# ## 7. Casos difíciles

# %%
dificil_doc = comp_doc[comp_doc.tipo == "manuscrito"].pivot_table(index="id", columns="modelo", values="cer").round(2)
display(dificil_doc)
calle = aud[aud.fuente.str.contains("Commons")][["id", "duracion_seg", "n_hablantes", "texto_asr"]]
calle = calle.assign(texto_asr=calle.texto_asr.str[:160])
display(calle)

# %% [markdown]
# ## 8. Tabla comparativa y decisión

# %%
tabla = pd.concat([
    tabla_doc.reset_index().rename(columns={"CER": "error", "seg_por_doc": "costo"}).assign(modalidad="documentos", metrica="CER", unidad_costo="s/documento (CPU)"),
    tabla_aud.reset_index().rename(columns={"WER": "error", "RTF": "costo"}).assign(modalidad="audio", metrica="WER", unidad_costo="RTF (CPU)"),
])[["modalidad", "modelo", "metrica", "error", "costo", "unidad_costo"]].round(3)
display(tabla)

mejor_ocr = tabla_doc.CER.idxmin(); mejor_asr = tabla_aud.WER.idxmin()
metricas = {
    "cer_base": round(float(tabla_doc.loc["PaddleOCR (base)", "CER"]), 3),
    "wer_base": round(float(tabla_aud.loc["faster-whisper small (base)", "WER"]), 3),
    "cer_elegido": round(float(tabla_doc.CER.min()), 3), "modelo_ocr_elegido": mejor_ocr,
    "wer_elegido": round(float(tabla_aud.WER.min()), 3), "modelo_asr_elegido": mejor_asr,
    "auditoria_ok": ok, "auditoria_n": 20,
    "tabla_comparativa": tabla.to_dict("records"),
}
(DATOS / "metricas.json").write_text(json.dumps(metricas, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"Resultados Test: WER: {metricas['wer_elegido']:.2f} | CER: {metricas['cer_elegido']:.2f} | Acuerdo LLM-Humano: {ok}/20")

# %% [markdown]
# ## 9. Decisión y reflexión
#
# **Decisión para un entorno real (CPU, sin GPU):**
# - **Documentos → PaddleOCR (PP-OCRv5 mobile, reconocedor latino).** Menor CER en los 10 documentos (0,35 vs 0,41) y en los tres tipos, y además ~40 % más rápido
#   por documento que EasyOCR en la misma laptop. EasyOCR no aporta ventaja en ningún tipo.
# - **Audio → faster-whisper `small` (int8, VAD).** WER 0,03 vs 0,23 de wav2vec2 en los mismos 10 clips y menor RTF. wav2vec2 (CTC sin modelo de lenguaje)
#   produce errores ortográficos fonéticos (b/v, s/z, palabras partidas) y no puntúa, lo que además empeora la extracción posterior con el LLM.
# - **LLM → Qwen2.5-1.5B solo como borrador.** 4/20 extracciones completamente correctas: no es utilizable sin revisión humana. Para producción haría falta un modelo
#   más grande (7B+ o API) y validación de campos (p. ej., rechazar fechas que no sean años/fechas reales y citas que no estén literalmente en el texto).
#
# **Reflexión por tipo de documento:**
# - *Impresos* (CER 0,22 con PaddleOCR, pero ≈0,01 en las páginas de texto corrido): el mejor caso. El promedio sube solo por la portada desvaída de 1856 (doc_003),
#   donde el OCR casi no detecta texto: el problema es el contraste, no la tipografía.
# - *Fotos* (CER 0,32): bien en placas con letras grandes y poca perspectiva (doc_011: 0,09); mal en el cartel bilingüe de Huaca Melgarejo (0,59), porque el OCR lee por líneas
#   cruzando las dos columnas (español/inglés) y el orden de lectura no coincide con la referencia; y en relieves metálicos con reflejos (doc_017: 0,28).
# - *Manuscritos* (CER 0,54): el peor caso, como se esperaba. PaddleOCR no tiene un modelo de escritura a mano; acierta parcialmente en la partida de 1792 con letra
#   regular (0,34) y fracasa en el Acta de la Independencia (0,81), con letra del s. XIX, abreviaturas y decenas de firmas superpuestas.
#
# **Reflexión por tipo de audio:**
# - *Habla leída de OpenSLR 73* (WER 0,03): casi perfecta; los errores son nombres propios y palabras poco frecuentes ("sarsamora", "Ruflo" por Rulfo).
# - *Entrevistas de calle de Commons* (sin referencia): la inspección muestra errores claros con ruido de fondo y voces lejanas (palabras inventadas, nombres deformados) y
#   una diarización que sobresegmenta. Es el caso donde el pipeline necesita más trabajo: un modelo más grande (`large-v3`) y diarización entrenada (pyannote) con GPU.
