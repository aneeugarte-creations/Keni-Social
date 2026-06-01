"""Conformidad LIVE handler ↔ contrato (`esquema_api`) para las áreas de churn (#120).

`test_esquema_api.py` solo ancla TS ↔ esquema (que el `types.gen.ts` siga al
`TypedDict`). NO comprueba que el handler HTTP emita de verdad esa forma: los
handlers arman dicts ad-hoc. Este módulo cierra ese hueco para las entidades de
mayor churn (publicaciones, runs, comercial): ejercita el endpoint REAL (TestClient,
todo OFFLINE) y comprueba que el JSON emitido CUMPLE su `$def`:

  - todas las claves REQUERIDAS del `$def` están presentes, y
  - el handler NO emite claves que el contrato desconozca (las claves del response
    son subconjunto de las `properties` del `$def`). El emisor deja
    `additionalProperties` abierto a propósito (cambios aditivos del backend), pero
    aquí EXIGIMOS que un campo nuevo del handler se modele también en el `TypedDict`,
    porque si no, el frontend nunca lo verá tipado (drift silencioso al revés).

Generaciones se DEFIERE del subconjunto generado (su `resultado` es libre y el
frontend lo tipa rico); por eso no aparece aquí.
"""

from __future__ import annotations

from keni_consola import agentes
from keni_consola.dominio import stream as skills  # stream reúne lo que era la fachada api.skills
from keni_consola.esquema_api import esquema_json

from .conftest import _cliente

_MARCA = "unotv"
_DEFS = esquema_json()["$defs"]


# --------------------------------------------------------------------------- #
# Helper de conformidad: response (dict) cumple un `$def`                      #
# --------------------------------------------------------------------------- #


def _conforma(datos: dict, def_nombre: str) -> None:
    """Afirma que `datos` cumple el `$def` `def_nombre`: requeridos presentes y
    sin claves fuera de `properties` (drift handler↔contrato en ambos sentidos)."""
    esquema = _DEFS[def_nombre]
    props = set(esquema.get("properties", {}))
    requeridos = set(esquema.get("required", []))
    claves = set(datos)
    faltan = requeridos - claves
    assert not faltan, f"{def_nombre}: faltan claves requeridas {sorted(faltan)} en {sorted(claves)}"
    extra = claves - props
    assert not extra, (
        f"{def_nombre}: el handler emite claves NO modeladas {sorted(extra)}; "
        f"añádelas al TypedDict en esquema_api/modelos.py y regenera (npm run gen:types)"
    )


# --------------------------------------------------------------------------- #
# Publicaciones                                                                #
# --------------------------------------------------------------------------- #


def _crear_pub(cli, **campos):
    base = {"marca": "unotv", "red": "x", "titulo": "T", "contenido": "C"}
    base.update(campos)
    return cli.post("/api/publicaciones", json=base)


def test_publicacion_conforma(cliente):
    _crear_pub(cliente)
    pub = cliente.get("/api/publicaciones").json()["publicaciones"][0]
    _conforma(pub, "Publicacion")


def test_respuesta_publicaciones_conforma(cliente):
    _crear_pub(cliente)
    resp = cliente.get("/api/publicaciones").json()
    _conforma(resp, "RespuestaPublicaciones")
    _conforma(resp["paginacion"], "Paginacion")


def test_respuesta_publicacion_detalle_conforma(cliente):
    pid = _crear_pub(cliente).json()["publicacion"]["id"]
    resp = cliente.get(f"/api/publicaciones/{pid}").json()
    _conforma(resp, "RespuestaPublicacion")
    _conforma(resp["publicacion"], "Publicacion")


def test_publicacion_fecha_programada_y_origen_son_cadena(cliente):
    """El backend SIEMPRE emite `fecha_programada`/`origen` como cadena (nunca null)."""
    pub = _crear_pub(cliente).json()["publicacion"]
    assert pub["fecha_programada"] == ""
    assert pub["origen"] == ""
    assert isinstance(pub["fecha_programada"], str)
    assert isinstance(pub["origen"], str)


# --------------------------------------------------------------------------- #
# Runs (canónico, listado por agente, listado global, agregados)              #
# --------------------------------------------------------------------------- #


_METRICAS_DEMO = skills.MetricasRun(
    tokens_in=130, tokens_out=50, num_turns=3, total_cost_usd=0.0123,
    duration_ms=4200, session_id="sess-abc-123", modelo="claude-opus-4-7",
)


def _lanzador_con_metricas(texto: str, metricas: skills.MetricasRun):
    def lanzar(marca_id, run_id, prompt, *, cwd):  # noqa: ANN001
        agentes.actualizar_run(
            marca_id, run_id,
            {"estado": "completado", "salida": texto,
             "metricas": skills.metricas_a_dict(metricas), "fecha_fin": agentes.ahora_iso()},
        )

    return lanzar


