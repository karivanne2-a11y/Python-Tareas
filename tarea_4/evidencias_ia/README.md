# Evidencias del uso de IA

Asistente utilizado: **Claude Code** (app de escritorio), con los modelos Claude Sonnet 5.5 y Claude Opus 5.5. Se ocultó el correo y los nombres y usuarios de GitHub de otros estudiantes se reemplazaron por códigos («Estudiante 1», etc.); el nombre de usuario de Windows sigue visible en las rutas. No hay claves ni tokens.

| Archivo / carpeta | Contenido |
|---|---|
| `conversacion_claude_code.md` | Conversación completa de la sesión de desarrollo, legible (resultados largos abreviados) |
| `conversacion_claude_code.jsonl` | Mismo registro, íntegro y filtrado a mensajes de usuario y asistente |
| `mcp/pruebas.txt` | Salida de `pytest -v`: 10 passed (8 originales + 2 propias) |
| `skills/` | Salidas de validación de las Skills (ver `../salidas/validacion.txt`, `../mapas/validacion_mapa.txt`) |
| `integracion/` | Bitácora de la ejecución integrada MCP + Skills y demostración en Claude Code |
| `evaluacion/logs/` | 20 logs `stream-json` (uno por pregunta y modo) de las sesiones independientes de `claude -p` |

## Dónde está cada etapa en la conversación
Revisión de las instrucciones del issue y de las entregas de los compañeros → servidor MCP (herramientas `serie`, `resumen`, `correlacion`, recurso y prompt; 10 pruebas) → Skills de ENAHO (limpieza con validación, gráficos, mapa) → investigación integrada y verificación independiente → informe → diseño y ejecución de la evaluación → README.

Cronología de la sesión: `conversacion_claude_code.md` está ordenado por fecha y hora (UTC).
