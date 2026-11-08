# Evidencia de integración MCP + Skills

- `bitacora_agente_script.json`: bitácora de `agente/investigar.py`, que en una sola ejecución llamó a 4 herramientas MCP distintas
  (`buscar_series`, `serie`, `resumen`, `correlacion`), leyó el recurso `bcrp://serie/{codigo}` y ejecutó 3 Skills
  (`limpiando-enaho`, `graficando-enaho`, `mapeando-enaho`). El MCP se llama con un cliente FastMCP por stdio.
- `../evaluacion/logs/`: 20 sesiones reales de Claude Code (`claude -p`). En las del Modo B el agente usó las herramientas
  `mcp__bcrp__*` del servidor definido en `.mcp.json` (6 de 10 sesiones) y ejecutó los scripts de las Skills (4 de 10);
  p. ej. `C2_B.jsonl` combina `mcp__bcrp__serie` (25 llamadas) con la Skill de limpieza.
- `demo_nativa_claude_code.md` y `.jsonl`: sesión real de Claude Code (`claude -p`) ante un pedido en lenguaje natural, sobre una copia sin `salidas/`. En una misma sesión usó 2 herramientas MCP distintas (`buscar_series`, `serie`) y 2 Skills con la herramienta `Skill` (`mapeando-enaho`, que al no existir la base llevó a ejecutar antes `limpiando-enaho`). Se genera con `uv run evaluacion/demo_nativa.py`. Esta demostración cubre el mapa y dos cifras del BCRP; el informe final lo produjeron `agente/investigar.py` y `agente/generar_informe.py`.
