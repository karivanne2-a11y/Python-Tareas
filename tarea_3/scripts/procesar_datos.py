"""Limpia los datos crudos y construye las tablas procesadas.

Salidas en datos/procesados/:
- productos_anual.csv   año, producto, valor FOB, peso y precio implícito (US$/kg)
- destinos.csv          año, producto, país de destino, valor FOB
- agro_vs_total.csv     peso de los capítulos agropecuarios (HS 01-24) en el total
                        y contraste del total con la cifra oficial del BCRP

Uso:  uv run python scripts/procesar_datos.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from obtener_datos import PRODUCTOS

RAIZ = Path(__file__).resolve().parents[1]
ORIG = RAIZ / "datos" / "originales"
PROC = RAIZ / "datos" / "procesados"
PROC.mkdir(parents=True, exist_ok=True)

MESES = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6,
         "Jul": 7, "Ago": 8, "Set": 9, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12}


def leer(patron):
    filas = []
    for f in sorted(ORIG.glob(patron)):
        filas += json.loads(f.read_text(encoding="utf-8"))
    return pd.DataFrame(filas)


def paises():
    ref = json.loads((ORIG / "comtrade_paises.json").read_text(encoding="utf-8"))["results"]
    p = pd.DataFrame(ref)[["PartnerCode", "PartnerDesc", "PartnerCodeIsoAlpha3"]]
    p.columns = ["partnerCode", "pais_en", "iso3"]
    return p.drop_duplicates("partnerCode")


def productos():
    d = leer("comtrade_productos_*.json")
    d = d[(d.flowCode == "X") & (d.motCode == 0) & (d.customsCode == "C00")]
    d = d.drop_duplicates(["refYear", "cmdCode", "partnerCode"])
    d["producto"] = d.cmdCode.map(PRODUCTOS)
    d = d.rename(columns={"refYear": "anio", "cmdCode": "hs"})
    d["valor_usd"] = d.fobvalue.fillna(d.primaryValue)

    # Totales por producto (socio 0 = Mundo)
    mundo = d[d.partnerCode == 0][["anio", "hs", "producto", "valor_usd", "netWgt"]].copy()
    mundo["peso_kg"] = mundo.netWgt.where(mundo.netWgt > 0)
    # Algunos años el total Mundo viene sin peso: se usa la suma de los destinos
    peso_socios = d[d.partnerCode != 0].groupby(["anio", "hs"]).netWgt.sum()
    falta = mundo.peso_kg.isna()
    mundo.loc[falta, "peso_kg"] = [peso_socios.get((a, h)) or np.nan
                                   for a, h in zip(mundo.anio[falta], mundo.hs[falta])]
    mundo["precio_usd_kg"] = (mundo.valor_usd / mundo.peso_kg).round(3)
    mundo = mundo.drop(columns="netWgt").sort_values(["producto", "anio"])
    # Quinua solo tiene código HS propio desde 2012: antes no es comparable
    mundo.to_csv(PROC / "productos_anual.csv", index=False)

    # Destinos (sin el agregado Mundo ni agrupaciones)
    dest = d[d.partnerCode != 0].merge(paises(), on="partnerCode", how="left")
    dest = dest[dest.iso3.notna() & (dest.iso3.str.len() == 3)]
    dest = dest[["anio", "hs", "producto", "partnerCode", "iso3", "pais_en", "valor_usd"]]
    dest = dest[dest.valor_usd > 0].sort_values(["anio", "producto", "valor_usd"], ascending=[True, True, False])
    dest.to_csv(PROC / "destinos.csv", index=False)
    return mundo, dest


def agro_vs_total():
    c = leer("comtrade_capitulos_*.json")
    c = c[(c.partnerCode == 0) & (c.motCode == 0)].drop_duplicates(["refYear", "cmdCode"])
    c["valor"] = c.fobvalue.fillna(c.primaryValue)
    total = c[c.cmdCode == "TOTAL"].set_index("refYear").valor
    caps = c[c.cmdCode != "TOTAL"].copy()
    caps["cap"] = caps.cmdCode.astype(int)
    agro = caps[caps.cap <= 24].groupby("refYear").valor.sum()

    b = json.loads((ORIG / "bcrp_exportaciones_mensual.json").read_text(encoding="utf-8"))
    bc = pd.DataFrame([(p["name"], p["values"][0]) for p in b["periods"]], columns=["mes", "v"])
    bc = bc[bc.v != "n.d."]
    bc["anio"] = bc.mes.str[-4:].astype(int)
    bc["v"] = bc.v.astype(float)
    meses = bc.groupby("anio").size()
    bcrp = bc.groupby("anio").v.sum().where(meses == 12) * 1e6  # solo años completos

    out = pd.DataFrame({"export_total_comtrade": total, "export_agro_comtrade": agro,
                        "export_total_bcrp": bcrp})
    out.index.name = "anio"
    out["pct_agro"] = (100 * out.export_agro_comtrade / out.export_total_comtrade).round(2)
    out["dif_pct_vs_bcrp"] = (100 * (out.export_total_comtrade / out.export_total_bcrp - 1)).round(2)
    out.round(0).to_csv(PROC / "agro_vs_total.csv")
    return out


if __name__ == "__main__":
    mundo, dest = productos()
    tot = agro_vs_total()
    print(mundo.groupby("producto").anio.agg(["min", "max", "count"]))
    print(f"destinos: {len(dest)} filas, {dest.iso3.nunique()} países")
    print(tot)
