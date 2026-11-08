# Tarea 4 – Agente de investigación socioeconómica (BCRP + ENAHO 2024)

## 1. Objetivo
Construir un agente con Claude Code que responda con herramientas verificables (servidor MCP del BCRP y Skills de ENAHO), no solo con conocimiento previo. Pregunta de investigación:

> Entre 2020 y 2024, ¿cómo evolucionaron el crédito del sistema financiero y la tasa de interés en el Perú, y en 2024 los departamentos con más crédito por habitante tenían menos pobreza monetaria? ¿Cambia esa relación entre áreas urbanas y rurales?

Informe: [`informes/informe_final.md`](informes/informe_final.md). Es un análisis descriptivo; no se afirma causalidad.

## 2. Arquitectura
```
Claude Code ── MCP "bcrp" (mcp/server.py) ──► API oficial del BCRP
     │
     └─ Skills (.claude/skills/) ──► limpiando-enaho ─► graficando-enaho
                                              └──────► mapeando-enaho   ──► salidas/, figuras/, mapas/
agente/investigar.py   orquesta MCP + Skills en una ejecución y cruza ambas fuentes
agente/verificar.py    recalcula cifras por otro camino  ·  agente/generar_informe.py  genera el informe
evaluacion/            10 preguntas, Modo A (sin MCP/Skills) vs Modo B (con MCP/Skills)
```

## 3. Herramientas MCP (`mcp/server.py`)
| Herramienta | Función |
|---|---|
| `buscar_series` | Encuentra series del catálogo oficial por palabras clave |
| `serie` | Descarga una serie entre dos fechas (mensual, trimestral, diaria o anual) |
| `resumen` | Primero, último, cambio, variación %, promedio, máximo y mínimo con su período |
| `correlacion` (propia) | Alinea dos series de la misma frecuencia, descarta faltantes y calcula Pearson o Spearman; rechaza frecuencias distintas, series constantes y menos de 3 períodos comunes |

Recurso: `bcrp://serie/{codigo}` (ficha de la serie). Prompt: `informe(tema)`.

## 4. Skills (`.claude/skills/`)
- **`limpiando-enaho`**: lee los módulos 34 y 02, llaves como texto con ceros iniciales, filtra residentes habituales, une con `validate="m:1"`, construye pobreza/área/departamento, pondera y valida (`salidas/validacion.txt`). Si falla una validación esencial, se detiene sin guardar la base.
- **`graficando-enaho`**: pobreza por área, sexo y departamento, ponderada, con título analítico, unidades y fuente (`figuras/`).
- **`mapeando-enaho`**: mapa coroplético de 25 unidades uniendo `ubigeo[:2]` con `FIRST_IDDP`; compara con la referencia de la Sesión 16 (`mapas/validacion_mapa.txt`).

- **`explorando-resultados`** (adicional): genera `dashboard/index.html`, un dashboard interactivo (mapa con selector de variable, dispersión con selector de eje y tabla) con el cruce BCRP × ENAHO. Se abre en el navegador (carga Plotly desde CDN).

`graficando-enaho` admite `--grafico area|sexo|edad|departamento|todos` y `mapeando-enaho` admite `--indicador pobreza|extrema`. Las Skills de gráficos y mapas ejecutan antes `limpiando-enaho` si no existe `salidas/personas_2024.parquet`.

## 5. Fuentes y datos
| Fuente | Enlace |
|---|---|
| ENAHO 2024, módulo 34 (sumaria) | https://proyectos.inei.gob.pe/iinei/srienaho/descarga/STATA/966-Modulo34.zip |
| ENAHO 2024, módulo 02 (miembros) | https://proyectos.inei.gob.pe/iinei/srienaho/descarga/STATA/966-Modulo02.zip |
| Límites departamentales | https://raw.githubusercontent.com/d2cml-ai/Data-Science-Python/main/sessions/06-geoespacial/lab/Data/peru_departamental_simple.geojson |
| BCRP, series estadísticas | https://estadisticas.bcrp.gob.pe/estadisticas/series/ (series usadas en `docs/series_bcrp_verificadas.md`) |

Descarguen los tres primeros a `datos/` (los microdatos no se suben a Git). El catálogo del BCRP se baja solo la primera vez.

## 6. Instalación con `uv`
```bash
uv sync
```

## 7. Conectar el MCP a Claude Code
`.mcp.json` ya define el servidor `bcrp` (`uv run mcp/server.py`). Abran `claude` en esta carpeta y aprueben el servidor; `/mcp` debe mostrarlo conectado. Las Skills se detectan solas desde `.claude/skills/`.

## 8. Reproducir
```bash
uv run pytest mcp/ -q                       # 10 passed (8 originales + 2 propias en mcp/test_propias.py)
uv run pytest tests/ -q                     # 4 pruebas offline de las Skills (datos sintéticos)
uv run .claude/skills/explorando-resultados/scripts/dashboard.py   # dashboard/index.html
uv run agente/investigar.py                 # Skills + MCP -> salidas/, figuras/, mapas/
uv run agente/verificar.py                  # verificación independiente de 7 cifras
uv run agente/generar_informe.py            # informes/informe_final.md
uv run evaluacion/esperadas_independientes.py   # respuestas esperadas (ya generadas)
uv run evaluacion/evaluar.py ejecutar       # 20 sesiones aisladas con `claude -p`
uv run evaluacion/evaluar.py calificar      # resultados.csv y comparacion.md
```

