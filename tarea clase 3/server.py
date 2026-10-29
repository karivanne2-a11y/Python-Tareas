"""Servidor MCP del INEI (Perú).

El INEI no publica una API de series como la del BCRP: sus datos salen por el
portal de Datos Abiertos del Estado (catálogo de datasets + archivos CSV). Este
servidor construye encima un catálogo de "series": cada recurso tabular de un
dataset del INEI recibe un código, y sobre ese código funcionan las mismas tres
operaciones del proyecto.

Primitivas expuestas:
  tool     buscar_series(texto, limite)        -> busca series en el catálogo
  tool     serie(codigo, desde, hasta)         -> datos entre dos periodos
  tool     resumen(codigo, desde, hasta)       -> estadísticas de la serie
  tool     comparar(codigos, desde, hasta)     -> herramienta propia
  resource inei://serie/{codigo}               -> ficha de una serie
  prompt   informe(tema)                       -> receta de informe con cifras

Uso:
    uv run server.py                 # stdio, para Claude Code
    uv run server.py --probe         # prueba de humo, sin MCP
    claude mcp add --scope project inei -- uv run server.py
"""

from __future__ import annotations

import csv
import io
import json
import re
import statistics
import sys
import unicodedata
from pathlib import Path
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

# --------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------

PORTAL = "https://www.datosabiertos.gob.pe"
API = f"{PORTAL}/api/3/action"
ORG_INEI = "instituto-nacional-de-estadistica-e-informatica-inei"

DIR_DATOS = Path(__file__).parent / "datos"
CACHE_CATALOGO = DIR_DATOS / "catalogo_inei.json"
MAX_DATASETS = 500          # cuántos datasets del INEI se indexan
TIMEOUT = 30.0
MAX_BYTES_CSV = 25 * 1024 * 1024

mcp = FastMCP(
    "inei",
    instructions=(
        "Series del INEI (Perú) tomadas del portal de Datos Abiertos del Estado. "
        "Flujo: buscar_series para hallar el código, luego serie o resumen. "
        "Toda cifra debe venir de una llamada; cita siempre código y periodo."
    ),
)

_memoria: dict[str, Any] = {}


# --------------------------------------------------------------------------
# Catálogo
# --------------------------------------------------------------------------


def _api(accion: str, **params: Any) -> Any:
    """Llama una acción del catálogo (API estilo CKAN/DKAN)."""
    url = f"{API}/{accion}"
    try:
        r = httpx.get(url, params=params, timeout=TIMEOUT, follow_redirects=True)
        r.raise_for_status()
        datos = r.json()
    except httpx.HTTPError as e:
        raise ToolError(f"No se pudo consultar el portal de Datos Abiertos: {e}") from e
    except ValueError as e:
        raise ToolError(f"{url} no devolvió JSON válido.") from e

    if isinstance(datos, dict) and datos.get("success") is False:
        raise ToolError(f"El portal rechazó la consulta: {datos.get('error')}")
    return datos.get("result", datos) if isinstance(datos, dict) else datos


def _sin_tildes(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in base if not unicodedata.combining(c))


def _tabulares(paquete: dict) -> list[dict]:
    salida = []
    for rec in paquete.get("resources", []) or []:
        fmt = str(rec.get("format", "")).lower()
        url = rec.get("url") or ""
        if fmt in {"csv", "tsv"} or url.lower().endswith((".csv", ".tsv")):
            salida.append({"nombre": rec.get("name") or "", "url": url, "formato": fmt or "csv"})
    return salida


