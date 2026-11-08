# Demostración nativa: MCP + Skills en Claude Code

**Pedido:** Haz un mapa de la pobreza monetaria por departamento con ENAHO 2024 y dime, con datos oficiales del BCRP, cuánto fue el crédito directo total del sistema financiero al sector privado a fines de 2024 y cuál era la tasa de referencia en diciembre de 2024. Cita el código de serie y el período de cada cifra.

**Condiciones:** copia limpia del proyecto sin `salidas/` (no existe la base procesada), con `.mcp.json` y `.claude/skills/`; 
`claude -p` con las herramientas Bash, Read, Glob, Grep, Skill y el servidor MCP `bcrp`.

## Secuencia de herramientas

1. `ToolSearch` — `{"query": "select:mcp__bcrp__buscar_series,mcp__bcrp__serie,mcp__bcrp__resumen", "max_results": 5}`
2. `Skill` — `{"skill": "mapeando-enaho"}`
3. `Glob` — `{"pattern": "**/*", "path": "C:\\Users\\Karen\\AppData\\Local\\Temp\\eval_tarea4\\modo_B"}`
4. `mcp__bcrp__buscar_series` — `{"texto": "crédito directo sistema financiero sector privado", "limite": 15}`
5. `mcp__bcrp__buscar_series` — `{"texto": "tasa de referencia", "limite": 10}`
6. `mcp__bcrp__serie` — `{"codigo": "RD13637DM", "desde": "2024-11", "hasta": "2024-12"}`
7. `mcp__bcrp__serie` — `{"codigo": "PD04722MM", "desde": "2024-11", "hasta": "2024-12"}`
8. `Skill` — `{"skill": "limpiando-enaho"}`
9. `Bash` — `{"command": "cd \"C:/Users/Karen/AppData/Local/Temp/eval_tarea4/modo_B\" && uv run C:/Users/Karen/AppData/Local/Temp/eval_tarea4/modo_B/.claude/skills/limpiando`
10. `Bash` — `{"command": "cd \"C:/Users/Karen/AppData/Local/Temp/eval_tarea4/modo_B\" && uv run C:/Users/Karen/AppData/Local/Temp/eval_tarea4/modo_B/.claude/skills/mapeando-`
11. `Read` — `{"file_path": "C:\\Users\\Karen\\AppData\\Local\\Temp\\eval_tarea4\\modo_B\\mapas\\pobreza_departamento.csv"}`
12. `Read` — `{"file_path": "C:\\Users\\Karen\\AppData\\Local\\Temp\\eval_tarea4\\modo_B\\mapas\\pobreza_departamento.png"}`

## Respuesta final

Hice el mapa de pobreza monetaria por departamento con la ENAHO 2024 y consulté las dos cifras del BCRP.

## Mapa de pobreza monetaria (ENAHO 2024, INEI)
- **Archivo:** `C:\Users\Karen\AppData\Local\Temp\eval_tarea4\modo_B\mapas\pobreza_departamento.png`. La tabla de datos está en `mapas\pobreza_departamento.csv`.
- **Más pobre:** Cajamarca, con 45.0 %.
- **Menos pobre:** Ica, con 6.0 %.
- **Validación:** pasó la limpieza de datos (pobreza nacional 27.6 %, urbana 24.8 %, rural 39.3 %, las tres dentro de ±0.1 pp de la referencia). El mapa tiene las 25 unidades con dato, con Lima y Callao separados. La diferencia máxima frente a la referencia de la Sesión 16 es 0.05 pp (Amazonas), y las 25 unidades quedan dentro de ±0.1 pp.

## Cifras del BCRP

| Dato | Código de serie | Período | Valor |
|---|---|---|---|
| Crédito directo del sistema financiero al sector privado, total, fin de período | `RD13637DM` (mensual) | Diciembre 2024 | S/ 407 351.7 millones (407 351.742) |
| Tasa de referencia de la política monetaria | `PD04722MM` (mensual) | Diciembre 2024 | 5.00 % |

- **Crédito directo:** `RD13637DM` es la suma de los departamentos. Su valor de noviembre 2024 fue S/ 404 194.8 millones.
- **Tasa de referencia:** también la consulté en noviembre 2024 y fue 5.00 %. En diciembre no hubo cambio.

Ambas series las leí con las herramientas del servidor `bcrp`. No usé la serie diaria de la tasa (`PD12301MD`), así que el 5.00 % es el valor mensual de `PD04722MM`.

Registro completo: `demo_nativa_claude_code.jsonl`.