# Tarea 2 – Voces y documentos peruanos: del archivo escaneado al texto buscable

**Dashboard público:** `https://<COMPLETAR>.streamlit.app` · **Estudiante:** <Nombre Completo> (@<usuario_github>)

## 1. Pregunta del proyecto

> ¿Pueden convertirse documentos escaneados y entrevistas en audio en un archivo de texto estructurado y buscable?

Construí un pipeline que (1) extrae texto de 25 documentos peruanos con **PaddleOCR**, (2) transcribe 39 minutos de audio en
español peruano con **faster-whisper** + VAD y diariza las entrevistas, (3) seudonimiza datos personales, (4) mide CER/WER
contra transcripciones de referencia en 10 documentos y 10 clips, (5) compara cada modelo con una alternativa
(**EasyOCR** y **wav2vec2-XLSR-53-español**) y (6) extrae campos JSON con un LLM local (**Qwen2.5-1.5B-Instruct**, llama.cpp),
auditando 20 extracciones a mano. El dashboard de Streamlit solo lee los CSV precalculados.

**Respuesta corta:** sí para impresos y audio de estudio; parcialmente para fotos y entrevistas de calle; no todavía para manuscritos
(ver hallazgos).

## 2. Corpus, fuentes y licencias (extracción: 25-oct-2026)

| Corpus | Contenido | Fuente | Licencias |
|---|---|---|---|
| A. Documentos (25) | 8 impresos (páginas de las Constituciones de 1828, 1856 y 1860 y del Código de Ética de la PNP de 1989), 8 fotos con sombra/reflejo/inclinación (Capitulación de Ayacucho en vitrina, placas y carteles de Trujillo, Lima y Huaca Las Balsas), 9 manuscritos (libros de bautismo de Lampa, partidas de 1792 y 1897, Acta de la Independencia, Estado General del Huáscar, recibo de 1895, diploma de 1921) | Wikimedia Commons (API) | Dominio público, CC0, CC BY 2.0, CC BY-SA 3.0/4.0 |
| B. Audio (24 clips, 39 min) | 10 entrevistas reales en la calle y en eventos (Lima, Áncash) registradas por estudiantes de la UNMSM, varias con 2+ hablantes; 14 clips de ~80 s de OpenSLR 73 (12 enunciados del mismo hablante concatenados, 7 voces femeninas y 7 masculinas) | Wikimedia Commons; OpenSLR 73 (Guevara-Rukoz et al., 2020) | CC BY-SA 4.0 |

El detalle por archivo (URL estable `?curid=`, autor, licencia y forma de recuperación) está en `datos/fuentes.csv`.
Los originales no se versionan (`datos/raw/` en `.gitignore`) y se recuperan con `uv run python datos.py`
(User-Agent descriptivo, 1,5 s entre solicitudes, reintentos ante HTTP 429; OpenSLR por HTTP Range sin bajar los zips de ~1 GB).

**Datos personales.** Se seudonimizan nombres de entrevistados (tomados de las descripciones de Commons), DNI, teléfonos y correos
(`voz.seudonimizar`), también en los títulos de `fuentes.csv`. No se seudonimizan figuras históricas públicas ni personas de registros
de más de un siglo de antigüedad. La tabla seudónimo↔nombre real queda solo en `datos/raw/`.

## 3. Resultados (muestra de evaluación: 10 documentos y 10 clips)

Muestra sorteada con semilla fija antes de correr los modelos alternativos: 4 impresos + 3 fotos + 3 manuscritos, y 10 clips de OpenSLR 73
(5 voces femeninas y 5 masculinas, con transcripción humana publicada). Las mismas muestras se usaron para todos los modelos.

| Modalidad | Modelo | Error | Impreso | Foto | Manuscrito | Costo (CPU 4 núcleos) |
|---|---|---|---|---|---|---|
| Documentos | **PaddleOCR 3.7 (PP-OCRv5 mobile, latin) – base y elegido** | **CER 0,35** | 0,22 | 0,32 | 0,54 | 59 s/doc |
| Documentos | EasyOCR 1.7 (es) – alternativo | CER 0,41 | 0,25 | 0,36 | 0,67 | 94 s/doc |
| Audio | **faster-whisper small int8 + VAD – base y elegido** | **WER 0,03** | | | | RTF 1,2 |
| Audio | wav2vec2-large-xlsr-53-spanish – alternativo | WER 0,23 | | | | RTF 2,5 |
| LLM | Qwen2.5-1.5B-Instruct Q4 (llama.cpp) | **4/20** extracciones completamente correctas (20 %) | | | | ~50 s/registro |

**Resultados Test: WER: 0.03 | CER: 0.35 | Acuerdo LLM-Humano: 4/20**

Decisión: PaddleOCR + faster-whisper `small`, porque ganan en error y en costo; el LLM de 1,5B solo sirve como borrador con revisión humana
(detalle y reflexión por tipo en `02_evaluacion.ipynb`, sección 9).

