"""Servidor MCP del BCRP (Tarea 4).

    uv run pytest mcp/ -q       # 8 pruebas originales + 2 propias (test_propias.py)
    uv run mcp/server.py        # el servidor, por stdio
    claude mcp add --scope project bcrp -- uv run mcp/server.py

Herramientas: buscar_series, serie, resumen y correlacion (propia).
Recurso: bcrp://serie/{codigo}. Prompt: informe(tema).
Las cuentas las hace Python, no el modelo: así cada cifra sale de una llamada que se puede repetir.
"""
import json
import re
import time
import unicodedata
from functools import cache
from pathlib import Path

import httpx
import pandas as pd
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

AQUI = Path(__file__).parent.parent  # raíz de tarea_4/ (el servidor vive en mcp/)
CATALOGO = AQUI / "datos" / "catalogo_bcrp.csv"
URL_CATALOGO = "https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata"
API = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"
SOLO_LECTURA = {"readOnlyHint": True, "openWorldHint": True}

mcp = FastMCP("bcrp", instructions=(
    "Series oficiales del Banco Central de Reserva del Perú (BCRP). Primero busca el código con buscar_series; "
    "luego usa resumen para variaciones, promedios y extremos, serie para los datos y correlacion para asociar "
    "dos series. No calcules a mano: cita siempre el código de la serie y el periodo."))


def _sin_tildes(s):
    return unicodedata.normalize("NFD", str(s).lower()).encode("ascii", "ignore").decode()


@cache
def catalogo():
    """El catálogo oficial: 17 mil series en unos 7 MB. Se baja una vez y queda en datos/."""
    if not CATALOGO.exists():
        CATALOGO.parent.mkdir(exist_ok=True)
        r = httpx.get(URL_CATALOGO, timeout=120)
        r.raise_for_status()
        CATALOGO.write_text(r.content.decode("latin-1"), encoding="utf-8")
    df = pd.read_csv(CATALOGO, sep=";", dtype=str).fillna("")
    df = df.rename(columns={"Código de serie": "codigo", "Categoría de serie": "categoria", "Grupo de serie": "grupo",
                            "Nombre de serie": "nombre", "Frecuencia": "frecuencia",
                            "Fecha de actualización": "actualizada", "Fecha de inicio": "inicio"})
    df["texto"] = (df.categoria + " " + df.grupo + " " + df.nombre).map(_sin_tildes)
    return df


def _ficha(codigo):
    fila = catalogo().query("codigo == @codigo")
    if fila.empty:
        raise ToolError(f"No existe el código de serie {codigo!r}. Búsquenlo con buscar_series.")
    f = fila.iloc[0]
    return {"codigo": f.codigo, "nombre": f"{f.grupo} - {f.nombre}", "categoria": f.categoria,
            "frecuencia": f.frecuencia, "inicio": f.inicio, "actualizada": f.actualizada}


@mcp.tool(annotations=SOLO_LECTURA)
def buscar_series(texto: str, frecuencia: str | None = None, limite: int = 10) -> list[dict]:
    """Busca series del BCRP por palabras: todas deben aparecer en la categoría, el grupo o el nombre.

    Ejemplos: "ipc 12 meses", "tipo de cambio interbancario venta", "reservas internacionales netas",
    "tasa de referencia", "cobre precio". frecuencia: "Diaria", "Mensual", "Trimestral" o "Anual".
    Devuelve el código, el nombre completo, la frecuencia y desde cuándo hay datos. Si no hay resultados,
    prueben con menos palabras.
    """
    df = catalogo()
    m = pd.Series(True, index=df.index)
    for palabra in _sin_tildes(texto).split():
        m &= df.texto.str.contains(re.escape(palabra))
    if frecuencia:
        m &= df.frecuencia.str.lower() == frecuencia.lower()
    # primero las series vigentes y, entre ellas, las de nombre más corto (las más generales)
    sel = df[m]
    orden = sel.assign(vieja=sel.actualizada < "2025", largo=(sel.grupo + sel.nombre).str.len())
    return [_ficha(c) for c in orden.sort_values(["vieja", "largo"]).head(limite).codigo]


# ---------------------------------------------------------------- serie

# La API a veces devuelve los meses en inglés ("Jan.2024") y la documentación los muestra en español ("Ene.2025").
MESES = {"ene": 1, "jan": 1, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "may": 5, "jun": 6, "jul": 7,
         "ago": 8, "aug": 8, "set": 9, "sep": 9, "oct": 10, "nov": 11, "dic": 12, "dec": 12}


