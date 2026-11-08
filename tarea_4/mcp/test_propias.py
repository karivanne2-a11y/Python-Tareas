"""Pruebas propias de la herramienta `correlacion` (las 8 originales están en test_server.py, sin cambios).

    uv run pytest mcp/ -q   # 10 passed
"""
import asyncio

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from server import mcp


def llamar(herramienta, **args):
    async def f():
        async with Client(mcp) as c:
            return await c.call_tool(herramienta, args)
    return asyncio.run(f()).data


def test_correlacion_de_una_serie_consigo_misma_es_uno():
    r = llamar("correlacion", codigo_a="PN01273PM", codigo_b="PN01273PM", desde="2024-01", hasta="2024-12")
    assert r["coeficiente"] == pytest.approx(1.0)
    assert r["n"] == 12 and r["periodos_descartados"] == 0
    assert r["primer_periodo"] == "2024-01" and r["ultimo_periodo"] == "2024-12"


def test_correlacion_rechaza_frecuencias_distintas():
    # PN01273PM es mensual; RD16127DA (crédito de Amazonas) es anual: no se pueden alinear.
    with pytest.raises(ToolError, match="frecuencia"):
        llamar("correlacion", codigo_a="PN01273PM", codigo_b="RD16127DA", desde="2020-01", hasta="2024-12")