def catalogo(refrescar: bool = False) -> list[dict]:
    """Catálogo de series del INEI. Se descarga una vez y se guarda en datos/."""
    if not refrescar and "catalogo" in _memoria:
        return _memoria["catalogo"]

    if not refrescar and CACHE_CATALOGO.exists():
        try:
            filas = json.loads(CACHE_CATALOGO.read_text(encoding="utf-8"))
            _memoria["catalogo"] = filas
            return filas
        except (json.JSONDecodeError, OSError):
            pass  # cache corrupta: se vuelve a bajar

    filas: list[dict] = []
    paso = 100
    for inicio in range(0, MAX_DATASETS, paso):
        res = _api(
            "package_search",
            q=f"organization:{ORG_INEI}",
            rows=paso,
            start=inicio,
        )
        paquetes = res.get("results", []) if isinstance(res, dict) else []
        if not paquetes:
            break
        for p in paquetes:
            slug = p.get("name") or p.get("id") or ""
            recursos = _tabulares(p)
            for i, rec in enumerate(recursos):
                codigo = slug if i == 0 else f"{slug}#{i}"
                filas.append(
                    {
                        "codigo": codigo,
                        "nombre": p.get("title", slug),
                        "recurso": rec["nombre"],
                        "url": rec["url"],
                        "actualizado": p.get("metadata_modified", ""),
                        "notas": (p.get("notes") or "")[:400],
                    }
                )
        if len(paquetes) < paso:
            break

    if not filas:
        raise ToolError(
            "El catálogo del INEI llegó vacío. Revisa la conexión o corre "
            "`uv run server.py --probe`."
        )

    DIR_DATOS.mkdir(exist_ok=True)
    CACHE_CATALOGO.write_text(json.dumps(filas, ensure_ascii=False), encoding="utf-8")
    _memoria["catalogo"] = filas
    return filas


def _ficha(codigo: str) -> dict:
    for fila in catalogo():
        if fila["codigo"] == codigo:
            return fila
    raise ToolError(
        f"No existe la serie {codigo!r} en el catálogo del INEI. "
        f"Usa buscar_series para encontrar el código correcto."
    )


# --------------------------------------------------------------------------
# Descarga y lectura de la tabla
# --------------------------------------------------------------------------


def _descargar(url: str) -> list[dict[str, str]]:
    if url in _memoria:
        return _memoria[url]

    try:
        with httpx.stream("GET", url, timeout=TIMEOUT, follow_redirects=True) as r:
            r.raise_for_status()
            crudo = b""
            for trozo in r.iter_bytes():
                crudo += trozo
                if len(crudo) > MAX_BYTES_CSV:
                    raise ToolError(
                        f"El archivo supera {MAX_BYTES_CSV // 1024 // 1024} MB; "
                        "descárgalo aparte y trabájalo fuera del MCP."
                    )
    except httpx.HTTPError as e:
        raise ToolError(f"No se pudo descargar {url}: {e}") from e

    texto = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            texto = crudo.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        raise ToolError(f"No se pudo decodificar el archivo de {url}.")

    muestra = texto[:4096]
    try:
        dialecto = csv.Sniffer().sniff(muestra, delimiters=",;\t|")
    except csv.Error:
        dialecto = csv.excel
        dialecto.delimiter = ";" if muestra.count(";") > muestra.count(",") else ","

    filas = [
        {(k or "").strip(): (v or "").strip() for k, v in f.items()}
        for f in csv.DictReader(io.StringIO(texto), dialect=dialecto)
    ]
    if not filas:
        raise ToolError(f"El archivo de {url} no tiene filas de datos.")

    _memoria[url] = filas
    return filas


def _a_float(valor: Any) -> float | None:
    """'1 234,5' y '1,234.5' -> float. None si no es un número."""
    if valor is None:
        return None
    t = str(valor).strip().replace("%", "").replace(" ", "").replace(" ", "")
    if t.lower() in {"", "-", "--", "n.d.", "nd", "s.i.", "na", "null", "..."}:
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


MESES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
}


