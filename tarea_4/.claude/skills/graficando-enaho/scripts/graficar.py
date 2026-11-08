"""Gráficos ponderados de pobreza monetaria (ENAHO 2024) a partir de la base limpia.

    uv run .claude/skills/graficando-enaho/scripts/graficar.py --grafico area|sexo|departamento|todos

Entra : salidas/personas_2024.parquet (lo genera la skill limpiando-enaho) y salidas/indicadores.csv
Sale  : figuras/pobreza_<grupo>_2024.png (200 dpi)
"""
import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

COLOR = "#8c2d04"
FUENTE = ("Fuente: INEI, ENAHO 2024 (módulos 34 y 02). Pobreza monetaria, % de la población residente habitual; "
          "estimación ponderada con {peso}.")
PESO_HOGARES = "factor07 × mieperho (método del INEI, por hogares)"
PESO_PERSONAS = "facpob07 (personas)"


def ponderada(df: pd.DataFrame, por: str) -> pd.Series:
    """% de pobres por grupo, ponderado (nunca promedio simple). Sexo: personas con facpob07; el resto, hogares
    con factor07 × mieperho, que es el método del INEI y reproduce la referencia de la Sesión 16."""
    if por in ("sexo", "grupo_edad"):
        d = df.dropna(subset=[por]).assign(w=lambda d: d.facpob07)
    else:
        d = df.drop_duplicates(["conglome", "vivienda", "hogar"]).assign(w=lambda d: d.factor07 * d.mieperho)
    g = d.assign(pw=d.pobre * d.w).groupby(por)
    return g.pw.sum() / g.w.sum() * 100


def barras(valores: pd.Series, titulo: str, subtitulo: str, salida: Path, horizontal=False, peso=PESO_HOGARES):
    valores = valores.sort_values(ascending=horizontal)  # horizontal: la mayor queda arriba
    fig, ax = plt.subplots(figsize=(8, 9) if horizontal else (7, 5))
    if horizontal:
        b = ax.barh(valores.index, valores.values, color=COLOR)
        ax.set_xlim(0, valores.max() * 1.15)
        ax.set_xlabel("% de personas en pobreza monetaria")
        ax.bar_label(b, fmt="%.1f%%", padding=3, fontsize=8)
    else:
        b = ax.bar(valores.index, valores.values, color=COLOR, width=0.55)
        ax.set_ylim(0, valores.max() * 1.18)
        ax.set_ylabel("% de personas en pobreza monetaria")
        ax.bar_label(b, fmt="%.1f%%", padding=3, fontsize=10)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.suptitle(titulo, x=0.01, ha="left", fontsize=12, fontweight="bold")
    ax.set_title(subtitulo, loc="left", fontsize=9, color="#555")
    fig.text(0.01, 0.01, FUENTE.format(peso=peso), fontsize=6.5, color="#555", wrap=True)
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    salida.parent.mkdir(exist_ok=True)
    fig.savefig(salida, dpi=200)
    plt.close(fig)
    print(f"Guardado {salida}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grafico", default="todos", choices=["area", "sexo", "edad", "departamento", "todos"])
    ap.add_argument("--anio", type=int, default=2024)
    ap.add_argument("--salidas", default="salidas")
    ap.add_argument("--figuras", default="figuras")
    a = ap.parse_args()
    base_path = Path(a.salidas) / f"personas_{a.anio}.parquet"
    if not base_path.exists():
        sys.exit(f"ERROR: no existe {base_path}. Ejecuten primero la skill limpiando-enaho.")
    base = pd.read_parquet(base_path)
    fig = Path(a.figuras)
    nombres = pd.read_csv(Path(a.salidas) / "indicadores.csv", dtype={"codigo": str})
    nombres = nombres[nombres.nivel == "departamento"].set_index("codigo").nombre

    if a.grafico in ("area", "todos"):
        v = ponderada(base, "area")
        barras(v, f"La pobreza rural ({v['Rural']:.1f}%) supera a la urbana ({v['Urbana']:.1f}%) en {v['Rural'] - v['Urbana']:.1f} puntos porcentuales",
               f"Pobreza monetaria por área, Perú {a.anio}", fig / f"pobreza_area_{a.anio}.png")
    if a.grafico in ("sexo", "todos"):
        v = ponderada(base, "sexo")
        dif = abs(v["Mujer"] - v["Hombre"])
        barras(v, f"La pobreza de mujeres ({v['Mujer']:.1f}%) y hombres ({v['Hombre']:.1f}%) difiere en {dif:.1f} puntos porcentuales",
               f"Pobreza monetaria por sexo, Perú {a.anio}", fig / f"pobreza_sexo_{a.anio}.png", peso=PESO_PERSONAS)
    if a.grafico in ("edad", "todos"):
        base["grupo_edad"] = pd.cut(base.edad, [-1, 17, 29, 44, 59, 200], labels=["0–17", "18–29", "30–44", "45–59", "60 o más"])
        v = ponderada(base, "grupo_edad")
        v.index = v.index.astype(str)
        barras(v, f"La pobreza es mayor entre los de {v.idxmax()} años ({v.max():.1f}%) y menor entre los de {v.idxmin()} ({v.min():.1f}%)",
               f"Pobreza monetaria por grupo de edad, Perú {a.anio}", fig / f"pobreza_edad_{a.anio}.png", peso=PESO_PERSONAS)
    if a.grafico in ("departamento", "todos"):
        v = ponderada(base, "departamento")
        v.index = [nombres[c] for c in v.index]
        mx, mn = v.idxmax(), v.idxmin()
        barras(v, f"{mx} ({v.max():.1f}%) tuvo {v.max() / v.min():.1f} veces la pobreza de {mn} ({v.min():.1f}%)",
               f"Pobreza monetaria por departamento, Perú {a.anio} (25 unidades; Lima y Callao separados)",
               fig / f"pobreza_departamento_{a.anio}.png", horizontal=True)


if __name__ == "__main__":
    main()
