"""Tests de las 8 tools del MCP ejercitadas EN PROCESO (sin servidor ni red).

Replica el registro que hace `server.crear_servidor` (`registrar(mcp, fuente,
historico)`) sobre una `FastMCP` de prueba y las invoca con `mcp.call_tool`,
que es la misma superficie que usa un cliente MCP real. Asi se ejecuta la logica
de verdad de `tools.py` (antes los tests mockeaban `registrar` y nunca corrian
las funciones, dejandolas al 8% de cobertura).

`call_tool` devuelve una lista de `TextContent` cuyo `.text` es el JSON que la
tool retorno (incluido el camino de error `{"error": ...}`, que NO es excepcion).
`_payload` lo deserializa para asertar sobre el dict real.
"""

from __future__ import annotations

import json

import pytest
from mcp.server.fastmcp import FastMCP

from keni_metricas.agregador import FuenteCompuesta
from keni_metricas.config import CuentaConfig, FuenteScoped
from keni_metricas.fuentes.muestra import FuenteMuestra
from keni_metricas.historico import Historico
from keni_metricas.schema import MetricaPlataforma, Pieza, Plataforma
from keni_metricas.tools import registrar

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    # solo asyncio: las tools son corrutinas sincronas envueltas por FastMCP,
    # no hace falta probar trio.
    return "asyncio"


def _mcp(fuente, historico: Historico | None = None) -> FastMCP:
    """Una FastMCP de prueba con las 8 tools registradas sobre `fuente`."""
    mcp = FastMCP("keni-metricas-test")
    registrar(mcp, fuente, historico)
    return mcp


def _payload(resultado) -> dict:
    """Deserializa el JSON que la tool devolvio (primer bloque de texto)."""
    assert resultado, "la tool no devolvio contenido"
    bloque = resultado[0]
    return json.loads(bloque.text)


async def _llamar(mcp: FastMCP, nombre: str, **args) -> dict:
    return _payload(await mcp.call_tool(nombre, args))


# --- T1: camino feliz de las 8 tools ----------------------------------------


async def test_listar_cuentas_lista_las_marcas_y_la_fuente():
    out = await _llamar(_mcp(FuenteMuestra()), "listar_cuentas")
    assert out["fuente"] == "muestra"
    ids = [c["id"] for c in out["cuentas"]]
    assert ids == [
        "claro_sports",
        "unotv",
        "nacion_gamer",
        "piso_15",
        "fundacion",
        "claro_sports_tv",
        "csport_golf",
    ]
    # cada cuenta trae nombre y plataformas
    cs = next(c for c in out["cuentas"] if c["id"] == "claro_sports")
    assert cs["nombre"] == "Claro Sports"
    assert "tiktok" in cs["plataformas"]


async def test_metricas_resumen_trae_visualizaciones_engagement_y_por_plataforma():
    out = await _llamar(_mcp(FuenteMuestra()), "metricas_resumen", cuenta="claro_sports", rango="mes")
    assert out["cuenta"] == "claro_sports"
    assert out["rango"] == "mes"
    assert out["visualizaciones"] > 0
    assert isinstance(out["engagement_pct"], (int, float))
    assert out["por_plataforma"], "debe desglosar por plataforma"
    # cada plataforma trae su propio engagement_pct
    assert all("engagement_pct" in m for m in out["por_plataforma"])
    # variacion vs anterior usa la clave engagement_pct (convencion unica)
    assert "engagement_pct" in out["variacion_vs_anterior"]


async def test_mejores_piezas_ordenadas_por_engagement_desc():
    out = await _llamar(_mcp(FuenteMuestra()), "mejores_piezas", cuenta="claro_sports", rango="semana", n=5)
    assert out["n"] == 5
    engs = [p["engagement_pct"] for p in out["piezas"]]
    assert len(engs) == 5
    assert engs == sorted(engs, reverse=True), "deben venir ordenadas por engagement desc"


