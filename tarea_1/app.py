import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

st.set_page_config(page_title="Clasificador de noticias – La República", layout="wide")
CARPETA = Path(__file__).parent


@st.cache_data
def cargar_datos():
    return pd.read_csv(CARPETA / "datos" / "noticias.csv")


@st.cache_data
def cargar_metricas():
    return json.loads((CARPETA / "modelo" / "metricas.json").read_text(encoding="utf-8"))


@st.cache_resource
def cargar_modelo():
    tok = AutoTokenizer.from_pretrained(CARPETA / "modelo")
    mod = AutoModelForSequenceClassification.from_pretrained(CARPETA / "modelo")
    mod.eval()
    return tok, mod


df = cargar_datos()
met = cargar_metricas()

st.title("¿Se pueden convertir titulares peruanos en un clasificador de noticias?")
st.markdown(
    "Recolecté titulares de **La República** (RSS, sitemaps y notas individuales), los etiqueté de forma "
    "débil con un LLM (Gemini) y audité 20 casos a mano. Luego hice fine-tuning de **DistilBERT multilingüe** "
    "en 4 categorías: política, economía, deportes y ciencia/tecnología."
)

st.sidebar.header("Filtros")
medios = st.sidebar.multiselect("Medio", sorted(df["medio"].unique()), default=sorted(df["medio"].unique()))
categorias = st.sidebar.multiselect("Categoría", sorted(df["etiqueta"].unique()),
                                    default=sorted(df["etiqueta"].unique()))
filtrado = df[df["medio"].isin(medios) & df["etiqueta"].isin(categorias)]

c1, c2, c3 = st.columns(3)
c1.metric("Noticias recolectadas", f"{len(df)}")
c2.metric("F1 macro en test", f"{met['f1_macro_test']:.2f}")
c3.metric("Acuerdo LLM vs humano", f"{met['acuerdo_llm_humano_pct']:.0%}")

conteo = filtrado["etiqueta"].value_counts().reset_index()
conteo.columns = ["categoria", "noticias"]
fig = px.bar(conteo, x="categoria", y="noticias", color="categoria", text="noticias",
             title=f"Distribución por categoría ({len(filtrado)} noticias filtradas)")
fig.update_layout(showlegend=False)
st.plotly_chart(fig, width="stretch")

st.subheader("Noticias")
st.dataframe(filtrado, width="stretch", hide_index=True)
st.download_button("Descargar CSV filtrado", filtrado.to_csv(index=False).encode("utf-8"),
                   file_name="noticias_filtradas.csv", mime="text/csv")

st.subheader("Clasificador en vivo")
titular = st.text_input("Escribe un titular", "Congreso aprueba moción de censura contra ministro del Interior")
if st.button("Clasificar"):
    if not titular.strip():
        st.warning("Escribe un titular primero.")
    else:
        tok, mod = cargar_modelo()
        with torch.no_grad():
            logits = mod(**tok(titular, return_tensors="pt", truncation=True, max_length=64)).logits
        probs = torch.softmax(logits, dim=-1)[0]
        idx = int(probs.argmax())
        st.success(f"Categoría: **{mod.config.id2label[idx]}** – probabilidad {probs[idx]:.1%}")
        tabla = pd.DataFrame({"categoria": [mod.config.id2label[i] for i in range(len(probs))],
                              "probabilidad": probs.numpy()})
        st.bar_chart(tabla, x="categoria", y="probabilidad")