def _clave(periodo: str) -> tuple[int, int, int] | None:
    """Convierte '2025', '2025-03', '15/03/2025' o 'Mar.2025' en (año, mes, día)."""
    t = _sin_tildes(str(periodo).strip())
    if not t:
        return None

    m = re.match(r"^(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?$", t)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)

    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", t)
    if m:
        return int(m.group(3)), int(m.group(2)), int(m.group(1))

    m = re.match(r"^([a-z]{3})[a-z]*\.?\s*[-/]?\s*(\d{4})$", t)
    if m and m.group(1) in MESES:
        return int(m.group(2)), MESES[m.group(1)], 0

    m = re.match(r"^(\d{4})$", t)
    if m:
        return int(m.group(1)), 0, 0

    return None


def _limite(periodo: str, arriba: bool) -> tuple[int, int, int] | None:
    """Convierte el extremo de un rango en una clave comparable."""
    if not periodo:
        return None
    t = str(periodo).strip()
    k = _clave(t)
    if k is None:
        raise ToolError(
            f"No entiendo el periodo {periodo!r}. Usa '2025', '2025-03' o '2025-03-15'."
        )
    a, m, d = k
    if arriba:
        return (a, m or 12, d or 31)
    return (a, m or 1, d or 1)


_PATRON_PERIODO = re.compile(r"(a[nñ]o|periodo|per[ií]odo|fecha|mes|trimestre|year|date)", re.I)