## 9. Resultados
**Validación ENAHO 2024** (`salidas/validacion.txt`, 12/12 aprobadas): pobreza nacional 27.58 % (sumaria, `factor07 × mieperho`; 27.53 % por personas con `facpob07`; referencia 27.6 %), 108,664 residentes habituales, 25/25 unidades, urbana 24.81 %, rural 39.30 %. Mapa vs. Sesión 16: diferencia máxima 0.05 pp.

**Hallazgos** (detalle en el informe): el crédito creció 10.1 % nominal entre 2020 y 2024; el crédito por habitante de Lima es 22 veces el de Huancavelica; la correlación de Spearman entre crédito per cápita y pobreza departamental es −0.60 (n = 25) y aparece tanto en pobreza urbana como rural, pero el crédito también se asocia con menor ruralidad, por lo que no es una relación causal demostrada.

**Robustez** (Hallazgo 4 del informe): la asociación se mantiene en rangos (Spearman parcial controlando por ruralidad −0.53; entre −0.57 y −0.67 al omitir un departamento cada vez; más fuerte con pobreza extrema, −0.68), pero en un modelo lineal con control por ruralidad el coeficiente del crédito deja de ser significativo (p = 0.17); el crecimiento del crédito 2020–2024 no se asocia con la pobreza (p = 0.32).

**Verificación:** 7/7 cifras coinciden por script independiente y 3 cifras de ambas fuentes se comprobaron a mano (`informes/verificacion_cifras.md`).

**Evaluación del agente** (`evaluacion/resultados.csv`, `evaluacion/comparacion.md`): ver la sección siguiente.

### Resultados de la evaluación (10 preguntas × 2 modos, 20 sesiones independientes)
| | Sin MCP/Skills (A) | Con MCP/Skills (B) |
|---|---:|---:|
| Respuestas correctas | 8/10 | 9/10 |
| Incorrectas / no contestadas | 1 / 1 | 1 / 0 |
| Tiempo promedio (s) | 81.2 (≈32 sin C2) | 25.1 (≈22 sin C2) |
| Costo total (USD) | 0.76 | 0.92 |

Mejoró con MCP: B3 (crédito total BCRP; el Modo A no supo dónde buscarlo). E2 falló en ambos modos por una pregunta ambigua (se pedían «residentes habituales» y respondieron la cifra expandida, 34.1 millones, en vez de 108,664 registros de la muestra); se deja como incorrecta porque las esperadas no se modificaron tras ver los resultados. Se corrigió un error del calificador en C1 (declarado en `evaluacion/comparacion.md`). El Modo A tiene Bash e internet, por lo que la ventaja en exactitud es pequeña; MCP y Skills ayudaron sobre todo en descubrimiento, rapidez y trazabilidad. Una sola ejecución por pregunta: no es estadísticamente concluyente. Detalle: [`evaluacion/comparacion.md`](evaluacion/comparacion.md), [`evaluacion/resultados.csv`](evaluacion/resultados.csv).

## 10. Limitaciones y problemas encontrados
- Asociación descriptiva de 25 observaciones de un solo año; no se controla por ruralidad ni actividad económica.
- No se verificó en la metodología del BCRP cómo se asigna el crédito a cada departamento; si se registra por la ubicación de la agencia o la sede, el de Lima podría incluir financiamiento a otros departamentos. Series nominales, sin deflactar.
- Por departamento solo el método de la sumaria (`factor07 × mieperho`) reproduce la referencia de la Sesión 16 (0.05 pp frente a 0.52 pp con personas y `facpob07`).
- `correlacion(metodo="spearman")` requería `scipy` (agregado como dependencia).
- La API del BCRP devuelve los meses en inglés y el JSON precedido de avisos HTML; el servidor lo maneja.
- `agente/investigar.py` llama al MCP con un cliente FastMCP; la demostración nativa en Claude Code está en `evidencias_ia/integracion/demo_nativa_claude_code.md` (se genera con `uv run evaluacion/demo_nativa.py`).
- El Modo A de la evaluación tiene Bash y por tanto acceso a las APIs públicas: mide el valor de los componentes especializados, no de tener o no datos.

## 11. Ejemplo de una ejecución completa
```bash
uv run agente/investigar.py
```
Salida: 4 herramientas MCP (`buscar_series`, `serie`, `resumen`, `correlacion`) + recurso, 3 Skills (`limpiando-enaho`, `graficando-enaho`, `mapeando-enaho`), `salidas/bitacora_agente.json` con cada llamada, `salidas/resultados_investigacion.json`, 6 figuras y el mapa. Demostración nativa en Claude Code: `evidencias_ia/integracion/`.

## 12. Evidencias del uso de IA
Conversaciones completas con Claude Code en [`evidencias_ia/`](evidencias_ia/): `mcp/`, `skills/`, `integracion/` y `evaluacion/` (incluye los 20 logs de sesión en `evaluacion/logs/`). Se ocultaron datos personales.
