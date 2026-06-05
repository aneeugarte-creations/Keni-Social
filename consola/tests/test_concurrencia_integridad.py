"""Hardening de concurrencia / integridad de datos (Postgres-backed, vía fixture `entorno`).

Cubre los seis arreglos de la ronda de endurecimiento (cada uno con su test focalizado):

  1. CAS de la máquina de estados de aprobación: una segunda decisión sobre un nivel YA
     decidido no se aplica (rowcount 0 -> None -> 409 en la API). Incluye el invariante
     cruzado entre filas (mismo decisor en dos niveles) bajo `decidir_nivel_aprobacion_tx`.
  2. Contador de versiones (documento + copy): el índice ÚNICO impide versiones duplicadas
     y el INSERT REINTENTA con el número siguiente bajo carrera real (N hilos).
  3. Swap de rota: re-aplicar un swap ya `aplicado` es un no-op idempotente (no doble-swap).
  4. Parrilla: el índice parcial único impide doble-reserva del mismo (red, fecha) y el
     encolado RECALCULA el siguiente hueco ante un choque (retry).
  5. Job huérfano cuyo registro ya es terminal NO se re-ejecuta (evita el borrador duplicado).
  6. Single-flight de barridos: un segundo `lock_barrido` concurrente NO obtiene el lock.

NO se llama a `claude` ni a la red. Las pruebas con hilos están acotadas (timeout) para no
colgar nunca la suite.
"""

from __future__ import annotations

import threading

import pytest

from keni_consola import db, generaciones, repos
from keni_consola.dominio import colaboracion
from keni_consola.estados import (
    DECISION_APROBADO,
    DECISION_PENDIENTE,
    DECISION_RECHAZADO,
)

_MARCA = "unotv"


# --------------------------------------------------------------------------- #
# 1) CAS de la aprobación: segunda decisión sobre un nivel ya decidido         #
# --------------------------------------------------------------------------- #


def _cadena_un_nivel(plataforma_id: str) -> dict:
    cadena = repos.crear_cadena_aprobacion(
        plataforma_id=plataforma_id, contenido_id="", etiquetas=["Edición"]
    )
    return cadena[0]


def test_aprobar_dos_veces_el_mismo_nivel_el_segundo_no_aplica(entorno):
    pub = repos.crear_publicacion(_MARCA, "x", titulo="T", contenido="C")
    nivel = _cadena_un_nivel(pub["id"])
    campos = {
        "decision": DECISION_APROBADO,
        "decisor_id": "u1",
        "decisor_nombre": "Ana",
        "comentario": "",
        "decidido_en": "2026-06-05T10:00",
    }
    # Primera decisión: aplica (CAS pendiente->aprobado).
    primero = db.actualizar_aprobacion(nivel["id"], campos)
    assert primero is not None and primero["decision"] == DECISION_APROBADO

    # Segunda decisión (otra persona, doble-click, etc.): el nivel YA no está pendiente,
    # el CAS no aplica -> None (la API lo traduce a 409). NO pisa al decisor original.
    segundo = db.actualizar_aprobacion(
        nivel["id"], {**campos, "decisor_id": "u2", "decisor_nombre": "Beto"}
    )
    assert segundo is None
    vivo = repos.obtener_aprobacion(nivel["id"])
    assert vivo["decisor_id"] == "u1"  # gana el primero; no se sobrescribe.


def test_aprobar_tras_rechazar_no_aplica(entorno):
    pub = repos.crear_publicacion(_MARCA, "x", titulo="T", contenido="C")
    nivel = _cadena_un_nivel(pub["id"])
    base = {"decisor_id": "u1", "decisor_nombre": "Ana", "comentario": "", "decidido_en": "z"}
    assert db.actualizar_aprobacion(nivel["id"], {**base, "decision": DECISION_RECHAZADO}) is not None
    # Aprobar un nivel ya rechazado: el CAS exige `decision='pendiente'`, así que no aplica.
    assert db.actualizar_aprobacion(nivel["id"], {**base, "decision": DECISION_APROBADO}) is None
    assert repos.obtener_aprobacion(nivel["id"])["decision"] == DECISION_RECHAZADO


def test_deshacer_resetea_sin_guardia_cas(entorno):
    # Resetear a `pendiente` (deshacer) NO lleva guardia CAS: siempre puede deshacerse.
    pub = repos.crear_publicacion(_MARCA, "x", titulo="T", contenido="C")
    nivel = _cadena_un_nivel(pub["id"])
    db.actualizar_aprobacion(
        nivel["id"],
        {"decision": DECISION_APROBADO, "decisor_id": "u1", "decisor_nombre": "Ana",
         "comentario": "", "decidido_en": "z"},
    )
    reset = db.actualizar_aprobacion(nivel["id"], dict(colaboracion.CAMPOS_NIVEL_PENDIENTE))
    assert reset is not None and reset["decision"] == DECISION_PENDIENTE