async def test_mejores_piezas_clamp_de_n_a_1_y_10():
    mcp = _mcp(FuenteMuestra())
    # por debajo: n=0 -> clamp a 1
    bajo = await _llamar(mcp, "mejores_piezas", cuenta="claro_sports", n=0)
    assert bajo["n"] == 1
    assert len(bajo["piezas"]) == 1
    # por encima: n=999 -> clamp a 10 (limite real del codigo)
    alto = await _llamar(mcp, "mejores_piezas", cuenta="claro_sports", n=999)
    assert alto["n"] == 10
    assert len(alto["piezas"]) == 10


async def test_comparar_periodos_calcula_diferencia_con_clave_engagement_pct():
    """H3: la diferencia de engagement se emite como `engagement_pct` (puntos),
    igual que historico.variacion y variacion_vs_anterior. NUNCA `engagement_pp`."""
    mcp = _mcp(FuenteMuestra())
    out = await _llamar(mcp, "comparar_periodos", cuenta="claro_sports", rango_a="semana", rango_b="mes")
    dif = out["diferencia"]
    assert "engagement_pct" in dif, "H3: la clave unificada es engagement_pct"
    assert "engagement_pp" not in dif, "H3: engagement_pp ya no debe existir"
    assert "visualizaciones_pct" in dif
    # la diferencia coincide con el delta de los dos resumenes anidados (en puntos)
    esperado = round(out["a"]["engagement_pct"] - out["b"]["engagement_pct"], 1)
    assert dif["engagement_pct"] == esperado


async def test_reporte_consolidado_devuelve_estructura_serializable():
    out = await _llamar(_mcp(FuenteMuestra()), "reporte_consolidado", rango="mes", top=2)
    assert out["rango"] == "mes"
    assert out["fuente"] == "muestra"
    assert out["total"]["cuentas"] == 7  # las 7 marcas de la muestra
    assert out["total"]["visualizaciones"] > 0
    assert out["cobertura"]["completa"] is True  # la muestra siempre responde todo
    assert len(out["cuentas"]) == 7
    # cada fila trae resumen + mejores_piezas (top=2)
    fila = out["cuentas"][0]
    assert "resumen" in fila
    assert len(fila["mejores_piezas"]) == 2
    # serializable de extremo a extremo (TextContent ya es JSON; revalidamos)
    json.dumps(out)


async def test_picos_devuelve_estructura_serializable():
    out = await _llamar(_mcp(FuenteMuestra()), "picos", rango="semana", umbral_pct=50)
    assert out["rango"] == "semana"
    assert out["umbral_pct"] == 50
    assert isinstance(out["alertas"], list)
    assert out["cobertura"]["completa"] is True
    json.dumps(out)


async def test_analisis_diario_devuelve_narrativa_con_siguiente_paso():
    out = await _llamar(_mcp(FuenteMuestra()), "analisis_diario", rango="semana")
    assert out["rango"] == "semana"
    assert out["es_muestra"] is True  # marca datos de muestra (issue #131)
    assert isinstance(out["movimientos"], list)
    # cierra con un siguiente paso accionable (loop a la accion, UX-roadmap #11)
    assert out["siguiente_paso"] is not None
    assert "Pídele a Claude" in out["siguiente_paso"]["texto"]
    json.dumps(out)


async def test_analisis_diario_rango_invalido_devuelve_error():
    out = await _llamar(_mcp(FuenteMuestra()), "analisis_diario", rango="trimestre")
    assert "error" in out
    assert "trimestre" in out["error"]


async def test_tendencia_historica_devuelve_serie_tras_poblar_el_historico():
    h = Historico(":memory:")
    mcp = _mcp(FuenteMuestra(), h)
    # un resumen guarda un snapshot en el historico...
    await mcp.call_tool("metricas_resumen", {"cuenta": "claro_sports", "rango": "semana"})
    serie = await _llamar(mcp, "tendencia_historica", cuenta="claro_sports", rango="semana")
    assert serie["cuenta"] == "claro_sports"
    assert len(serie["puntos"]) == 1
    punto = serie["puntos"][0]
    assert "visualizaciones" in punto
    assert "engagement_pct" in punto
    json.dumps(serie)


