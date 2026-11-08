---
name: graficando-enaho
description: Grafica la pobreza monetaria de la ENAHO 2024 del INEI por área urbana/rural, sexo, grupo de edad o departamento, con estimaciones ponderadas, título analítico, unidades y fuente. Úsala cuando pidan un gráfico, barras o comparación de pobreza con ENAHO.
argument-hint: [area|sexo|departamento|todos]
---
# Graficar la pobreza con ENAHO

1. Si no existe `salidas/personas_2024.parquet`, usa primero la skill `limpiando-enaho` y espera a que su validación esté aprobada.
2. Corre, desde la raíz del proyecto: `uv run ${CLAUDE_SKILL_DIR}/scripts/graficar.py --grafico <area|sexo|edad|departamento|todos>` (elige según el pedido; "todos" por defecto).
3. Los PNG quedan en `figuras/` (200 dpi). Revísalos y descríbelos citando las cifras que imprime el título.

Reglas que el script ya cumple (no las cambies):
- Pondera siempre: área y departamento con `factor07 × mieperho` (método del INEI, por hogares); sexo con `facpob07` (personas). Nunca promedios simples.
- Barras que empiezan en cero, ordenadas, un solo color, valor escrito en cada barra.
- Título analítico con el período, unidad en el eje y nota al pie «Fuente: INEI, ENAHO 2024».

No interpretes las diferencias como causales: son asociaciones descriptivas.