def test_decidir_tx_revalida_bajo_lock_otro_par_de_ojos(entorno):
    """`decidir_nivel_aprobacion_tx` re-valida la regla cruzada con la cadena bloqueada.

    Cadena de dos niveles; la misma persona da el OK del nivel 1 y luego intenta el del
    nivel 2: la regla "el otro OK lo da otra persona" debe rechazar el segundo (error, no
    se aplica), aunque sea otra fila distinta (invariante CRUZADO entre filas).
    """
    pub = repos.crear_publicacion(_MARCA, "x", titulo="T", contenido="C")
    cadena = repos.crear_cadena_aprobacion(
        plataforma_id=pub["id"], contenido_id="", etiquetas=["Edición", "Coordinación"]
    )
    decisor = {"id": "u1", "usuario": "Ana"}

    def _validar(nivel, cad):
        return colaboracion.decidir(nivel, cad, DECISION_APROBADO, decisor, rol=None)

    # Nivel 1 por Ana: aplica.
    n1, err1 = db.decidir_nivel_aprobacion_tx(pub["id"], cadena[0]["id"], _validar)
    assert err1 is None and n1 is not None and n1["decisor_id"] == "u1"

    # Nivel 2 por la MISMA Ana: la regla del dominio lo rechaza (otro par de ojos).
    n2, err2 = db.decidir_nivel_aprobacion_tx(pub["id"], cadena[1]["id"], _validar)
    assert n2 is None and err2 is not None
    assert repos.obtener_aprobacion(cadena[1]["id"])["decision"] == DECISION_PENDIENTE


# --------------------------------------------------------------------------- #
# 2) Contador de versiones: índice único + retry, sin duplicados              #
# --------------------------------------------------------------------------- #


def _en_paralelo(trabajo, n=12, timeout=15):
    errores: list[BaseException] = []
    arrancar = threading.Barrier(n, timeout=timeout)

    def correr(i):
        try:
            arrancar.wait()
            trabajo(i)
        except BaseException as exc:  # noqa: BLE001
            errores.append(exc)

    hilos = [threading.Thread(target=correr, args=(i,)) for i in range(n)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=timeout)
        assert not h.is_alive(), "un hilo quedó colgado"
    assert not errores, f"errores en hilos: {errores!r}"


@pytest.mark.timeout(40)
def test_copy_versiones_concurrentes_sin_duplicar_version(entorno):
    pub = repos.crear_publicacion(_MARCA, "x", titulo="T", contenido="C")
    n = 12
    _en_paralelo(
        lambda i: repos.registrar_copy_version(
            plataforma_id=pub["id"], contenido_id="", copy=f"copy {i}"
        ),
        n=n,
    )
    versiones = [v["version"] for v in repos.listar_copy_versiones(pub["id"])]
    # N inserciones -> versiones 1..N, todas distintas (ninguna duplicada por la carrera).
    assert sorted(versiones) == list(range(1, n + 1))
    assert len(versiones) == len(set(versiones))


@pytest.mark.timeout(40)
def test_documento_versiones_concurrentes_sin_duplicar_version(entorno):
    pub = repos.crear_publicacion(_MARCA, "x", titulo="T", contenido="C")
    plat = repos.obtener_contenido_plataforma(pub["id"])
    contenido_id = plat["contenido_id"]
    n = 12
    _en_paralelo(
        lambda i: db.crear_documento_version(
            contenido_id=contenido_id, plataforma_id=pub["id"], documento=f'{{"v": {i}}}'
        ),
        n=n,
    )
    versiones = [v["version"] for v in db.listar_documento_versiones(contenido_id, pub["id"])]
    assert sorted(versiones) == list(range(1, n + 1))
    assert len(versiones) == len(set(versiones))


def test_indice_unico_copy_version_rechaza_duplicado(entorno):
    # El índice único (plataforma_id, version) es un backstop duro: un INSERT manual con una
    # versión ya existente revienta con IntegrityError.
    pub = repos.crear_publicacion(_MARCA, "x", titulo="T", contenido="C")
    repos.registrar_copy_version(plataforma_id=pub["id"], contenido_id="", copy="v1")
    con = db._conectar()
    try:
        with pytest.raises(db.IntegrityError):
            con.execute(
                "INSERT INTO contenido_copy_versiones "
                "(id, plataforma_id, contenido_id, version, copy, autor_id, autor_nombre, nota, creado) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("dup1", pub["id"], "", 1, "choca", "", "", "", "2026-06-05T10:00"),
            )
            con.commit()
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# 4) Parrilla: índice parcial único + retry evitan la doble-reserva           #
# --------------------------------------------------------------------------- #


