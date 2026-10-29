"""Ocho pruebas del servidor MCP del INEI.

Las cuatro primeras son de estructura y corren sin red.
Las cuatro últimas consultan el portal de Datos Abiertos; llevan la marca
`red` y se saltan solas si el portal no responde.

    uv run pytest -q              # las ocho
    uv run pytest -q -m "not red" # solo las de estructura
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from server import PORTAL, mcp


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------


def hay_portal() -> bool:
    try:
        httpx.get(f"{PORTAL}/api/3/action/site_read", timeout=10.0)
        return True
    except httpx.HTTPError:
        return False


red = pytest.mark.skipif(not hay_portal(), reason="el portal de Datos Abiertos no responde")


def correr(corutina):
    return asyncio.run(corutina)


async def _listar(que: str):
    async with Client(mcp) as c:
        return await getattr(c, f"list_{que}")()


# --------------------------------------------------------------------------
# 1-4 · Estructura (sin red)
# --------------------------------------------------------------------------


def test_1_hay_cuatro_herramientas():
    """Las tres pedidas más la propia."""
    nombres = {t.name for t in correr(_listar("tools"))}
    assert {"buscar_series", "serie", "resumen"} <= nombres
    assert len(nombres) >= 4, f"falta la herramienta propia; hay {nombres}"


def test_2_las_herramientas_tienen_docstring():
    """El docstring es lo que lee el modelo para decidir si usarlas."""
    for t in correr(_listar("tools")):
        assert t.description, f"{t.name} no tiene docstring"
        assert len(t.description.split()) >= 8, f"{t.name} tiene un docstring muy pobre"


def test_3_hay_un_recurso_o_una_plantilla():
    async def comprobar():
        async with Client(mcp) as c:
            recursos = await c.list_resources()
            plantillas = await c.list_resource_templates()
            return len(recursos) + len(plantillas)

    assert correr(comprobar()) >= 1


def test_4_hay_un_prompt():
    nombres = {p.name for p in correr(_listar("prompts"))}
    assert "informe" in nombres, f"prompts encontrados: {nombres}"


# --------------------------------------------------------------------------
# 5-8 · Datos reales (con red)
# --------------------------------------------------------------------------


@red
def test_5_buscar_series_encuentra_algo():
    async def pedir():
        async with Client(mcp) as c:
            return await c.call_tool("buscar_series", {"texto": "poblacion"})

    r = correr(pedir())
    assert r.data["total"] >= 1
    assert r.data["series"][0]["codigo"]
    assert "INEI" in r.data["fuente"]


@red
def test_6_serie_devuelve_datos_con_fuente():
    async def pedir():
        async with Client(mcp) as c:
            busqueda = await c.call_tool("buscar_series", {"texto": "poblacion", "limite": 1})
            codigo = busqueda.data["series"][0]["codigo"]
            return await c.call_tool("serie", {"codigo": codigo})

    r = correr(pedir())
    assert r.data["n"] >= 1
    assert r.data["datos"][0]["periodo"]
    assert isinstance(r.data["datos"][0]["valor"], (int, float))
    assert r.data["fuente"].startswith("INEI")


@red
def test_7_resumen_es_coherente_con_la_serie():
    async def pedir():
        async with Client(mcp) as c:
            busqueda = await c.call_tool("buscar_series", {"texto": "poblacion", "limite": 1})
            codigo = busqueda.data["series"][0]["codigo"]
            s = await c.call_tool("serie", {"codigo": codigo})
            r = await c.call_tool("resumen", {"codigo": codigo})
            return s.data, r.data

    s, r = correr(pedir())
    valores = [d["valor"] for d in s["datos"]]
    assert r["n"] == len(valores)
    assert r["minimo"] == min(valores)
    assert r["maximo"] == max(valores)
    assert r["ultimo"] == valores[-1]


@red
def test_8_codigo_inexistente_da_toolerror_que_lo_nombra():
    async def pedir():
        async with Client(mcp) as c:
            await c.call_tool("serie", {"codigo": "no-existe-esta-serie-999"})

    with pytest.raises(ToolError) as e:
        correr(pedir())
    assert "no-existe-esta-serie-999" in str(e.value)
