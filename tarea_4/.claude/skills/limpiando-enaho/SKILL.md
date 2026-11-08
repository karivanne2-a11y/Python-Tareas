---
name: limpiando-enaho
description: Limpia los módulos 34 (sumaria) y 02 (miembros) de la ENAHO 2024 del INEI, une personas con hogares, filtra residentes habituales, aplica factores de expansión y valida la pobreza monetaria contra la cifra oficial (27.6 %). Úsala cuando pidan limpiar, preparar, unir o analizar la ENAHO, o calcular pobreza por área, sexo o departamento.
argument-hint: [año]
---
# Limpiar la ENAHO

1. Si faltan los zip en `datos/` (`966-Modulo34.zip` y `966-Modulo02.zip`), no los inventes: indica al usuario que los baje del INEI (código 966 = 2024; enlaces en el README).
2. Corre exactamente, desde la raíz del proyecto:
   `uv run ${CLAUDE_SKILL_DIR}/scripts/limpiar.py --anio 2024` (cambia el año solo si el usuario lo pide y los zip lo permiten)
3. Lee `salidas/validacion.txt`. Si el script termina con error o hay una validación esencial FALLIDA, **detente** y reporta el mensaje tal cual. No ajustes los resultados para que coincidan con la referencia.
4. Si todo está aprobado, usa `salidas/personas_2024.parquet` (una fila por persona residente habitual) y `salidas/indicadores.csv` (pobreza ponderada por nacional, área, sexo y departamento).
5. Toda cifra va ponderada. Nacional, área y departamento: un registro por hogar con `factor07 × mieperho` (método del INEI; reproduce la referencia de la Sesión 16 con diferencia máxima de 0.05 pp). Sexo y cruces por persona: `facpob07`. Nunca uses promedios simples.
6. Antes de usar una variable que no está en la base, lee `reference.md`.

No presentes asociaciones descriptivas como relaciones causales.
