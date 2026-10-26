"""Dashboard Tarea 2 — Voces y documentos peruanos: del archivo escaneado al texto buscable.

Solo lee los CSV y ejemplos ligeros generados en los notebooks (no ejecuta OCR, ASR ni LLM en vivo).
"""
import json
import re
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

RAIZ = Path(__file__).parent
DATOS = RAIZ / "datos"
EJ = DATOS / "ejemplos"

st.set_page_config(page_title="Voces y documentos peruanos", page_icon="🎙️", layout="wide")


@st.cache_data
def cargar():
    docs = pd.read_csv(DATOS / "documentos.csv")
    aud = pd.read_csv(DATOS / "transcripciones.csv")
    llm = pd.read_csv(DATOS / "extraccion_llm.csv")
    fuentes = pd.read_csv(DATOS / "fuentes.csv")
    met = json.loads((DATOS / "metricas.json").read_text(encoding="utf-8"))
    comp_doc = pd.read_csv(DATOS / "comparacion_ocr.csv")
    comp_aud = pd.read_csv(DATOS / "comparacion_asr.csv")
    return docs, aud, llm, fuentes, met, comp_doc, comp_aud


docs, aud, llm, fuentes, met, comp_doc, comp_aud = cargar()
llm_campos = {r.id: json.loads(r.campos_json) for r in llm.itertuples()}

# ------------------------------------------------------------------ Encabezado
st.title("¿Pueden los documentos escaneados y las entrevistas en audio volverse texto estructurado y buscable?")
st.markdown(
    "Pipeline sobre **25 documentos peruanos** (impresos, fotos y manuscritos de Wikimedia Commons) y "
    f"**{aud.duracion_seg.sum() / 60:.0f} minutos de audio** en español peruano (entrevistas de Commons y OpenSLR 73): "
    "OCR con PaddleOCR, ASR con faster-whisper + VAD y diarización, seudonimización, evaluación CER/WER sobre "
    "10 documentos y 10 clips con referencia manual, y extracción de campos JSON con un LLM local auditado a mano. "
    "Todo se calculó previamente en los notebooks; esta app solo explora los resultados."
)

# ------------------------------------------------------------------ Barra lateral
st.sidebar.header("Filtros")
busqueda = st.sidebar.text_input("Buscar palabra en textos OCR/ASR", "")
tipos = st.sidebar.multiselect("Tipo de documento", sorted(docs.tipo.unique()), default=sorted(docs.tipo.unique()))
modelos_doc = sorted(comp_doc.modelo.unique(), key=lambda m: "(base)" not in m)  # el modelo base primero
modelo_doc = st.sidebar.selectbox("Modelo OCR para métricas", modelos_doc)
modelos_aud = sorted(comp_aud.modelo.unique(), key=lambda m: "(base)" not in m)
modelo_aud = st.sidebar.selectbox("Modelo ASR para métricas", modelos_aud)
fuentes_aud = st.sidebar.multiselect("Fuente de audio", sorted(aud.fuente.unique()), default=sorted(aud.fuente.unique()))
dmin, dmax = float(aud.duracion_seg.min()), float(aud.duracion_seg.max())
rango = st.sidebar.slider("Duración del clip (s)", dmin, dmax, (dmin, dmax))

d_f = docs[docs.tipo.isin(tipos)]
a_f = aud[aud.fuente.isin(fuentes_aud) & aud.duracion_seg.between(*rango)]
if busqueda:
    d_f = d_f[d_f.texto_ocr.fillna("").str.contains(busqueda, case=False, regex=False)]
    a_f = a_f[a_f.texto_asr.fillna("").str.contains(busqueda, case=False, regex=False)]

# ------------------------------------------------------------------ KPIs
c = st.columns(5)
c[0].metric("Documentos procesados", f"{len(d_f)} / {len(docs)}")
c[1].metric("Minutos de audio transcritos", f"{a_f.duracion_seg.sum() / 60:.1f}")
cer = comp_doc[comp_doc.modelo == modelo_doc].cer.mean()
wer = comp_aud[comp_aud.modelo == modelo_aud].wer.mean()
c[2].metric(f"CER · {modelo_doc}", f"{cer:.2f}", help="Media sobre los 10 documentos de evaluación")
c[3].metric(f"WER · {modelo_aud}", f"{wer:.2f}", help="Media sobre los 10 clips de evaluación")
c[4].metric("Acuerdo LLM vs. auditoría humana", f"{met['auditoria_ok']}/{met['auditoria_n']}",
            f"{100 * met['auditoria_ok'] / met['auditoria_n']:.0f} %", delta_color="off")

tab_res, tab_doc, tab_aud, tab_datos = st.tabs(["📊 Resultados", "📄 Documentos", "🎧 Audios", "🗂️ Datos y fuentes"])

