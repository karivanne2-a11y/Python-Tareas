"""Experimento: las mismas 10 preguntas con Claude Code SIN y CON el MCP y las Skills del proyecto.

    uv run evaluacion/evaluar.py ejecutar [--ids B1,E2] [--modos A,B]   # una sesión independiente por pregunta y modo
    uv run evaluacion/evaluar.py calificar                              # lee los logs y escribe resultados.csv y comparacion.md

Aislamiento: cada sesión corre con `claude -p --no-session-persistence` en una copia limpia (carpeta temporal) que NO
contiene salidas/, informes/, evaluacion/, agente/, figuras/ ni mapas/, y sin ajustes de usuario (--setting-sources project).
  Modo A: sin servidor MCP (--strict-mcp-config) y sin skills (--disable-slash-commands, Skill bloqueada).
  Modo B: con .mcp.json (servidor bcrp) y .claude/skills.
En ambos: Bash, Read, Glob y Grep; WebSearch y WebFetch bloqueadas; mismos datos crudos (zips ENAHO y GeoJSON);
mismo modelo (sonnet), misma instrucción, mismo entorno de Python (UV_PROJECT_ENVIRONMENT).
"""
import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EVAL = RAIZ / "evaluacion"
LOGS = RAIZ / "evidencias_ia" / "evaluacion" / "logs"
SANDBOX = Path(tempfile.gettempdir()) / "eval_tarea4"
MODELO = "sonnet"
TIMEOUT = 900

INSTRUCCION = (
    "Responde la pregunta usando solo datos oficiales y cálculos verificables; no estimes ni inventes cifras. "
    "Si no puedes obtener el dato con certeza, di que no lo sabes. Trabaja solo dentro de la carpeta actual. "
    'Cierra con una línea que empiece con RESPUESTA FINAL: seguida de un JSON con las claves "valores" '
    '(lista de números en las unidades pedidas, o null si no lo sabes), "texto" (respuesta breve) y "fuente" '
    "(código de serie o archivo usado).\n\nPregunta: ")


def sin_tildes(s):
    return unicodedata.normalize("NFD", str(s).lower()).encode("ascii", "ignore").decode()


