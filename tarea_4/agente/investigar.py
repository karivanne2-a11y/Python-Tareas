"""Agente de investigación: crédito del sistema financiero (BCRP) y pobreza departamental (ENAHO 2024).

    uv run agente/investigar.py

En UNA ejecución coordina:
  - el servidor MCP del BCRP (mcp/server.py, por stdio): buscar_series, serie, resumen, correlacion + recurso bcrp://serie/{codigo}
  - las Skills de ENAHO (sus scripts): limpiando-enaho -> graficando-enaho -> mapeando-enaho
y escribe salidas/resultados_investigacion.json, salidas/credito_pobreza_departamento.csv,
salidas/bitacora_agente.json y las figuras del informe. Ninguna cifra se escribe a mano.
"""
import asyncio
import importlib.util
import json
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from fastmcp import Client

RAIZ = Path(__file__).resolve().parent.parent
SALIDAS, FIGURAS = RAIZ / "salidas", RAIZ / "figuras"
SKILLS = RAIZ / ".claude" / "skills"
BITACORA: list[dict] = []
MIN_HOGARES = 30  # celdas departamento × área con menos hogares muestrales se excluyen


def sin_tildes(s):
    return unicodedata.normalize("NFD", str(s).lower()).encode("ascii", "ignore").decode()