# ------------------------------------------------------------------ Resultados
with tab_res:
    g1, g2 = st.columns(2)
    cd = comp_doc[comp_doc.tipo.isin(tipos)]
    fig = px.box(cd, x="tipo", y="cer", color="modelo", points="all",
                 title="El CER se dispara en manuscritos para ambos OCR", labels={"cer": "CER"})
    g1.plotly_chart(fig, use_container_width=True)
    ca = comp_aud.merge(aud[["id", "fuente"]], on="id")
    fig = px.bar(ca, x="id", y="wer", color="modelo", barmode="group",
                 title="WER por clip de evaluación y modelo ASR", labels={"wer": "WER"})
    g2.plotly_chart(fig, use_container_width=True)
    g3, g4 = st.columns(2)
    fig = px.histogram(d_f, x="tipo", color="tipo", title="Documentos filtrados por tipo")
    g3.plotly_chart(fig, use_container_width=True)
    fig = px.histogram(a_f, x="duracion_seg", color="fuente", nbins=20,
                       title="Distribución de duración de los clips filtrados", labels={"duracion_seg": "segundos"})
    g4.plotly_chart(fig, use_container_width=True)
    st.subheader("Tabla comparativa de modelos")
    st.dataframe(pd.DataFrame(met["tabla_comparativa"]), use_container_width=True, hide_index=True)

# ------------------------------------------------------------------ Documentos
with tab_doc:
    if d_f.empty:
        st.info("Ningún documento coincide con los filtros.")
    else:
        sel = st.selectbox("Documento", d_f.id, format_func=lambda i: f"{i} · {docs.set_index('id').tipo[i]}")
        r = docs.set_index("id").loc[sel]
        izq, der = st.columns([1, 1])
        img = EJ / f"{sel}.jpg"
        if img.exists():
            izq.image(str(img), caption=r.fuente, use_container_width=True)
        else:
            izq.caption(f"Imagen no incluida en el repositorio. Fuente: {r.fuente}")
        der.markdown(f"**Tipo:** {r.tipo} · **Modelo:** {r.modelo_ocr} · **Confianza media:** {r.conf_ocr}")
        der.text_area("Texto OCR (seudonimizado)", r.texto_ocr if isinstance(r.texto_ocr, str) else "", height=220)
        if isinstance(r.texto_referencia, str) and r.texto_referencia.strip():
            der.text_area("Texto de referencia (transcripción manual)", r.texto_referencia, height=160)
            filas = comp_doc[comp_doc.id == sel][["modelo", "cer"]]
            der.dataframe(filas, hide_index=True)
        st.markdown("**Campos estructurados extraídos por el LLM**")
        st.json(llm_campos.get(sel, {}))

# ------------------------------------------------------------------ Audios
with tab_aud:
    if a_f.empty:
        st.info("Ningún audio coincide con los filtros.")
    else:
        sel = st.selectbox("Clip", a_f.id, format_func=lambda i: f"{i} · {aud.set_index('id').fuente[i]}")
        r = aud.set_index("id").loc[sel]
        st.markdown(f"**Duración:** {r.duracion_seg:.0f} s · **Hablantes detectados:** {r.n_hablantes} · **Modelo:** {r.modelo_asr}")
        mp3 = EJ / f"{sel}.mp3"
        if mp3.exists():
            st.audio(str(mp3))
        else:
            st.caption("Audio no incluido en el repositorio (consultar `datos/fuentes.csv` para recuperarlo).")
        texto = r.texto_asr if isinstance(r.texto_asr, str) else ""
        st.markdown(re.sub(r"\[(HABLANTE_\d+)\]", r"\n\n**[\1]**", texto))
        if isinstance(r.texto_referencia, str) and r.texto_referencia.strip():
            st.markdown("**Comparación en la muestra de evaluación**")
            comp = comp_aud[comp_aud.id == sel][["modelo", "wer", "rtf", "hipotesis"]]
            st.dataframe(comp, hide_index=True, use_container_width=True)
            st.text_area("Referencia manual", r.texto_referencia, height=120)
        st.markdown("**Campos estructurados extraídos por el LLM**")
        st.json(llm_campos.get(sel, {}))

# ------------------------------------------------------------------ Datos
with tab_datos:
    st.subheader("Documentos (texto revisado y seudonimizado)")
    cols_d = ["id", "tipo", "fuente", "modelo_ocr", "texto_ocr", "texto_referencia"]
    st.dataframe(d_f[cols_d], use_container_width=True, hide_index=True)
    st.download_button("Descargar documentos filtrados (CSV)", d_f[cols_d].to_csv(index=False).encode("utf-8"),
                       "documentos_filtrados.csv", "text/csv")
    st.subheader("Transcripciones")
    cols_a = ["id", "fuente", "duracion_seg", "n_hablantes", "modelo_asr", "texto_asr", "texto_referencia"]
    st.dataframe(a_f[cols_a], use_container_width=True, hide_index=True)
    st.download_button("Descargar transcripciones filtradas (CSV)", a_f[cols_a].to_csv(index=False).encode("utf-8"),
                       "transcripciones_filtradas.csv", "text/csv")
    st.subheader("Fuentes y licencias")
    st.dataframe(fuentes, use_container_width=True, hide_index=True)