# --- T2: errores devueltos como dict (no excepcion) -------------------------


async def test_metricas_resumen_marca_inexistente_devuelve_error():
    out = await _llamar(_mcp(FuenteMuestra()), "metricas_resumen", cuenta="no_existe")
    assert "error" in out
    assert "no_existe" in out["error"]


async def test_metricas_resumen_rango_invalido_devuelve_error():
    out = await _llamar(_mcp(FuenteMuestra()), "metricas_resumen", cuenta="claro_sports", rango="trimestre")
    assert "error" in out
    assert "trimestre" in out["error"]


async def test_mejores_piezas_marca_inexistente_devuelve_error():
    out = await _llamar(_mcp(FuenteMuestra()), "mejores_piezas", cuenta="no_existe")
    assert "error" in out


async def test_comparar_periodos_rango_invalido_devuelve_error():
    out = await _llamar(_mcp(FuenteMuestra()), "comparar_periodos", cuenta="claro_sports", rango_a="decada")
    assert "error" in out


async def test_reporte_consolidado_rango_invalido_devuelve_error():
    out = await _llamar(_mcp(FuenteMuestra()), "reporte_consolidado", rango="trimestre")
    assert "error" in out


async def test_picos_rango_invalido_devuelve_error():
    out = await _llamar(_mcp(FuenteMuestra()), "picos", rango="trimestre")
    assert "error" in out


async def test_tendencia_historica_sin_historico_activo_devuelve_error_explicativo():
    # sin pasar Historico, la tool no puede dar serie y lo dice
    out = await _llamar(_mcp(FuenteMuestra(), None), "tendencia_historica", cuenta="claro_sports")
    assert "error" in out
    assert "historico" in out["error"].lower()


async def test_tendencia_historica_vacia_devuelve_puntos_vacios_con_nota():
    # historico activo pero aun sin lecturas para esa cuenta/rango
    h = Historico(":memory:")
    out = await _llamar(_mcp(FuenteMuestra(), h), "tendencia_historica", cuenta="claro_sports", rango="semana")
    assert out["puntos"] == []
    assert "nota" in out  # explica que aun no hay historico


# --- T3: scoping por marca (FuenteScoped) -----------------------------------


def _muestra_scoped(*marcas: str) -> FuenteScoped:
    return FuenteScoped(FuenteMuestra(), list(marcas))


async def test_scoped_listar_cuentas_solo_devuelve_la_marca_en_alcance():
    out = await _llamar(_mcp(_muestra_scoped("claro_sports")), "listar_cuentas")
    ids = [c["id"] for c in out["cuentas"]]
    assert ids == ["claro_sports"]


async def test_scoped_metricas_resumen_de_otra_marca_es_fuera_de_alcance():
    out = await _llamar(_mcp(_muestra_scoped("claro_sports")), "metricas_resumen", cuenta="unotv")
    assert "error" in out
    assert "alcance" in out["error"].lower()


async def test_scoped_metricas_resumen_de_la_marca_en_alcance_funciona():
    out = await _llamar(_mcp(_muestra_scoped("claro_sports")), "metricas_resumen", cuenta="claro_sports")
    assert out["cuenta"] == "claro_sports"
    assert out["visualizaciones"] > 0


# --- T11: degradacion elegante (cobertura parcial) --------------------------


class _AdaptadorOK:
    """Adaptador minimo de prueba que SI responde (cobertura ok)."""

    def __init__(self, plataforma: Plataforma, vis: int = 1000, inter: int = 50):
        self.plataforma = plataforma
        self._vis = vis
        self._inter = inter

    def disponible(self) -> bool:
        return True

    def metricas(self, handle, desde, hasta):
        return MetricaPlataforma(
            plataforma=self.plataforma,
            visualizaciones=self._vis,
            alcance=int(self._vis * 0.7),
            interacciones=self._inter,
            engagement_pct=round(self._inter / self._vis * 100, 1),
        )

    def piezas(self, handle, desde, hasta, n):
        return [
            Pieza(
                id=f"{self.plataforma.value}-1",
                plataforma=self.plataforma,
                titulo="pieza",
                publicado=hasta,
                visualizaciones=self._vis,
                interacciones=self._inter,
                engagement_pct=round(self._inter / self._vis * 100, 1),
            )
        ]


