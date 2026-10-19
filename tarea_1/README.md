# Tarea 1 – Noticias peruanas: del titular al clasificador

**Estudiante:** Karen Macedo · **Medio:** La República (Opción A)

## 1. Pregunta del proyecto
¿Se pueden convertir titulares peruanos en un clasificador de noticias? Recolecté noticias de La República, las etiqueté de forma débil con un LLM (Gemini) y entrené un DistilBERT multilingüe que clasifica en `politica`, `economia`, `deportes` y `ciencia_tecnologia`.

| Modelo (test) | F1 macro |
| :-- | :-: |
| Zero-shot XNLI | [completar] |
| LLM débil (Gemini) | [completar] |
| **DistilBERT fine-tuned** | **[completar]** |

Acuerdo LLM–humano: [xx]/20.

## 2. Medio y fechas de extracción
- **Medio:** La República (`larepublica.pe`), [N] noticias (~100 por categoría).
- **Fecha de descarga:** [fecha]. Las noticias van de [fecha mínima] a [fecha máxima].
- **Fuentes:** RSS y sitemaps oficiales y, para completar, URLs antiguas listadas con Internet Archive y descargadas de `larepublica.pe`. Respeté `robots.txt`, usé un User-Agent descriptivo, pausas de 1–2 s y como máximo 1 reintento.

## 3. Hallazgos
1. El fine-tuning mejora mucho al zero-shot ([0.xx] vs [0.xx] de F1) con menos de 300 titulares de entrenamiento.
2. Deportes es la categoría más fácil por su vocabulario propio; la más difícil es [categoría], porque se mezcla con temas de [política/economía].

## 4. Limitaciones
1. Pocos datos y un solo medio: el test tiene ~60 noticias, así que un error cambia bastante el F1 de una categoría.
2. La etiqueta viene de la sección del diario, que no siempre coincide con el tema del titular (notas de frontera). Además, los pesos del modelo (~540 MB) no se suben a GitHub: se regeneran ejecutando `02_clasificacion.ipynb`.

## 5. Cómo ejecutar en local
```bash
cd tarea_1
python -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
# (opcional) regenerar datos y modelo: ejecutar 01_recoleccion.ipynb y 02_clasificacion.ipynb
streamlit run app.py
```
