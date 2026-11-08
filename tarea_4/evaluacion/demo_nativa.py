"""Demostración nativa: una sesión de Claude Code con el .mcp.json y las Skills del proyecto, ante un pedido en lenguaje natural.

    uv run evaluacion/demo_nativa.py

Corre en una copia SIN salidas/ para comprobar que, al no existir la base procesada, el agente ejecuta primero la Skill de
limpieza y luego la de mapas, y consulta el MCP del BCRP. El registro queda en evidencias_ia/integracion/.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import evaluar  # noqa: E402

PEDIDO = ("Haz un mapa de la pobreza monetaria por departamento con ENAHO 2024 y dime, con datos oficiales del BCRP, cuánto fue el "
          "crédito directo total del sistema financiero al sector privado a fines de 2024 y cuál era la tasa de referencia en "
          "diciembre de 2024. Cita el código de serie y el período de cada cifra.")


def main():
    cwd = evaluar.preparar("B")
    cmd = ["claude", "-p", PEDIDO, "--model", evaluar.MODELO, "--output-format", "stream-json", "--verbose", "--no-session-persistence",
           "--setting-sources", "project", "--strict-mcp-config", "--mcp-config", ".mcp.json",
           "--allowedTools", "Bash", "Read", "Glob", "Grep", "Skill", "mcp__bcrp", "--disallowedTools", "WebSearch", "WebFetch"]
    env = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(evaluar.RAIZ / ".venv"), "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    destino = evaluar.RAIZ / "evidencias_ia" / "integracion"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "demo_nativa_claude_code.jsonl").write_text(r.stdout, encoding="utf-8")
    herr, texto = [], ""
    for linea in r.stdout.splitlines():
        try:
            ev = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            herr += [(i["name"], json.dumps(i.get("input", {}), ensure_ascii=False)[:160]) for i in ev["message"]["content"] if i.get("type") == "tool_use"]
        elif ev.get("type") == "result":
            texto = ev.get("result", "")
    md = ["# Demostración nativa: MCP + Skills en Claude Code", "", f"**Pedido:** {PEDIDO}", "",
          "**Condiciones:** copia limpia del proyecto sin `salidas/` (no existe la base procesada), con `.mcp.json` y `.claude/skills/`; ",
          "`claude -p` con las herramientas Bash, Read, Glob, Grep, Skill y el servidor MCP `bcrp`.", "", "## Secuencia de herramientas", ""]
    md += [f"{i}. `{n}` — `{a}`" for i, (n, a) in enumerate(herr, 1)]
    md += ["", "## Respuesta final", "", texto, "", "Registro completo: `demo_nativa_claude_code.jsonl`."]
    (destino / "demo_nativa_claude_code.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
