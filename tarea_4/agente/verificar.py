"""Verificación independiente de cifras del informe (no usa el MCP ni las Skills).

    uv run agente/verificar.py

Recalcula tres afirmaciones por otro camino y escribe informes/verificacion_cifras.md:
  1. Crédito total 2024 y tasa de referencia dic-2024: API del BCRP con httpx, sin pasar por el MCP.
  2. Pobreza nacional y de Cajamarca: microdatos .dta leídos directamente + referencias oficiales (INEI / Sesión 16).
  3. Correlación de Spearman: scipy.stats.spearmanr sobre el CSV del cruce.
"""
import json
import re
from pathlib import Path

import httpx
import pandas as pd
from scipy.stats import spearmanr

RAIZ = Path(__file__).resolve().parent.parent
API = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"


def bcrp(codigo, desde, hasta):
    txt = httpx.get(f"{API}/{codigo}/json/{desde}/{hasta}", timeout=60).text
    js = json.loads(txt[re.search(r'\{\s*"config"', txt).start():])
    return {p["name"]: float(p["values"][0]) for p in js["periods"]}


def main():
    res = json.loads((RAIZ / "salidas" / "resultados_investigacion.json").read_text(encoding="utf-8"))
    ind = pd.read_csv(RAIZ / "salidas" / "indicadores.csv", dtype={"codigo": str})
    cruce = pd.read_csv(RAIZ / "salidas" / "credito_pobreza_departamento.csv", dtype={"codigo": str})
    filas = []

    # 1a. crédito total 2024
    informe = res["bcrp"]["credito_resumen"]["ultimo"]["valor"]
    directo = bcrp("RD16202DA", "2024", "2024")["2024"]
    filas.append(("Crédito directo total a fines de 2024 (millones de S/)", f"{informe:,.2f}", f"{directo:,.2f}",
                  "API del BCRP con httpx, serie RD16202DA, sin MCP", abs(informe - directo) < 0.01, f"{informe - directo:+.4f}"))
    suma_dep = cruce.credito_2024_mill_soles.sum()
    filas.append(("Suma de los 25 departamentos = total nacional (millones de S/)", f"{suma_dep:,.2f}", f"{directo:,.2f}",
                  "Suma de las series departamentales vs total nacional del BCRP", abs(suma_dep - directo) < 0.5, f"{suma_dep - directo:+.3f}"))
    # 1b. tasa de referencia dic-2024
    informe = res["bcrp"]["tasa_ref_resumen"]["ultimo"]["valor"]
    directo = next(iter(bcrp("PD04722MM", "2024-12", "2024-12").values()))
    filas.append(("Tasa de referencia a dic-2024 (%)", f"{informe:.2f}", f"{directo:.2f}", "API del BCRP con httpx, serie PD04722MM",
                  abs(informe - directo) < 0.005, f"{informe - directo:+.3f}"))

    # 2. pobreza desde los .dta, sin las Skills
    dta = next((RAIZ / "datos").rglob("sumaria-2024.dta"))
    s = pd.read_stata(dta, convert_categoricals=False)
    s.columns = [c.lower() for c in s.columns]
    w = s.factor07 * s.mieperho
    nac = float((w * (s.pobreza <= 2)).sum() / w.sum() * 100)
    informe = float(ind[ind.nivel == "nacional"].pobreza_pct.iloc[0])
    filas.append(("Pobreza monetaria nacional 2024 (%)", f"{informe:.2f}", f"{nac:.2f}",
                  "Lectura directa de sumaria-2024.dta con factor07 × mieperho (sin Skills). Referencia INEI: 27.6 %", abs(informe - nac) < 0.01, f"{informe - nac:+.3f}"))
    ref = pd.read_csv(RAIZ / "referencias" / "pobreza_departamento_2024.csv", dtype={"ccdd": str}).set_index("ccdd")
    caj = float(cruce.loc[cruce.codigo == "06", "pobreza_pct"].iloc[0])
    filas.append(("Pobreza en Cajamarca 2024 (%)", f"{caj:.2f}", f"{ref.loc['06', 'pobreza_pct']:.1f}",
                  "Referencia de la Sesión 16 (redondeada a 1 decimal)", abs(caj - ref.loc["06", "pobreza_pct"]) <= 0.1,
                  f"{caj - ref.loc['06', 'pobreza_pct']:+.2f}"))

    # 3. Spearman con scipy
    r, p = spearmanr(cruce.credito_pc_2024_soles, cruce.pobreza_pct)
    informe = res["correlaciones"]["principal"]["spearman"]
    filas.append(("Spearman crédito per cápita vs pobreza (n=25)", f"{informe:+.3f}", f"{r:+.3f}",
                  "scipy.stats.spearmanr sobre salidas/credito_pobreza_departamento.csv", abs(informe - r) < 0.001, f"{informe - r:+.4f}"))

    # 4. pendiente de la regresión simple con scipy.stats.linregress
    import numpy as np
    from scipy.stats import linregress
    lr = linregress(np.log(cruce.credito_pc_2024_soles), cruce.pobreza_pct)
    informe = res["correlaciones"]["robustez"]["ols_credito"]["coef"]["ln_credito_pc"]["beta"]
    filas.append(("Pendiente de pobreza sobre ln(crédito per cápita)", f"{informe:+.3f}", f"{lr.slope:+.3f}",
                  "scipy.stats.linregress sobre el CSV del cruce", abs(informe - lr.slope) < 0.001, f"{informe - lr.slope:+.4f}"))

    md = ["# Verificación independiente de cifras del informe", "",
          "Cada afirmación se recalculó por un camino distinto al del agente (sin el MCP ni las Skills). Generado por `agente/verificar.py`.", "",
          "| Afirmación del informe | Valor del informe | Valor verificado | Procedimiento | ¿Coincide? | Diferencia |", "|---|---:|---:|---|:---:|---:|"]
    for a, i, v, pr, ok, d in filas:
        md.append(f"| {a} | {i} | {v} | {pr} | {'Sí' if ok else 'NO'} | {d} |")
    md += ["", f"Resultado: {sum(f[4] for f in filas)}/{len(filas)} verificaciones coinciden.", "",
           "## Comprobación manual de la estudiante (8 de noviembre de 2026)", "",
           "Comprobadas a mano, abriendo la fuente en el navegador o el archivo de validación, y comparando con el informe.", "",
           "| Afirmación del informe | Valor del informe | Fuente o procedimiento | ¿Coincide? | Diferencia observada |", "|---|---:|---|:---:|---|",
           "| Crédito directo total a fines de 2024 (millones de S/) | 407,351.74 | API del BCRP en el navegador: `.../api/RD16202DA/json/2024/2024` | Sí | Ninguna |",
           "| Tasa de referencia a dic-2024 (%) | 5.00 | API del BCRP en el navegador: `.../api/PD04722MM/json/2024-12/2024-12` | Sí | Ninguna |",
           "| Pobreza monetaria nacional 2024 (%) | 27.58 | `salidas/validacion.txt` frente al 27.6 % de referencia del enunciado | Sí | 0.02 pp, por redondeo de la referencia |", ""]
    (RAIZ / "informes" / "verificacion_cifras.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