def test_indice_parrilla_rechaza_doble_reserva_mismo_slot(entorno):
    # Dos piezas de la misma red programadas en la MISMA fecha: el índice parcial único
    # (red, fecha) WHERE estado='programado' rechaza la segunda.
    pub_a = repos.crear_publicacion(_MARCA, "x", titulo="A", contenido="C")
    pub_b = repos.crear_publicacion(_MARCA, "x", titulo="B", contenido="C")
    slot = "2026-06-10T15:00"
    assert repos.actualizar_publicacion(
        pub_a["id"], {"estado": "programado", "fecha_programada": slot}
    ) is not None
    with pytest.raises(db.IntegrityError):
        repos.actualizar_publicacion(
            pub_b["id"], {"estado": "programado", "fecha_programada": slot}
        )


def test_indice_parrilla_no_afecta_borradores_ni_otras_redes(entorno):
    # El índice es PARCIAL: dos borradores (sin fecha) y dos redes distintas en el mismo
    # minuto conviven sin chocar (solo cuenta `programado` con fecha no vacía y misma red).
    a = repos.crear_publicacion(_MARCA, "x", titulo="A", contenido="C")
    b = repos.crear_publicacion(_MARCA, "instagram", titulo="B", contenido="C")
    slot = "2026-06-10T15:00"
    assert repos.actualizar_publicacion(a["id"], {"estado": "programado", "fecha_programada": slot})
    # Otra red, mismo minuto: permitido.
    assert repos.actualizar_publicacion(b["id"], {"estado": "programado", "fecha_programada": slot})


def test_encolar_recalcula_hueco_ante_choque(entorno, monkeypatch):
    # `_encolar_en_hueco_libre` debe REINTENTAR con el siguiente hueco si el primero choca.
    # Simulamos: el primer cálculo devuelve un slot ya OCUPADO por otra pieza programada; el
    # segundo cálculo (tras el IntegrityError) devuelve uno libre.
    from keni_consola.api import publicaciones as ap

    ocupado = repos.crear_publicacion(_MARCA, "x", titulo="ocupa", contenido="C")
    slot_ocupado = "2026-06-10T15:00"
    slot_libre = "2026-06-17T15:00"
    repos.actualizar_publicacion(
        ocupado["id"], {"estado": "programado", "fecha_programada": slot_ocupado}
    )

    pieza = repos.crear_publicacion(_MARCA, "x", titulo="nueva", contenido="C")
    huecos = iter([slot_ocupado, slot_libre])
    monkeypatch.setattr(ap, "calcular_hueco_para", lambda pub, ahora=None: next(huecos))

    actualizada, hubo_hueco = ap._encolar_en_hueco_libre(pieza)
    assert hubo_hueco is True
    assert actualizada is not None
    assert actualizada["fecha_programada"] == slot_libre  # tomó el libre tras el choque.


# --------------------------------------------------------------------------- #
# 3) Swap de rota: re-aplicar es no-op idempotente                            #
# --------------------------------------------------------------------------- #


_LUNES = "2026-05-25"
_DIA_A = "2026-05-25"  # lunes
_DIA_B = "2026-05-26"  # martes


def _sembrar_swap_aplicable():
    """Siembra dos turnos (ana@A, beto@B) y un swap ACEPTADO entre ellos.

    Devuelve `(swap_id, franja_id, fecha_a, fecha_b)`. Mismo patrón que `test_api_rota_swaps`:
    `crear_turno_rota` siembra las franjas por defecto de la semana; tomamos su id real.
    """
    repos.crear_turno_rota(_LUNES, _DIA_A, miembro_id="ana", miembro_nombre="Ana", franja="matutino")
    repos.crear_turno_rota(_LUNES, _DIA_B, miembro_id="beto", miembro_nombre="Beto", franja="matutino")
    franjas = {f["nombre"]: f["id"] for f in repos.listar_franjas_semana(_LUNES)}
    franja_id = franjas.get("Mañana", "")
    assert franja_id, f"no se sembró la franja Mañana: {franjas}"
    swap = repos.crear_swap_turno(
        "ana", "beto", _DIA_A, franja_id, _DIA_B, franja_id,
        solicitante_nombre="Ana", destinatario_nombre="Beto",
    )
    repos.actualizar_swap_turno(swap["id"], {"estado": "aceptado"})
    return swap["id"], franja_id


