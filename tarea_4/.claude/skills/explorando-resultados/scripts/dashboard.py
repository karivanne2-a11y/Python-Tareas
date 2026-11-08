"""Dashboard interactivo (HTML + Plotly) con los resultados BCRP × ENAHO por departamento.

    uv run .claude/skills/explorando-resultados/scripts/dashboard.py

Entra : salidas/credito_pobreza_departamento.csv (lo genera agente/investigar.py), datos/peru_departamental_simple.geojson
Sale  : dashboard/index.html (se abre en cualquier navegador; Plotly se carga desde CDN)
Todo se lee de los CSV: ninguna cifra se escribe a mano.
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

VARIABLES = {
    "pobreza_pct": "Pobreza monetaria 2024 (%)",
    "pobreza_extrema_pct": "Pobreza extrema 2024 (%)",
    "credito_pc_2024_soles": "Crédito por habitante 2024 (S/)",
    "pct_poblacion_rural": "Población rural (%)",
    "crecimiento_nominal_2020_2024_pct": "Crecimiento nominal del crédito 2020-2024 (%)",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="salidas/credito_pobreza_departamento.csv")
    ap.add_argument("--geojson", default="datos/peru_departamental_simple.geojson")
    ap.add_argument("--salida", default="dashboard/index.html")
    a = ap.parse_args()
    if not Path(a.csv).exists():
        sys.exit(f"ERROR: falta {a.csv}. Ejecuten primero `uv run agente/investigar.py` (MCP + Skills).")
    df = pd.read_csv(a.csv, dtype={"codigo": str})
    geo = json.loads(Path(a.geojson).read_text(encoding="utf-8"))
    for f in geo["features"]:
        f["properties"]["FIRST_IDDP"] = str(f["properties"]["FIRST_IDDP"]).zfill(2)
    assert len(df) == 25 and set(df.codigo) == {f["properties"]["FIRST_IDDP"] for f in geo["features"]}, "deben ser 25 códigos iguales"

    # --- mapa con selector de variable
    claves = list(VARIABLES)
    mapa = go.Figure()
    for i, k in enumerate(claves):
        mapa.add_trace(go.Choropleth(
            geojson=geo, featureidkey="properties.FIRST_IDDP", locations=df.codigo, z=df[k], text=df.departamento,
            colorscale="OrRd", marker_line_color="white", marker_line_width=0.5, visible=(i == 0),
            colorbar={"title": VARIABLES[k]}, hovertemplate="<b>%{text}</b><br>" + VARIABLES[k] + ": %{z:,.1f}<extra></extra>"))
    mapa.update_geos(fitbounds="locations", visible=False)
    mapa.update_layout(
        margin={"l": 0, "r": 0, "t": 40, "b": 0}, height=620,
        updatemenus=[{"buttons": [{"label": VARIABLES[k], "method": "update", "args": [{"visible": [j == i for j in range(len(claves))]}]}
                                  for i, k in enumerate(claves)], "x": 0, "y": 1.12, "xanchor": "left"}])

    # --- dispersión con selector de eje x
    dis = go.Figure()
    for k in ("credito_pc_2024_soles", "pct_poblacion_rural", "crecimiento_nominal_2020_2024_pct"):
        dis.add_trace(go.Scatter(
            x=df[k], y=df.pobreza_pct, mode="markers+text", text=df.departamento, textposition="top center", textfont={"size": 9},
            marker={"size": (df.poblacion_enaho / 1.2e5 + 8), "color": "#8c2d04", "opacity": 0.75}, visible=(k == "credito_pc_2024_soles"),
            hovertemplate="<b>%{text}</b><br>x: %{x:,.1f}<br>pobreza: %{y:.1f}%<extra></extra>"))
    xs = ["credito_pc_2024_soles", "pct_poblacion_rural", "crecimiento_nominal_2020_2024_pct"]
    dis.update_layout(
        height=560, yaxis_title="Pobreza monetaria 2024 (%)", xaxis_title=VARIABLES[xs[0]], yaxis_rangemode="tozero",
        xaxis_type="log", margin={"t": 40},
        updatemenus=[{"buttons": [{"label": VARIABLES[k], "method": "update",
                                   "args": [{"visible": [j == i for j in range(3)]},
                                            {"xaxis.title.text": VARIABLES[k], "xaxis.type": "log" if k == "credito_pc_2024_soles" else "linear"}]}
                                  for i, k in enumerate(xs)], "x": 0, "y": 1.12, "xanchor": "left"}])

    # --- tabla ordenable
    tabla = go.Figure(go.Table(
        header={"values": ["Departamento"] + [VARIABLES[k] for k in claves], "fill_color": "#8c2d04", "font": {"color": "white"}},
        cells={"values": [df.departamento] + [df[k].round(1) for k in claves], "align": "left"}))
    tabla.update_layout(height=700, margin={"t": 10})

    rho = df.credito_pc_2024_soles.corr(df.pobreza_pct, method="spearman")
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Crédito y pobreza por departamento – BCRP × ENAHO 2024</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1100px;margin:auto;padding:16px;color:#222}}h1{{font-size:1.4rem}}
h2{{font-size:1.1rem;margin-top:28px}}.nota{{color:#555;font-size:.85rem}}</style></head><body>
<h1>Crédito del sistema financiero (BCRP) y pobreza monetaria (ENAHO 2024) por departamento</h1>
<p>Correlación de Spearman entre crédito por habitante y pobreza: <b>{rho:+.2f}</b> (n = {len(df)}). Es una asociación descriptiva, no causal.
Use el menú de cada gráfico para cambiar la variable.</p>
<h2>Mapa</h2>{mapa.to_html(full_html=False, include_plotlyjs="cdn")}
<h2>Pobreza frente a crédito, ruralidad y crecimiento del crédito (tamaño = población)</h2>{dis.to_html(full_html=False, include_plotlyjs=False)}
<h2>Datos</h2>{tabla.to_html(full_html=False, include_plotlyjs=False)}
<p class="nota">Fuentes: BCRP (series de crédito directo por departamento, RD16127DA…RD16199DA, consultadas por el servidor MCP del proyecto) e INEI, ENAHO 2024
(módulos 34 y 02; pobreza por hogares con factor07 × mieperho). Crédito nominal, fin de periodo; población estimada con la ENAHO. Generado desde {a.csv}.</p>
</body></html>"""
    out = Path(a.salida)
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Guardado {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
