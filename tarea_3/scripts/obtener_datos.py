"""Descarga los datos crudos del proyecto.

Fuentes:
- UN Comtrade (API pública "preview", sin clave): exportaciones anuales del Perú
  (reporter 604) por producto HS y país de destino, 2010-2025.
- BCRP (API de series estadísticas): exportaciones totales mensuales FOB,
  para contrastar con la cifra oficial peruana.

Uso:  uv run python scripts/obtener_datos.py
"""

import json
import time
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
ORIG = RAIZ / "datos" / "originales"
ORIG.mkdir(parents=True, exist_ok=True)

COMTRADE = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
BCRP = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"
ANIOS = range(2010, 2026)

# Productos estrella de la agroexportación peruana (código HS -> nombre)
PRODUCTOS = {
    "080440": "Palta",
    "081040": "Arándano",
    "080610": "Uva fresca",
    "070920": "Espárrago fresco",
    "080450": "Mango",
    "090111": "Café verde",
    "0805": "Cítricos",
    "180100": "Cacao en grano",
    "100850": "Quinua",
}
# La API preview devuelve máx. 500 filas: se parte en dos grupos
GRUPOS = [list(PRODUCTOS)[:4], list(PRODUCTOS)[4:]]


def pedir(url, params, intentos=5):
    for i in range(intentos):
        r = requests.get(url, params=params, timeout=60)
        if r.status_code == 200:
            return r.json()
        time.sleep(3 * (i + 1))  # límite de peticiones: esperar y reintentar
    r.raise_for_status()


def comtrade():
    # 1) Productos por país de destino
    for anio in ANIOS:
        destino = ORIG / f"comtrade_productos_{anio}.json"
        if destino.exists():
            continue
        filas = []
        for grupo in GRUPOS:
            res = pedir(COMTRADE, {"reporterCode": 604, "period": anio,
                                   "cmdCode": ",".join(grupo), "flowCode": "X"})
            filas += res["data"]
            time.sleep(1.5)
        destino.write_text(json.dumps(filas), encoding="utf-8")
        print(f"productos {anio}: {len(filas)} filas")

    # 2) Exportaciones totales por capítulo HS (para el peso del agro)
    for anio in ANIOS:
        destino = ORIG / f"comtrade_capitulos_{anio}.json"
        if destino.exists():
            continue
        res = pedir(COMTRADE, {"reporterCode": 604, "period": anio,
                               "cmdCode": "AG2,TOTAL", "flowCode": "X",
                               "partnerCode": 0})
        destino.write_text(json.dumps(res["data"]), encoding="utf-8")
        print(f"capítulos {anio}: {len(res['data'])} filas")
        time.sleep(1.5)

    # 3) Catálogo de países (nombre e ISO3 para el mapa)
    ref = ORIG / "comtrade_paises.json"
    if not ref.exists():
        r = requests.get("https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json", timeout=60)
        ref.write_text(r.text, encoding="utf-8")


def bcrp():
    # PN38714BM: Balanza comercial - Exportaciones FOB (millones US$), mensual
    destino = ORIG / "bcrp_exportaciones_mensual.json"
    if destino.exists():
        return
    r = requests.get(f"{BCRP}/PN38714BM/json/2010-1/2025-12", timeout=60)
    destino.write_text(r.text, encoding="utf-8")
    print("BCRP exportaciones totales: ok")


if __name__ == "__main__":
    comtrade()
    bcrp()
