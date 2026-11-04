# Tarea 3 – El boom agroexportador del Perú, 2010–2025

**Pregunta de investigación:** ¿qué productos y qué mercados explican el crecimiento de la agroexportación peruana entre 2010 y 2025, y ese crecimiento vino de vender *más* (volumen) o de vender *más caro* (precio)?

- 📊 **Dashboard público:** https://karivanne2-a11y.github.io/Python-Tareas/tarea_3/web/
- 🎬 **Reel:** [`reel/reel.mp4`](reel/reel.mp4)
- 💼 **Publicación de LinkedIn:** _(enlace pendiente)_

## Descripción

El proyecto sigue nueve productos emblemáticos de la agroexportación peruana: palta, arándano, uva fresca, espárrago fresco, mango, café verde, cítricos, cacao en grano y quinua. Para cada uno mide el valor exportado, el volumen, el precio implícito por kilo y los países de destino. El dashboard permite filtrar por producto, rango de años e indicador. Además separa el crecimiento del valor en un efecto volumen y un efecto precio, y muestra en un mapa a dónde va cada producto.

## Datos y metodología

| Fuente | Qué se usó | Acceso |
|---|---|---|
| UN Comtrade | Exportaciones anuales del Perú (reporter 604) por código HS y país de destino, 2010–2025. También el total por capítulo HS. | API pública *preview*, sin clave: https://comtradeplus.un.org/ |
| BCRP | Serie PN38714BM, exportaciones FOB mensuales (millones US$), usada para contrastar el total | https://estadisticas.bcrp.gob.pe/estadisticas/series/ |

Los datos se consultaron el 4 de noviembre de 2026. Los archivos crudos están en `datos/originales/`.

**Procesamiento** (`scripts/procesar_datos.py`):
- Se usan solo los registros agregados de Comtrade (todos los medios de transporte y regímenes) y se eliminan duplicados por año, producto y destino.
- **Precio implícito** = valor FOB / peso neto (US$/kg). En los años en que el total mundial venía sin peso (por ejemplo, 2015), se usó la suma del peso por destino.
- Los países se identifican con su código ISO3 para el mapa, y se descartan las agrupaciones regionales.
- **Peso del agro** = suma de los capítulos HS 01–24 dividida entre el total exportado.

**Análisis** (`scripts/analizar_datos.py`):
- **Descomposición volumen/precio**, 2015–2025: crecimiento del valor = crecimiento del volumen × crecimiento del precio.
- **Concentración de destinos:** índice Herfindahl-Hirschman, HHI = Σ cuota² × 10 000.
- Todas las cifras de los hallazgos quedan en `datos/procesados/hallazgos.json`.

## Tres hallazgos principales

1. **El arándano pasó de casi cero a ser el primer producto.** En 2012 se exportaron US$ 0,5 millones; en 2025, US$ 2455 millones, más que la uva (US$ 1960 M) y la palta (US$ 1363 M). Entre los tres pasaron del 17 % al 59 % de la canasta, que se multiplicó por 6: de US$ 1632 M en 2010 a US$ 9827 M en 2025.
2. **Las frutas crecieron por volumen; el cacao y el café, por precio.** Entre 2015 y 2025:
   - El arándano multiplicó su volumen por 36 mientras su precio por kilo bajó 30 %.
   - La palta creció 338 % en toneladas con un precio casi igual (+2 %).
   - El cacao subió su valor 159 % con el mismo volumen (+3 %), porque su precio aumentó 153 %.
   - En el café, el precio (+124 %) explica tres cuartas partes del alza.
3. **Dos mercados compran más de la mitad.** En 2025, Estados Unidos (38 %) y Países Bajos (17 %) compraron el 55 % de estos productos, frente al 51 % de 2015. El HHI de destinos es ≈ 1881 (concentración moderada), aunque los envíos llegan a 97 países.

Además, el peso del agro (capítulos HS 01–24) en las exportaciones totales del Perú subió del 16 % en 2010 al 21 % en 2025.

![Dashboard: KPIs y evolución](web/assets/captura_1.jpg)
![Dashboard: mapa de destinos](web/assets/captura_2.jpg)

## Limitaciones

- **Comtrade frente al BCRP:** el total anual de Comtrade difiere de la cifra oficial del BCRP entre −12 % y +12 % según el año, por diferencias de registro y revisiones. Las tendencias son robustas; los niveles exactos deben leerse con cautela.
- **Datos de 2025:** son los primeros que reportó el país y pueden revisarse.
- **Quinua:** tiene código HS propio solo desde 2012, así que su serie empieza ese año.
- **Cobertura:** son nueve productos, no todo el agro. Quedan fuera, por ejemplo, el banano, la páprika y los procesados.
- **Precio implícito:** es un promedio por kilo que mezcla calidades, presentaciones y meses.
- **Alcance:** el análisis es descriptivo y no identifica causas (clima, tratados comerciales, irrigación).

## Estructura

```
tarea_3/
├── README.md
├── pyproject.toml, requirements.txt
├── datos/
│   ├── originales/      respuestas crudas de Comtrade y BCRP (JSON)
│   └── procesados/      productos_anual.csv, destinos.csv, agro_vs_total.csv, precio_volumen.csv, hallazgos.json
├── scripts/
│   ├── obtener_datos.py
│   ├── procesar_datos.py
│   └── analizar_datos.py
├── web/
│   ├── index.html       dashboard (HTML + Plotly.js)
│   ├── data/datos.json
│   └── assets/          capturas del dashboard
└── reel/
    ├── guion.json       guion de 7 escenas con las cifras verificadas
    ├── graficos.py      gráficos de cada escena
    ├── reel.py, hacer_reel.py   voz clonada + video (adaptado de la sesión 15)
    ├── subtitulos.srt, reel.mp4
    └── recursos/        gráficos y captura del dashboard usados en el reel
```

## Cómo reproducirlo

Requiere [uv](https://docs.astral.sh/uv/) (o `pip install -r requirements.txt`).

```bash
cd tarea_3
uv run python scripts/obtener_datos.py     # descarga (omite lo que ya existe)
uv run python scripts/procesar_datos.py
uv run python scripts/analizar_datos.py    # genera hallazgos.json y web/data/datos.json
uv run python -m http.server 8000 --directory web   # abrir http://localhost:8000
```

Reel. Graba entre 15 y 25 segundos de tu voz en `reel/recursos/mi_voz.m4a`; ese archivo no se sube al repositorio. Luego:

```bash
uv run python reel/graficos.py
uv run python reel/hacer_reel.py --muda                                  # vista previa sin voz
uv run --extra reel python reel/hacer_reel.py --voz reel/recursos/mi_voz.m4a
```

La narración usa Qwen3-TTS (Qwen/Qwen3-TTS-12Hz-0.6B-Base), que clona la voz de la autora. Los subtítulos y el control de calidad (WER por escena) usan faster-whisper. El video se arma con Pillow y ffmpeg, en formato 1080 × 1920. La música de fondo se genera por código (acordes con ondas seno), así que no tiene derechos de autor.

## Uso de IA

Se usó un asistente de IA (Claude) para buscar fuentes, escribir el código de descarga, procesamiento y dashboard, y redactar el guion. La narración del reel es una voz generada con IA (Qwen3-TTS) a partir de la voz de la autora. Las cifras se verificaron contra los datos procesados (`hallazgos.json`) y se contrastaron con el BCRP.
