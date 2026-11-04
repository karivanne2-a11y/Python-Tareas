"""Gráficos de cada escena del reel (PNG 900x760, fondo oscuro del video).

Lee los datos procesados, así cada cifra del reel sale del mismo análisis que el dashboard.

Uso:  uv run python reel/graficos.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
PROC = RAIZ / "datos" / "procesados"
SALIDA = RAIZ / "reel" / "recursos"
SALIDA.mkdir(parents=True, exist_ok=True)

# Mismos colores que reel.py
FONDO, TEXTO, SUAVE, ACENTO, CAJA = "#1C1A17", "#F7F3EC", "#B8AE9F", "#F08A4B", "#3A3631"
AZUL = "#6DA7EC"

plt.rcParams.update({
    "figure.facecolor": FONDO, "axes.facecolor": FONDO, "savefig.facecolor": FONDO,
    "text.color": TEXTO, "axes.labelcolor": SUAVE, "xtick.color": SUAVE, "ytick.color": SUAVE,
    "axes.edgecolor": CAJA, "font.size": 22, "font.family": "DejaVu Sans",
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.grid": True, "grid.color": CAJA, "grid.linewidth": 1, "axes.axisbelow": True,
})

prod = pd.read_csv(PROC / "productos_anual.csv")
dest = pd.read_csv(PROC / "destinos.csv")
pv = prod.pivot(index="anio", columns="producto", values="valor_usd") / 1e6


def figura():
    return plt.subplots(figsize=(9, 7.6), dpi=100)


def guardar(fig, n):
    fig.tight_layout()
    fig.savefig(SALIDA / f"escena_{n}.png")
    plt.close(fig)


def miles(x, _=None):
    return f"{x:,.0f}"


# 1. El arándano: de casi cero a primera fruta
fig, ax = figura()
s = pv["Arándano"]
ax.fill_between(s.index, s, color=ACENTO, alpha=0.18)
ax.plot(s.index, s, color=ACENTO, lw=5)
ax.scatter([s.index[-1]], [s.iloc[-1]], s=160, color=ACENTO, zorder=3, edgecolor=FONDO, linewidth=3)
ax.annotate(f"{s.iloc[-1]:,.0f}", (s.index[-1], s.iloc[-1]), xytext=(-24, -10), textcoords="offset points",
            ha="right", va="top", fontsize=30, fontweight="bold", color=TEXTO)
ax.set_title("Arándano: exportaciones (millones US$)", loc="left", fontsize=24, color=SUAVE, pad=16)
ax.yaxis.set_major_formatter(miles)
ax.set_xticks([2010, 2015, 2020, 2025])
guardar(fig, 1)

# 2. La canasta completa por año
fig, ax = figura()
tot = pv.sum(axis=1) / 1000
ax.bar(tot.index, tot, color=[ACENTO if a in (2010, 2025) else SUAVE for a in tot.index], width=0.7)
for a in (2010, 2025):
    ax.text(a, tot[a] + 0.2, f"{tot[a]:.1f}", ha="center", fontsize=26, fontweight="bold")
ax.set_title("Nueve productos: miles de millones de US$", loc="left", fontsize=24, color=SUAVE, pad=16)
ax.set_xticks([2010, 2015, 2020, 2025])
ax.grid(axis="x", visible=False)
guardar(fig, 2)

# 3. Ranking 2025, con las tres frutas resaltadas
fig, ax = figura()
r = pv.loc[2025].sort_values()
top3 = {"Arándano", "Uva fresca", "Palta"}
ax.barh(r.index, r, color=[ACENTO if n in top3 else SUAVE for n in r.index], height=0.65)
for i, (n, v) in enumerate(r.items()):
    ax.text(v + 30, i, f"{v:,.0f}", va="center", fontsize=20, color=TEXTO)
ax.set_title("Exportaciones 2025 (millones US$)", loc="left", fontsize=24, color=SUAVE, pad=16)
ax.set_xlim(0, r.max() * 1.22)
ax.set_xticks([])
ax.grid(axis="y", visible=False)
guardar(fig, 3)

# 4 y 5. ¿Volumen o precio? Índice 2015 = 100
def indices(producto, n, log=False):
    g = prod[(prod.producto == producto) & (prod.anio >= 2015)].set_index("anio")
    vol = 100 * g.peso_kg / g.peso_kg.iloc[0]
    pre = 100 * g.precio_usd_kg / g.precio_usd_kg.iloc[0]
    fig, ax = figura()
    ax.axhline(100, color=SUAVE, lw=1.5, ls=":")
    ax.plot(vol.index, vol, color=ACENTO, lw=5)
    ax.plot(pre.index, pre, color=AZUL, lw=5)
    if log:
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(miles)
        ax.yaxis.set_minor_formatter(lambda *_: "")
    ax.text(2025.2, vol.iloc[-1], "Volumen", color=ACENTO, va="center", fontsize=24, fontweight="bold")
    ax.text(2025.2, pre.iloc[-1], "Precio", color=AZUL, va="center", fontsize=24, fontweight="bold")
    ax.set_xlim(2015, 2028.4)
    ax.set_xticks([2015, 2020, 2025])
    ax.set_title(f"{producto}: índice 2015 = 100", loc="left", fontsize=24, color=SUAVE, pad=16)
    guardar(fig, n)


indices("Arándano", 4, log=True)
indices("Cacao en grano", 5)

# 6. Destinos 2025
fig, ax = figura()
d = dest[dest.anio == 2025].groupby("iso3").valor_usd.sum()
c = (100 * d / d.sum()).sort_values(ascending=False)
nombres = {"USA": "Estados Unidos", "NLD": "Países Bajos", "ESP": "España", "GBR": "Reino Unido",
           "CHN": "China", "CAN": "Canadá", "DEU": "Alemania", "KOR": "Corea del Sur"}
top = c.head(6)[::-1]
etq = [nombres.get(k, k) for k in top.index]
ax.barh(etq, top, color=[ACENTO if k in ("USA", "NLD") else SUAVE for k in top.index], height=0.65)
for i, v in enumerate(top):
    ax.text(v + 0.6, i, f"{v:.0f} %", va="center", fontsize=22)
ax.set_xlim(0, top.max() * 1.2)
ax.set_title("¿Quién compra? % del valor en 2025", loc="left", fontsize=24, color=SUAVE, pad=16)
ax.grid(axis="y", visible=False)
ax.set_xticks([])
guardar(fig, 6)

print("gráficos en", SALIDA)