def _fuente_parcial() -> FuenteCompuesta:
    """Marca con facebook OK y tiktok configurada PERO sin adaptador (omitida).

    Mismo patron que test_cobertura.py: el adaptador de tiktok no se inyecta, asi
    que la fuente la reporta como omitida por `sin_credenciales`.
    """
    cuenta = CuentaConfig(
        id="marca",
        nombre="Marca",
        plataformas={Plataforma.facebook: "h1", Plataforma.tiktok: "h2"},
    )
    return FuenteCompuesta([cuenta], {Plataforma.facebook: _AdaptadorOK(Plataforma.facebook)})


async def test_metricas_resumen_refleja_cobertura_parcial():
    out = await _llamar(_mcp(_fuente_parcial()), "metricas_resumen", cuenta="marca", rango="semana")
    cob = out["cobertura"]
    assert cob["ok"] == ["facebook"]
    assert cob["omitidas"] == ["tiktok"]
    assert cob["motivo"] == {"tiktok": "sin_credenciales"}


async def test_reporte_consolidado_refleja_cobertura_parcial():
    out = await _llamar(_mcp(_fuente_parcial()), "reporte_consolidado", rango="semana", top=1)
    assert out["cobertura"]["completa"] is False
    assert out["cobertura"]["cuentas_parciales"] == ["marca"]
    # la fila de la marca tambien lleva su propia cobertura
    cob_fila = out["cuentas"][0]["resumen"]["cobertura"]
    assert cob_fila["omitidas"] == ["tiktok"]


async def test_picos_refleja_cobertura_parcial():
    out = await _llamar(_mcp(_fuente_parcial()), "picos", rango="semana", umbral_pct=50)
    assert out["cobertura"]["completa"] is False
    assert out["cobertura"]["cuentas_parciales"] == ["marca"]


# --- degradacion EXPLICITA --------------------------------------------------


async def test_comparar_periodos_sin_baseline_omite_visualizaciones_pct():
    """Con baseline 0 (b sin visualizaciones) la clave se OMITE: un 0.0 era
    indistinguible de 'sin variacion real' (mismo patron que engagement_pct)."""
    vacia = CuentaConfig(id="vacia", nombre="Vacia", plataformas={})
    out = await _llamar(
        _mcp(FuenteCompuesta([vacia], {})),
        "comparar_periodos",
        cuenta="vacia",
        rango_a="semana",
        rango_b="mes",
    )
    assert "visualizaciones_pct" not in out["diferencia"]
    assert "engagement_pct" not in out["diferencia"]  # ambos None: tampoco hay delta


async def test_mejores_piezas_expone_cobertura_parcial_con_nota():
    """Si una plataforma configurada no aporto piezas (p. ej. sin credenciales), la
    respuesta lo dice (`cobertura` + `nota`), en vez de degradar en silencio."""
    cuenta = CuentaConfig(
        id="marca", nombre="Marca", plataformas={Plataforma.tiktok: "h1"}
    )
    out = await _llamar(
        _mcp(FuenteCompuesta([cuenta], {})), "mejores_piezas", cuenta="marca", n=3
    )
    assert out["piezas"] == []
    assert out["cobertura"]["omitidas"] == ["tiktok"]
    assert out["cobertura"]["motivo"]["tiktok"] == "sin_credenciales"
    assert "PARCIAL" in out["nota"] and "tiktok" in out["nota"]


async def test_mejores_piezas_sin_degradacion_no_anade_nota():
    """La muestra responde todo: ni `nota` ni `cobertura` (la respuesta no cambia)."""
    out = await _llamar(_mcp(FuenteMuestra()), "mejores_piezas", cuenta="claro_sports", n=2)
    assert "nota" not in out
    assert "cobertura" not in out