def test_run_canonico_conforma(entorno):
    c = _cliente(lanzar_run=_lanzador_con_metricas("salida", _METRICAS_DEMO))
    run = c.post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "p"}).json()["run"]
    # El run completo trae salida/fecha_fin (NotRequired pero presentes).
    _conforma(run, "Run")
    assert {"salida", "fecha_fin"} <= set(run)
    detalle = c.get(f"/api/agentes/{_MARCA}/runs/{run['id']}").json()["run"]
    _conforma(detalle, "Run")
    _conforma(detalle["metricas"], "MetricasRun")


def test_run_interactivo_envelope_lleva_mensaje(entorno):
    c = _cliente()  # abrir mock devuelve "ok-mock"
    resp = c.post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "p", "modo": "interactivo"}).json()
    _conforma(resp, "RespuestaRun")
    assert "mensaje" in resp  # solo el lanzamiento interactivo lo añade
    _conforma(resp["run"], "Run")


def test_respuesta_runs_por_agente_conforma(entorno):
    c = _cliente(lanzar_run=_lanzador_con_metricas("ok", _METRICAS_DEMO))
    c.post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "p"})
    resp = c.get(f"/api/agentes/{_MARCA}/runs").json()
    _conforma(resp, "RespuestaRuns")  # sin paginacion (NotRequired)
    for run in resp["runs"]:
        _conforma(run, "Run")


def test_respuesta_runs_global_conforma(entorno):
    c = _cliente(lanzar_run=_lanzador_con_metricas("ok", _METRICAS_DEMO))
    c.post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "p"})
    resp = c.get("/api/runs").json()
    _conforma(resp, "RespuestaRuns")
    _conforma(resp["paginacion"], "Paginacion")
    for run in resp["runs"]:
        _conforma(run, "Run")
        # El listado global denormaliza agente/agente_nombre y omite salida/fecha_fin.
        assert {"agente", "agente_nombre"} <= set(run)


def test_respuesta_runs_agregados_conforma(entorno):
    c = _cliente(lanzar_run=_lanzador_con_metricas("ok", _METRICAS_DEMO))
    c.post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "p"})
    resp = c.get("/api/runs/agregados").json()
    _conforma(resp, "RespuestaRunsAgregados")
    _conforma(resp["total"], "TotalRuns")
    for fila in resp["por_agente"]:
        _conforma(fila, "AgregadoPorAgente")
    for fila in resp["por_dia"]:
        _conforma(fila, "AgregadoPorDia")


# --------------------------------------------------------------------------- #
# Comercial (lista con fuente/es_muestra, detalle con serie, refrescar)       #
# --------------------------------------------------------------------------- #

_URL = "https://www.instagram.com/p/ABC123/"


def _crear_comercial(cli, **campos):
    return cli.post("/api/comercial/publicaciones", json={"url": _URL, **campos})


def test_publicacion_comercial_conforma(cliente):
    pub = _crear_comercial(cliente, objetivo=100).json()["publicacion"]
    _conforma(pub, "PublicacionComercial")
    _conforma(pub["actual"], "ActualComercial")
    # El alta usa con_serie=True: la serie viene y conforma.
    assert "serie" in pub
    for snap in pub["serie"]:
        _conforma(snap, "SnapshotComercial")


def test_respuesta_publicaciones_comercial_conforma(cliente):
    _crear_comercial(cliente)
    resp = cliente.get("/api/comercial/publicaciones").json()
    _conforma(resp, "RespuestaPublicacionesComercial")
    assert resp["fuente"] and isinstance(resp["es_muestra"], bool)  # #124
    for pub in resp["publicaciones"]:
        _conforma(pub, "PublicacionComercial")


def test_respuesta_publicacion_comercial_detalle_conforma(cliente):
    cid = _crear_comercial(cliente).json()["publicacion"]["id"]
    resp = cliente.get(f"/api/comercial/publicaciones/{cid}").json()
    _conforma(resp, "RespuestaPublicacionComercial")
    _conforma(resp["publicacion"], "PublicacionComercial")


def test_respuesta_refrescar_comercial_conforma(cliente):
    _crear_comercial(cliente)
    resp = cliente.post("/api/comercial/refrescar").json()
    _conforma(resp, "RespuestaRefrescarComercial")


def test_listado_comercial_sin_serie(cliente):
    """En el LISTADO la pieza NO trae `serie` (peso); `serie` es NotRequired en el `$def`."""
    _crear_comercial(cliente)
    pub = cliente.get("/api/comercial/publicaciones").json()["publicaciones"][0]
    assert "serie" not in pub
    _conforma(pub, "PublicacionComercial")
