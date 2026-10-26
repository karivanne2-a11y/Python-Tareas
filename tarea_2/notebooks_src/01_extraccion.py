# %% [markdown]
# # Tarea 2 · Parte 1 — Corpus y extracción (OCR + ASR)
#
# **Pregunta guía:** ¿Pueden convertirse documentos escaneados y entrevistas en audio en un archivo de texto estructurado y buscable?
#
# | Campo | Valor |
# |---|---|
# | Fecha de extracción | 2026-10-25 |
# | Corpus A (documentos) | 25 imágenes/páginas de documentos peruanos de **Wikimedia Commons** (8 impresos, 8 fotos con sombra/inclinación, 9 manuscritos). Licencias: dominio público, CC BY-SA 3.0/4.0, CC BY 2.0 (detalle por archivo en `datos/fuentes.csv`). |
# | Corpus B (audio) | 10 entrevistas reales en español peruano de **Wikimedia Commons** (CC BY-SA 4.0, registradas por estudiantes de la UNMSM) + 14 clips de **OpenSLR 73** (*Crowdsourced high-quality Peruvian Spanish*, CC BY-SA 4.0, Guevara-Rukoz et al., 2020). |
# | OCR | PaddleOCR (PP-OCRv5 mobile: detector + reconocedor latino, `lang=es`, CPU) — versión impresa abajo |
# | ASR | faster-whisper `small` (int8, CPU) + VAD Silero integrado; diarización con embeddings ECAPA (SpeechBrain) + clustering aglomerativo |
# | Entornos | `uv sync` (equivalente a los grupos `docai` y `audio` de las sesiones) |
#
# **Política de datos personales.** Se seudonimizan nombres de personas privadas vivas (entrevistados), DNI, teléfonos y correos.
# No se seudonimizan figuras históricas públicas ni personas fallecidas hace más de un siglo presentes en documentos de archivo
# (p. ej. registros parroquiales del s. XVII–XIX, Miguel Grau), porque la Ley 29733 protege datos de personas naturales vivas.
# La tabla de correspondencias seudónimo↔nombre real se guarda solo en `datos/raw/` (no versionado).

