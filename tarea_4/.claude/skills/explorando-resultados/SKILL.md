---
name: explorando-resultados
description: Genera un dashboard interactivo en HTML (mapa, dispersión y tabla con selectores) que cruza el crédito por departamento del BCRP con la pobreza monetaria de la ENAHO 2024. Úsala cuando pidan un dashboard, un panel interactivo, explorar los resultados o una visualización interactiva del cruce BCRP y ENAHO.
---
# Dashboard interactivo del cruce BCRP × ENAHO

1. Si no existe `salidas/credito_pobreza_departamento.csv`, genera primero los insumos: usa la skill `limpiando-enaho` (base y validación aprobadas) y corre `uv run agente/investigar.py`, que consulta el MCP `bcrp` y escribe ese CSV.
2. Comprueba que existe `datos/peru_departamental_simple.geojson`. Si falta, pide al usuario descargarlo (enlace en el README).
3. Corre, desde la raíz del proyecto: `uv run ${CLAUDE_SKILL_DIR}/scripts/dashboard.py`
4. El resultado es `dashboard/index.html`: mapa con selector de variable, dispersión con selector de eje x y tabla. Dile al usuario que lo abra en el navegador (necesita internet para cargar Plotly).

Reglas: todas las cifras vienen de los CSV; no las inventes ni las escribas a mano. Presenta el resultado como asociación descriptiva, nunca como causalidad.
