"""Tests del REGISTRO declarativo de daemons (`daemons_registro`) y del estado "sin_datos".

Tres frentes:
  - COMPLETITUD por AST: cada `iniciar_*` cableado en `daemons.py` tiene entrada(s) en el
    registro y viceversa — no se puede añadir un daemon nuevo sin registrarlo.
  - SINTONÍA con las fuentes únicas de `latidos` (barribles/gates apuntan a nombres
    registrados; ningún registrado está retirado).
  - SONDA: un daemon registrado SIN fila de latido sale "sin_datos" en
    `GET /api/sistema/daemons` (misma forma que una fila real), una fila real lo
    sustituye, su historial de barridos responde vacío (no 404) y el endpoint sigue
    siendo solo-admin.
"""

from __future__ import annotations

import ast
from pathlib import Path

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, daemons_registro, db, latidos

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"


def _cli_como(rol: str) -> TestClient:
    auth.crear_usuario("u", CLAVE, rol)
    c = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))
    r = c.post(
        "/api/auth/login", json={"usuario": "u", "password": CLAVE}, headers=_ORIGIN
    )
    assert r.status_code == 200
    return c


# --------------------------------------------------------------------------- #
# Completitud: el registro cubre EXACTAMENTE lo que daemons.py cablea          #
# --------------------------------------------------------------------------- #


def _iniciadores_cableados() -> set[str]:
    """Las funciones `iniciar_*` que `daemons.py` LLAMA, leídas de su AST."""
    import keni_consola

    fuente = (Path(keni_consola.__file__).parent / "daemons.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    llamadas: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call):
            fn = nodo.func
            nombre = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            if nombre.startswith("iniciar_"):
                llamadas.add(nombre)
    return llamadas


def test_registro_cubre_cada_iniciador_de_daemons_py():
    # AMBOS sentidos: un `iniciar_*` nuevo en daemons.py sin entrada aquí (o sin declararse
    # listener en INICIADORES_SIN_DAEMON) rompe; una entrada del registro cuyo iniciador ya
    # no se cablea, también.
    cableados = _iniciadores_cableados()
    assert cableados, "daemons.py no llama a ningún iniciar_*: ¿se movió el cableado?"
    declarados = daemons_registro.iniciadores() | daemons_registro.INICIADORES_SIN_DAEMON
    sin_registrar = cableados - declarados
    assert not sin_registrar, (
        f"daemons.py arranca {sorted(sin_registrar)} pero no está(n) en daemons_registro. "
        "Añade su(s) daemon(s) al REGISTRO (o a INICIADORES_SIN_DAEMON si no deja latidos)."
    )
    huerfanos = declarados - cableados
    assert not huerfanos, (
        f"daemons_registro declara {sorted(huerfanos)} pero daemons.py ya no lo(s) cablea. "
        "Retira la(s) entrada(s) del REGISTRO (y añade el nombre a latidos.RETIRADOS si "
        "quedan filas viejas en daemon_latidos)."
    )


def test_registro_nombres_unicos_y_no_retirados():
    nombres = daemons_registro.esperados()
    assert len(nombres) == len(set(nombres))
    assert not set(nombres) & set(latidos.RETIRADOS), (
        "Un daemon no puede estar registrado como esperado Y retirado a la vez."
    )


def test_registro_en_sintonia_con_latidos():
    # Las fuentes únicas de `latidos` apuntan a daemons que EXISTEN según el registro:
    # todo barrible y todo daemon con gate propio debe estar registrado.
    esperados = set(daemons_registro.esperados())
    assert set(latidos.BARRIBLES) <= esperados
    assert set(latidos.CLAVE_GATE) <= esperados
    # Los siempre-on sin gate también, salvo los ya retirados del arranque (comercial).
    assert set(latidos.SIN_GATE) - set(latidos.RETIRADOS) <= esperados


def test_por_nombre_devuelve_la_entrada_o_none():
    entrada = daemons_registro.por_nombre("caducidad")
    assert entrada is not None
    assert entrada.iniciador == "iniciar_ingesta"
    assert entrada.latido_propio is False
    assert daemons_registro.por_nombre("no-existe") is None


# --------------------------------------------------------------------------- #
# Sonda: estado "sin_datos" para lo registrado sin latido                      #
# --------------------------------------------------------------------------- #


def test_endpoint_daemons_registrados_sin_latido_salen_sin_datos(entorno):
    # BD sin latidos: TODOS los registrados aparecen igualmente, en estado "sin_datos",
    # con la MISMA forma que una fila real (gate y clasificación incluidos) y sin ofrecer
    # "Barrer ahora" (ningún bucle confirmado vivo consumiría la solicitud).
    c = _cli_como("admin")
    r = c.get("/api/sistema/daemons")
    assert r.status_code == 200
    por_nombre = {d["daemon"]: d for d in r.json()["daemons"]}
    assert set(daemons_registro.esperados()) <= set(por_nombre)
    trends = por_nombre["trends"]
    assert trends["estado"] == "sin_datos"
    assert trends["edad_seg"] is None
    assert trends["visto"] == ""
    assert trends["barrible"] is False
    assert trends["clave_gate"] == "KENI_TRENDS"
    assert trends["clase"] == "maquina"
    # Un siempre-on registrado también sale (no tiene gate: switch nulo).
    assert por_nombre["limpiador"]["estado"] == "sin_datos"
    assert por_nombre["limpiador"]["clave_gate"] is None


def test_endpoint_daemons_fila_real_sustituye_a_la_sintetica(entorno):
    # En cuanto el daemon late, manda su fila REAL: una sola entrada y estado juzgado
    # por el latido, no "sin_datos".
    db.latido_barrido("trends", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    c = _cli_como("admin")
    filas = [d for d in c.get("/api/sistema/daemons").json()["daemons"] if d["daemon"] == "trends"]
    assert len(filas) == 1
    assert filas[0]["estado"] != "sin_datos"


def test_barridos_de_registrado_sin_latido_devuelve_vacio(entorno):
    # El detalle de un daemon registrado que aún no late debe poder abrirse: historial
    # vacío (200), no 404. Un nombre desconocido sí es 404.
    c = _cli_como("admin")
    r = c.get("/api/sistema/daemons/trends/barridos")
    assert r.status_code == 200
    assert r.json() == {"daemon": "trends", "barridos": []}
    assert c.get("/api/sistema/daemons/no-existe/barridos").status_code == 404


def test_barrer_registrado_sin_latido_sigue_siendo_404(entorno):
    # Sin fila de latido no hay bucle confirmado que consuma la solicitud: forzar un
    # barrido sobre un "sin_datos" se rechaza (mismo contrato que un desconocido).
    c = _cli_como("admin")
    assert c.post("/api/sistema/daemons/trends/barrer", headers=_ORIGIN).status_code == 404


def test_endpoint_daemons_solo_admin(entorno):
    c = _cli_como("editor")
    assert c.get("/api/sistema/daemons").status_code == 403
