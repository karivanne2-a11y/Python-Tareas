"""Mapa coroplético de la pobreza monetaria departamental (ENAHO 2024).

    uv run .claude/skills/mapeando-enaho/scripts/mapear.py

Entra : salidas/personas_2024.parquet, datos/peru_departamental_simple.geojson, referencias/pobreza_departamento_2024.csv
Sale  : mapas/pobreza_departamento.png, mapas/pobreza_departamento.csv, mapas/validacion_mapa.txt
La unión es por código (ubigeo[:2] con FIRST_IDDP), nunca por nombre.
"""
import argparse
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anio", type=int, default=2024)
    ap.add_argument("--indicador", default="pobreza", choices=["pobreza", "extrema"],
                    help="pobreza monetaria (por defecto, se valida contra la Sesión 16) o pobreza extrema")
    ap.add_argument("--salidas", default="salidas")
    ap.add_argument("--geojson", default="datos/peru_departamental_simple.geojson")
    ap.add_argument("--referencia", default="referencias/pobreza_departamento_2024.csv")
    ap.add_argument("--mapas", default="mapas")
    a = ap.parse_args()
    base_path = Path(a.salidas) / f"personas_{a.anio}.parquet"
    if not base_path.exists():
        sys.exit(f"ERROR: no existe {base_path}. Ejecuten primero la skill limpiando-enaho.")
    if not Path(a.geojson).exists():
        sys.exit(f"ERROR: falta {a.geojson}. Bájenlo del repositorio del curso (ver README).")

    base = pd.read_parquet(base_path)
    # método del INEI: un registro por hogar, ponderado con factor07 × mieperho (reproduce la referencia de la Sesión 16)
    hog = base.drop_duplicates(["conglome", "vivienda", "hogar"]).assign(w=lambda d: d.factor07 * d.mieperho)
    col = "pobre" if a.indicador == "pobreza" else "pobre_extremo"
    nombre_ind = "pobreza monetaria" if a.indicador == "pobreza" else "pobreza monetaria extrema"
    g = hog.assign(pw=hog[col] * hog.w).groupby("departamento")
    pob = (g.pw.sum() / g.w.sum() * 100).rename("pobreza_pct").reset_index()

    geo = gpd.read_file(a.geojson)
    geo["FIRST_IDDP"] = geo["FIRST_IDDP"].astype(str).str.strip().str.zfill(2)
    assert len(geo) == 25, f"El GeoJSON debe tener 25 unidades y tiene {len(geo)}"
    assert {"07", "15"} <= set(geo.FIRST_IDDP), "Lima (15) y Callao (07) deben ir separados"

    mapa = geo.merge(pob, left_on="FIRST_IDDP", right_on="departamento", how="left", validate="1:1")
    assert mapa.pobreza_pct.notna().all(), f"Departamentos sin dato: {mapa[mapa.pobreza_pct.isna()].FIRST_IDDP.tolist()}"

    fig, ax = plt.subplots(figsize=(7, 9))
    vmax = 50 if a.indicador == "pobreza" else float(int(mapa.pobreza_pct.max() / 5) + 1) * 5
    mapa.plot(column="pobreza_pct", cmap="OrRd", vmin=0, vmax=vmax, edgecolor="white", linewidth=0.5, ax=ax,
              legend=True, legend_kwds={"label": f"% de personas en {nombre_ind}", "shrink": 0.6})
    ax.set_axis_off()
    mx, mn = mapa.loc[mapa.pobreza_pct.idxmax()], mapa.loc[mapa.pobreza_pct.idxmin()]
    fig.suptitle(f"La {nombre_ind} va de {mn.pobreza_pct:.1f}% a {mx.pobreza_pct:.1f}% según el departamento, Perú {a.anio}",
                 x=0.02, ha="left", fontsize=12, fontweight="bold")
    fig.text(0.02, 0.01, "Fuente: INEI, ENAHO 2024 (módulos 34 y 02). % de personas residentes habituales, ponderado con factor07 × mieperho (método del INEI). "
             "25 unidades; Lima y Callao separados.", fontsize=6.5, color="#555", wrap=True)
    salida = Path(a.mapas)
    salida.mkdir(exist_ok=True)
    nombre_png = "pobreza_departamento.png" if a.indicador == "pobreza" else "pobreza_extrema_departamento.png"
    fig.savefig(salida / nombre_png, dpi=200, bbox_inches="tight")
    plt.close(fig)
    if a.indicador != "pobreza":  # la referencia de la Sesión 16 es solo de pobreza monetaria
        print(f"Guardado {salida / nombre_png} ({len(mapa)} unidades, sin comparación con referencia)")
        return

    # comparación con la referencia de la Sesión 16
    ref = pd.read_csv(a.referencia, dtype={"ccdd": str}).rename(columns={"pobreza_pct": "referencia_pct"})
    cmp = mapa[["FIRST_IDDP", "pobreza_pct"]].rename(columns={"FIRST_IDDP": "ccdd", "pobreza_pct": "calculado_pct"})
    cmp = cmp.merge(ref, on="ccdd", validate="1:1")
    cmp["dif_pp"] = (cmp.calculado_pct - cmp.referencia_pct).round(2)
    cmp.round({"calculado_pct": 2}).to_csv(salida / "pobreza_departamento.csv", index=False)
    max_dif = cmp.dif_pp.abs().max()
    peor = cmp.loc[cmp.dif_pp.abs().idxmax()]
    lineas = [f"VALIDACIÓN DEL MAPA ({len(mapa)} unidades)", "=" * 60,
              f"[APROBADA] Unión por código FIRST_IDDP = ubigeo[:2]: {mapa.pobreza_pct.notna().sum()}/25 con dato",
              "[APROBADA] Lima (15) y Callao (07) separados",
              f"Comparación con la referencia de la Sesión 16 (redondeada a 1 decimal): diferencia máxima {max_dif:.2f} pp "
              f"({peor.departamento}) ; {int((cmp.dif_pp.abs() <= 0.1).sum())}/25 dentro de ±0.1 pp"]
    (salida / "validacion_mapa.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas))
    print(f"Guardado {salida / 'pobreza_departamento.png'}")


if __name__ == "__main__":
    main()
