"""Pruebas offline de las Skills de ENAHO con datos sintéticos (no necesitan los microdatos).

    uv run pytest tests/ -q
"""
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parent.parent


def cargar(ruta):
    spec = importlib.util.spec_from_file_location(Path(ruta).stem, RAIZ / ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


limpiar = cargar(".claude/skills/limpiando-enaho/scripts/limpiar.py")
graficar = cargar(".claude/skills/graficando-enaho/scripts/graficar.py")


def test_llaves_conservan_ceros_iniciales_aunque_lleguen_como_numero():
    df = pd.DataFrame({"conglome": [123.0, "000456"], "vivienda": [7, "007"], "hogar": ["1", 11], "ubigeo": [10101, "150101"]})
    r = limpiar.llaves_texto(df)
    assert r.conglome.tolist() == ["000123", "000456"]
    assert r.vivienda.tolist() == ["007", "007"]
    assert r.hogar.tolist() == ["01", "11"]
    assert r.ubigeo.tolist() == ["010101", "150101"]


def test_pct_es_ponderado_y_no_promedio_simple():
    pobre = pd.Series([1, 0, 0, 0])
    peso = pd.Series([100.0, 1.0, 1.0, 1.0])
    assert limpiar.pct(pobre, peso) == pytest.approx(100 / 103 * 100)
    assert limpiar.pct(pobre, peso) != pytest.approx(pobre.mean() * 100)


def test_graficar_pondera_por_hogar_y_usa_un_registro_por_hogar():
    # dos hogares: A (pobre, 3 miembros, factor 10) y B (no pobre, 1 miembro, factor 10); A aparece 3 veces (una por persona)
    base = pd.DataFrame({
        "conglome": ["1"] * 4, "vivienda": ["1"] * 4, "hogar": ["01", "01", "01", "02"],
        "area": ["Urbana"] * 4, "pobre": [1, 1, 1, 0], "factor07": [10.0] * 4, "mieperho": [3, 3, 3, 1], "facpob07": [10.0] * 4})
    v = graficar.ponderada(base, "area")
    assert v["Urbana"] == pytest.approx(30 / 40 * 100)  # (10*3) / (10*3 + 10*1); contar personas daría 75 por otra vía


def test_graficar_sexo_usa_personas_con_facpob07():
    base = pd.DataFrame({"sexo": ["Hombre", "Hombre", "Mujer", "Mujer"], "pobre": [1, 0, 1, 1], "facpob07": [1.0, 3.0, 1.0, 1.0]})
    v = graficar.ponderada(base, "sexo")
    assert v["Hombre"] == pytest.approx(25.0) and v["Mujer"] == pytest.approx(100.0)
