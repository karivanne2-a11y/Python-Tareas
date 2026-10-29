"""Mide si el MCP del INEI ayuda: Claude de memoria contra Claude con el servidor.

Lee preguntas.csv (columna `verdad` llenada a mano), le hace cada pregunta a
Claude Code dos veces — sin MCP y con MCP — y escribe resultados.csv y
grafico.png.

    uv run evaluar.py                 # las dos modalidades
    uv run evaluar.py --modos memoria # solo una
    uv run evaluar.py --modelo sonnet

Requiere el CLI de Claude Code en el PATH (`claude --version`).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).parent
PREGUNTAS = AQUI / "preguntas.csv"
RESULTADOS = AQUI / "resultados.csv"
GRAFICO = AQUI / "grafico.png"
CONFIG_MCP = AQUI / ".mcp.json"

TOLERANCIA = 0.02  # 2 % de holgura relativa para dar una cifra por acertada

INSTRUCCION = (
    "Responde solo con la cifra pedida, en números, sin unidades ni texto. "
    "Si no la sabes con certeza, responde exactamente: null"
)


def leer_preguntas() -> list[dict]:
    if not PREGUNTAS.exists():
        sys.exit(f"Falta {PREGUNTAS.name}.")
    with PREGUNTAS.open(encoding="utf-8") as f:
        filas = [x for x in csv.DictReader(f) if (x.get("pregunta") or "").strip()]
    sin_verdad = [x["id"] for x in filas if not (x.get("verdad") or "").strip()]
    if sin_verdad:
        sys.exit(
            f"Estas preguntas no tienen verdad verificada a mano: {', '.join(sin_verdad)}.\n"
            "Llena la columna `verdad` (y `fuente_url`) antes de evaluar."
        )
    return filas


def preguntar(pregunta: str, con_mcp: bool, modelo: str) -> str:
    """Una pregunta a Claude Code, en modo no interactivo."""
    cmd = ["claude", "-p", f"{pregunta}\n\n{INSTRUCCION}", "--model", modelo]
    if con_mcp:
        cmd += ["--mcp-config", str(CONFIG_MCP), "--strict-mcp-config"]
    else:
        cmd += ["--strict-mcp-config", "--mcp-config", "{}"]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        sys.exit("No encuentro el CLI `claude` en el PATH.")
    except subprocess.TimeoutExpired:
        return "timeout"
    if r.returncode != 0:
        return f"error: {r.stderr.strip()[:200]}"
    return r.stdout.strip()


def a_numero(texto: str) -> float | None:
    """Primera cifra de la respuesta. None si contestó null o no hay número."""
    t = (texto or "").strip().lower()
    if not t or t.startswith(("null", "no ", "error", "timeout")):
        return None
    m = re.search(r"-?\d[\d\s.,]*", t.replace("%", ""))
    if not m:
        return None
    crudo = m.group(0).strip().replace(" ", "")
    if "," in crudo and "." in crudo:
        crudo = (
            crudo.replace(".", "").replace(",", ".")
            if crudo.rfind(",") > crudo.rfind(".")
            else crudo.replace(",", "")
        )
    elif "," in crudo:
        crudo = crudo.replace(",", ".")
    try:
        return float(crudo)
    except ValueError:
        return None


def acierta(dada: float | None, verdad: float) -> bool:
    if dada is None:
        return False
    if verdad == 0:
        return abs(dada) <= TOLERANCIA
    return abs(dada - verdad) / abs(verdad) <= TOLERANCIA


def graficar(filas: list[dict], modos: list[str]) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib no está instalado; me salto grafico.png")
        return

    etiquetas = {"memoria": "Sin MCP", "mcp": "Con MCP"}
    aciertos, nulos, errados = [], [], []
    for modo in modos:
        de_este = [f for f in filas if f["modo"] == modo]
        aciertos.append(sum(1 for f in de_este if f["acierta"] == "si"))
        nulos.append(sum(1 for f in de_este if f["respuesta_num"] == ""))
        errados.append(len(de_este) - aciertos[-1] - nulos[-1])

    x = range(len(modos))
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(x, aciertos, label="Acierta", color="#2a7f62")
    ax.bar(x, errados, bottom=aciertos, label="Se equivoca", color="#b4452f")
    ax.bar(
        x,
        nulos,
        bottom=[a + e for a, e in zip(aciertos, errados)],
        label="Dice null",
        color="#bdb6a8",
    )
    ax.set_xticks(list(x), [etiquetas.get(m, m) for m in modos])
    ax.set_ylabel("Preguntas")
    ax.set_title("Claude con y sin el MCP del INEI")
    ax.legend()
    fig.tight_layout()
    fig.savefig(GRAFICO, dpi=150)
    print(f"Figura en {GRAFICO.name}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--modos", nargs="+", default=["memoria", "mcp"], choices=["memoria", "mcp"])
    p.add_argument("--modelo", default="sonnet")
    args = p.parse_args()

    preguntas = leer_preguntas()
    filas: list[dict] = []

    for modo in args.modos:
        for q in preguntas:
            bruta = preguntar(q["pregunta"], con_mcp=(modo == "mcp"), modelo=args.modelo)
            num = a_numero(bruta)
            verdad = a_numero(q["verdad"])
            ok = acierta(num, verdad) if verdad is not None else False
            filas.append(
                {
                    "id": q["id"],
                    "modo": modo,
                    "pregunta": q["pregunta"],
                    "verdad": q["verdad"],
                    "respuesta_bruta": bruta.replace("\n", " ")[:300],
                    "respuesta_num": "" if num is None else num,
                    "acierta": "si" if ok else "no",
                    "fuente_url": q.get("fuente_url", ""),
                }
            )
            print(f"[{modo}] {q['id']}: {num} (verdad {verdad}) → {'ok' if ok else 'no'}")

    with RESULTADOS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    print(f"\nTabla en {RESULTADOS.name}")

    for modo in args.modos:
        de_este = [f for f in filas if f["modo"] == modo]
        ok = sum(1 for f in de_este if f["acierta"] == "si")
        print(f"  {modo}: {ok} de {len(de_este)} aciertos")

    graficar(filas, args.modos)


if __name__ == "__main__":
    main()