def cargar_server():
    """Importa mcp/server.py solo para reutilizar calcular_correlacion (la misma función que usa la herramienta)."""
    spec = importlib.util.spec_from_file_location("bcrp_server", RAIZ / "mcp" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- Skills
def correr_skill(skill: str, script: str, *args):
    cmd = ["uv", "run", f".claude/skills/{skill}/scripts/{script}", *args]
    t = time.time()
    p = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace")
    BITACORA.append({"tipo": "skill", "skill": skill, "comando": " ".join(cmd), "codigo_salida": p.returncode,
                     "segundos": round(time.time() - t, 1), "ultimas_lineas": p.stdout.strip().splitlines()[-4:]})
    if p.returncode != 0:
        sys.exit(f"La skill {skill} falló (código {p.returncode}); no se continúa.\n{p.stdout[-800:]}\n{p.stderr[-800:]}")
    return p.stdout


# ---------------------------------------------------------------- MCP
async def llamar(c, herramienta, **args):
    t = time.time()
    r = await c.call_tool(herramienta, args)
    BITACORA.append({"tipo": "mcp", "herramienta": herramienta, "argumentos": args, "segundos": round(time.time() - t, 1)})
    return r.data


def codigo_credito(cc: int) -> str:
    """Departamentos 01-25 -> series anuales RD16127DA, RD16130DA, ... (cada departamento ocupa 3 códigos: MN, ME y total)."""
    return f"RD{16127 + 3 * (cc - 1)}DA"


async def consultar_bcrp(nombres: dict[str, str]):
    out = {}
    async with Client(RAIZ / "mcp" / "server.py") as c:
        out["busqueda"] = await llamar(c, "buscar_series", texto="tasa de referencia politica monetaria", frecuencia="Mensual", limite=3)
        ficha = await c.read_resource("bcrp://serie/RD16202DA")
        BITACORA.append({"tipo": "mcp_recurso", "uri": "bcrp://serie/RD16202DA"})
        out["ficha_credito_total"] = json.loads(ficha[0].text)
        out["credito_nacional"] = await llamar(c, "serie", codigo="RD16202DA", desde="2020", hasta="2024")
        out["credito_resumen"] = await llamar(c, "resumen", codigo="RD16202DA", desde="2020", hasta="2024")
        for clave, cod in (("tasa_ref", "PD04722MM"), ("tamn", "PN07807NM")):
            out[f"{clave}_serie"] = await llamar(c, "serie", codigo=cod, desde="2020-01", hasta="2024-12")
            out[f"{clave}_resumen"] = await llamar(c, "resumen", codigo=cod, desde="2020-01", hasta="2024-12")
        out["corr_tasas"] = await llamar(c, "correlacion", codigo_a="PD04722MM", codigo_b="PN07807NM",
                                         desde="2020-01", hasta="2024-12")
        deps = {}
        for cc, nombre in nombres.items():
            cod = codigo_credito(int(cc))
            s = await llamar(c, "serie", codigo=cod, desde="2020", hasta="2024")
            # control: el nombre de la serie debe corresponder al departamento (no confiar solo en la aritmética de códigos)
            assert sin_tildes(nombre) in sin_tildes(s["nombre"]) and "total" in sin_tildes(s["nombre"]), (cc, nombre, s["nombre"])
            deps[cc] = {"codigo_serie": cod, "serie": {d["periodo"]: d["valor"] for d in s["datos"]}}
        out["departamentos"] = deps
    return out


# ---------------------------------------------------------------- análisis
def permutacion_spearman(x, y, n=20000, seed=42):
    rng = np.random.default_rng(seed)
    r0 = pd.Series(x).corr(pd.Series(y), method="spearman")
    rx = pd.Series(x).rank().to_numpy()
    ry = pd.Series(y).rank().to_numpy()
    mayores = sum(abs(np.corrcoef(rx, rng.permutation(ry))[0, 1]) >= abs(r0) - 1e-12 for _ in range(n))
    return float((mayores + 1) / (n + 1))


def correlaciones(df, x, y, srv, etiqueta):
    dd = df.dropna(subset=[x, y])
    a = [{"periodo": c, "valor": v} for c, v in zip(dd.codigo, dd[x])]
    b = [{"periodo": c, "valor": v} for c, v in zip(dd.codigo, dd[y])]
    sp = srv.calcular_correlacion(a, b, "spearman")
    pe = srv.calcular_correlacion(a, b, "pearson")
    return {"etiqueta": etiqueta, "n": sp["n"], "spearman": round(sp["coeficiente"], 3), "pearson": round(pe["coeficiente"], 3),
            "p_permutacion_spearman": round(permutacion_spearman(dd[x].to_numpy(), dd[y].to_numpy()), 4)}


def main():
    SALIDAS.mkdir(exist_ok=True), FIGURAS.mkdir(exist_ok=True)
    srv = cargar_server()
    # 1) Skills de ENAHO: limpieza validada -> gráficos -> mapa
    correr_skill("limpiando-enaho", "limpiar.py", "--anio", "2024")
    correr_skill("graficando-enaho", "graficar.py", "--grafico", "todos")
    correr_skill("mapeando-enaho", "mapear.py")
    ind = pd.read_csv(SALIDAS / "indicadores.csv", dtype={"codigo": str})
    deptos = ind[ind.nivel == "departamento"].set_index("codigo")
    base = pd.read_parquet(SALIDAS / "personas_2024.parquet")

    # 2) MCP del BCRP
    nombres = deptos.nombre.to_dict()
    bcrp = asyncio.run(consultar_bcrp(nombres))

    # 3) Cruce por departamento (todo con el mismo método de la sumaria: un registro por hogar, factor07 × mieperho)
    hog = base.drop_duplicates(["conglome", "vivienda", "hogar"]).assign(w=lambda d: d.factor07 * d.mieperho)
    filas = []
    for cc, nombre in nombres.items():
        h = hog[hog.departamento == cc]
        rural = h[~h.urbano]
        urb = h[h.urbano]
        cr24 = bcrp["departamentos"][cc]["serie"]["2024"]
        cr20 = bcrp["departamentos"][cc]["serie"]["2020"]
        poblacion = float(deptos.loc[cc, "poblacion"])
        filas.append({
            "codigo": cc, "departamento": nombre, "serie_credito": bcrp["departamentos"][cc]["codigo_serie"],
            "credito_2024_mill_soles": cr24, "credito_2020_mill_soles": cr20,
            "crecimiento_nominal_2020_2024_pct": (cr24 / cr20 - 1) * 100,
            "poblacion_enaho": poblacion, "credito_pc_2024_soles": cr24 * 1e6 / poblacion,
            "pobreza_pct": float(deptos.loc[cc, "pobreza_pct"]),
            "pobreza_extrema_pct": float(deptos.loc[cc, "pobreza_extrema_pct"]),
            "pct_poblacion_rural": float(rural.w.sum() / h.w.sum() * 100),
            "hogares_rurales": len(rural), "hogares_urbanos": len(urb),
            "pobreza_rural_pct": float((rural.pobre * rural.w).sum() / rural.w.sum() * 100) if len(rural) >= MIN_HOGARES else np.nan,
            "pobreza_urbana_pct": float((urb.pobre * urb.w).sum() / urb.w.sum() * 100) if len(urb) >= MIN_HOGARES else np.nan})
    df = pd.DataFrame(filas)
    df.round(3).to_csv(SALIDAS / "credito_pobreza_departamento.csv", index=False)

    sin_lima_callao = df[~df.codigo.isin(["07", "15"])]
    corr = {
        "principal": correlaciones(df, "credito_pc_2024_soles", "pobreza_pct", srv, "Crédito per cápita vs pobreza (25 unidades)"),
        "sin_lima_callao": correlaciones(sin_lima_callao, "credito_pc_2024_soles", "pobreza_pct", srv, "Sin Lima ni Callao (23 unidades)"),
        "vs_rural_pobreza": correlaciones(df, "credito_pc_2024_soles", "pobreza_rural_pct", srv, "Crédito per cápita vs pobreza rural"),
        "vs_urbana_pobreza": correlaciones(df, "credito_pc_2024_soles", "pobreza_urbana_pct", srv, "Crédito per cápita vs pobreza urbana"),
        "ruralidad_vs_pobreza": correlaciones(df, "pct_poblacion_rural", "pobreza_pct", srv, "% población rural vs pobreza"),
        "credito_vs_ruralidad": correlaciones(df, "credito_pc_2024_soles", "pct_poblacion_rural", srv, "Crédito per cápita vs % rural"),
    }

    # 3b) Robustez: controles por ruralidad, sensibilidad a un departamento y otros resultados
    from scipy import stats as st

    def ols(y, X, nombres):
        X1 = np.column_stack([np.ones(len(y)), *X])
        beta = np.linalg.lstsq(X1, y, rcond=None)[0]
        res_ = y - X1 @ beta
        n, k = X1.shape
        cov = res_ @ res_ / (n - k) * np.linalg.inv(X1.T @ X1)
        se = np.sqrt(np.diag(cov))
        t = beta / se
        p_ = 2 * st.t.sf(np.abs(t), n - k)
        r2 = 1 - (res_ @ res_) / ((y - y.mean()) @ (y - y.mean()))
        return {"n": int(n), "r2": round(float(r2), 3),
                "coef": {nm: {"beta": round(float(b), 3), "ee": round(float(s_), 3), "p": round(float(pp), 4)}
                         for nm, b, s_, pp in zip(["const"] + nombres, beta, se, p_)}}

    d = df.assign(ln_credito_pc=np.log(df.credito_pc_2024_soles))
    robustez = {
        "ols_credito": ols(d.pobreza_pct.to_numpy(), [d.ln_credito_pc.to_numpy()], ["ln_credito_pc"]),
        "ols_credito_rural": ols(d.pobreza_pct.to_numpy(), [d.ln_credito_pc.to_numpy(), d.pct_poblacion_rural.to_numpy()],
                                 ["ln_credito_pc", "pct_poblacion_rural"]),
    }
    r_ = d.ln_credito_pc.rank(), d.pobreza_pct.rank(), d.pct_poblacion_rural.rank()
    res_x = r_[0] - np.polyval(np.polyfit(r_[2], r_[0], 1), r_[2])
    res_y = r_[1] - np.polyval(np.polyfit(r_[2], r_[1], 1), r_[2])
    rho_p = float(np.corrcoef(res_x, res_y)[0, 1])
    t_p = rho_p * np.sqrt((len(d) - 3) / (1 - rho_p**2))
    robustez["spearman_parcial_control_ruralidad"] = {"rho": round(rho_p, 3), "n": len(d), "p_aprox": round(float(2 * st.t.sf(abs(t_p), len(d) - 3)), 4)}
    loo = []
    for i in range(len(d)):
        s_ = d.drop(d.index[i])
        loo.append((d.departamento.iloc[i], float(s_.credito_pc_2024_soles.corr(s_.pobreza_pct, method="spearman"))))
    robustez["leave_one_out_spearman"] = {"min": min(loo, key=lambda x: x[1]), "max": max(loo, key=lambda x: x[1])}
    robustez["extrema"] = correlaciones(df, "credito_pc_2024_soles", "pobreza_extrema_pct", srv, "Crédito per cápita vs pobreza extrema")
    robustez["crecimiento_2020_2024_vs_pobreza"] = correlaciones(df, "crecimiento_nominal_2020_2024_pct", "pobreza_pct", srv,
                                                                  "Crecimiento nominal del crédito 2020-2024 vs pobreza")
    corr["robustez"] = robustez

    # 4) Figuras del informe (BCRP y dispersión)
    cn = bcrp["credito_nacional"]["datos"]
    tr = bcrp["tasa_ref_serie"]["datos"]
    tm = bcrp["tamn_serie"]["datos"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.6), gridspec_kw={"width_ratios": [1, 1.5]})
    a1.bar([d["periodo"] for d in cn], [d["valor"] / 1000 for d in cn], color="#8c2d04", width=0.6)
    a1.bar_label(a1.containers[0], fmt="%.0f", padding=3, fontsize=9)
    a1.set_ylim(0, max(d["valor"] for d in cn) / 1000 * 1.15)
    a1.set_ylabel("miles de millones de S/ (fin de periodo)")
    a1.set_title("Crédito directo al sector privado", loc="left", fontsize=10)
    xs = pd.to_datetime([d["periodo"] for d in tr])
    a2.plot(xs, [d["valor"] for d in tr], color="#2b6cb0", label="Tasa de referencia (PD04722MM)")
    a2.plot(xs, [d["valor"] for d in tm], color="#8c2d04", label="TAMN, tasa activa (PN07807NM)")
    a2.set_ylim(0, None)
    a2.set_ylabel("% anual")
    a2.set_title("Tasas de interés, mensual", loc="left", fontsize=10)
    a2.legend(frameon=False, fontsize=8)
    for a in (a1, a2):
        a.spines[["top", "right"]].set_visible(False)
    rs = bcrp["credito_resumen"]
    fig.suptitle(f"El crédito creció {rs['variacion_pct']:.0f}% nominal entre {rs['primero']['periodo']} y {rs['ultimo']['periodo']} mientras la tasa de referencia "
                 f"pasó de {bcrp['tasa_ref_resumen']['maximo']['valor']:.2f}% (máx., {bcrp['tasa_ref_resumen']['maximo']['periodo']}) a {bcrp['tasa_ref_resumen']['ultimo']['valor']:.2f}%",
                 x=0.01, ha="left", fontsize=10.5, fontweight="bold")
    fig.text(0.01, 0.01, "Fuente: BCRP, series RD16202DA (anual), PD04722MM y PN07807NM (mensuales), consultadas por el servidor MCP del proyecto.",
             fontsize=7, color="#555")
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))
    fig.savefig(FIGURAS / "bcrp_credito_tasas_2020_2024.png", dpi=200)
    plt.close(fig)

    p = corr["principal"]
    if abs(p["spearman"]) < 0.3:
        frase = "no muestra una asociación clara con la pobreza"
    else:
        frase = "se asocia con " + ("menos" if p["spearman"] < 0 else "más") + " pobreza"
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(df.credito_pc_2024_soles, df.pobreza_pct, s=df.poblacion_enaho / 1.2e5 + 15, color="#8c2d04", alpha=0.75)
    for _, r in df.iterrows():
        ax.annotate(r.departamento, (r.credito_pc_2024_soles, r.pobreza_pct), fontsize=7, xytext=(4, 3), textcoords="offset points")
    ax.set_xscale("log")
    ax.set_ylim(0, None)
    ax.set_xlabel("Crédito directo por habitante, 2024 (S/, escala logarítmica)")
    ax.set_ylabel("% de personas en pobreza monetaria, 2024")
    ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(f"Más crédito por habitante {frase} (Spearman {p['spearman']:+.2f}, n={p['n']}, p={p['p_permutacion_spearman']:.3f})",
                 x=0.01, ha="left", fontsize=10.5, fontweight="bold")
    fig.text(0.01, 0.01, "Fuente: BCRP (crédito, series RD16127DA…RD16199DA) e INEI, ENAHO 2024. Tamaño = población. Asociación descriptiva, no causal.",
             fontsize=6.5, color="#555")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(FIGURAS / "credito_vs_pobreza_2024.png", dpi=200)
    plt.close(fig)

    # 5) resultados y bitácora
    top_cr = df.nlargest(3, "credito_pc_2024_soles")[["departamento", "credito_pc_2024_soles", "pobreza_pct"]]
    bot_cr = df.nsmallest(3, "credito_pc_2024_soles")[["departamento", "credito_pc_2024_soles", "pobreza_pct"]]
    res = {"bcrp": {k: v for k, v in bcrp.items() if k != "departamentos"}, "correlaciones": corr,
           "mas_credito_pc": top_cr.round(1).to_dict("records"), "menos_credito_pc": bot_cr.round(1).to_dict("records"),
           "nacional_enaho": ind[ind.nivel == "nacional"].iloc[0][["pobreza_pct", "poblacion"]].to_dict(),
           "area": ind[ind.nivel == "area"].set_index("nombre").pobreza_pct.to_dict()}
    (SALIDAS / "resultados_investigacion.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    (SALIDAS / "bitacora_agente.json").write_text(json.dumps(BITACORA, ensure_ascii=False, indent=2), encoding="utf-8")
    herr = sorted({b["herramienta"] for b in BITACORA if b["tipo"] == "mcp"})
    skills = sorted({b["skill"] for b in BITACORA if b["tipo"] == "skill"})
    print(f"Herramientas MCP usadas ({len(herr)}): {herr}; recurso: sí")
    print(f"Skills ejecutadas ({len(skills)}): {skills}")
    print(json.dumps(corr, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
