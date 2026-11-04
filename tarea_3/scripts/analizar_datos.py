"""Calcula los indicadores y hallazgos y exporta los datos del dashboard.

Salidas:
- datos/procesados/hallazgos.json   cifras que respaldan los hallazgos del README y del reel
- datos/procesados/precio_volumen.csv  descomposición del crecimiento 2015-2025
- web/data/datos.json               datos compactos que lee el dashboard

Uso:  uv run python scripts/analizar_datos.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
PROC = RAIZ / "datos" / "procesados"
WEB = RAIZ / "web" / "data"
WEB.mkdir(parents=True, exist_ok=True)

# Nombres en español de los principales destinos (el resto queda en inglés)
PAISES_ES = {
    "USA": "Estados Unidos", "NLD": "Países Bajos", "ESP": "España", "GBR": "Reino Unido",
    "CHN": "China", "CAN": "Canadá", "DEU": "Alemania", "FRA": "Francia", "BEL": "Bélgica",
    "ITA": "Italia", "JPN": "Japón", "KOR": "Corea del Sur", "CHL": "Chile", "MEX": "México",
    "COL": "Colombia", "ECU": "Ecuador", "BRA": "Brasil", "RUS": "Rusia", "HKG": "Hong Kong",
    "TWN": "Taiwán", "THA": "Tailandia", "IDN": "Indonesia", "MYS": "Malasia", "SGP": "Singapur",
    "SAU": "Arabia Saudita", "ARE": "Emiratos Árabes", "IND": "India", "CRI": "Costa Rica",
    "PAN": "Panamá", "GTM": "Guatemala", "HND": "Honduras", "SWE": "Suecia", "CHE": "Suiza",
    "POL": "Polonia", "PRT": "Portugal", "IRL": "Irlanda", "DNK": "Dinamarca", "NOR": "Noruega",
    "FIN": "Finlandia", "AUS": "Australia", "NZL": "Nueva Zelanda", "PHL": "Filipinas",
    "VNM": "Vietnam", "ARG": "Argentina", "BOL": "Bolivia", "URY": "Uruguay", "PRY": "Paraguay",
    "VEN": "Venezuela", "DOM": "República Dominicana", "EST": "Estonia", "LTU": "Lituania",
    "UKR": "Ucrania", "TUR": "Turquía", "ISR": "Israel", "MAR": "Marruecos", "EGY": "Egipto",
    "ZAF": "Sudáfrica", "BGD": "Bangladés", "AUT": "Austria", "GRC": "Grecia", "CZE": "Chequia",
}


def descomponer(prod, a0=2015, a1=2025):
    """Crecimiento del valor = efecto volumen + efecto precio (en logaritmos)."""
    filas = []
    for p, g in prod.groupby("producto"):
        g = g.set_index("anio")
        if a0 not in g.index or a1 not in g.index:
            continue
        v0, v1 = g.loc[a0, "valor_usd"], g.loc[a1, "valor_usd"]
        k0, k1 = g.loc[a0, "peso_kg"], g.loc[a1, "peso_kg"]
        if min(v0, v1, k0, k1) <= 0 or np.isnan([k0, k1]).any():
            continue
        dv, dk = np.log(v1 / v0), np.log(k1 / k0)
        filas.append({"producto": p, "valor_2015": v0, "valor_2025": v1,
                      "crec_valor_pct": 100 * (v1 / v0 - 1),
                      "parte_volumen_pct": 100 * dk / dv if dv else np.nan,
                      "parte_precio_pct": 100 * (dv - dk) / dv if dv else np.nan,
                      "precio_2015": v0 / k0, "precio_2025": v1 / k1,
                      "crec_volumen_pct": 100 * (k1 / k0 - 1),
                      "crec_precio_pct": 100 * ((v1 / k1) / (v0 / k0) - 1)})
    return pd.DataFrame(filas).round(2)


def main():
    prod = pd.read_csv(PROC / "productos_anual.csv", dtype={"hs": str})
    dest = pd.read_csv(PROC / "destinos.csv", dtype={"hs": str})
    tot = pd.read_csv(PROC / "agro_vs_total.csv")

    # --- Hallazgo 1: el arándano pasa de cero a líder de la canasta
    pv = prod.pivot(index="anio", columns="producto", values="valor_usd")
    ranking_2025 = pv.loc[2025].sort_values(ascending=False)
    canasta = pv.sum(axis=1)

    # --- Hallazgo 2: concentración de destinos (2025, nueve productos)
    d25 = dest[dest.anio == 2025].groupby("iso3").valor_usd.sum().sort_values(ascending=False)
    cuota = d25 / d25.sum()
    hhi = float((cuota ** 2).sum() * 10000)
    d15 = dest[dest.anio == 2015].groupby("iso3").valor_usd.sum()
    cuota15 = d15 / d15.sum()

    # --- Hallazgo 3: ¿volumen o precio?
    pvol = descomponer(prod)
    pvol.to_csv(PROC / "precio_volumen.csv", index=False)

    hallazgos = {
        "canasta_2010_musd": round(canasta[2010] / 1e6, 1),
        "canasta_2025_musd": round(canasta[2025] / 1e6, 1),
        "canasta_crec_veces": round(canasta[2025] / canasta[2010], 2),
        "arandano_2012_musd": round(pv.loc[2012, "Arándano"] / 1e6, 2),
        "arandano_2025_musd": round(pv.loc[2025, "Arándano"] / 1e6, 1),
        "ranking_2025_musd": (ranking_2025 / 1e6).round(1).to_dict(),
        "top3_frutas_pct_canasta_2025": round(100 * pv.loc[2025, ["Arándano", "Uva fresca", "Palta"]].sum() / canasta[2025], 1),
        "top3_frutas_pct_canasta_2010": round(100 * pv.loc[2010, ["Arándano", "Uva fresca", "Palta"]].sum() / canasta[2010], 1),
        "destinos_top5_2025_pct": (100 * cuota.head(5)).round(1).to_dict(),
        "usa_nld_pct_2025": round(100 * (cuota.get("USA", 0) + cuota.get("NLD", 0)), 1),
        "usa_nld_pct_2015": round(100 * (cuota15.get("USA", 0) + cuota15.get("NLD", 0)), 1),
        "hhi_destinos_2025": round(hhi),
        "n_paises_2025": int((d25 > 0).sum()),
        "precio_volumen": pvol.set_index("producto")[["crec_valor_pct", "crec_volumen_pct", "crec_precio_pct", "parte_precio_pct"]].to_dict("index"),
        "pct_agro_total_2010": float(tot.loc[tot.anio == 2010, "pct_agro"].iloc[0]),
        "pct_agro_total_2025": float(tot.loc[tot.anio == 2025, "pct_agro"].iloc[0]),
        "agro_total_2025_musd": round(float(tot.loc[tot.anio == 2025, "export_agro_comtrade"].iloc[0]) / 1e6, 1),
    }
    (PROC / "hallazgos.json").write_text(json.dumps(hallazgos, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- Datos para el dashboard (compactos: valores en millones US$)
    nombres = dest.drop_duplicates("iso3").set_index("iso3").pais_en.to_dict()
    web = {
        "productos": prod.assign(v=(prod.valor_usd / 1e6).round(3),
                                 t=(prod.peso_kg / 1e6).round(3),
                                 p=prod.precio_usd_kg.round(3))
                         [["anio", "producto", "hs", "v", "t", "p"]]
                         .rename(columns={"anio": "a", "producto": "n"}).to_dict("records"),
        "destinos": dest.assign(v=(dest.valor_usd / 1e6).round(5), t=(dest.peso_kg / 1e6).round(5))
                        [["anio", "producto", "iso3", "v", "t"]]
                        .rename(columns={"anio": "a", "producto": "n", "iso3": "c"})
                        .query("v > 0").to_dict("records"),
        "paises": {k: PAISES_ES.get(k, v) for k, v in nombres.items()},
        "totales": tot.assign(agro=(tot.export_agro_comtrade / 1e6).round(1),
                              total=(tot.export_total_comtrade / 1e6).round(1),
                              bcrp=(tot.export_total_bcrp / 1e6).round(1))
                      [["anio", "agro", "total", "bcrp", "pct_agro"]]
                      .rename(columns={"anio": "a"}).to_dict("records"),
    }
    txt = json.dumps(web, ensure_ascii=False, separators=(",", ":")).replace("NaN", "null")
    (WEB / "datos.json").write_text(txt, encoding="utf-8")
    print(json.dumps(hallazgos, ensure_ascii=False, indent=2))
    print(f"web/data/datos.json: {len(txt) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
