"""ESPEJO entre redes + CLONAR a otra red (`/api/piezas`).

Una idea (`contenido`) suele ir PAREJA en todas sus redes, así que el espejo nace ACTIVADO
(`contenido.espejo`): editar el contenido de una pieza por el PUT lo propaga a sus redes
hermanas (saltando las ya publicadas, con el mismo reset de aprobaciones). `clonar` copia
el contenido a OTRA red de la MISMA idea (creando la pieza si la idea no salía ahí), a
diferencia de `duplicar` (que crea una idea nueva).

Requiere Postgres de pruebas (fixture `entorno`/`cliente`). Scope CI: app_operacion.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.app_operacion

_ORIGIN = {"Origin": "http://testserver"}


def _crear_idea(cliente, redes=("x", "instagram"), **extra):
    """Una idea con N redes; devuelve (contenido, {red: pieza_id})."""
    r = cliente.post(
        "/api/publicaciones",
        json={"titulo": "Idea", "redes": list(redes), **extra},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    cont = r.json()["contenido"]
    return cont, {p["red"]: p["id"] for p in cont["plataformas"]}


def _pub(cliente, pid: str) -> dict:
    r = cliente.get(f"/api/piezas/{pid}")
    assert r.status_code == 200, r.text
    return r.json()["pieza"]


# --------------------------------------------------------------------------- #
# Espejo entre redes (default ON)                                             #
# --------------------------------------------------------------------------- #


def test_espejo_nace_activado_y_propaga_contenido(cliente):
    _cont, por_red = _crear_idea(cliente)
    r = cliente.put(
        f"/api/piezas/{por_red['x']}",
        json={"contenido": "Copy nuevo", "copy_in": "Titular", "foto": "f1.webp"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["pieza"]["espejo"] is True
    hermana = _pub(cliente, por_red["instagram"])
    assert hermana["contenido"] == "Copy nuevo"
    assert hermana["copy_in"] == "Titular"
    assert hermana["foto"] == "f1.webp"


def test_espejo_propaga_estado_falta_imagen_a_las_hermanas(cliente):
    """Al añadir la foto a UNA red, el ESPEJO actualiza la flag ALMACENADA `falta_imagen`
    de las hermanas (lo que lee la LISTA del feed), sin tener que abrir cada una.

    El espejo NO aprueba en las hermanas, pero SÍ refleja el estado de contenido.
    """
    from keni_consola import repos

    _cont, por_red = _crear_idea(cliente)
    # Ambas nacen sin foto: les FALTA imagen (flag almacenada).
    assert bool(repos.obtener_pieza_fila(por_red["instagram"])["falta_imagen"]) is True

    r = cliente.put(f"/api/piezas/{por_red['x']}", json={"foto": "f1.webp"})
    assert r.status_code == 200, r.text

    # La editada Y su espejo tienen la flag ALMACENADA ya a 0 (sin reabrir la hermana).
    assert bool(repos.obtener_pieza_fila(por_red["x"])["falta_imagen"]) is False
    assert bool(repos.obtener_pieza_fila(por_red["instagram"])["falta_imagen"]) is False


def test_espejo_off_cada_red_por_separado(cliente):
    _cont, por_red = _crear_idea(cliente)
    r = cliente.put(f"/api/piezas/{por_red['x']}", json={"espejo": False})
    assert r.status_code == 200, r.text
    assert r.json()["pieza"]["espejo"] is False
    # El toggle vive en el PADRE: la hermana también lo ve apagado.
    assert _pub(cliente, por_red["instagram"])["espejo"] is False
    r = cliente.put(f"/api/piezas/{por_red['x']}", json={"contenido": "Solo X"})
    assert r.status_code == 200, r.text
    assert _pub(cliente, por_red["instagram"])["contenido"] == ""


def test_espejo_no_bool_400(cliente):
    _cont, por_red = _crear_idea(cliente)
    r = cliente.put(f"/api/piezas/{por_red['x']}", json={"espejo": "si"})
    assert r.status_code == 400


def test_espejo_no_toca_hermanas_publicadas(cliente):
    _cont, por_red = _crear_idea(cliente)
    r = cliente.put(f"/api/piezas/{por_red['instagram']}", json={"estado": "publicado"})
    assert r.status_code == 200, r.text
    r = cliente.put(f"/api/piezas/{por_red['x']}", json={"contenido": "Editado"})
    assert r.status_code == 200, r.text
    hermana = _pub(cliente, por_red["instagram"])
    assert hermana["estado"] == "publicado"
    assert hermana["contenido"] == ""  # lo que salió a la red no cambia desde aquí


def test_espejo_resetea_hermana_con_aprobaciones(cliente):
    _cont, por_red = _crear_idea(cliente)
    # `programado` es el estado "plenamente aprobado" del modelo nuevo (aprobar = juntar los 2
    # likes -> auto-programa; sustituye al retirado `aprobado`): tiene aprobación que perder.
    r = cliente.put(f"/api/piezas/{por_red['instagram']}", json={"estado": "programado"})
    assert r.status_code == 200, r.text
    r = cliente.put(f"/api/piezas/{por_red['x']}", json={"contenido": "Editado"})
    assert r.status_code == 200, r.text
    hermana = _pub(cliente, por_red["instagram"])
    # El contenido cambió: la hermana pierde su aprobación (mismo reset que la pieza editada).
    assert hermana["contenido"] == "Editado"
    assert hermana["estado"] == "borrador"


def test_espejo_no_propaga_estado_ni_fecha(cliente):
    _cont, por_red = _crear_idea(cliente)
    r = cliente.put(f"/api/piezas/{por_red['x']}", json={"estado": "en_revision"})
    assert r.status_code == 200, r.text
    assert _pub(cliente, por_red["instagram"])["estado"] == "borrador"


# --------------------------------------------------------------------------- #
# Clonar a otra red (misma idea)                                              #
# --------------------------------------------------------------------------- #


def test_clonar_crea_la_pieza_en_una_red_nueva(cliente):
    cont, por_red = _crear_idea(cliente, redes=("x",))
    r = cliente.put(
        f"/api/piezas/{por_red['x']}",
        json={"contenido": "Copy", "copy_in": "T", "foto": "f.webp"},
    )
    assert r.status_code == 200, r.text
    r = cliente.post(
        f"/api/piezas/{por_red['x']}/clonar", json={"red": "tiktok"}, headers=_ORIGIN
    )
    assert r.status_code == 200, r.text
    pub = r.json()["pieza"]
    assert pub["red"] == "tiktok"
    assert pub["publicacion_id"] == cont["id"]  # misma idea, NO una idea nueva
    assert pub["estado"] == "borrador"
    assert pub["contenido"] == "Copy"
    assert pub["copy_in"] == "T"
    assert pub["foto"] == "f.webp"


def test_clonar_sobrescribe_la_hermana_existente(cliente):
    _cont, por_red = _crear_idea(cliente)
    r = cliente.put(f"/api/piezas/{por_red['x']}", json={"espejo": False})
    assert r.status_code == 200, r.text
    r = cliente.put(f"/api/piezas/{por_red['x']}", json={"contenido": "Copy X"})
    assert r.status_code == 200, r.text
    assert _pub(cliente, por_red["instagram"])["contenido"] == ""  # divergieron
    r = cliente.post(
        f"/api/piezas/{por_red['x']}/clonar", json={"red": "instagram"}, headers=_ORIGIN
    )
    assert r.status_code == 200, r.text
    assert r.json()["pieza"]["id"] == por_red["instagram"]
    assert _pub(cliente, por_red["instagram"])["contenido"] == "Copy X"


def test_clonar_red_invalida_o_la_misma_400(cliente):
    _cont, por_red = _crear_idea(cliente, redes=("x",))
    pid = por_red["x"]
    assert (
        cliente.post(f"/api/piezas/{pid}/clonar", json={"red": "myspace"}, headers=_ORIGIN)
    ).status_code == 400
    assert (
        cliente.post(f"/api/piezas/{pid}/clonar", json={"red": "x"}, headers=_ORIGIN)
    ).status_code == 400


def test_clonar_sobre_publicada_409(cliente):
    _cont, por_red = _crear_idea(cliente)
    r = cliente.put(f"/api/piezas/{por_red['x']}", json={"espejo": False})
    assert r.status_code == 200, r.text
    r = cliente.put(f"/api/piezas/{por_red['instagram']}", json={"estado": "publicado"})
    assert r.status_code == 200, r.text
    r = cliente.post(
        f"/api/piezas/{por_red['x']}/clonar", json={"red": "instagram"}, headers=_ORIGIN
    )
    assert r.status_code == 409


def test_clonar_404(cliente):
    r = cliente.post("/api/piezas/no-existe/clonar", json={"red": "x"}, headers=_ORIGIN)
    assert r.status_code == 404
