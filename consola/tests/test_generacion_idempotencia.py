"""Tests de la IDEMPOTENCIA del lanzamiento de generaciones (item HIGH: coste + drafts dup).

Un doble-click en la UI (o un POST reintentado) llamaba a `dominio.generar.lanzar` y mintaba un
`gen_id` FRESCO por llamada -> dos `claude -p` -> dos borradores competidores del mismo tema. El
guardia de idempotencia (clave estable derivada del lanzamiento + claim atomico en disco) hace
que dos lanzamientos del MISMO trabajo CONVERJAN a UNA sola generacion, mientras un lanzamiento
DISTINTO sigue arrancando el suyo.

OFFLINE: nunca se llama a `claude`. Se inyecta un `encolar_job_claude` fake que solo CUENTA las
veces que se encola (= numero de runs que arrancarian), sin tocar la cola ni Popen.
"""

from __future__ import annotations

import pytest

from keni_consola import generaciones
from keni_consola.dominio import generar

_MARCA = "unotv"


@pytest.fixture
def cuenta_encolados(monkeypatch):
    """Parchea `generaciones.encolar_job_claude` por un fake que solo cuenta los encolados.

    Devuelve una lista mutable con los `gen_id` encolados: su longitud es cuantos `claude -p`
    arrancarian. No toca la cola ni el worker (OFFLINE).
    """
    encolados: list[str] = []

    def _fake_encolar(gen_id, *, prompt, cwd, procesar, dir_temporal=None, spec=None):  # noqa: ANN001
        encolados.append(gen_id)

    monkeypatch.setattr(generaciones, "encolar_job_claude", _fake_encolar)
    return encolados


def _lanzar(prompt: str, *, autor=None, tipo="copy", marca=_MARCA):
    """Lanza una generacion NEUTRA (sin post-procesado real): el fake solo cuenta el encolado."""
    return generar.lanzar(
        tipo=tipo,
        titulo="Copy",
        marca=marca,
        prompt=prompt,
        procesar=lambda salida, metricas: {},
        procesar_spec={},
        autor=autor,
    )


# --------------------------------------------------------------------------- #
# Clave de idempotencia: estable para lo igual, distinta para lo distinto      #
# --------------------------------------------------------------------------- #


def test_clave_idempotencia_estable_y_distinta():
    a = generaciones.clave_idempotencia("u1", "copy", _MARCA, "prompt X")
    b = generaciones.clave_idempotencia("u1", "copy", _MARCA, "prompt X")
    c = generaciones.clave_idempotencia("u1", "copy", _MARCA, "prompt Y")
    assert a == b  # mismas partes -> misma clave
    assert a != c  # otro prompt (otro tema) -> otra clave
    assert all(ch in "0123456789abcdef" for ch in a)  # nombre de fichero seguro


# --------------------------------------------------------------------------- #
# crear_idempotente: convergencia + reciclaje tras terminar                    #
# --------------------------------------------------------------------------- #


def test_crear_idempotente_converge_misma_clave(entorno):
    datos = {"tipo": "copy", "marca": _MARCA, "etiqueta": "X"}
    g1, nueva1 = generaciones.crear_idempotente("aa11", datos)
    g2, nueva2 = generaciones.crear_idempotente("aa11", datos)
    assert nueva1 is True  # el primero crea
    assert nueva2 is False  # el segundo NO crea: comparte el run en vuelo
    assert g1["id"] == g2["id"]  # misma generacion


def test_crear_idempotente_distinta_clave_arranca_otra(entorno):
    g1, n1 = generaciones.crear_idempotente("aa11", {"tipo": "copy", "marca": _MARCA, "etiqueta": "X"})
    g2, n2 = generaciones.crear_idempotente("bb22", {"tipo": "copy", "marca": _MARCA, "etiqueta": "Y"})
    assert n1 is True and n2 is True
    assert g1["id"] != g2["id"]


def test_crear_idempotente_recicla_tras_terminal(entorno):
    """Un re-lanzamiento legitimo TRAS completar el run anterior vuelve a crear (no se bloquea)."""
    g1, n1 = generaciones.crear_idempotente("cc33", {"tipo": "copy", "marca": _MARCA, "etiqueta": "X"})
    assert n1 is True
    # El run termina (completado): la idempotencia ya no debe retener a un nuevo lanzamiento.
    generaciones.actualizar(g1["id"], {"estado": generaciones.ESTADO_COMPLETADO})
    g2, n2 = generaciones.crear_idempotente("cc33", {"tipo": "copy", "marca": _MARCA, "etiqueta": "X"})
    assert n2 is True  # corre de nuevo
    assert g2["id"] != g1["id"]


# --------------------------------------------------------------------------- #
# lanzar: dos lanzamientos identicos -> UN encolado; uno distinto -> el suyo   #
# --------------------------------------------------------------------------- #


def test_lanzar_doble_identico_converge_a_un_run(entorno, cuenta_encolados):
    autor = {"id": "u1", "usuario": "ana"}
    g1 = _lanzar("PROMPT IDENTICO", autor=autor)
    g2 = _lanzar("PROMPT IDENTICO", autor=autor)
    # Convergen a la MISMA generacion y SOLO se encola un run (un solo `claude -p`).
    assert g1["id"] == g2["id"]
    assert cuenta_encolados == [g1["id"]]


def test_lanzar_distinto_arranca_su_propio_run(entorno, cuenta_encolados):
    autor = {"id": "u1", "usuario": "ana"}
    g1 = _lanzar("PROMPT UNO", autor=autor)
    g2 = _lanzar("PROMPT DOS", autor=autor)  # otro tema -> otra clave
    assert g1["id"] != g2["id"]
    assert sorted(cuenta_encolados) == sorted([g1["id"], g2["id"]])  # dos runs distintos


def test_lanzar_limpia_temporal_del_lanzamiento_redundante(entorno, cuenta_encolados, tmp_path):
    """El segundo lanzamiento (redundante) limpia el `dir_temporal` que preparó y no se usará."""
    autor = {"id": "u1", "usuario": "ana"}
    _lanzar("PROMPT IDENTICO", autor=autor)
    temp = tmp_path / "subida"
    temp.mkdir()
    (temp / "foto.png").write_bytes(b"x")
    g2 = generar.lanzar(
        tipo="copy", titulo="Copy", marca=_MARCA, prompt="PROMPT IDENTICO",
        procesar=lambda s, m: {}, procesar_spec={}, autor=autor, dir_temporal=temp,
    )
    # Convergió al run en vuelo (no encoló otro) y borró el temporal redundante.
    assert len(cuenta_encolados) == 1
    assert not temp.exists()
    assert g2["id"] == cuenta_encolados[0]
