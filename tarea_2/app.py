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

st.set_page_config(page_title="Voces y documentos peruanos", page_icon="🦙", layout="wide")

# Paleta inspirada en textiles andinos: turquesa, magenta, ocre y terracota
TURQUESA, MAGENTA, OCRE, TERRACOTA, NOCHE = "#0f9d9a", "#c2185b", "#f2a900", "#d9480f", "#1b1f3b"
PALETA = [TURQUESA, MAGENTA, OCRE, TERRACOTA, "#5c6bc0", "#43a047"]
COLOR_TIPO = {"impreso": TURQUESA, "foto": OCRE, "manuscrito": MAGENTA}

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:wght@600;800&family=Nunito:wght@400;600;800&display=swap');
html, body, [class*="css"], .stMarkdown, p, label {{ font-family: 'Nunito', sans-serif; }}
.stApp {{ background: linear-gradient(180deg, #fff8ef 0%, #fdf1f5 100%); }}
section[data-testid="stSidebar"] {{ background: linear-gradient(200deg, {NOCHE} 0%, #3a1c4f 60%, #7a1f4b 100%); }}
section[data-testid="stSidebar"] * {{ color: #fff7e6 !important; }}
section[data-testid="stSidebar"] input {{ color: {NOCHE} !important; }}
section[data-testid="stSidebar"] span[data-baseweb="tag"] {{ background-color: {OCRE} !important; border-radius: 999px !important; }}
section[data-testid="stSidebar"] [data-baseweb="tag"] * {{ color: {NOCHE} !important; font-weight: 800; }}
.franja {{ height: 10px; border-radius: 6px; margin: 4px 0 18px 0;
  background: repeating-linear-gradient(90deg, {TURQUESA} 0 40px, {OCRE} 40px 80px, {MAGENTA} 80px 120px, {TERRACOTA} 120px 160px); }}
.hero {{ background: linear-gradient(120deg, {TURQUESA} 0%, #116a8c 45%, {MAGENTA} 100%); color: white;
  padding: 34px 38px; border-radius: 26px; box-shadow: 0 14px 34px rgba(194,24,91,.25); }}
.hero h1 {{ font-family: 'Fraunces', serif; font-size: 2.5rem; line-height: 1.15; margin: 0 0 12px 0; color: white; }}
.hero p {{ font-size: 1.05rem; opacity: .95; margin: 0; }}
.chips {{ margin-top: 16px; }}
.chip {{ display: inline-block; background: rgba(255,255,255,.18); border: 1px solid rgba(255,255,255,.45);
  padding: 6px 14px; border-radius: 999px; margin: 4px 6px 0 0; font-weight: 800; font-size: .9rem; }}
.kpi {{ background: white; border-radius: 20px; padding: 16px 18px; box-shadow: 0 8px 22px rgba(27,31,59,.08);
  border-top: 6px solid var(--c); height: 100%; }}
.kpi .t {{ font-size: .85rem; color: #6b6f86; font-weight: 800; text-transform: uppercase; letter-spacing: .04em; }}
.kpi .v {{ font-family: 'Fraunces', serif; font-size: 2.1rem; color: {NOCHE}; margin-top: 4px; }}
.kpi .s {{ font-size: .85rem; color: var(--c); font-weight: 800; }}
.stTabs [data-baseweb="tab"] {{ background: white; border-radius: 999px; padding: 8px 18px; margin-right: 8px;
  box-shadow: 0 4px 12px rgba(27,31,59,.08); font-weight: 800; }}
.stTabs [aria-selected="true"] {{ background: {MAGENTA} !important; color: white !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}
.tarjeta {{ background: white; border-radius: 18px; padding: 16px 20px; box-shadow: 0 6px 18px rgba(27,31,59,.07); margin-bottom: 12px; }}
.etq {{ display: inline-block; padding: 3px 12px; border-radius: 999px; color: white; font-weight: 800; font-size: .8rem; margin-right: 6px; }}
.hablante {{ display: inline-block; padding: 2px 10px; border-radius: 8px; color: white; font-weight: 800; font-size: .8rem; margin-right: 6px; }}
h2, h3 {{ font-family: 'Fraunces', serif; color: {NOCHE}; }}
</style>
""", unsafe_allow_html=True)


@st.cache_data
def cargar():
    docs = pd.read_csv(DATOS / "documentos.csv")
    aud = pd.read_csv(DATOS / "transcripciones.csv")
    llm = pd.read_csv(DATOS / "extraccion_llm.csv")
    fuentes = pd.read_csv(DATOS / "fuentes.csv")
    met = json.loads((DATOS / "metricas.json").read_text(encoding="utf-8"))
    comp_doc = pd.read_csv(DATOS / "comparacion_ocr.csv")
    comp_aud = pd.read_csv(DATOS / "comparacion_asr.csv")
    auditoria = pd.read_csv(DATOS / "auditoria_llm.csv")
    return docs, aud, llm, fuentes, met, comp_doc, comp_aud, auditoria


docs, aud, llm, fuentes, met, comp_doc, comp_aud, auditoria = cargar()
llm_campos = {r.id: json.loads(r.campos_json) for r in llm.itertuples()}
aud["fuente_corta"] = aud.fuente.str.replace(r"\s*\(.*\)", "", regex=True)
docs["en_muestra"] = docs.texto_referencia.fillna("").str.strip() != ""
aud["en_muestra"] = aud.texto_referencia.fillna("").str.strip() != ""


def tema(i):
    t = llm_campos.get(i, {}).get("tema")
    return t if isinstance(t, str) else ""


# ------------------------------------------------------------------ Encabezado
st.markdown(f"""
<div class="hero">
  <h1>¿Pueden los documentos escaneados y las entrevistas en audio volverse texto estructurado y buscable?</h1>
  <p>Un pipeline con modelos abiertos lee documentos peruanos con <b>PaddleOCR</b>, transcribe voces con
  <b>faster-whisper</b> + VAD y diarización, seudonimiza datos personales, mide CER/WER contra transcripciones de
  referencia y cataloga cada registro con un LLM local auditado a mano. Todo se calculó en los notebooks:
  aquí solo se exploran los resultados.</p>
  <div class="chips">
    <span class="chip">📄 {len(docs)} documentos</span>
    <span class="chip">🎙️ {aud.duracion_seg.sum() / 60:.0f} min de audio</span>
    <span class="chip">🧪 4 modelos comparados</span>
    <span class="chip">✅ 20 extracciones auditadas</span>
  </div>
</div>
<div class="franja"></div>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------ Barra lateral
st.sidebar.markdown("## 🦙 Voces & Documentos")
st.sidebar.caption("Archivo peruano · OCR + ASR + LLM")
busqueda = st.sidebar.text_input("🔎 Buscar en textos OCR y ASR", placeholder="ej. Lima, Congreso, partido")
tipos = st.sidebar.multiselect("📄 Tipo de documento", ["impreso", "foto", "manuscrito"],
                               default=["impreso", "foto", "manuscrito"])
modelos = st.sidebar.multiselect("🧠 Modelos a comparar",
                                 list(comp_doc.modelo.unique()) + list(comp_aud.modelo.unique()),
                                 default=list(comp_doc.modelo.unique()) + list(comp_aud.modelo.unique()))
fuentes_aud = st.sidebar.multiselect("🎧 Fuente del audio", sorted(aud.fuente_corta.unique()),
                                     default=sorted(aud.fuente_corta.unique()))
hmin, hmax = int(aud.n_hablantes.min()), int(aud.n_hablantes.max())
hablantes = st.sidebar.slider("🗣️ Hablantes detectados", hmin, hmax, (hmin, hmax))
dmin, dmax = float(aud.duracion_seg.min()), float(aud.duracion_seg.max())
rango = st.sidebar.slider("⏱️ Duración del clip (s)", dmin, dmax, (dmin, dmax))
solo_muestra = st.sidebar.toggle("🎯 Solo la muestra de evaluación (10 + 10)", value=False)

d_f = docs[docs.tipo.isin(tipos)]
a_f = aud[aud.fuente_corta.isin(fuentes_aud) & aud.duracion_seg.between(*rango) & aud.n_hablantes.between(*hablantes)]
if solo_muestra:
    d_f, a_f = d_f[d_f.en_muestra], a_f[a_f.en_muestra]
if busqueda:
    d_f = d_f[d_f.texto_ocr.fillna("").str.contains(busqueda, case=False, regex=False)]
    a_f = a_f[a_f.texto_asr.fillna("").str.contains(busqueda, case=False, regex=False)]
cd = comp_doc[comp_doc.modelo.isin(modelos) & comp_doc.tipo.isin(tipos)]
ca = comp_aud[comp_aud.modelo.isin(modelos)]

# ------------------------------------------------------------------ KPIs
mejor_cer = cd.groupby("modelo").cer.mean().min() if not cd.empty else float("nan")
mejor_wer = ca.groupby("modelo").wer.mean().min() if not ca.empty else float("nan")
kpis = [
    ("Documentos", f"{len(d_f)}", f"de {len(docs)} en el corpus", TURQUESA),
    ("Minutos de audio", f"{a_f.duracion_seg.sum() / 60:.1f}", f"{len(a_f)} clips filtrados", OCRE),
    ("Mejor CER", f"{mejor_cer:.0%}" if pd.notna(mejor_cer) else "—", "10 documentos de evaluación", MAGENTA),
    ("Mejor WER", f"{mejor_wer:.0%}" if pd.notna(mejor_wer) else "—", "10 clips de evaluación", TERRACOTA),
    ("Auditoría LLM", f"{met['auditoria_ok']}/{met['auditoria_n']}",
     f"{100 * met['auditoria_ok'] / met['auditoria_n']:.0f} % completamente correctas", "#5c6bc0"),
]
for col, (t, v, s, c) in zip(st.columns(5), kpis):
    col.markdown(f'<div class="kpi" style="--c:{c}"><div class="t">{t}</div><div class="v">{v}</div>'
                 f'<div class="s">{s}</div></div>', unsafe_allow_html=True)
st.write("")


def estilo(fig, titulo, sub):
    fig.update_layout(title=dict(text=f"<b>{titulo}</b><br><sup>{sub}</sup>", font=dict(family="Fraunces", size=18)),
                      paper_bgcolor="white", plot_bgcolor="white", margin=dict(t=80, l=20, r=20, b=20),
                      font=dict(family="Nunito"), legend_title_text="")
    return fig


tab_res, tab_doc, tab_aud, tab_llm, tab_datos = st.tabs(
    ["📊 Resultados", "📜 Documentos", "🎧 Audios", "🤖 Auditoría LLM", "🗂️ Datos y fuentes"])

# ------------------------------------------------------------------ Resultados
with tab_res:
    g1, g2 = st.columns(2)
    fig = px.box(cd, x="tipo", y="cer", color="modelo", points="all", color_discrete_sequence=PALETA,
                 category_orders={"tipo": ["impreso", "foto", "manuscrito"]})
    g1.plotly_chart(estilo(fig, "El CER se dispara en manuscritos", "Error por carácter, menor es mejor"),
                    use_container_width=True)
    fig = px.bar(ca, x="id", y="wer", color="modelo", barmode="group", color_discrete_sequence=[TURQUESA, MAGENTA])
    g2.plotly_chart(estilo(fig, "faster-whisper gana en casi todos los clips", "Error por palabra en los 10 clips"),
                    use_container_width=True)
    g3, g4 = st.columns(2)
    conteo = d_f.tipo.value_counts().rename_axis("tipo").reset_index(name="n")
    fig = px.pie(conteo, names="tipo", values="n", hole=.55, color="tipo", color_discrete_map=COLOR_TIPO)
    g3.plotly_chart(estilo(fig, "Tres tipos de documentos peruanos", "Documentos que cumplen los filtros"),
                    use_container_width=True)
    fig = px.bar(a_f.sort_values("duracion_seg"), x="duracion_seg", y="id", orientation="h", color="fuente_corta",
                 color_discrete_sequence=[OCRE, TURQUESA], labels={"duracion_seg": "segundos", "id": ""})
    fig.update_layout(height=520)
    g4.plotly_chart(estilo(fig, "Minutos por clip", "Entrevistas de calle vs. habla leída de OpenSLR"),
                    use_container_width=True)
    st.markdown("### 🧪 Tabla comparativa de modelos")
    tabla = pd.DataFrame(met["tabla_comparativa"])
    st.dataframe(tabla[tabla.modelo.isin(modelos)], use_container_width=True, hide_index=True)

# ------------------------------------------------------------------ Documentos
with tab_doc:
    if d_f.empty:
        st.info("Ningún documento coincide con los filtros.")
    else:
        sel = st.selectbox("Elige un documento", d_f.id,
                           format_func=lambda i: f"{i} · {docs.set_index('id').tipo[i]} · {tema(i)[:50]}")
        r = docs.set_index("id").loc[sel]
        st.markdown(f'<span class="etq" style="background:{COLOR_TIPO[r.tipo]}">{r.tipo}</span>'
                    f'<span class="etq" style="background:{NOCHE}">confianza OCR {r.conf_ocr:.2f}</span>'
                    + (f'<span class="etq" style="background:{MAGENTA}">muestra de evaluación</span>' if r.en_muestra else ""),
                    unsafe_allow_html=True)
        izq, der = st.columns([1, 1.2])
        img = EJ / f"{sel}.jpg"
        if img.exists():
            izq.image(str(img), caption=r.fuente, use_container_width=True)
        else:
            izq.info(f"Imagen no publicada (contiene datos personales o no es redistribuible). Fuente: {r.fuente}")
        der.text_area("Texto OCR (seudonimizado)", r.texto_ocr if isinstance(r.texto_ocr, str) else "", height=230)
        if r.en_muestra:
            der.text_area("Transcripción de referencia", r.texto_referencia, height=150)
            m = comp_doc[comp_doc.id == sel][["modelo", "cer"]]
            for c, fila in zip(der.columns(len(m)), m.itertuples()):
                c.metric(fila.modelo, f"CER {fila.cer:.2f}")
        st.markdown("#### 🤖 Campos estructurados extraídos por el LLM")
        st.json(llm_campos.get(sel, {}))

# ------------------------------------------------------------------ Audios
COLOR_H = [TURQUESA, MAGENTA, OCRE, TERRACOTA]
with tab_aud:
    if a_f.empty:
        st.info("Ningún audio coincide con los filtros.")
    else:
        sel = st.selectbox("Elige un clip", a_f.id,
                           format_func=lambda i: f"{i} · {aud.set_index('id').fuente_corta[i]} · {tema(i)[:50]}")
        r = aud.set_index("id").loc[sel]
        st.markdown(f'<span class="etq" style="background:{OCRE}">{r.fuente_corta}</span>'
                    f'<span class="etq" style="background:{NOCHE}">{r.duracion_seg:.0f} s</span>'
                    f'<span class="etq" style="background:{TURQUESA}">{int(r.n_hablantes)} hablante(s)</span>',
                    unsafe_allow_html=True)
        mp3 = EJ / f"{sel}.mp3"
        if mp3.exists():
            st.audio(str(mp3))
        else:
            st.caption("🔒 Audio no publicado en el repositorio: consulta `datos/fuentes.csv` para recuperarlo.")
        texto = r.texto_asr if isinstance(r.texto_asr, str) else ""
        html = re.sub(r"\[HABLANTE_(\d+)\]",
                      lambda m: f'<br><span class="hablante" style="background:{COLOR_H[(int(m.group(1)) - 1) % 4]}">'
                                f'Hablante {m.group(1)}</span>', texto)
        st.markdown(f'<div class="tarjeta">{html}</div>', unsafe_allow_html=True)
        if r.en_muestra:
            st.markdown("#### ⚖️ Comparación de modelos en este clip")
            comp = comp_aud[comp_aud.id == sel][["modelo", "wer", "rtf", "hipotesis"]]
            st.dataframe(comp, hide_index=True, use_container_width=True)
            st.text_area("Transcripción de referencia (OpenSLR 73)", r.texto_referencia, height=110)
        st.markdown("#### 🤖 Campos estructurados extraídos por el LLM")
        st.json(llm_campos.get(sel, {}))

# ------------------------------------------------------------------ Auditoría LLM
with tab_llm:
    c1, c2 = st.columns([1, 1.4])
    err = auditoria.assign(resultado=auditoria.correcto.map({True: "correcta", False: "con error"}))
    fig = px.sunburst(err, path=["modalidad", "resultado"], color="resultado",
                      color_discrete_map={"correcta": TURQUESA, "con error": MAGENTA, "(?)": OCRE})
    c1.plotly_chart(estilo(fig, f"{met['auditoria_ok']} de 20 extracciones correctas", "Auditoría manual por modalidad"),
                    use_container_width=True)
    tipos_err = auditoria[~auditoria.correcto].tipo_error.value_counts().rename_axis("tipo").reset_index(name="n")
    fig = px.bar(tipos_err, x="n", y="tipo", orientation="h", color="tipo", color_discrete_sequence=PALETA)
    fig.update_layout(showlegend=False)
    c2.plotly_chart(estilo(fig, "¿Cómo se equivoca el LLM?", "Tipos de error en las extracciones incorrectas"),
                    use_container_width=True)
    st.dataframe(auditoria, use_container_width=True, hide_index=True)

# ------------------------------------------------------------------ Datos
with tab_datos:
    st.markdown("### 📜 Documentos (texto revisado y seudonimizado)")
    cols_d = ["id", "tipo", "fuente", "modelo_ocr", "texto_ocr", "texto_referencia"]
    st.dataframe(d_f[cols_d], use_container_width=True, hide_index=True)
    st.download_button("⬇️ Descargar documentos filtrados (CSV)", d_f[cols_d].to_csv(index=False).encode("utf-8"),
                       "documentos_filtrados.csv", "text/csv")
    st.markdown("### 🎧 Transcripciones")
    cols_a = ["id", "fuente", "duracion_seg", "n_hablantes", "modelo_asr", "texto_asr", "texto_referencia"]
    st.dataframe(a_f[cols_a], use_container_width=True, hide_index=True)
    st.download_button("⬇️ Descargar transcripciones filtradas (CSV)", a_f[cols_a].to_csv(index=False).encode("utf-8"),
                       "transcripciones_filtradas.csv", "text/csv")
    st.markdown("### 🔖 Fuentes y licencias")
    st.dataframe(fuentes, use_container_width=True, hide_index=True)
