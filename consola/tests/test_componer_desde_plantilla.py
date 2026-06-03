"""`componer_desde_plantilla` inyecta la FOTO de la pieza en el documento de la plantilla.

PURO: monkeypatcheamos `renderizar_documento` (que es quien shellea a Node) para verificar SOLO
la lógica de inyección —sustituir el `objeto` de la capa imagen de fondo por la foto de la pieza
y pasar el copy-in como binding— sin ejecutar el motor Node.
"""

from __future__ import annotations

from keni_consola.dominio import estudio_imagen as ei


def _doc():
    # Plantilla del estudio: imagen de fondo (z 0) con una foto de MUESTRA + un texto con binding.
    return {
        "formato": {"w": 1080, "h": 1080},
        "capas": [
            {"tipo": "imagen", "z": 0, "objeto": "muestra.png"},
            {"tipo": "texto", "z": 1, "binding": "copy_in", "texto": ""},
        ],
    }


def test_inyecta_foto_y_copy_in(monkeypatch):
    capturado: dict = {}
    monkeypatch.setattr(
        ei, "renderizar_documento",
        lambda doc, bindings=None: (capturado.update(doc=doc, bindings=bindings),
                                    {"id": "out.png", "url": "/api/media/out.png"})[1],
    )
    doc = _doc()
    res = ei.componer_desde_plantilla(doc, copy_in="HOLA", foto="real.png")

    assert res["id"] == "out.png"
    # La capa imagen de fondo (z 0) ahora apunta a la FOTO real de la pieza, no a la de muestra.
    fondo = next(c for c in capturado["doc"]["capas"] if c["tipo"] == "imagen")
    assert fondo["objeto"] == "real.png"
    # El copy-in va como binding del titular.
    assert capturado["bindings"] == {"copy_in": "HOLA"}
    # No muta el documento de la plantilla original (deepcopy).
    assert doc["capas"][0]["objeto"] == "muestra.png"


def test_sin_foto_deja_hueco(monkeypatch):
    capturado: dict = {}
    monkeypatch.setattr(
        ei, "renderizar_documento",
        lambda doc, bindings=None: (capturado.update(doc=doc), {"id": "o.png", "url": "/x"})[1],
    )
    ei.componer_desde_plantilla(_doc(), copy_in="", foto="")
    fondo = next(c for c in capturado["doc"]["capas"] if c["tipo"] == "imagen")
    assert fondo["objeto"] == ""  # sin foto -> hueco vacío (no la de muestra)


def test_acepta_documento_como_json_string(monkeypatch):
    monkeypatch.setattr(ei, "renderizar_documento", lambda doc, bindings=None: {"id": "o", "url": "/x"})
    import json
    # No revienta si el documento llega como JSON string (lo que guarda PlantillaDiseno).
    assert ei.componer_desde_plantilla(json.dumps(_doc()), copy_in="x", foto="f.png")["id"] == "o"


def test_reencuadre_pisa_foco_y_zoom_del_fondo(monkeypatch):
    capturado: dict = {}
    monkeypatch.setattr(
        ei, "renderizar_documento",
        lambda doc, bindings=None: (capturado.update(doc=doc), {"id": "o.png", "url": "/x"})[1],
    )
    # foco/zoom de la pieza pisan el encuadre de muestra de la capa de fondo.
    ei.componer_desde_plantilla(_doc(), copy_in="", foto="f.png", foco=(0.2, 0.8), zoom=1.5)
    fondo = next(c for c in capturado["doc"]["capas"] if c["tipo"] == "imagen")
    assert fondo["foco"] == [0.2, 0.8]
    assert fondo["zoom"] == 1.5


def test_sin_reencuadre_no_toca_foco(monkeypatch):
    capturado: dict = {}
    monkeypatch.setattr(
        ei, "renderizar_documento",
        lambda doc, bindings=None: (capturado.update(doc=doc), {"id": "o.png", "url": "/x"})[1],
    )
    # Sin foco/zoom (None/0) no se inyecta encuadre: la capa de fondo no gana esas claves.
    ei.componer_desde_plantilla(_doc(), copy_in="", foto="f.png")
    fondo = next(c for c in capturado["doc"]["capas"] if c["tipo"] == "imagen")
    assert "foco" not in fondo and "zoom" not in fondo


def test_parsear_encuadre():
    # "" o JSON inválido -> sin reencuadre.
    assert ei.parsear_encuadre("") == (None, 0.0)
    assert ei.parsear_encuadre("no-json") == (None, 0.0)
    # Válido: foco recortado a [0,1], zoom a [1,6].
    foco, zoom = ei.parsear_encuadre('{"foco": [0.3, 1.9], "zoom": 12}')
    assert foco == [0.3, 1.0]
    assert zoom == 6.0
    # Sin zoom -> 0.0 (el render usa su defecto).
    foco, zoom = ei.parsear_encuadre('{"foco": [0.5, 0.5]}')
    assert foco == [0.5, 0.5]
    assert zoom == 0.0