def _fecha_api(fecha, frecuencia):
    """'2025-01' -> '2025-1' (mensual/trimestral); diaria '2026-10-01' y anual '2025' pasan igual."""
    f = fecha.strip().upper().replace("T", "-")
    if frecuencia in ("Mensual", "Trimestral"):
        m = re.fullmatch(r"(\d{4})-0*(\d{1,2})", f)
        if not m:
            raise ToolError(f"Fecha {fecha!r} no válida para una serie {frecuencia.lower()}: usen AAAA-MM (o AAAA-T para trimestral).")
        return f"{m[1]}-{int(m[2])}"
    return fecha.strip()


def _periodo(nombre, frecuencia):
    """Convierte el nombre que devuelve la API en '2025-01', '2026-10-01', '2025-T1' o '2025'."""
    n = nombre.strip()
    if frecuencia == "Anual":
        return n
    if frecuencia == "Trimestral":
        m = re.fullmatch(r"T(\d)\.(\d{2,4})", n)
        anio = m[2] if len(m[2]) == 4 else "20" + m[2]
        return f"{anio}-T{m[1]}"
    if frecuencia == "Diaria":
        d, mes, a = n.split(".")
        return f"{'20' + a if len(a) == 2 else a}-{MESES[mes.lower()[:3]]:02d}-{int(d):02d}"
    mes, a = n.split(".")
    return f"{a}-{MESES[mes.lower()[:3]]:02d}"


def _json_de(texto):
    """La API antepone avisos PHP en HTML al JSON; se toma desde el primer '{\"config\"'."""
    m = re.search(r'\{\s*"config"', texto)  # a veces viene como '{ "config"' (con espacio)
    if not m:
        return None
    try:
        return json.loads(texto[m.start():])
    except json.JSONDecodeError:
        return None


@cache
def _descargar(codigo, desde, hasta):
    ficha = _ficha(codigo)
    frec = ficha["frecuencia"]
    url = f"{API}/{codigo}/json/{_fecha_api(desde, frec)}/{_fecha_api(hasta, frec)}"
    js = None
    for intento in range(4):  # si hay muchos pedidos seguidos responde HTML: esperar y reintentar
        r = httpx.get(url, timeout=60)
        js = _json_de(r.text)
        if js is not None:
            break
        time.sleep(2 * (intento + 1))
    if js is None:
        raise ToolError(f"El BCRP no devolvió datos para {codigo} ({desde} a {hasta}). Prueben otro rango o reintenten.")
    datos = []
    for p in js["periods"]:
        v = p["values"][0]
        if v in ("n.d.", "", None):
            continue
        datos.append({"periodo": _periodo(p["name"], frec), "valor": float(v)})
    return {"codigo": codigo, "nombre": ficha["nombre"], "frecuencia": frec, "datos": datos,
            "fuente": f"https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{codigo}/json/{desde}/{hasta}"}


@mcp.tool(annotations=SOLO_LECTURA)
def serie(codigo: str, desde: str, hasta: str) -> dict:
    """Descarga los datos de una serie del BCRP entre dos fechas.

    Formato de fechas según la frecuencia: mensual y trimestral "2025-01", diaria "2025-01-15", anual "2025".
    Devuelve codigo, nombre, frecuencia, datos [{periodo, valor}] y la URL de la fuente. Se omiten los "n.d.".
    """
    return _descargar(codigo, desde, hasta)


@mcp.tool(annotations=SOLO_LECTURA)
def resumen(codigo: str, desde: str, hasta: str) -> dict:
    """Resume una serie: primero, último, cambio, variación %, promedio, máximo y mínimo (con su periodo).

    Úsenla en vez de calcular a mano. El cambio está en las unidades de la serie y la variación_pct es
    (último - primero) / primero × 100; si la serie ya es una tasa, interpreten el cambio, no la variación %.
    """
    s = _descargar(codigo, desde, hasta)
    d = s["datos"]
    if not d:
        raise ToolError(f"La serie {codigo} no tiene datos entre {desde} y {hasta}.")
    v = pd.Series([x["valor"] for x in d], index=[x["periodo"] for x in d])
    cambio = v.iloc[-1] - v.iloc[0]
    return {"codigo": codigo, "nombre": s["nombre"], "frecuencia": s["frecuencia"], "n": len(v),
            "primero": {"periodo": v.index[0], "valor": float(v.iloc[0])},
            "ultimo": {"periodo": v.index[-1], "valor": float(v.iloc[-1])},
            "cambio": float(cambio),
            "variacion_pct": float(cambio / v.iloc[0] * 100) if v.iloc[0] != 0 else None,
            "promedio": float(v.mean()),
            "maximo": {"periodo": v.idxmax(), "valor": float(v.max())},
            "minimo": {"periodo": v.idxmin(), "valor": float(v.min())},
            "fuente": s["fuente"]}