def test_aplicar_swap_dos_veces_es_idempotente(entorno):
    swap_id, franja_id = _sembrar_swap_aplicable()

    def _aplicar():
        return repos.aplicar_swap_turno(
            swap_id,
            solicitante_id="ana", solicitante_nombre="Ana",
            destinatario_id="beto", destinatario_nombre="Beto",
            fecha_a=_DIA_A, franja_a=franja_id, fecha_b=_DIA_B, franja_b=franja_id,
        )

    primero = _aplicar()
    assert primero is not None and "error" not in primero
    assert primero["estado"] == "aplicado"
    # Tras el primero, ana quedó en DIA_B y beto en DIA_A (intercambio).
    turnos = {(t["fecha"], t["miembro_id"]) for t in repos.listar_turnos_rota(_LUNES)}
    assert (_DIA_B, "ana") in turnos and (_DIA_A, "beto") in turnos

    # Re-aplicar: NO vuelve a intercambiar (sería corrupción: devolvería ana a DIA_A); el
    # guard `estado <> 'aplicado'` + el lock hacen que sea un no-op idempotente.
    segundo = _aplicar()
    assert segundo is not None and "error" not in segundo
    assert segundo["estado"] == "aplicado"
    turnos2 = {(t["fecha"], t["miembro_id"]) for t in repos.listar_turnos_rota(_LUNES)}
    assert (_DIA_B, "ana") in turnos2 and (_DIA_A, "beto") in turnos2  # sin deshacerse.


# --------------------------------------------------------------------------- #
# 5) Job huérfano cuyo registro ya es terminal NO se re-ejecuta               #
# --------------------------------------------------------------------------- #


def test_reclamar_no_reejecuta_huerfano_terminal(entorno):
    """Un job `reclamado` huérfano cuyo `gen_id` YA es terminal se cierra sin relanzarse."""
    from datetime import datetime, timedelta

    from keni_consola import config

    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
    repos.encolar_job(gen["id"], "{}")
    clavado = repos.reclamar_job("w-muerto")
    assert clavado is not None

    # El worker terminó el trabajo (registro terminal) pero murió antes de `terminar_job`.
    generaciones.actualizar(
        gen["id"], {"estado": generaciones.ESTADO_COMPLETADO, "fecha_fin": "z"}
    )
    # Envejecemos `claimed_at` para que cuente como huérfano.
    viejo = (
        datetime.now() - timedelta(seconds=config.claude_timeout() + db._RECLAIM_STALE_MARGEN_S + 60)
    ).isoformat(timespec="seconds")
    con = db._conectar()
    try:
        con.execute("UPDATE jobs SET claimed_at = ? WHERE gen_id = ?", (viejo, gen["id"]))
        con.commit()
    finally:
        con.close()

    # NO se re-reclama (su trabajo ya se hizo); el job queda cerrado (terminado).
    assert repos.reclamar_job("w-nuevo") is None
    con = db._conectar()
    try:
        fila = con.execute(
            "SELECT estado FROM jobs WHERE gen_id = ?", (gen["id"],)
        ).fetchone()
    finally:
        con.close()
    assert fila["estado"] == db.JOB_TERMINADO


def test_reclamar_si_reejecuta_huerfano_no_terminal(entorno):
    """Salvaguarda: un huérfano cuyo registro sigue `ejecutando` SÍ se re-reclama (no se pierde)."""
    from datetime import datetime, timedelta

    from keni_consola import config

    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
    repos.encolar_job(gen["id"], "{}")
    primero = repos.reclamar_job("w-muerto")
    assert primero is not None
    viejo = (
        datetime.now() - timedelta(seconds=config.claude_timeout() + db._RECLAIM_STALE_MARGEN_S + 60)
    ).isoformat(timespec="seconds")
    con = db._conectar()
    try:
        con.execute("UPDATE jobs SET claimed_at = ? WHERE gen_id = ?", (viejo, gen["id"]))
        con.commit()
    finally:
        con.close()
    # El registro sigue `ejecutando`: el huérfano se re-reclama para sacarlo adelante.
    rereclamado = repos.reclamar_job("w-nuevo")
    assert rereclamado is not None and rereclamado["gen_id"] == gen["id"]


# --------------------------------------------------------------------------- #
# 6) Single-flight de barridos (advisory lock)                                #
# --------------------------------------------------------------------------- #


def test_lock_barrido_excluye_segundo_concurrente(entorno):
    with db.lock_barrido("test-barrido") as ok1:
        assert ok1 is True
        # Un segundo intento MIENTRAS el primero retiene el lock NO lo obtiene.
        with db.lock_barrido("test-barrido") as ok2:
            assert ok2 is False
    # Tras soltar, vuelve a estar disponible.
    with db.lock_barrido("test-barrido") as ok3:
        assert ok3 is True


def test_lock_barrido_distintas_claves_no_se_excluyen(entorno):
    with db.lock_barrido("barrido-a") as a, db.lock_barrido("barrido-b") as b:
        assert a is True and b is True