# %%
import hashlib, json, time, warnings
from pathlib import Path
import torch  # importar torch antes que paddle evita un conflicto de DLL en Windows
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.io as pio
# Gráficos interactivos en Jupyter + copia PNG estática para que se vean en GitHub (kaleido usa Chrome/Edge)
import os
os.environ.setdefault("BROWSER_PATH", "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
pio.renderers.default = "notebook_connected+png"
warnings.filterwarnings("ignore")
pd.set_option("display.max_colwidth", 120)

import paddleocr, paddle, faster_whisper
import voz

RAIZ = Path(".")
RAW = RAIZ / "datos" / "raw"
CACHE = RAW / "cache"; CACHE.mkdir(parents=True, exist_ok=True)
print("PaddleOCR", paddleocr.__version__, "| PaddlePaddle", paddle.__version__, "| faster-whisper", faster_whisper.__version__)

# %% [markdown]
# ## 1. Corpus descargado
# Los archivos se descargan con `datos.py` (API de Commons, User-Agent descriptivo, 1,5 s entre solicitudes; OpenSLR por HTTP Range sin bajar el zip completo de ~1 GB).
# Los originales quedan en `datos/raw/` (ignorado por Git).

# %%
man_doc = pd.read_csv(RAW / "documentos" / "manifiesto.csv")
man_aud = pd.read_csv(RAW / "audio" / "manifiesto.csv")
print(man_doc.shape, man_aud.shape)
man_doc[["id", "tipo", "titulo", "pagina", "licencia"]]

# %% [markdown]
# ## 2. Limpieza: duplicados por hash y descartes

# %%
dup = man_doc[man_doc.duplicated("sha256", keep="first")]
print(f"Duplicados por SHA-256: {len(dup)} ->", dup[["id", "titulo"]].to_dict("records"))
man_doc = man_doc.drop_duplicates("sha256", keep="first").reset_index(drop=True)
dup_a = man_aud[man_aud.duplicated("sha256", keep="first")]
print(f"Audios duplicados: {len(dup_a)}")
man_aud = man_aud.drop_duplicates("sha256").reset_index(drop=True)
man_doc.tipo.value_counts()

# %% [markdown]
# ## 3. OCR con PaddleOCR
# Parámetros: `lang="es"` (PP-OCRv5 mobile, reconocedor `latin` que cubre el español), sin orientación de documento ni *unwarping* (configuración base de la sesión 10),
# imágenes reescaladas a 1280 px de ancho por Commons (o tamaño original si es menor). Se guarda el JSON crudo de cada documento en `datos/raw/documentos/ocr_paddle/`.

# %%
from paddleocr import PaddleOCR
ocr_dir = RAW / "documentos" / "ocr_paddle"; ocr_dir.mkdir(exist_ok=True)
ocr = PaddleOCR(lang="es", use_doc_orientation_classify=False, use_doc_unwarping=False,
                use_textline_orientation=False, enable_mkldnn=False,
                text_detection_model_name="PP-OCRv5_mobile_det",
                text_recognition_model_name="latin_PP-OCRv5_mobile_rec")

def ocr_paddle(ruta: str) -> tuple[str, float, float]:
    salida = ocr_dir / (Path(ruta).stem + ".json")
    if salida.exists():
        d = json.loads(salida.read_text(encoding="utf-8"))
        return d["texto"], d["conf_media"], d["segundos"]
    t0 = time.perf_counter()
    res = ocr.predict(ruta)[0]
    textos, confs = list(res["rec_texts"]), [float(c) for c in res["rec_scores"]]
    d = {"texto": "\n".join(textos), "conf_media": float(np.mean(confs)) if confs else 0.0,
         "segundos": time.perf_counter() - t0, "lineas": textos, "scores": confs,
         "cajas": [np.asarray(b).tolist() for b in res["rec_polys"]]}
    salida.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d["texto"], d["conf_media"], d["segundos"]

filas = []
for r in man_doc.itertuples():
    texto, conf, seg = ocr_paddle(r.archivo)
    filas.append({"id": r.id, "texto_ocr_crudo": texto, "conf_ocr": round(conf, 3), "seg_ocr": round(seg, 1)})
    print(f"{r.id} {r.tipo:<10} conf={conf:.2f} chars={len(texto):>5} t={seg:.1f}s")
ocr_df = man_doc.merge(pd.DataFrame(filas), on="id")

# %% [markdown]
# ### Descartes de documentos ilegibles
# Criterio fijado *antes* de ver métricas: el OCR marca como candidato todo documento con < 15 caracteres; se descarta solo si la
# **inspección visual** confirma que no hay texto legible para una persona. Un fallo del OCR sobre un documento legible no es motivo de
# descarte: ese documento queda como caso difícil.
# Si algún documento se descarta, se reemplaza por uno del mismo tipo hasta cumplir 8/8/9.

# %%
candidatos = ocr_df[ocr_df.texto_ocr_crudo.str.len() < 15]
print("Candidatos (OCR < 15 caracteres):", candidatos[["id", "tipo", "titulo"]].to_dict("records") or "ninguno")
# Revisión visual de cada candidato (anotada a mano):
REVISION_VISUAL = {
    "doc_009": "ILEGIBLE: la imagen es una pintura de la firma de la Capitulación, no contiene texto -> se descarta",
    "doc_010": "legible: foto de baja resolución de la Capitulación de Ayacucho; se conserva como caso difícil",
}
for i in candidatos.id:
    print(f"  {i}: {REVISION_VISUAL.get(i, 'SIN REVISAR')}")
ilegibles = candidatos[candidatos.id.map(lambda i: REVISION_VISUAL.get(i, "ILEGIBLE")).str.startswith("ILEGIBLE")]
print("Descartados por ilegibles:", ilegibles.id.tolist() or "ninguno")
ocr_df = ocr_df.drop(ilegibles.index)
# Cuotas del enunciado; los documentos sobrantes de cada tipo son reservas que solo entran si se descarta otro
CUOTA = {"impreso": 8, "foto": 8, "manuscrito": 9}
reservas = pd.concat([g.iloc[CUOTA[t]:] for t, g in ocr_df.groupby("tipo")])
print("Reservas no usadas:", reservas[["id", "tipo", "titulo"]].to_dict("records"))
ocr_df = pd.concat([g.iloc[:CUOTA[t]] for t, g in ocr_df.groupby("tipo")]).sort_values("id").reset_index(drop=True)
man_doc = man_doc[man_doc.id.isin(ocr_df.id)]
print("Conteo final por tipo:", ocr_df.tipo.value_counts().to_dict(), "| total", len(ocr_df))

# %% [markdown]
# ## 4. ASR: VAD + faster-whisper + diarización
# - VAD Silero (`vad_filter=True`, silencios ≥ 500 ms) para evitar alucinaciones en silencios/ruido.
# - `condition_on_previous_text=False` para cortar bucles de repetición; decodificación greedy (beam 1) por el costo en CPU de 4 núcleos.
# - Diarización en **todas las entrevistas de Commons** (varias tienen entrevistador + entrevistado(s)); los clips de OpenSLR son de un solo hablante por construcción.
#   Umbral de distancia coseno 0,70 (tope 4 hablantes). Un primer intento con 0,55 asignó el tope de 4 hablantes a *todas* las entrevistas
#   (sobresegmentación evidente, incluso en entrevistas de una sola persona), por lo que se rehízo la diarización desde los SRT con
#   `scripts/rediarizar.py` sin repetir el ASR. No hay referencia de hablantes, así que este umbral no se ajustó contra ninguna métrica.
# - Exportación por clip a SRT y TXT en `datos/raw/audio/salidas/`.

# %%
sal_dir = RAW / "audio" / "salidas"; sal_dir.mkdir(exist_ok=True)

def procesar_audio(r) -> dict:
    cache = CACHE / f"asr_{r.id}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
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
    return d

res = []
for r in man_aud.itertuples():
    d = procesar_audio(r)
    res.append(d)
    print(f"{r.id} {r.tipo:<18} {d['duracion_seg']:>6.1f}s voz={d['duracion_voz']:>6.1f}s hablantes={d['n_hablantes']} RTF={d['seg_proceso']/d['duracion_seg']:.2f}")
asr_df = man_aud.merge(pd.DataFrame(res), on="id")
print(f"Total audio: {asr_df.duracion_seg.sum()/60:.1f} min en {len(asr_df)} clips; multihablante: {(asr_df.n_hablantes>1).sum()} clips")

# %% [markdown]
# ### Descarte de audios sin voz
# Criterio: duración de voz tras VAD < 5 % de la duración total o transcripción vacía.

# %%
sin_voz = asr_df[(asr_df.duracion_voz < 0.05 * asr_df.duracion_seg) | (asr_df.texto_asr_crudo.str.strip() == "")]
print("Audios descartados por falta de voz:", sin_voz.id.tolist() or "ninguno")
asr_df = asr_df.drop(sin_voz.index).reset_index(drop=True)

# %% [markdown]
# ## 5. Seudonimización
# Nombres de personas privadas tomados de las descripciones de Commons de las entrevistas (no se imprimen aquí) + patrones DNI/teléfono/correo + nombres tras "me llamo / mi nombre es / señora…".
# Después se hizo **revisión humana** de las transcripciones de las entrevistas leyendo los TXT. La revisión encontró (a) variantes de los
# nombres deformadas por el ASR (apellidos mal transcritos, con *z* en lugar de *s*, pegados a otra palabra) y (b) nombres de
# entrevistadores y entrevistados que no figuraban en las descripciones de Commons. Se añadieron a la lista privada (no versionada) y se
# volvió a ejecutar esta celda. Nombres de futbolistas y figuras públicas mencionados en las entrevistas no se seudonimizan.

# %%
nombres_privados = json.loads((RAW / "nombres_privados.json").read_text(encoding="utf-8"))  # no versionado
tabla = {}
cont_doc = cont_aud = 0
ocr_df["texto_ocr"], n = zip(*[(t, k) for t, k, _ in (voz.seudonimizar(x, nombres_privados, tabla, disparadores=False) for x in ocr_df.texto_ocr_crudo)])
cont_doc = sum(n)
asr_df["texto_asr"], n = zip(*[(t, k) for t, k, _ in (voz.seudonimizar(x, nombres_privados, tabla) for x in asr_df.texto_asr_crudo)])
cont_aud = sum(n)
(RAW / "tabla_seudonimos.json").write_text(json.dumps(tabla, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"Reemplazos en documentos: {cont_doc} | en audio: {cont_aud} | entidades únicas: {len(tabla)}")
print("Clases de entidad reemplazadas:", pd.Series([v.split('_')[0].strip('[') for v in tabla.values()]).value_counts().to_dict())

# %% [markdown]
# ## 6. Análisis exploratorio (Plotly Express)

# %%
ocr_df["chars_ocr"] = ocr_df.texto_ocr.str.len()
asr_df["palabras_asr"] = asr_df.texto_asr.map(lambda t: len(voz.normalizar(t).split()))
asr_df["fuente_corta"] = asr_df.tipo.map({"entrevista_commons": "Entrevistas Commons", "openslr73": "OpenSLR 73"})

conteo = ocr_df.tipo.value_counts().rename_axis("tipo").reset_index(name="n")
conf_tipo = ocr_df.groupby("tipo").conf_ocr.mean().round(2).to_dict()
fig1 = px.bar(conteo, x="tipo", y="n", color="tipo", text="n",
              title=f"Corpus balanceado (8/8/9), pero la confianza OCR cae en manuscritos: {conf_tipo.get('manuscrito')} vs {conf_tipo.get('impreso')} en impresos",
              labels={"n": "documentos", "tipo": "tipo de documento"})
fig1.show()

# %%
fig2 = px.bar(asr_df.sort_values("duracion_seg"), x="id", y="duracion_seg", color="fuente_corta",
              title=f"{asr_df.duracion_seg.sum()/60:.0f} min de audio: las entrevistas de calle son más largas y variables que los clips de OpenSLR (~1 min)",
              labels={"duracion_seg": "duración (s)", "id": "clip", "fuente_corta": "fuente"})
fig2.show()

# %%
long_df = pd.concat([
    pd.DataFrame({"longitud": ocr_df.chars_ocr, "medida": "caracteres OCR (documentos)", "grupo": ocr_df.tipo}),
    pd.DataFrame({"longitud": asr_df.palabras_asr, "medida": "palabras ASR (audios)", "grupo": asr_df.fuente_corta}),
])
fig3 = px.histogram(long_df, x="longitud", color="grupo", facet_col="medida", nbins=20, barmode="overlay",
                    title="Los impresos concentran los textos OCR largos; los manuscritos casi no producen texto útil",
                    labels={"longitud": "longitud del texto"})
fig3.update_xaxes(matches=None)
fig3.show()

# %% [markdown]
# ## 7. Validación: extremos de longitud

# %%
cols = ["id", "tipo", "chars_ocr", "conf_ocr"]
print("OCR más largos"); display(ocr_df.nlargest(3, "chars_ocr")[cols + ["texto_ocr"]].assign(texto_ocr=lambda d: d.texto_ocr.str[:150]))
print("OCR más cortos"); display(ocr_df.nsmallest(3, "chars_ocr")[cols + ["texto_ocr"]])
cols_a = ["id", "fuente_corta", "duracion_seg", "palabras_asr", "n_hablantes"]
print("Clips más largos"); display(asr_df.nlargest(3, "duracion_seg")[cols_a + ["texto_asr"]].assign(texto_asr=lambda d: d.texto_asr.str[:150]))
print("Clips más cortos"); display(asr_df.nsmallest(3, "duracion_seg")[cols_a + ["texto_asr"]].assign(texto_asr=lambda d: d.texto_asr.str[:150]))

# %% [markdown]
# Coherencia con los histogramas: los OCR más largos son páginas impresas (cola derecha del histograma de caracteres) y los más cortos son manuscritos o fotos
# con poco texto; los clips más largos son entrevistas de Commons y los más cortos, entrevistas breves de calle.

# %% [markdown]
# ## 8. Exportación

# %%
DATOS = RAIZ / "datos"
documentos = ocr_df.assign(
    fuente=lambda d: "Wikimedia Commons (" + d.licencia + ") " + d.fuente_url,
    modelo_ocr=f"PaddleOCR {paddleocr.__version__} (PP-OCRv5 mobile det + latin rec, sin unwarping ni orientación)",
    texto_referencia="",
)[["id", "archivo", "tipo", "fuente", "texto_ocr", "modelo_ocr", "texto_referencia", "conf_ocr", "chars_ocr"]]

transcripciones = asr_df.assign(
    idioma="es (español peruano, según la fuente)",
    modelo_asr="faster-whisper small int8 (VAD Silero on, greedy) + diarización ECAPA",
    texto_referencia="",
    fuente=lambda d: d.fuente_corta + " (" + d.licencia + ")",
)[["id", "archivo", "duracion_seg", "idioma", "texto_asr", "modelo_asr", "n_hablantes", "texto_referencia", "fuente", "seg_proceso"]]
transcripciones = transcripciones.rename(columns={"archivo": "archivo_audio"})

fuentes = pd.concat([
    man_doc.assign(modalidad="documento", titulo_pagina=lambda d: [t if pd.isna(p) else f"{t} (p. {int(p)})" for t, p in zip(d.titulo, d.pagina)]),
    man_aud.assign(modalidad="audio", titulo_pagina=lambda d: d.titulo),
])[["id", "modalidad", "fuente_url", "licencia", "autor", "titulo_pagina"]]
fuentes["acceso"] = np.where(fuentes.fuente_url.str.contains("openslr"),
                             "HTTP Range sobre el zip de OpenSLR 73 con datos.py (hablante indicado en el título)",
                             "Descarga directa por la API de Commons con datos.py")
# Los títulos de algunas entrevistas incluyen nombres de entrevistados: se seudonimizan también aquí
fuentes["titulo_pagina"] = [voz.seudonimizar(t, nombres_privados, tabla, disparadores=False)[0] for t in fuentes.titulo_pagina]

documentos.to_csv(DATOS / "documentos.csv", index=False)
transcripciones.to_csv(DATOS / "transcripciones.csv", index=False)
fuentes.to_csv(DATOS / "fuentes.csv", index=False)
for nombre, df in [("documentos", documentos), ("transcripciones", transcripciones), ("fuentes", fuentes)]:
    print(nombre, df.shape)
display(documentos.head())
display(transcripciones.head())