# ---------------------------------------------------------------- herramienta propia

def calcular_correlacion(a: list[dict], b: list[dict], metodo: str = "pearson") -> dict:
    """Alinea dos listas [{periodo, valor}] por periodo, descarta los faltantes y calcula la correlación."""
    if metodo not in ("pearson", "spearman"):
        raise ToolError("metodo debe ser 'pearson' o 'spearman'.")
    sa = pd.Series({x["periodo"]: x["valor"] for x in a}, dtype=float)
    sb = pd.Series({x["periodo"]: x["valor"] for x in b}, dtype=float)
    df = pd.concat([sa.rename("a"), sb.rename("b")], axis=1)
    comunes = df.dropna()
    if len(comunes) < 3:
        raise ToolError(f"Solo hay {len(comunes)} periodos en común con datos en ambas series; se necesitan al menos 3.")
    if comunes.a.nunique() < 2 or comunes.b.nunique() < 2:
        raise ToolError("Una de las series es constante en el rango común: la correlación no está definida.")
    r = comunes.a.corr(comunes.b, method=metodo)
    return {"metodo": metodo, "coeficiente": float(r), "n": int(len(comunes)),
            "primer_periodo": comunes.index.min(), "ultimo_periodo": comunes.index.max(),
            "periodos_descartados": int(len(df) - len(comunes))}


@mcp.tool(annotations=SOLO_LECTURA)
def correlacion(codigo_a: str, codigo_b: str, desde: str, hasta: str, metodo: str = "pearson") -> dict:
    """Correlación entre dos series del BCRP de la MISMA frecuencia, alineadas por periodo.

    Descarga ambas series, conserva solo los periodos con dato en las dos (los demás se cuentan en
    periodos_descartados) y calcula la correlación de Pearson o de Spearman (metodo="spearman").
    Devuelve coeficiente, n, primer y último periodo usados y las fuentes. Es una asociación descriptiva:
    no demuestra causalidad, y con pocos periodos el coeficiente es poco estable (n pequeño).
    """
    fa, fb = _ficha(codigo_a)["frecuencia"], _ficha(codigo_b)["frecuencia"]
    if fa != fb:  # se comprueba antes de descargar: las fechas válidas dependen de la frecuencia
        raise ToolError(f"Las series tienen distinta frecuencia ({codigo_a}: {fa}, {codigo_b}: {fb}). "
                        "Elijan series de la misma frecuencia.")
    a, b = _descargar(codigo_a, desde, hasta), _descargar(codigo_b, desde, hasta)
    res = calcular_correlacion(a["datos"], b["datos"], metodo)
    res.update({"serie_a": {"codigo": codigo_a, "nombre": a["nombre"]},
                "serie_b": {"codigo": codigo_b, "nombre": b["nombre"]},
                "frecuencia": a["frecuencia"], "fuentes": [a["fuente"], b["fuente"]],
                "advertencia": "Asociación descriptiva; no implica causalidad."})
    return res


# ---------------------------------------------------------------- recurso y prompt

@mcp.resource("bcrp://serie/{codigo}", mime_type="application/json")
def ficha_serie(codigo: str) -> str:
    """Ficha descriptiva de una serie: código, nombre, categoría, frecuencia, inicio y última actualización."""
    return json.dumps(_ficha(codigo), ensure_ascii=False)


@mcp.prompt
def informe(tema: str) -> str:
    """Pide un informe breve sobre un tema macroeconómico con cada cifra trazable a una serie del BCRP."""
    return (f"Elabora un informe breve sobre: {tema}.\n"
            "1. Usa buscar_series para encontrar las series oficiales y anota sus códigos.\n"
            "2. Obtén las cifras con serie, resumen o correlacion; no hagas cuentas a mano.\n"
            "3. Cita en cada cifra el código de la serie, el periodo y la fuente.\n"
            "4. Si una herramienta falla o no hay datos, dilo; no inventes valores.\n"
            "5. Describe asociaciones sin afirmar causalidad y cierra con las limitaciones.")


if __name__ == "__main__":
    mcp.run()
