# Comparación: Claude Code sin y con MCP y Skills

Generado por `evaluacion/evaluar.py calificar` a partir de los logs de `evidencias_ia/evaluacion/logs/`.

## Diseño

| | |
|---|---|
| Preguntas | 10 (`preguntas.csv`): 4 BCRP, 4 ENAHO, 2 combinadas. Respuestas esperadas calculadas **antes** de correr con `esperadas_independientes.py` (API del BCRP con httpx y microdatos .dta leídos directamente; ENAHO contrastada con las cifras del INEI) |
| Modelo | `sonnet` (alias de Claude Code), el mismo en ambos modos |
| Sesiones | Una sesión independiente por pregunta y modo (`claude -p --no-session-persistence`): 20 sesiones |
| Instrucción | Idéntica en ambos modos (ver `INSTRUCCION` en `evaluar.py`): no estimar, decir «no sé» si no hay certeza, cerrar con `RESPUESTA FINAL` + JSON |
| Aislamiento | Copia limpia por sesión, sin `salidas/`, `informes/`, `evaluacion/`, `agente/`, `figuras/` ni `mapas/`; sin ajustes de usuario (`--setting-sources project`) |
| Corrección | Automática según `tolerancia_abs` y `texto_esperado` de `preguntas.csv`, fijados antes de correr; C2 además exige no afirmar causalidad |

### Herramientas habilitadas

| | Modo A: sin MCP ni Skills | Modo B: con MCP y Skills |
|---|---|---|
| Herramientas generales | Bash, Read, Glob, Grep | Las mismas |
| Servidor MCP `bcrp` | No (`--strict-mcp-config`, sin `.mcp.json`) | Sí |
| Skills del proyecto | No (`--disable-slash-commands`, Skill bloqueada, sin `.claude/`) | Sí (`.claude/skills/`) |
| Web (WebSearch, WebFetch) | Bloqueada | Bloqueada |
| Datos en la copia | Zips ENAHO 2024 y GeoJSON | Los mismos + catálogo del BCRP y `referencias/` |
| Entorno de Python | El del proyecto (`UV_PROJECT_ENVIRONMENT`) | El mismo |

El Modo A **no** es «Claude sin herramientas»: tiene Bash, por lo que puede llamar a la API pública del BCRP con `curl` o `httpx` y procesar los zips de la ENAHO por su cuenta. La comparación mide el valor de los componentes especializados, no el de tener o no acceso a datos.

## Resultados

| | Modo A | Modo B |
|---|---:|---:|
| Correctas | 8/10 | 9/10 |
| Incorrectas | 1 | 1 |
| No contestadas / sin formato | 1 | 0 |
| Tiempo promedio por pregunta (s) | 81.2 | 25.1 |
| Costo total (USD) | 0.76 | 0.92 |
| Sesiones que usaron MCP | 0 | 6 |
| Sesiones que usaron Skills | 0 | 4 |

### Por pregunta

| Id | Tipo | Esperado | Modo A | Modo B | Herramientas B |
|---|---|---|---|---|---|
| B1 | BCRP | 1.97 % | ✔ correcta (21s) | ✔ correcta (12s) | ToolSearch×1, mcp__bcrp__buscar_series×2, mcp__bcrp__serie×1 |
| B2 | BCRP | 8.81 % en Jun.2022 | ✔ correcta (20s) | ✔ correcta (12s) | ToolSearch×1, mcp__bcrp__buscar_series×1, mcp__bcrp__resumen×1 |
| B3 | BCRP | 407,351.74 millones de S/ | ✘ no contestada (14s) | ✔ correcta (11s) | ToolSearch×1, mcp__bcrp__buscar_series×1, mcp__bcrp__serie×1 |
| B4 | BCRP | 5.00 % | ✔ correcta (15s) | ✔ correcta (17s) | ToolSearch×1, mcp__bcrp__buscar_series×1, mcp__bcrp__serie×1 |
| C1 | Combinada | S/ 26,461 por habitante | ✔ correcta (59s) | ✔ correcta (32s) | Glob×1, ToolSearch×1, mcp__bcrp__buscar_series×1, Read×1, mcp__bcrp__serie×2, Bash×3, PowerShell×1, Write×1 |
| C2 | Combinada | Lima: pobreza 27.1 %. No se puede concluir causalidad | ✔ correcta (523s) | ✔ correcta (51s) | Glob×1, ToolSearch×1, mcp__bcrp__buscar_series×1, Read×2, Bash×2, mcp__bcrp__serie×25 |
| E1 | ENAHO | 27.6 % | ✔ correcta (82s) | ✔ correcta (29s) | Glob×1, Grep×1, Bash×1 |
| E2 | ENAHO | 108,664 | ✘ incorrecta (22s) | ✘ incorrecta (30s) | Glob×1, Read×1, Bash×3 |
| E3 | ENAHO | 39.3 % | ✔ correcta (32s) | ✔ correcta (25s) | Glob×1, Read×2, Bash×1 |
| E4 | ENAHO | 5.5 % | ✔ correcta (23s) | ✔ correcta (32s) | Glob×1, Read×3, Bash×1 |

