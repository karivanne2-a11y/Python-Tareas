---
name: mapeando-enaho
description: Construye un mapa coroplético de la pobreza monetaria por departamento con la ENAHO 2024 del INEI (25 unidades, Lima y Callao separados), uniendo por código territorial y comparando con la referencia de la Sesión 16. Úsala cuando pidan un mapa, mapa coroplético o distribución territorial de la pobreza en el Perú.
---
# Mapear la pobreza departamental

1. Si no existe `salidas/personas_2024.parquet`, usa primero la skill `limpiando-enaho` y espera a que su validación esté aprobada.
2. Comprueba que existe `datos/peru_departamental_simple.geojson` (140 KB; enlace en el README). Si falta, pide al usuario descargarlo; no lo reemplaces por otro archivo.
3. Corre, desde la raíz del proyecto: `uv run ${CLAUDE_SKILL_DIR}/scripts/mapear.py` (añade `--indicador extrema` si piden pobreza extrema; por defecto pobreza monetaria)
4. Salidas: `mapas/pobreza_departamento.png`, `mapas/pobreza_departamento.csv` y `mapas/validacion_mapa.txt` (comparación con `referencias/pobreza_departamento_2024.csv`).
5. Reporta el departamento más y menos pobre y la diferencia máxima con la referencia tal como la imprime el script.

Reglas que el script ya cumple (no las cambies):
- Une por código, **nunca por nombre**: `ubigeo[:2]` con `FIRST_IDDP`, ambos como texto de 2 dígitos.
- Exige 25 unidades con dato; Lima (15) y Callao (07) separados.
- Escala de un solo color, de claro a oscuro, desde 0; leyenda «% de personas en pobreza monetaria»; fuente al pie.