def _columnas(filas: list[dict], col_periodo: str | None, col_valor: str | None) -> tuple[str, str]:
    columnas = list(filas[0].keys())

    for nombre, dado in (("periodo", col_periodo), ("valor", col_valor)):
        if dado and dado not in columnas:
            raise ToolError(f"No existe la columna {dado!r} ({nombre}). Columnas: {columnas}")

    periodo = col_periodo or next((c for c in columnas if _PATRON_PERIODO.search(c)), None)
    if periodo is None:
        periodo = next((c for c in columnas if any(_clave(f.get(c, "")) for f in filas[:20])), columnas[0])

    valor = col_valor
    if valor is None:
        muestra = filas[: min(30, len(filas))]
        for c in columnas:
            if c == periodo:
                continue
            if sum(1 for f in muestra if _a_float(f.get(c)) is not None) >= max(1, len(muestra) // 2):
                valor = c
                break
    if valor is None:
        raise ToolError(f"No encontré una columna numérica. Columnas: {columnas}")

    return periodo, valor


def _extraer(
    codigo: str,
    desde: str = "",
    hasta: str = "",
    columna_periodo: str | None = None,
    columna_valor: str | None = None,
) -> dict:
    """Núcleo compartido por serie, resumen y comparar."""
    ficha = _ficha(codigo)
    filas = _descargar(ficha["url"])
    periodo, valor = _columnas(filas, columna_periodo, columna_valor)

    k_desde = _limite(desde, arriba=False)
    k_hasta = _limite(hasta, arriba=True)

    datos = []
    for f in filas:
        v = _a_float(f.get(valor))
        if v is None:
            continue
        etiqueta = f.get(periodo, "")
        k = _clave(etiqueta)
        if k is not None:
            if k_desde and k < k_desde:
                continue
            if k_hasta and k > k_hasta:
                continue
        elif k_desde or k_hasta:
            continue  # sin periodo legible, no se puede filtrar
        datos.append({"periodo": etiqueta, "valor": v})

    if not datos:
        raise ToolError(
            f"La serie {codigo!r} no tiene datos numéricos en ese rango "
            f"(columna {valor!r}, periodos {desde or 'inicio'}–{hasta or 'fin'})."
        )

    return {
        "codigo": codigo,
        "nombre": ficha["nombre"],
        "columna_periodo": periodo,
        "columna_valor": valor,
        "columnas_disponibles": list(filas[0].keys()),
        "datos": datos,
        "fuente": f"INEI · {ficha['nombre']} · {ficha['url']}",
    }


# --------------------------------------------------------------------------
# Herramientas
# --------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True})
def buscar_series(texto: str, limite: int = 10) -> dict:
    """Busca series del INEI por palabras del título o de la descripción.

    Es el primer paso: devuelve el código que piden `serie` y `resumen`.
    Ejemplos de búsqueda: "pobreza monetaria", "población", "empleo Lima".
    """
    limite = max(1, min(int(limite), 50))
    terminos = [t for t in _sin_tildes(texto).split() if t]

    encontradas = []
    for fila in catalogo():
        heno = _sin_tildes(f"{fila['nombre']} {fila['recurso']} {fila['notas']}")
        if all(t in heno for t in terminos):
            encontradas.append(
                {
                    "codigo": fila["codigo"],
                    "nombre": fila["nombre"],
                    "recurso": fila["recurso"],
                    "actualizado": fila["actualizado"],
                }
            )

    return {
        "consulta": texto,
        "total": len(encontradas),
        "series": encontradas[:limite],
        "fuente": f"INEI · catálogo de Datos Abiertos ({PORTAL})",
    }


@mcp.tool(annotations={"readOnlyHint": True})
def serie(
    codigo: str,
    desde: str = "",
    hasta: str = "",
    columna_periodo: str | None = None,
    columna_valor: str | None = None,
) -> dict:
    """Datos de una serie del INEI entre dos periodos, ambos incluidos.

    Periodos: "2025" (anual), "2025-03" (mensual), "2025-03-15" (diaria).
    Si se omiten `desde` y `hasta`, devuelve toda la serie. Las columnas se
    detectan solas; indícalas si la detección elige mal.
    """
    res = _extraer(codigo, desde, hasta, columna_periodo, columna_valor)
    res["n"] = len(res["datos"])
    return res


@mcp.tool(annotations={"readOnlyHint": True})
def resumen(
    codigo: str,
    desde: str = "",
    hasta: str = "",
    columna_periodo: str | None = None,
    columna_valor: str | None = None,
) -> dict:
    """Estadísticas descriptivas de una serie del INEI en un rango de periodos.

    Devuelve n, primer y último valor, mínimo y máximo con su periodo,
    promedio, mediana, desviación y variación porcentual punta a punta.
    """
    res = _extraer(codigo, desde, hasta, columna_periodo, columna_valor)
    datos = res["datos"]
    valores = [d["valor"] for d in datos]

    d_min = min(datos, key=lambda d: d["valor"])
    d_max = max(datos, key=lambda d: d["valor"])
    primero, ultimo = valores[0], valores[-1]

    return {
        "codigo": codigo,
        "nombre": res["nombre"],
        "columna_valor": res["columna_valor"],
        "n": len(valores),
        "periodo_inicial": datos[0]["periodo"],
        "periodo_final": datos[-1]["periodo"],
        "primero": primero,
        "ultimo": ultimo,
        "minimo": d_min["valor"],
        "periodo_minimo": d_min["periodo"],
        "maximo": d_max["valor"],
        "periodo_maximo": d_max["periodo"],
        "promedio": round(statistics.fmean(valores), 4),
        "mediana": round(statistics.median(valores), 4),
        "desviacion": round(statistics.pstdev(valores), 4) if len(valores) > 1 else 0.0,
        "variacion_pct": round((ultimo - primero) / primero * 100, 2) if primero else None,
        "fuente": res["fuente"],
    }


@mcp.tool(annotations={"readOnlyHint": True})
def comparar(codigos: list[str], desde: str = "", hasta: str = "") -> dict:
    """Compara dos o más series del INEI en el mismo rango de periodos.

    Úsala cuando la pregunta enfrenta dos indicadores ("¿creció más X o Y?",
    "¿cómo se mueven juntos?"). Alinea las series por periodo y devuelve, para
    cada una, su variación punta a punta; si hay dos series con al menos tres
    periodos comunes, añade la correlación de Pearson entre ellas.
    """
    if len(codigos) < 2:
        raise ToolError("Pasa al menos dos códigos para comparar.")
    if len(codigos) > 5:
        raise ToolError("Compara como máximo cinco series a la vez.")

    series: dict[str, dict[str, float]] = {}
    detalle = []
    for c in codigos:
        res = _extraer(c, desde, hasta)
        series[c] = {d["periodo"]: d["valor"] for d in res["datos"]}
        valores = [d["valor"] for d in res["datos"]]
        detalle.append(
            {
                "codigo": c,
                "nombre": res["nombre"],
                "n": len(valores),
                "primero": valores[0],
                "ultimo": valores[-1],
                "variacion_pct": round((valores[-1] - valores[0]) / valores[0] * 100, 2)
                if valores[0]
                else None,
                "fuente": res["fuente"],
            }
        )

    comunes = sorted(set.intersection(*(set(v) for v in series.values())))
    correlacion = None
    if len(codigos) == 2 and len(comunes) >= 3:
        a = [series[codigos[0]][p] for p in comunes]
        b = [series[codigos[1]][p] for p in comunes]
        try:
            correlacion = round(statistics.correlation(a, b), 4)
        except statistics.StatisticsError:
            correlacion = None

    return {
        "series": detalle,
        "periodos_comunes": len(comunes),
        "rango_comun": [comunes[0], comunes[-1]] if comunes else [],
        "correlacion": correlacion,
        "aviso": "Correlación no es causalidad; revisa metodología y cobertura antes de concluir.",
    }


# --------------------------------------------------------------------------
# Recurso (plantilla) y prompt
# --------------------------------------------------------------------------


@mcp.resource("inei://serie/{codigo}")
def ficha(codigo: str) -> dict:
    """Ficha de una serie del INEI: nombre, recurso, columnas y cobertura."""
    f = _ficha(codigo)
    filas = _descargar(f["url"])
    periodo, valor = _columnas(filas, None, None)
    etiquetas = [x.get(periodo, "") for x in filas if _clave(x.get(periodo, ""))]
    return {
        "codigo": f["codigo"],
        "nombre": f["nombre"],
        "recurso": f["recurso"],
        "url": f["url"],
        "actualizado": f["actualizado"],
        "filas": len(filas),
        "columnas": list(filas[0].keys()),
        "columna_periodo": periodo,
        "columna_valor": valor,
        "cobertura": [etiquetas[0], etiquetas[-1]] if etiquetas else [],
        "descripcion": f["notas"],
    }


@mcp.resource("inei://catalogo")
def indice() -> dict:
    """Índice de las series del INEI disponibles en este servidor."""
    filas = catalogo()
    return {
        "total": len(filas),
        "series": [{"codigo": f["codigo"], "nombre": f["nombre"]} for f in filas[:200]],
        "fuente": PORTAL,
    }


@mcp.prompt
def informe(tema: str) -> str:
    """Informe corto sobre un tema del INEI, con cifras verificables."""
    return (
        f"Escribe cinco viñetas sobre «{tema}» con datos del INEI.\n\n"
        "Procedimiento: usa buscar_series para elegir la serie, luego resumen "
        "(y serie si necesitas el detalle). Si enfrentas dos indicadores, usa comparar.\n\n"
        "Reglas: cada viñeta lleva una cifra traída por una herramienta, con su "
        "código de serie y su periodo. No uses cifras de memoria. Cierra con una "
        "línea sobre los límites de los datos: cobertura, vacíos o cambios "
        "metodológicos."
    )


# --------------------------------------------------------------------------
# Arranque
# --------------------------------------------------------------------------

if __name__ == "__main__":
    if "--probe" in sys.argv:
        try:
            filas = catalogo(refrescar="--refrescar" in sys.argv)
            print(f"OK · {len(filas)} series en el catálogo del INEI")
            for f in filas[:5]:
                print(f"  - {f['codigo']}: {f['nombre']}")
        except Exception as e:  # noqa: BLE001
            print(f"FALLO: {e}")
            raise SystemExit(1)
    else:
        mcp.run()  # stdio por defecto
