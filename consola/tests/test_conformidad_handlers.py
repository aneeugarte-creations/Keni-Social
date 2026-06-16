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

from keni_consola.esquema_api import esquema_json

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
