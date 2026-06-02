"""Tests del panel ligero (#9, Fase 3): dashboard de un vistazo. OFFLINE, DB en tmp.

Cubre la agregacion de lectura del panel: resumen de metricas (reusa el camino de
Metricas con datos de muestra), contador de la cola de aprobacion y proximas piezas
programadas con su marca dry-run. Solo LECTURA: no muta nada.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import repos

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
_MARCA = "unotv"


def _cli() -> TestClient:
    return TestClient(
        app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False),
        headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"},
    )


def _crear(cli: TestClient, estado: str = "borrador", **campos) -> dict:
    base = {"marca": _MARCA, "red": "x", "titulo": "T", "contenido": "C", "estado": estado}
    base.update(campos)
    r = cli.post("/api/publicaciones", json=base, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()["publicacion"]


def test_panel_forma_basica(entorno):
    """El panel devuelve los cuatro bloques: metricas, cola, proximas y gating."""
    cli = _cli()
    datos = cli.get("/api/panel").json()
    assert set(datos) == {"metricas", "cola", "proximas", "gating"}
    # Metricas de muestra disponibles (fuente offline => "muestra").
    assert datos["metricas"]["disponible"] is True
    assert datos["metricas"]["fuente"] == "muestra"
    assert "visualizaciones" in datos["metricas"]["total"]
    # Gating: el sistema NO publica solo (frontera del producto, gated por KENI_PUBLICAR_REAL).
    assert datos["gating"]["publicacion_real_activa"] is False
    assert datos["gating"]["nota"]


def test_panel_cuenta_la_cola_de_aprobacion(entorno):
    """El contador de la cola refleja las piezas en revision (y no las demas)."""
    cli = _cli()
    p1 = _crear(cli)
    _crear(cli)  # se queda en borrador
    cli.post(f"/api/aprobacion/{p1['id']}/enviar-a-revision", headers=_ORIGIN)
    datos = cli.get("/api/panel").json()
    assert datos["cola"]["total"] == 1


def test_panel_lista_proximas_programadas_ordenadas(entorno):
    """Las proximas programadas salen ordenadas por fecha (mas inminente primero)."""
    cli = _cli()
    tarde = _crear(cli, estado="aprobado", titulo="Tarde")
    pronto = _crear(cli, estado="aprobado", titulo="Pronto")
    f_tarde = (datetime.now() + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M")
    f_pronto = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    cli.post(f"/api/aprobacion/{tarde['id']}/programar", json={"fecha": f_tarde}, headers=_ORIGIN)
    cli.post(f"/api/aprobacion/{pronto['id']}/programar", json={"fecha": f_pronto}, headers=_ORIGIN)

    datos = cli.get("/api/panel").json()
    proximas = datos["proximas"]
    assert proximas["total"] == 2
    assert [p["titulo"] for p in proximas["items"]] == ["Pronto", "Tarde"]
    # Aun no vencidas: sin marca dry-run.
    assert all(p["preparado_en"] == "" for p in proximas["items"])


def test_panel_muestra_marca_dry_run_en_preparadas(entorno):
    """Una pieza ya vencida y preparada aparece con su `preparado_en` (dry-run)."""
    from keni_consola.programador import preparar_vencidas

    cli = _cli()
    pub = _crear(cli, estado="programado")
    pasado = (datetime.now() - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M")
    repos.actualizar_publicacion(pub["id"], {"fecha_programada": pasado})
    preparar_vencidas(datetime.now())

    datos = cli.get("/api/panel").json()
    item = next(p for p in datos["proximas"]["items"] if p["id"] == pub["id"])
    assert item["preparado_en"]  # marca dry-run visible en el panel


def test_panel_lista_del_dia_colapsa_una_pieza_por_red(entorno):
    """Una pieza preparada para varias redes son varios temas con el MISMO título (el
    handoff crea un borrador por red). La lista del día solo muestra el título, así que se
    colapsan a UNO; otra pieza distinta NO se colapsa con ella."""
    cli = _cli()
    for red in ("x", "instagram", "facebook"):
        _crear(cli, red=red, titulo="Misma nota")
    _crear(cli, titulo="Otra nota")

    lista = cli.get("/api/panel/dia").json()
    titulos = [it["titulo"] for it in lista["items"]]
    assert titulos.count("Misma nota") == 1
    assert titulos.count("Otra nota") == 1
    assert lista["total"] == 2


def test_panel_rango_invalido_cae_a_semana(entorno):
    cli = _cli()
    datos = cli.get("/api/panel?rango=loquesea").json()
    assert datos["metricas"]["rango"] == "semana"


def test_panel_tuberia_forma_y_conteo(entorno):
    """Observabilidad de la tuberia (Flujo C): conteo de temas por etapa, forma estable.

    Una pieza creada con `origen='equipo'` y sin imagen entra como 'generando_arte' (tiene
    copy, le falta imagen); una pieza con copy + imagen es 'lista_para_revisar'.
    """
    from keni_consola import pipeline_estado as pe

    cli = _cli()
    _crear(cli, origen="equipo", titulo="Con copy sin arte")  # copy='C', sin imagen
    _crear(cli, origen="equipo", titulo="Completa", imagen="img.png")

    datos = cli.get("/api/panel/tuberia").json()
    # Forma estable para la UI: todas las etapas de la tuberia presentes, en orden canonico.
    assert set(datos["por_etapa"]) == set(pe.ETAPAS[:-1])
    assert datos["etapas"] == list(pe.ETAPAS[:-1])
    assert datos["por_etapa"][pe.ETAPA_GENERANDO_ARTE] >= 1
    assert datos["por_etapa"][pe.ETAPA_LISTA_REVISAR] >= 1
    assert datos["total"] == sum(datos["por_etapa"].values())