def preguntas():
    with (EVAL / "preguntas.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- sandbox y ejecución
def preparar(modo: str) -> Path:
    d = SANDBOX / f"modo_{modo}"
    if d.exists():
        shutil.rmtree(d)
    (d / "datos").mkdir(parents=True)
    for f in ("966-Modulo34.zip", "966-Modulo02.zip", "peru_departamental_simple.geojson"):
        shutil.copy(RAIZ / "datos" / f, d / "datos" / f)
    shutil.copy(RAIZ / "pyproject.toml", d)
    shutil.copy(RAIZ / "uv.lock", d)
    if modo == "B":
        shutil.copytree(RAIZ / ".claude", d / ".claude")
        shutil.copytree(RAIZ / "mcp", d / "mcp", ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        shutil.copy(RAIZ / ".mcp.json", d)
        shutil.copytree(RAIZ / "referencias", d / "referencias")
        shutil.copy(RAIZ / "datos" / "catalogo_bcrp.csv", d / "datos")
    return d


def ejecutar_una(p: dict, modo: str):
    log = LOGS / f"{p['id']}_{modo}.jsonl"
    if log.exists():
        print(f"{p['id']}-{modo}: ya existe, se omite")
        return
    cwd = preparar(modo)
    cmd = ["claude", "-p", INSTRUCCION + p["pregunta"], "--model", MODELO, "--output-format", "stream-json", "--verbose",
           "--no-session-persistence", "--setting-sources", "project", "--strict-mcp-config",
           "--disallowedTools", "WebSearch", "WebFetch", "--max-budget-usd", "3"]
    if modo == "A":
        cmd += ["--disable-slash-commands", "--disallowedTools", "Skill", "--allowedTools", "Bash", "Read", "Glob", "Grep"]
    else:
        cmd += ["--mcp-config", ".mcp.json", "--allowedTools", "Bash", "Read", "Glob", "Grep", "Skill", "mcp__bcrp"]
    env = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(RAIZ / ".venv"), "PYTHONIOENCODING": "utf-8"}
    t = time.time()
    try:
        r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
        salida, err = r.stdout, r.stderr[-500:]
    except subprocess.TimeoutExpired as e:
        salida, err = (e.stdout or "") if isinstance(e.stdout, str) else "", "TIMEOUT"
    seg = round(time.time() - t, 1)
    LOGS.mkdir(parents=True, exist_ok=True)
    meta = json.dumps({"_meta": {"id": p["id"], "modo": modo, "segundos_pared": seg, "stderr": err, "comando": cmd[:3] + ["…"] + cmd[3:]}})
    log.write_text(meta + "\n" + salida, encoding="utf-8")
    print(f"{p['id']}-{modo}: {seg}s")


# ---------------------------------------------------------------- calificación
def leer_log(path: Path):
    meta, herramientas, texto, res = {}, [], "", {}
    for linea in path.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if "_meta" in ev:
            meta = ev["_meta"]
        elif ev.get("type") == "assistant":
            for it in ev.get("message", {}).get("content", []):
                if it.get("type") == "tool_use":
                    herramientas.append((it["name"], json.dumps(it.get("input", {}), ensure_ascii=False)))
        elif ev.get("type") == "result":
            res = ev
            texto = ev.get("result", "") or ""
    return meta, herramientas, texto, res


def extraer_json(texto: str):
    i = texto.rfind("RESPUESTA FINAL")
    if i < 0:
        return None
    m = re.search(r"\{.*\}", texto[i:], re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def numeros(v):
    if isinstance(v, (int, float)):
        return [float(v)]
    if isinstance(v, str):
        return [float(x.replace(",", "")) for x in re.findall(r"-?\d[\d,]*\.?\d*", v)]
    if isinstance(v, list):
        return [n for x in v for n in numeros(x)]
    return []


def calificar_una(p: dict, texto: str, rj):
    """(estado, correcta, detalle). Estados: correcta, incorrecta, no contestada, sin formato."""
    if rj is None:
        return "sin formato", False, "no hay línea RESPUESTA FINAL con JSON"
    vals = numeros(rj.get("valores"))
    if not vals:
        return "no contestada", False, "valores = null o vacío"
    esperados = [float(x) for x in p["valores_esperados"].split(";") if x]
    tol = float(p["tolerancia_abs"])
    faltan = [e for e in esperados if not any(abs(v - e) <= tol + 1e-9 for v in vals)]
    if faltan:
        return "incorrecta", False, f"no coincide con {faltan} (tolerancia ±{tol})"
    t = sin_tildes(str(rj.get("texto", "")) + " " + texto[-600:])
    for grupo in [g for g in p["texto_esperado"].split(";") if g]:
        if not any(alt in t for alt in grupo.split("|")):
            return "incorrecta", False, f"falta el texto esperado {grupo!r}"
    if "causal" in p["criterio_interpretacion"].lower():  # solo C2 exige interpretar la causalidad (C1 solo anota su tolerancia)
        if re.search(r"reduce la pobreza|causa (menos|una menor)|disminuye la pobreza por", t) and not re.search(r"no (se puede|es posible|permite|implica|demuestra)|asociaci|correlaci|no causal", t):
            return "incorrecta", False, "afirma causalidad"
        if not re.search(r"no (se puede|es posible|permite|implica|demuestra|debe|podemos|puede)|asociaci|correlaci|no causal|causalidad", t):
            return "incorrecta", False, "no aborda la interpretación (causalidad)"
    return "correcta", True, f"coincide dentro de ±{tol}"


def calificar():
    P = {p["id"]: p for p in preguntas()}
    filas = []
    for p in P.values():
        for modo in ("A", "B"):
            log = LOGS / f"{p['id']}_{modo}.jsonl"
            if not log.exists():
                continue
            meta, herr, texto, res = leer_log(log)
            rj = extraer_json(texto)
            estado, ok, det = calificar_una(p, texto, rj)
            nombres = [h[0] for h in herr]
            usa_mcp = any(n.startswith("mcp__bcrp") for n in nombres)
            usa_skill = any(n == "Skill" for n in nombres) or any(".claude/skills" in a or "skills/" in a and "scripts" in a for n, a in herr if n == "Bash")
            fuera = any(str(RAIZ).replace("\\", "/").lower() in a.replace("\\", "/").lower() or "desktop/tarea" in a.replace("\\", "/").lower() for _, a in herr)
            resumen = {}
            for n in nombres:
                resumen[n] = resumen.get(n, 0) + 1
            filas.append({
                "id": p["id"], "tipo": p["tipo"], "modo": modo, "pregunta": p["pregunta"], "respuesta_esperada": p["respuesta_esperada"],
                "respuesta_generada": (rj or {}).get("texto") or texto[-300:].replace("\n", " "),
                "valores_generados": json.dumps((rj or {}).get("valores"), ensure_ascii=False),
                "fuente_utilizada": (rj or {}).get("fuente", ""), "herramientas": " | ".join(f"{k}×{v}" for k, v in resumen.items()),
                "uso_mcp": usa_mcp, "uso_skills": usa_skill, "estado": estado, "correcta": ok,
                "criterio": f"±{p['tolerancia_abs']} abs; {det}", "segundos": round(res.get("duration_ms", meta.get("segundos_pared", 0) * 1000) / 1000, 1),
                "turnos": res.get("num_turns", ""), "costo_usd": round(res.get("total_cost_usd", 0) or 0, 4),
                "error": "" if not res.get("is_error") and meta.get("stderr", "") not in ("TIMEOUT",) else (meta.get("stderr") or "is_error"),
                "acceso_fuera_sandbox": fuera, "log": str(log.relative_to(RAIZ)).replace("\\", "/")})
    if not filas:
        sys.exit("No hay logs: ejecuten primero `ejecutar`.")
    campos = list(filas[0].keys())
    with (EVAL / "resultados.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)
    escribir_comparacion(filas)
    for modo in ("A", "B"):
        fs = [x for x in filas if x["modo"] == modo]
        print(f"Modo {modo}: {sum(x['correcta'] for x in fs)}/{len(fs)} correctas")


def escribir_comparacion(filas):
    def stats(m):
        fs = [x for x in filas if x["modo"] == m]
        return {"n": len(fs), "ok": sum(x["correcta"] for x in fs),
                "inc": sum(x["estado"] == "incorrecta" for x in fs),
                "nc": sum(x["estado"] in ("no contestada", "sin formato") for x in fs),
                "seg": sum(x["segundos"] for x in fs) / max(len(fs), 1), "costo": sum(x["costo_usd"] for x in fs),
                "mcp": sum(x["uso_mcp"] for x in fs), "skills": sum(x["uso_skills"] for x in fs)}
    a, b = stats("A"), stats("B")
    por = {(x["id"], x["modo"]): x for x in filas}
    ids = sorted({x["id"] for x in filas}, key=lambda i: (i[0], int(i[1:])))
    mejoran = [i for i in ids if por.get((i, "B"), {}).get("correcta") and not por.get((i, "A"), {}).get("correcta")]
    empeoran = [i for i in ids if por.get((i, "A"), {}).get("correcta") and not por.get((i, "B"), {}).get("correcta")]
    iguales = [i for i in ids if i not in mejoran + empeoran]
    fuera = [f"{x['id']}-{x['modo']}" for x in filas if x["acceso_fuera_sandbox"]]
    md = ["# Comparación: Claude Code sin y con MCP y Skills", "",
          "Generado por `evaluacion/evaluar.py calificar` a partir de los logs de `evidencias_ia/evaluacion/logs/`.", "",
          "## Diseño", "",
          "| | |", "|---|---|",
          "| Preguntas | 10 (`preguntas.csv`): 4 BCRP, 4 ENAHO, 2 combinadas. Respuestas esperadas calculadas **antes** de correr con `esperadas_independientes.py` (API del BCRP con httpx y microdatos .dta leídos directamente; ENAHO contrastada con las cifras del INEI) |",
          f"| Modelo | `{MODELO}` (alias de Claude Code), el mismo en ambos modos |",
          "| Sesiones | Una sesión independiente por pregunta y modo (`claude -p --no-session-persistence`): 20 sesiones |",
          "| Instrucción | Idéntica en ambos modos (ver `INSTRUCCION` en `evaluar.py`): no estimar, decir «no sé» si no hay certeza, cerrar con `RESPUESTA FINAL` + JSON |",
          "| Aislamiento | Copia limpia por sesión, sin `salidas/`, `informes/`, `evaluacion/`, `agente/`, `figuras/` ni `mapas/`; sin ajustes de usuario (`--setting-sources project`) |",
          "| Corrección | Automática según `tolerancia_abs` y `texto_esperado` de `preguntas.csv`, fijados antes de correr; C2 además exige no afirmar causalidad |", "",
          "### Herramientas habilitadas", "",
          "| | Modo A: sin MCP ni Skills | Modo B: con MCP y Skills |", "|---|---|---|",
          "| Herramientas generales | Bash, Read, Glob, Grep | Las mismas |",
          "| Servidor MCP `bcrp` | No (`--strict-mcp-config`, sin `.mcp.json`) | Sí |",
          "| Skills del proyecto | No (`--disable-slash-commands`, Skill bloqueada, sin `.claude/`) | Sí (`.claude/skills/`) |",
          "| Web (WebSearch, WebFetch) | Bloqueada | Bloqueada |",
          "| Datos en la copia | Zips ENAHO 2024 y GeoJSON | Los mismos + catálogo del BCRP y `referencias/` |",
          "| Entorno de Python | El del proyecto (`UV_PROJECT_ENVIRONMENT`) | El mismo |", "",
          "El Modo A **no** es «Claude sin herramientas»: tiene Bash, por lo que puede llamar a la API pública del BCRP con `curl` o `httpx` y procesar los zips de la ENAHO por su cuenta. La comparación mide el valor de los componentes especializados, no el de tener o no acceso a datos.", "",
          "## Resultados", "",
          "| | Modo A | Modo B |", "|---|---:|---:|",
          f"| Correctas | {a['ok']}/{a['n']} | {b['ok']}/{b['n']} |",
          f"| Incorrectas | {a['inc']} | {b['inc']} |",
          f"| No contestadas / sin formato | {a['nc']} | {b['nc']} |",
          f"| Tiempo promedio por pregunta (s) | {a['seg']:.1f} | {b['seg']:.1f} |",
          f"| Costo total (USD) | {a['costo']:.2f} | {b['costo']:.2f} |",
          f"| Sesiones que usaron MCP | {a['mcp']} | {b['mcp']} |",
          f"| Sesiones que usaron Skills | {a['skills']} | {b['skills']} |", "",
          "### Por pregunta", "", "| Id | Tipo | Esperado | Modo A | Modo B | Herramientas B |", "|---|---|---|---|---|---|"]
    for i in ids:
        xa, xb = por.get((i, "A")), por.get((i, "B"))
        sa = f"{'✔' if xa['correcta'] else '✘'} {xa['estado']} ({xa['segundos']:.0f}s)" if xa else "—"
        sb = f"{'✔' if xb['correcta'] else '✘'} {xb['estado']} ({xb['segundos']:.0f}s)" if xb else "—"
        md.append(f"| {i} | {(xa or xb)['tipo']} | {(xa or xb)['respuesta_esperada']} | {sa} | {sb} | {xb['herramientas'].replace(' | ', ', ') if xb else ''} |")
    md += ["", f"- **Mejoraron con MCP/Skills:** {', '.join(mejoran) or 'ninguna'}",
           f"- **Empeoraron:** {', '.join(empeoran) or 'ninguna'}",
           f"- **Sin cambio (mismo resultado en ambos modos):** {', '.join(iguales) or 'ninguna'}",
           f"- **Accesos fuera de la carpeta aislada detectados en los logs:** {', '.join(fuera) or 'ninguno'}", ""]
    conc = EVAL / "conclusion.md"
    if conc.exists():
        md += [conc.read_text(encoding="utf-8")]
    (EVAL / "comparacion.md").write_text("\n".join(md), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("accion", choices=["ejecutar", "calificar"])
    ap.add_argument("--ids", default="")
    ap.add_argument("--modos", default="A,B")
    a = ap.parse_args()
    if a.accion == "calificar":
        return calificar()
    ids = set(a.ids.split(",")) if a.ids else None
    for p in preguntas():
        if ids and p["id"] not in ids:
            continue
        for modo in a.modos.split(","):
            ejecutar_una(p, modo)


if __name__ == "__main__":
    main()
