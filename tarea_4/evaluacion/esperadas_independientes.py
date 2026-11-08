"""Construye evaluacion/preguntas.csv con respuestas esperadas obtenidas por vías INDEPENDIENTES del agente.

    uv run evaluacion/esperadas_independientes.py

- BCRP: API oficial consultada directamente con httpx (no pasa por el MCP).
- ENAHO: microdatos .dta leídos directamente (no pasa por las Skills) y contrastados con las cifras publicadas
  por el INEI / la Sesión 16 (27.6 %, 24.8 %, 39.3 %, 5.5 %, 108,664).
Se ejecuta ANTES de correr los dos modos y no se modifica después de ver las respuestas.
"""
import csv
import json
import re
from pathlib import Path

import httpx
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
API = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"


def bcrp(codigo, desde, hasta):
    t = httpx.get(f"{API}/{codigo}/json/{desde}/{hasta}", timeout=60).text
    js = json.loads(t[re.search(r'\{\s*"config"', t).start():])
    return [(p["name"], float(p["values"][0])) for p in js["periods"] if p["values"][0] != "n.d."]


def main():
    # --- BCRP directo
    ipc = bcrp("PN01273PM", "2020-1", "2024-12")
    ipc_dic24 = dict(ipc)["Dic.2024"]
    mes_max, v_max = max(ipc, key=lambda x: x[1])
    credito_total = dict(bcrp("RD16202DA", "2024", "2024"))["2024"]
    tasa_dic24 = bcrp("PD04722MM", "2024-12", "2024-12")[0][1]

    # --- ENAHO directo desde los .dta
    sumaria = next((RAIZ / "datos").rglob("sumaria-2024.dta"))
    s = pd.read_stata(sumaria, convert_categoricals=False)
    s.columns = [c.lower() for c in s.columns]
    s["ubigeo"] = s.ubigeo.astype(str).str.zfill(6)
    w = s.factor07 * s.mieperho
    pobre = (s.pobreza <= 2).astype(int)
    nac = (w * pobre).sum() / w.sum() * 100
    rural = s.estrato.astype(float) > 5
    rur = (w[rural] * pobre[rural]).sum() / w[rural].sum() * 100
    ext = (w * (s.pobreza == 1)).sum() / w.sum() * 100
    m2 = next((RAIZ / "datos").rglob("Enaho01-2024-200.dta"), None) or next((RAIZ / "datos").rglob("enaho01-2024-200.dta"))
    p = pd.read_stata(m2, convert_categoricals=False)
    p.columns = [c.lower() for c in p.columns]
    for c in ("p204", "p205", "p206"):
        p[c] = pd.to_numeric(p[c], errors="coerce")
    residentes = int((((p.p204 == 1) & (p.p205 == 2)) | ((p.p204 == 2) & (p.p206 == 1))).sum())
    # crédito per cápita de Lima 2024 (población = suma de factor07 × mieperho de la sumaria, ubigeo[:2] == '15')
    pob_lima = float(w[s.ubigeo.str[:2] == "15"].sum())
    credito_lima = dict(bcrp("RD16169DA", "2024", "2024"))["2024"]
    pc_lima = credito_lima * 1e6 / pob_lima
    # departamento con más crédito per cápita y su pobreza
    pcs = {}
    for cc in range(1, 26):
        pob = float(w[s.ubigeo.str[:2] == f"{cc:02d}"].sum())
        pcs[cc] = dict(bcrp(f"RD{16127 + 3 * (cc - 1)}DA", "2024", "2024"))["2024"] * 1e6 / pob
    top = max(pcs, key=pcs.get)
    pob_top = float((w * pobre)[s.ubigeo.str[:2] == f"{top:02d}"].sum() / w[s.ubigeo.str[:2] == f"{top:02d}"].sum() * 100)

    # contraste de ENAHO con lo publicado por el INEI (tolerancia de redondeo)
    for nombre, calc, publicado in (("nacional", nac, 27.6), ("rural", rur, 39.3), ("extrema", ext, 5.5), ("residentes", residentes, 108664)):
        assert abs(calc - publicado) <= (0.1 if nombre != "residentes" else 0), (nombre, calc, publicado)

    filas = [
        ("B1", "BCRP", "Según el BCRP, ¿cuál fue la variación porcentual a 12 meses del IPC de Lima Metropolitana en diciembre de 2024?",
         f"{ipc_dic24:.2f} %", f"{ipc_dic24:.4f}", "", 0.01, "API del BCRP, serie PN01273PM, consulta directa con httpx", ""),
        ("B2", "BCRP", "Entre enero de 2020 y diciembre de 2024, ¿cuál fue el valor máximo de la inflación a 12 meses de Lima Metropolitana según el BCRP y en qué mes ocurrió?",
         f"{v_max:.2f} % en {mes_max}", f"{v_max:.4f}", "2022;jun|-06", 0.01, "API del BCRP, serie PN01273PM, máximo del rango", ""),
        ("B3", "BCRP", "Según el BCRP, ¿cuánto fue el crédito directo del sistema financiero al sector privado, total nacional, a fines de 2024, en millones de soles?",
         f"{credito_total:,.2f} millones de S/", f"{credito_total:.2f}", "", 500, "API del BCRP, serie RD16202DA, consulta directa", ""),
        ("B4", "BCRP", "¿Cuál era la tasa de referencia de la política monetaria del BCRP en diciembre de 2024, en porcentaje?",
         f"{tasa_dic24:.2f} %", f"{tasa_dic24:.4f}", "", 0.005, "API del BCRP, serie PD04722MM, consulta directa", ""),
        ("E1", "ENAHO", "Según la ENAHO 2024 del INEI, ¿cuál fue la pobreza monetaria nacional en 2024, en porcentaje?",
         "27.6 %", "27.6", "", 0.1, f"INEI (27.6 %); recalculado de sumaria-2024.dta con factor07×mieperho: {nac:.2f} %", ""),
        ("E2", "ENAHO", "En la ENAHO 2024 (módulo 02), ¿cuántas personas son residentes habituales? Residente habitual: ((p204==1)&(p205==2)) | ((p204==2)&(p206==1)).",
         "108,664", "108664", "", 0, f"Recalculado de Enaho01-2024-200.dta: {residentes:,}; Sesión 16", ""),
        ("E3", "ENAHO", "Según la ENAHO 2024, ¿cuál fue la pobreza monetaria en el área rural (estrato > 5), en porcentaje?",
         "39.3 %", "39.3", "", 0.1, f"INEI (39.3 %); recalculado de la sumaria: {rur:.2f} %", ""),
        ("E4", "ENAHO", "Según la ENAHO 2024, ¿cuál fue la pobreza monetaria extrema nacional, en porcentaje?",
         "5.5 %", "5.5", "", 0.1, f"INEI / Sesión 16 (5.5 %); recalculado de la sumaria: {ext:.2f} %", ""),
        ("C1", "Combinada", "Con el crédito directo total de Lima a fines de 2024 (BCRP, serie del departamento de Lima) y la población de Lima estimada con la ENAHO 2024 (suma de factor07×mieperho de la sumaria, ubigeo que empieza con 15), ¿cuál es el crédito por habitante de Lima, en soles?",
         f"S/ {pc_lima:,.0f} por habitante", f"{pc_lima:.2f}", "", round(pc_lima * 0.01, 2), f"BCRP RD16169DA / suma de factor07×mieperho en sumaria-2024.dta: {credito_lima:,.2f} millones / {pob_lima:,.0f} personas", "Tolerancia 1 %."),
        ("C2", "Combinada", "Con el crédito directo a fines de 2024 (BCRP, por departamento) y la población de la ENAHO 2024 (suma de factor07×mieperho): ¿qué departamento tenía el mayor crédito por habitante y cuál era su pobreza monetaria 2024 (ENAHO, %)? ¿Se puede concluir con esto que el crédito reduce la pobreza?",
         f"{'Lima' if top == 15 else top}: pobreza {pob_top:.1f} %. No se puede concluir causalidad", f"{pob_top:.2f}", "lima", 0.1, "Cálculo independiente (API BCRP + sumaria .dta)", "Debe indicar que es una asociación descriptiva y no afirmar causalidad."),
    ]
    assert top == 15
    out = RAIZ / "evaluacion" / "preguntas.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        wri = csv.writer(f)
        wri.writerow(["id", "tipo", "pregunta", "respuesta_esperada", "valores_esperados", "texto_esperado", "tolerancia_abs",
                      "fuente_verificacion", "criterio_interpretacion"])
        wri.writerows(filas)
    print(f"{len(filas)} preguntas escritas en {out}")
    for r in filas:
        print(r[0], "|", r[3], "|", r[7])


if __name__ == "__main__":
    main()
