"""Tests del DESACOPLO generacion (#130 Fase 2 / ADR 0002 Fase B): cola + worker.

TODO OFFLINE: nunca se llama a `claude` real (se mockea `runner.lanzar_proc` por un
subproceso de python que emite NDJSON canned). Cubre:
  - Cola: encolar -> reclamar (clava) -> terminar; reclamacion idempotente.
  - jobspec: round-trip de serializacion y reconstruccion del `procesar` por kind.
  - Worker: clava un job y corre el runner (con #137) -> el registro completa y el
    post-procesado real corre (historial/publicaciones).
  - Reclamacion concurrente NO doble-ejecuta un mismo job (varios hilos worker).
  - Cancelacion cross-proceso mata el ARBOL (proceso que lanza un hijo; sin huerfanos).
  - Reiniciar el back NO mata un job en vuelo del worker (el proceso sigue vivo).

Las pruebas que ejercitan el subproceso real usan `_LANZAR_CLAUDE_REAL` (referencia
genuina capturada al importar; ver test_generaciones.py).
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime, timedelta

import pytest

from keni_consola import cola, config, db, generaciones, repos, worker
from keni_consola.dominio import jobspec

_MARCA = "unotv"

# Referencias GENUINAS al runner/encolado reales. `crear_app` REASIGNA el atributo de
# modulo `encolar_job_claude` por una fake (y eso PERSISTE entre tests), asi que para
# ejercitar la cola de verdad capturamos las funciones reales al importar y las invocamos
# por estas referencias (mismo patron que test_generaciones.py con `lanzar_job_claude`).
_LANZAR_CLAUDE_REAL = generaciones.lanzar_job_claude
_ENCOLAR_REAL = generaciones.encolar_job_claude


# --------------------------------------------------------------------------- #
# Cola: encolar / reclamar / terminar                                         #
# --------------------------------------------------------------------------- #


def test_encolar_reclamar_terminar(entorno):
    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
    spec = jobspec.construir(prompt="hola", procesar=jobspec.construir_hashtags())
    job_id = cola.encolar(gen["id"], spec)
    assert job_id

    clavado = cola.reclamar("w1")
    assert clavado is not None
    assert clavado["gen_id"] == gen["id"]
    assert clavado["spec"]["prompt"] == "hola"
    assert clavado["spec"]["procesar"]["kind"] == jobspec.PROC_HASHTAGS

    # Ya no quedan pendientes (el unico job fue clavado).
    assert cola.reclamar("w2") is None

    cola.terminar(job_id)


def test_reclamar_vacia_devuelve_none(entorno):
    assert cola.reclamar() is None


def test_encolar_idempotente_por_gen_id(entorno):
    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
    spec = jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags())
    cola.encolar(gen["id"], spec)
    cola.encolar(gen["id"], spec)  # mismo gen_id: no duplica
    primero = cola.reclamar()
    assert primero is not None and primero["gen_id"] == gen["id"]
    assert cola.reclamar() is None  # no habia un segundo job


def test_reclama_job_huerfano_de_worker_muerto(entorno):
    """Un job `reclamado` cuyo worker murio (claimed_at viejo) lo RE-RECLAMA otro worker.

    Antes quedaba `reclamado` para siempre y su registro `ejecutando` -> "Generando..." sin
    fin. Un job recien reclamado (worker vivo) NO se re-reclama: solo al pasar el umbral.
    """
    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
    cola.encolar(gen["id"], jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags()))
    primero = cola.reclamar("worker-muerto")
    assert primero is not None
    # Recien reclamado: un segundo worker NO lo roba (el primero podria seguir vivo).
    assert cola.reclamar("worker-2") is None
    # Envejecemos `claimed_at` mas alla del umbral de huerfano (wall-timeout + margen).
    viejo = (
        datetime.now()
        - timedelta(seconds=config.claude_timeout() + db._RECLAIM_STALE_MARGEN_S + 60)
    ).isoformat(timespec="seconds")
    con = db._conectar()
    try:
        con.execute("UPDATE jobs SET claimed_at = ? WHERE id = ?", (viejo, primero["id"]))
        con.commit()
    finally:
        con.close()
    rereclamado = cola.reclamar("worker-2")
    assert rereclamado is not None and rereclamado["id"] == primero["id"]


def test_spec_corrupto_se_reclama_con_spec_none(entorno):
    # JSON corrupto en la fila: el worker lo recibe con spec=None y lo marca en error.
    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
    repos.encolar_job(gen["id"], "{ no es json valido")
    clavado = cola.reclamar()
    assert clavado is not None and clavado["spec"] is None


# --------------------------------------------------------------------------- #
# jobspec: round-trip + reconstruccion del procesar por kind                  #
# --------------------------------------------------------------------------- #


def test_jobspec_roundtrip(entorno):
    spec = jobspec.construir(
        prompt="el prompt",
        procesar=jobspec.construir_copy(
            skill="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="T",
            texto_base="nota", autor={"id": "u1", "usuario": "ana"},
        ),
        dir_temporal=None,
    )
    texto = jobspec.serializar(spec)
    vuelto = jobspec.deserializar(texto)
    assert vuelto["prompt"] == "el prompt"
    assert vuelto["procesar"]["kind"] == jobspec.PROC_COPY
    assert vuelto["procesar"]["autor"] == {"id": "u1", "usuario": "ana"}


def test_jobspec_copy_contenido_id_roundtrip_puro():
    # PURO (sin DB): el `contenido_id` viaja en el spec del copy y sobrevive al round-trip
    # de serializacion, para que el worker pueda NIDAR el borrador bajo el tema.
    spec = jobspec.construir(
        prompt="p",
        procesar=jobspec.construir_copy(
            skill="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="T",
            texto_base="nota", contenido_id="tema-123",
        ),
    )
    vuelto = jobspec.deserializar(jobspec.serializar(spec))
    assert vuelto["procesar"]["contenido_id"] == "tema-123"


def test_jobspec_copy_sin_contenido_id_default_vacio_puro():
    # PURO (sin DB): sin `contenido_id`, el spec lleva "" (back-compat: borrador suelto).
    spec = jobspec.construir_copy(
        skill="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="T",
        texto_base="nota",
    )
    assert spec["contenido_id"] == ""


def test_reconstruir_procesar_hashtags(entorno):
    spec = jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags())
    procesar = jobspec.reconstruir_procesar(spec)
    assert procesar("#uno #dos", None) == {"hashtags": ["#uno", "#dos"]}


def test_reconstruir_procesar_copy_crea_publicaciones(entorno):
    # El copy reconstruido en el worker corre el MISMO post-procesado: parsea piezas y
    # AUTO-GUARDA un borrador por red (verifica que el desacoplo conserva el comportamiento).
    spec = jobspec.construir(
        prompt="p",
        procesar=jobspec.construir_copy(
            skill="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="Titulo",
            texto_base="nota",
        ),
    )
    procesar = jobspec.reconstruir_procesar(spec)
    salida = 'Texto del copy\n\n```json\n{"piezas": [{"red": "x", "texto": "Hola X"}]}\n```'
    resultado = procesar(salida, None)
    assert resultado["historial_id"]
    assert len(resultado["publicaciones"]) == 1
    assert resultado["publicaciones"][0]["red"] == "x"
    # El borrador quedo guardado de verdad.
    pubs = repos.listar_publicaciones(marca=_MARCA, red="x")
    assert any("Hola X" in (p.get("contenido") or "") for p in pubs)


def test_reconstruir_procesar_copy_nida_bajo_el_tema(entorno):
    # Lista viva: con `contenido_id` de un tema existente, el borrador se ADJUNTA a ese
    # `contenido` (cuelga de su tarjeta) y aparece en publicaciones + cola de aprobacion.
    from keni_consola.dominio import publicaciones as dom_pub

    tema = repos.crear_contenido(
        clase="contenido", titulo="Tema origen", marca=_MARCA, origen="import-calendario",
    )
    spec = jobspec.construir(
        prompt="p",
        procesar=jobspec.construir_copy(
            skill="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="Titulo",
            texto_base="nota", contenido_id=tema["id"],
        ),
    )
    procesar = jobspec.reconstruir_procesar(spec)
    salida = '```json\n{"piezas": [{"red": "x", "texto": "Hola X"}]}\n```'
    resultado = procesar(salida, None)

    assert len(resultado["publicaciones"]) == 1
    # El borrador cuelga del tema: es una fila por plataforma es_publicacion=1 de ESE contenido.
    plats = [p for p in repos.listar_contenido_plataforma(tema["id"]) if p.get("es_publicacion")]
    assert len(plats) == 1
    assert plats[0]["copy"] == "Hola X"
    assert not plats[0]["falta_copy"]
    # Aparece en /api/publicaciones (filtra es_publicacion=1) ...
    pubs = repos.listar_publicaciones(marca=_MARCA, red="x")
    assert any("Hola X" in (p.get("contenido") or "") for p in pubs)
    # ... y en la cola de aprobacion (estado borrador == pendiente de plataforma).
    cola_aprob = dom_pub.cola_de_aprobacion()  # estado en_revision: aun ninguna
    assert all(p["estado"] == "en_revision" for p in cola_aprob)
    borradores = [p for p in repos.listar_publicaciones(estado="borrador") if p["red"] == "x"]
    assert any("Hola X" in (p.get("contenido") or "") for p in borradores)


def test_reconstruir_procesar_copy_contenido_inexistente_cae_a_borrador_suelto(entorno):
    # Robustez: si `contenido_id` no existe, NO se nida en el vacio; cae al borrador suelto
    # (con su propio padre), igual que el camino sin contenido_id.
    spec = jobspec.construir(
        prompt="p",
        procesar=jobspec.construir_copy(
            skill="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="T",
            texto_base="nota", contenido_id="no-existe",
        ),
    )
    procesar = jobspec.reconstruir_procesar(spec)
    procesar('```json\n{"piezas": [{"red": "x", "texto": "Suelto"}]}\n```', None)
    pubs = repos.listar_publicaciones(marca=_MARCA, red="x")
    assert any("Suelto" in (p.get("contenido") or "") for p in pubs)


def test_reconstruir_procesar_copy_sin_contenido_id_back_compat(entorno):
    # Back-compat: sin contenido_id, borrador suelto con padre propio (comportamiento de hoy);
    # NO cuelga de ningun tema preexistente.
    tema = repos.crear_contenido(clase="contenido", titulo="Tema", marca=_MARCA)
    spec = jobspec.construir(
        prompt="p",
        procesar=jobspec.construir_copy(
            skill="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="T",
            texto_base="nota",
        ),
    )
    procesar = jobspec.reconstruir_procesar(spec)
    procesar('```json\n{"piezas": [{"red": "x", "texto": "Suelto"}]}\n```', None)
    # El tema NO recibio ninguna fila publicacion.
    assert [p for p in repos.listar_contenido_plataforma(tema["id"]) if p.get("es_publicacion")] == []
    # Pero el borrador existe (con su propio padre).
    assert any(
        "Suelto" in (p.get("contenido") or "")
        for p in repos.listar_publicaciones(marca=_MARCA, red="x")
    )


def test_reconstruir_procesar_rss_marca_item(entorno):
    # RSS: tras el copy, marca el item del feed como usado (solo si la fuente existe).
    fuente = repos.crear_fuente_rss("F", "https://ej.com/rss", marca=_MARCA)
    spec = jobspec.construir(
        prompt="p",
        procesar=jobspec.construir_copy(
            skill="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="T",
            texto_base="nota", fuente_id=fuente["id"], clave="item-1",
        ),
    )
    procesar = jobspec.reconstruir_procesar(spec)
    procesar('```json\n{"piezas": [{"red": "x", "texto": "Hi"}]}\n```', None)
    assert "item-1" in repos.claves_vistas(fuente["id"])


def test_reconstruir_procesar_kind_desconocido_revienta(entorno):
    with pytest.raises(ValueError):
        jobspec.reconstruir_procesar({"procesar": {"kind": "inexistente"}})


# --------------------------------------------------------------------------- #
# Subproceso `claude` FALSO: emite NDJSON canned (sin red, sin claude real)   #
# --------------------------------------------------------------------------- #


def _fake_lanzar_proc_factory(lineas: list[str]):
    """Crea un `runner.lanzar_proc` fake: subproceso python que emite `lineas` NDJSON."""
    import subprocess as _sp

    guion = "import sys\n" + "".join(f"print({ln!r}, flush=True)\n" for ln in lineas)

    def _fake(argv, *, cwd, env=None):  # noqa: ANN001
        return _sp.Popen(
            [sys.executable, "-c", guion],
            cwd=cwd, stdout=_sp.PIPE, stderr=_sp.DEVNULL, text=True, bufsize=1,
            start_new_session=True,
        )

    return _fake


_LINEAS_OK_HASHTAGS = [
    '{"type": "stream_event", "event": {"type": "message_start", "message": {}}}',
    '{"type": "stream_event", "event": {"type": "content_block_delta", "index": 0, '
    '"delta": {"type": "text_delta", "text": "#uno\\n#dos"}}}',
    '{"type": "result", "subtype": "success", "result": "#uno\\n#dos", '
    '"usage": {"input_tokens": 1, "output_tokens": 1}}',
]


def _esperar_terminal(gid: str, timeout: float = 10.0) -> str:
    fin = time.monotonic() + timeout
    while time.monotonic() < fin:
        g = generaciones.obtener(gid)
        if g is not None and g["estado"] != generaciones.ESTADO_EJECUTANDO:
            return g["estado"]
        time.sleep(0.05)
    return (generaciones.obtener(gid) or {}).get("estado", "")


# --------------------------------------------------------------------------- #
# Worker: clava un job y corre el runner real (con #137); el job COMPLETA      #
# --------------------------------------------------------------------------- #


@pytest.mark.timeout(30)
@pytest.mark.skipif(os.name != "posix", reason="subproceso real")
def test_worker_procesa_job_encolado_end_to_end(entorno, monkeypatch):
    """Encolar -> el worker clava y corre `claude` (mockeado) -> el registro completa.

    Es el camino del desacoplo entero, salvo el binario real: el back encola (via admision
    + cola), el worker reclama, reconstruye el `procesar` de hashtags desde el spec y corre
    el runner #137; el registro queda `completado` con el resultado parseado.
    """
    monkeypatch.setattr(generaciones.shutil, "which", lambda _n: "/usr/bin/claude")
    monkeypatch.setattr(
        generaciones.runner, "lanzar_proc", _fake_lanzar_proc_factory(_LINEAS_OK_HASHTAGS)
    )

    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "Tags"})
    spec = jobspec.construir(prompt="sugiere", procesar=jobspec.construir_hashtags())
    # El encolado toma el cupo de admision (como el endpoint real).
    _ENCOLAR_REAL(
        gen["id"], prompt="sugiere", cwd=entorno, procesar=lambda s, m: {}, spec=spec
    )

    # El worker clava UN job y lo procesa (bloquea hasta el estado terminal).
    job = cola.reclamar("w-test")
    assert job is not None
    worker.procesar_job(job, "w-test")

    g = generaciones.obtener(gen["id"])
    assert g["estado"] == generaciones.ESTADO_COMPLETADO
    assert g["resultado"] == {"hashtags": ["#uno", "#dos"]}
    # El cupo de admision quedo liberado (no se fuga).
    assert generaciones.runner.admitidos() == 0


@pytest.mark.timeout(20)
def test_worker_spec_corrupto_marca_error_y_libera_cupo(entorno):
    """Un job con spec corrupto NO llama a `claude`: queda en error y libera el cupo."""
    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
    generaciones.runner.admitir()  # el encolado real lo habria tomado
    repos.encolar_job(gen["id"], "{ corrupto")
    job = cola.reclamar()
    worker.procesar_job(job, "w")
    g = generaciones.obtener(gen["id"])
    assert g["estado"] == generaciones.ESTADO_ERROR
    assert generaciones.runner.admitidos() == 0


# --------------------------------------------------------------------------- #
# Reclamacion CONCURRENTE: varios workers NO doble-ejecutan un mismo job       #
# --------------------------------------------------------------------------- #


@pytest.mark.timeout(30)
def test_reclamacion_concurrente_no_doble_ejecuta(entorno):
    """Con N workers reclamando a la vez y M jobs, cada job lo clava EXACTAMENTE uno.

    El claim guardado (SQLite) / FOR UPDATE SKIP LOCKED (Postgres) garantiza que dos
    workers no se lleven la misma fila. Comprobamos que la union de gen_ids clavados son
    todos los encolados, SIN repetidos.
    """
    encolados = []
    for _ in range(12):
        gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
        repos.encolar_job(gen["id"], jobspec.serializar(
            jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags())
        ))
        encolados.append(gen["id"])

    reclamados: list[str] = []
    lock = threading.Lock()
    arrancar = threading.Event()

    def trabajar(wid: str) -> None:
        arrancar.wait()
        while True:
            job = cola.reclamar(wid)
            if job is None:
                return
            with lock:
                reclamados.append(job["gen_id"])

    hilos = [threading.Thread(target=trabajar, args=(f"w{i}",)) for i in range(6)]
    for h in hilos:
        h.start()
    arrancar.set()
    for h in hilos:
        h.join(timeout=20)

    # Todos clavados, ninguno dos veces.
    assert sorted(reclamados) == sorted(encolados)
    assert len(reclamados) == len(set(reclamados))


# --------------------------------------------------------------------------- #
# Worker IN-PROCESO (perfil local): el bucle clava y procesa solo             #
# --------------------------------------------------------------------------- #


@pytest.mark.timeout(30)
@pytest.mark.skipif(os.name != "posix", reason="subproceso real")
def test_worker_inproceso_procesa_un_job(entorno, monkeypatch):
    """`iniciar_worker_inproceso` arranca un hilo que clava y procesa los jobs encolados.

    Es el modo LOCAL / un solo proceso: sin servicio aparte, el back encola y el mismo
    proceso ejecuta. Encolamos, arrancamos el worker in-proceso y esperamos el terminal.
    """
    monkeypatch.setattr(generaciones.shutil, "which", lambda _n: "/usr/bin/claude")
    monkeypatch.setattr(
        generaciones.runner, "lanzar_proc", _fake_lanzar_proc_factory(_LINEAS_OK_HASHTAGS)
    )

    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "Tags"})
    spec = jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags())
    _ENCOLAR_REAL(
        gen["id"], prompt="p", cwd=entorno, procesar=lambda s, m: {}, spec=spec
    )

    hilo = worker.iniciar_worker_inproceso()
    try:
        assert _esperar_terminal(gen["id"]) == generaciones.ESTADO_COMPLETADO
    finally:
        hilo._parar.set()  # type: ignore[attr-defined]
    g = generaciones.obtener(gen["id"])
    assert g["resultado"] == {"hashtags": ["#uno", "#dos"]}


# --------------------------------------------------------------------------- #
# CANCELACION cross-proceso: mata el ARBOL (sin huerfanos)                     #
# --------------------------------------------------------------------------- #


def _vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.mark.timeout(40)
@pytest.mark.skipif(os.name != "posix", reason="grupos de procesos POSIX")
def test_cancelacion_cross_proceso_mata_el_arbol(entorno, monkeypatch):
    """El worker sondea el flag de cancelacion de la COLA y mata el ARBOL (incluido el hijo).

    Simula el camino hosted: el back marca `cola.cancelar(gen_id)` (cross-proceso) y el
    vigia del worker lo ve y mata el arbol del subproceso `claude` (que lanzo un hijo). El
    hijo debe morir (sin huerfanos) y el registro quedar `cancelado`.
    """
    monkeypatch.setattr(generaciones.shutil, "which", lambda _n: "/usr/bin/claude")

    pids: dict[str, int] = {}
    guion = (
        "import subprocess, sys, time\n"
        "h = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
        "sys.stderr.write(str(h.pid) + '\\n'); sys.stderr.flush()\n"
        '''print('{"type": "stream_event", "event": {"type": "message_start", "message": {}}}', flush=True)\n'''
        "time.sleep(300)\n"
    )
    import subprocess as _sp

    def _fake_lanzar(argv, *, cwd, env=None):  # noqa: ANN001
        proc = _sp.Popen(
            [sys.executable, "-c", guion], cwd=cwd,
            stdout=_sp.PIPE, stderr=_sp.PIPE, text=True, bufsize=1, start_new_session=True,
        )
        pids["hijo"] = int(proc.stderr.readline().strip())
        return proc

    monkeypatch.setattr(generaciones.runner, "lanzar_proc", _fake_lanzar)
    # Vigia rapido para que el test no espere mucho.
    monkeypatch.setattr(worker, "_SONDEO_CANCELACION_S", 0.1)

    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "Cancelable"})
    spec = jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags())
    _ENCOLAR_REAL(
        gen["id"], prompt="p", cwd=entorno, procesar=lambda s, m: {}, spec=spec
    )
    job = cola.reclamar("w")

    # Procesar en un hilo (bloquea hasta terminal); cancelamos via la COLA desde fuera.
    hilo = threading.Thread(target=worker.procesar_job, args=(job, "w"), daemon=True)
    hilo.start()

    fin = time.monotonic() + 8
    while time.monotonic() < fin and "hijo" not in pids:
        time.sleep(0.05)
    assert "hijo" in pids and _vivo(pids["hijo"]), "el hijo deberia estar vivo antes de cancelar"

    # Cancelacion CROSS-PROCESO: solo marcamos el flag en la cola (lo que hace el back).
    assert cola.cancelar(gen["id"]) is True

    assert _esperar_terminal(gen["id"]) == generaciones.ESTADO_ERROR
    for _ in range(60):
        if not _vivo(pids["hijo"]):
            break
        time.sleep(0.1)
    assert not _vivo(pids["hijo"]), "cancelar debio matar el arbol entero (incluido el hijo)"
    g = generaciones.obtener(gen["id"])
    assert g["motivo"] == generaciones.MOTIVO_CANCELADO


@pytest.mark.timeout(20)
def test_cancelar_job_pendiente_no_lanza_claude(entorno, monkeypatch):
    """Un job AUN pendiente, cancelado antes de clavarse, se finaliza SIN llamar a `claude`."""
    # Si por error llamara a claude, esto reventaria (no hay binario): garantiza que NO se llama.
    monkeypatch.setattr(
        generaciones.runner, "lanzar_proc",
        lambda *a, **k: pytest.fail("no debe lanzar claude para un job cancelado"),
    )
    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
    spec = jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags())
    _ENCOLAR_REAL(
        gen["id"], prompt="p", cwd=entorno, procesar=lambda s, m: {}, spec=spec
    )
    cola.cancelar(gen["id"])  # cancelado ANTES de clavar
    job = cola.reclamar("w")
    worker.procesar_job(job, "w")
    g = generaciones.obtener(gen["id"])
    assert g["estado"] == generaciones.ESTADO_ERROR
    assert g["motivo"] == generaciones.MOTIVO_CANCELADO
    assert generaciones.runner.admitidos() == 0


# --------------------------------------------------------------------------- #
# Reiniciar el back NO mata un job en vuelo del worker                         #
# --------------------------------------------------------------------------- #


@pytest.mark.timeout(30)
@pytest.mark.skipif(os.name != "posix", reason="subproceso real")
def test_reinicio_back_no_mata_job_en_vuelo(entorno, monkeypatch):
    """Reiniciar el BACK no toca el proceso `claude` del worker (modelo hosted).

    Simulamos el back con la app (crear_app) y un worker SEPARADO (procesar_job en un
    subproceso `claude` vivo). 'Reiniciar el back' = soltar la app y crear otra. El
    proceso del worker debe seguir vivo (no es hijo del back) hasta que termina solo.
    """
    from .conftest import _cliente

    monkeypatch.setattr(generaciones.shutil, "which", lambda _n: "/usr/bin/claude")

    pids: dict[str, int] = {}
    # Subproceso que vive ~3s y luego emite un result de exito (simula `claude` trabajando).
    _start = '{"type": "stream_event", "event": {"type": "message_start", "message": {}}}'
    _result = (
        '{"type": "result", "subtype": "success", "result": "#x", '
        '"usage": {"input_tokens": 1, "output_tokens": 1}}'
    )
    guion = (
        "import sys, time, os\n"
        "sys.stderr.write(str(os.getpid()) + '\\n'); sys.stderr.flush()\n"
        f"print({_start!r}, flush=True)\n"
        "time.sleep(3)\n"
        f"print({_result!r}, flush=True)\n"
    )
    import subprocess as _sp

    def _fake_lanzar(argv, *, cwd, env=None):  # noqa: ANN001
        proc = _sp.Popen(
            [sys.executable, "-c", guion], cwd=cwd,
            stdout=_sp.PIPE, stderr=_sp.PIPE, text=True, bufsize=1, start_new_session=True,
        )
        pids["claude"] = int(proc.stderr.readline().strip())
        return proc

    monkeypatch.setattr(generaciones.runner, "lanzar_proc", _fake_lanzar)

    cli = _cliente()  # "back" #1
    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
    spec = jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags())
    _ENCOLAR_REAL(
        gen["id"], prompt="p", cwd=entorno, procesar=lambda s, m: {}, spec=spec
    )
    job = cola.reclamar("w-svc")
    hilo = threading.Thread(target=worker.procesar_job, args=(job, "w-svc"), daemon=True)
    hilo.start()

    fin = time.monotonic() + 8
    while time.monotonic() < fin and "claude" not in pids:
        time.sleep(0.05)
    assert "claude" in pids and _vivo(pids["claude"])

    # 'Reiniciar el back': soltamos el cliente/app y creamos otro. El job NO se cancela.
    del cli
    _ = _cliente()  # "back" #2 (nuevo)
    # El proceso del worker sigue vivo (el reinicio del back no lo toco).
    assert _vivo(pids["claude"]), "reiniciar el back no debe matar el job en vuelo del worker"

    # Y el job termina por su cuenta, sin perderse.
    assert _esperar_terminal(gen["id"]) == generaciones.ESTADO_COMPLETADO


def test_spec_no_se_puede_encolar_sin_spec(entorno):
    """`encolar_job_claude` exige un spec (defensa: sin spec el worker no reconstruye)."""
    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
    with pytest.raises(ValueError):
        _ENCOLAR_REAL(
            gen["id"], prompt="p", cwd=entorno, procesar=lambda s, m: {}, spec=None
        )
    # El cupo de admision NO se fuga aunque falle el encolado.
    assert generaciones.runner.admitidos() == 0