## 4. Hallazgos

1. **El tipo de documento importa más que el modelo.** Con PaddleOCR, las páginas impresas de texto corrido tienen un CER ≈ 0,01. En manuscritos
   el CER sube a 0,34–0,81 y en fotos de carteles a 0,59, porque el OCR lee por líneas atravesando las dos columnas (español/inglés) y
   altera el orden. Cambiar de modelo (EasyOCR) empeora todos los tipos: el cuello de botella es la fuente, no el OCR elegido. El texto
   impreso ya es *buscable*; los manuscritos todavía no.
2. **La transcripción es buena; la estructuración con un LLM pequeño, no.** faster-whisper comete 7 veces menos errores que wav2vec2 en los
   mismos clips (0,03 vs 0,23), pero el LLM de 1,5B solo acertó por completo en 4 de 20 extracciones. Sus errores se concentran en
   **inventar datos** cuando el texto de entrada es ruido OCR (fechas como "2023" o "1591", una "República del Darien") y en **campos mal
   asignados** (número de página como fecha, más citas de las pedidas). La calidad del OCR/ASR se propaga a la extracción: 5 de los 8
   documentos fallidos tenían un OCR deficiente o vacío.

Otras observaciones: dos documentos descargados no servían (una pintura sin texto y la portada de un pasaporte impreso clasificada como
manuscrito) y se reemplazaron; dos fotos (doc_011 y doc_012) muestran la misma placa desde ángulos distintos.

## 5. Limitaciones técnicas

1. **La evaluación de audio no cubre el caso difícil.** Los 10 clips evaluados son de OpenSLR 73 (habla leída, micrófono limpio),
   porque son los únicos con transcripción humana publicada; además, es posible que Whisper haya visto ese corpus en su entrenamiento.
   El WER de ~0,03 **sobreestima** el desempeño en las entrevistas de calle de Commons, que tienen ruido, solapamientos y voces lejanas
   (allí se observan palabras inventadas como "marchinga" o "Cesis Aspeológicas") y no tienen referencia para medirlas.
2. **Referencias y diarización con poca validación.** Las referencias de documentos son de un solo transcriptor, sin doble anotación; en el
   Acta de la Independencia (doc_026) se desarrollaron las abreviaturas siguiendo la transcripción publicada, lo que infla el CER de ambos OCR.
   La diarización ECAPA + clustering sobresegmenta en audio de calle (varias entrevistas llegan al tope de 4 hablantes) y no hay
   referencia de turnos para medirla, así que `n_hablantes` es una cota superior. Los tiempos (s/documento, RTF) se midieron con
   varios procesos compitiendo por los 4 núcleos de la laptop, por lo que solo sirven como comparación relativa.

## 6. Ejecutar en local

Dashboard (solo lee CSV):

```bash
pip install -r requirements.txt
streamlit run app.py
```

Reproducir los notebooks (CPU, Windows/Linux, Python 3.11):

```bash
uv sync                      # entorno completo: PaddleOCR, faster-whisper, EasyOCR, transformers, llama-cpp-python
uv run python datos.py       # descarga documentos y audio a datos/raw/
uv run jupyter nbconvert --to notebook --execute --inplace 01_extraccion.ipynb
uv run jupyter nbconvert --to notebook --execute --inplace 02_evaluacion.ipynb
uv run python scripts/preparar_ejemplos.py .
```

El LLM se descarga de `https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF` (`qwen2.5-1.5b-instruct-q4_k_m.gguf`) a `modelos/`.
En Windows: importar `torch` antes que `paddle` (conflicto de DLL), desactivar oneDNN en PaddleOCR (`enable_mkldnn=False`) y usar
torch 2.5.1 CPU + transformers 4.46.

## 7. Estructura

```
tarea_2/
├── 01_extraccion.ipynb        # OCR, ASR + diarización, seudonimización, limpieza, EDA, exportación
├── 02_evaluacion.ipynb        # muestra de evaluación, CER/WER, modelos alternativos, LLM, auditoría, decisión
├── app.py                     # dashboard Streamlit
├── datos.py                   # descarga reproducible de los corpus
├── voz.py                     # ASR, VAD, diarización, exportación SRT/TXT, seudonimización, normalización
├── scripts/                   # precálculo de OCR/ASR (mismo código que los notebooks) y ejemplos ligeros
├── notebooks_src/             # fuente .py (jupytext) de los notebooks
├── datos/
│   ├── documentos.csv · transcripciones.csv · extraccion_llm.csv · fuentes.csv
│   ├── referencias_documentos.json · auditoria_llm.csv · comparacion_ocr.csv · comparacion_asr.csv · metricas.json
│   └── ejemplos/              # imágenes y MP3 publicables
├── evidencias_ia/             # capturas de la conversación con el asistente de IA
└── modelos/                   # (pesos ignorados por Git)
```
