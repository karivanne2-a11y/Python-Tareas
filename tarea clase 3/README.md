# Tarea clase 3 – Un MCP del INEI: construirlo, conectarlo y medir si ayuda

**Estudiante:** Karen Macedo (@karivanne2-a11y) · Sesión 04 · Data Science con Python

## 1. Pregunta del proyecto

> ¿Responde Claude mejor sobre estadísticas peruanas cuando puede consultar los datos del INEI,
> en vez de contestar de memoria?

El experimento son 10 preguntas con la cifra correcta verificada a mano. Cada una se le hace
a Claude Code dos veces: sin MCP y con este servidor conectado.

## 2. Qué es este servidor

El INEI no publica una API de series como la del BCRP. Sus datos salen por el
[portal de Datos Abiertos del Estado](https://www.datosabiertos.gob.pe): un catálogo de datasets
con archivos CSV. Este servidor construye encima un catálogo de **series**: cada recurso tabular
de un dataset del INEI recibe un código, y sobre ese código funcionan las operaciones.

| Primitiva | Nombre | Qué hace |
|---|---|---|
| Herramienta | `buscar_series(texto, limite)` | Busca series por palabras del título o la descripción. Devuelve el código. |
| Herramienta | `serie(codigo, desde, hasta)` | Datos entre dos periodos, ambos incluidos. |
| Herramienta | `resumen(codigo, desde, hasta)` | n, mínimo y máximo con su periodo, promedio, mediana, desviación y variación. |
| Herramienta propia | `comparar(codigos, desde, hasta)` | Alinea dos o más series por periodo y calcula la correlación de Pearson. |
| Recurso (plantilla) | `inei://serie/{codigo}` | Ficha: columnas, cobertura, filas, URL de origen. |
| Recurso | `inei://catalogo` | Índice de las series disponibles. |
| Prompt | `informe(tema)` | Cinco viñetas con cifras traídas por herramienta, cada una con código y periodo. |

Formatos de periodo: `2025` (anual), `2025-03` (mensual), `2025-03-15` (diaria).
Un código inexistente levanta un `ToolError` que lo nombra.

La primera llamada baja el catálogo del INEI y lo guarda en `datos/catalogo_inei.json`;
las siguientes usan esa copia.

## 3. Cómo correrlo

```bash
cd "tarea clase 3"
uv sync
uv run server.py --probe       # prueba de humo: lista series del catálogo
uv run pytest -q               # las 8 pruebas
```

Conectarlo a Claude Code (el `.mcp.json` ya está en esta carpeta):

```bash
claude            # desde esta carpeta; /mcp debe mostrar inei y fetch conectados
```

En Claude Code: `@inei:inei://serie/<codigo>` adjunta una ficha y
`/mcp__inei__informe pobreza` lanza el prompt.

## 4. Las ocho pruebas

| # | Prueba | Red |
|---|---|---|
| 1 | Hay 4 herramientas o más: las 3 pedidas y la propia | no |
| 2 | Toda herramienta tiene un docstring con sustancia | no |
| 3 | Hay al menos un recurso o una plantilla de recurso | no |
| 4 | Hay al menos un prompt | no |
| 5 | `buscar_series` encuentra series y devuelve su fuente | sí |
| 6 | `serie` devuelve datos numéricos con periodo y fuente | sí |
| 7 | `resumen` es coherente con lo que devuelve `serie` | sí |
| 8 | Un código inexistente da un `ToolError` que lo nombra | sí |

Las cuatro con red se saltan solas si el portal no responde:
`uv run pytest -q -m "not red"` corre solo las de estructura.

## 5. La evaluación

1. Llena la columna `verdad` de `preguntas.csv` a mano, con su `fuente_url`. `evaluar.py`
   se niega a correr si falta alguna: la verdad no se le pide al modelo.
2. Escribe las preguntas `p09` y `p10`, que son propias.
3. `uv run evaluar.py` → `resultados.csv` y `grafico.png`.

Una cifra cuenta como acierto si cae dentro del 2 % de la verdad. «Dice null» se contabiliza
aparte de «se equivoca»: no es lo mismo no saber que inventar.

## 6. Hallazgos

_Pendiente: se completa con lo que salga de `resultados.csv` (ver `informe.md`)._

## 7. Límites conocidos

- El catálogo cubre los datasets del INEI publicados en Datos Abiertos, no el universo
  de estadísticas del instituto. Lo que solo vive en Perú en Cifras o SIRTOD no está aquí.
- Los CSV del portal no tienen un formato común: la detección de la columna de periodo y la
  de valor es heurística. Cuando se equivoca, hay que pasar `columna_periodo` y `columna_valor`.
- Series con desagregación (por región, por sexo) traen varias filas por periodo; el servidor
  no las agrega: hay que filtrar la columna que corresponda antes de leer la cifra.