- **Mejoraron con MCP/Skills:** B3
- **Empeoraron:** ninguna
- **Sin cambio (mismo resultado en ambos modos):** B1, B2, B4, C1, C2, E1, E2, E3, E4
- **Accesos fuera de la carpeta aislada detectados en los logs:** ninguno

## Análisis y conclusión

### Principales errores encontrados
- **B3, Modo A (no contestada):** sin el servidor MCP, la sesión revisó la carpeta, vio que solo tenía datos de la ENAHO y respondió «no lo sé» en vez de buscar la serie del BCRP. Es el único caso en que MCP/Skills cambió una respuesta de incorrecta a correcta.
- **E2, ambos modos (incorrecta):** la pregunta pedía «cuántas personas son residentes habituales». Los dos modos respondieron 34,147,770 (personas **expandidas** con `facpob07`) y solo mencionaron 108,664 como «registros de la muestra». La respuesta esperada era 108,664. **La causa es una pregunta mal formulada** (debió decir «registros muestrales, sin expandir»); no se modificó la respuesta esperada después de ver los resultados y por eso cuenta como incorrecta en los dos modos.
- **Corrección del calificador (transparencia):** en la primera calificación C1 salió «incorrecta» en ambos modos porque la nota «Tolerancia 1 %.» de `preguntas.csv` se interpretó por error como un criterio de causalidad. Los valores generados (26,460.5) eran correctos. Se corrigió la regla del calificador (`evaluar.py`: solo C2 exige interpretar la causalidad). `preguntas.csv` no cambió (su huella está en `preguntas.sha256`).

### Observaciones
- El Modo A **no es «sin herramientas»**: tiene Bash y acceso a internet, así que en B1, B2 y B4 llamó a la API pública del BCRP y acertó, y en C1 y C2 calculó el crédito por habitante con la ENAHO y la API. La ventaja de MCP/Skills en exactitud fue por tanto pequeña: 9/10 frente a 8/10.
- **Tiempo:** el promedio del Modo A (81.2 s) está dominado por C2 (522.8 s, 16 llamadas a Bash). Sin C2, los promedios son aproximadamente 32 s (Modo A) y 22 s (Modo B). En las preguntas del BCRP (B1–B4) el Modo B respondió con 1 a 3 llamadas al MCP.
- **Costo:** el Modo B costó algo más en total (USD 0.92 frente a 0.76), sobre todo en C1 y C2, donde hizo muchas llamadas `serie`.
- **Uso real de herramientas:** MCP en 6 de 10 sesiones del Modo B (las del BCRP y las combinadas). Las Skills se usaron en 4 de 10 (E1, E3, E4 y C2): el agente leyó `SKILL.md`, ejecutó su script y usó `indicadores.csv`; no llamó a la herramienta `Skill`, por lo que esta evaluación no demuestra la activación automática por descripción.

### Conclusión sobre la utilidad de MCP y Skills
En este experimento, MCP y Skills **no mejoraron de forma apreciable la exactitud** (9/10 frente a 8/10) porque un agente con Bash e internet ya puede obtener estas cifras por su cuenta; sí ayudaron en **descubrimiento** (B3: el MCP con `buscar_series` encuentra series que el agente sin MCP no sabe dónde buscar), **rapidez** (menos pasos y menos tiempo en las preguntas con cálculo, p. ej. C2) y **trazabilidad** (cada cifra sale con código de serie y validaciones de ENAHO). Limitaciones del experimento: 10 preguntas, una sola ejecución por pregunta y modo (sin repeticiones), un solo modelo, y una pregunta mal formulada (E2), por lo que las diferencias observadas no son estadísticamente concluyentes.
