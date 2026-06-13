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

from keni_consola import cola, config, db, db_jobs, generaciones, repos, worker
from keni_consola.dominio import jobspec

_MARCA = "unotv"

# Referencias GENUINAS al runner/encolado reales. `crear_app` REASIGNA el atributo de
# modulo `encolar_job_claude` por una fake (y eso PERSISTE entre tests), asi que para
# ejercitar la cola de verdad capturamos las funciones reales al importar y las invocamos
# por estas referencias (mismo patron que test_generaciones.py con `lanzar_job_claude`).
_LANZAR_CLAUDE_REAL = generaciones.lanzar_job_claude
_ENCOLAR_REAL = generaciones.encolar_job_claude


# NOTA: el post-procesado de copy YA NO compone una placa al crear (render on-demand): la
# imagen se deriva de la receta y se sirve por `/compuesta`. Por eso no hace falta stubear el
# compositor en la creación; los tests que sí componen (Estudio) lo mockean en su cuerpo.


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


def test_gate_cola_rechaza_fondo_al_tope_y_se_libera(entorno, monkeypatch):
    """`cola.encolar` rechaza con ColaLlenaError SOLO al trabajo de FONDO al llegar al tope.

    El gate cuenta los jobs EN VUELO en la cola compartida; al terminar uno, vuelve a haber
    sitio. El backpressure es para la MAQUINA (su tick reintenta solo); ver el test del bypass
    manual debajo.
    """
    monkeypatch.setenv("KENI_MAX_JOBS", "1")
    monkeypatch.setenv("KENI_MAX_COLA", "1")  # tope = 2
    assert cola.tope_cola() == 2

    def _encolar_fondo():
        gen = generaciones.crear({"tipo": "pipeline", "marca": _MARCA, "etiqueta": "X"})
        spec = jobspec.construir(
            prompt="p", procesar=jobspec.construir_hashtags(),
            prioridad=jobspec.PRIORIDAD_PIPELINE,
        )
        return cola.encolar(gen["id"], spec)

    j1 = _encolar_fondo()
    _encolar_fondo()  # 2do: la cola queda al tope
    # 3ro (fondo): rechazo SINCRONO -> el tick del pipeline lo trata como backpressure.
    with pytest.raises(generaciones.ColaLlenaError):
        _encolar_fondo()
    # Al terminar un job, se libera capacidad y vuelve a admitir.
    cola.terminar(j1)
    assert _encolar_fondo()  # ya cabe de nuevo


def test_gate_cola_manual_siempre_encola_y_va_primero(entorno, monkeypatch):
    """Un lanzamiento MANUAL nunca recibe 429: encola aunque la cola este al tope... y VA PRIMERO.

    La cola existe para que una persona espere EN COLA, no para pedirle que reintente mientras
    la maquina (flujo continuo) la mantiene llena. `reclamar` ademas despacha el manual ANTES
    que el lote de fondo ya encolado (orden por `jobs.prioridad`).
    """
    monkeypatch.setenv("KENI_MAX_JOBS", "1")
    monkeypatch.setenv("KENI_MAX_COLA", "1")  # tope = 2
    # Llena la cola con trabajo de FONDO hasta el tope.
    for i in range(cola.tope_cola()):
        gen = generaciones.crear({"tipo": "pipeline", "marca": _MARCA, "etiqueta": f"F{i}"})
        spec = jobspec.construir(
            prompt="p", procesar=jobspec.construir_hashtags(),
            prioridad=jobspec.PRIORIDAD_PIPELINE,
        )
        cola.encolar(gen["id"], spec)

    # Manual con la cola al tope: ENTRA igual (sin ColaLlenaError)...
    gen_manual = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "Manual"})
    spec_manual = jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags())
    assert cola.encolar(gen_manual["id"], spec_manual)

    # ...y el siguiente reclamo lo despacha PRIMERO (prioridad manual > pipeline).
    clavado = cola.reclamar("w-prio")
    assert clavado is not None and clavado["gen_id"] == gen_manual["id"]


def test_gate_cola_no_satura_tras_muchos_ciclos(entorno, monkeypatch):
    """REGRESION del leak de admision: encolar->reclamar->terminar MUCHAS veces NO satura.

    El gate de admision vivia en un contador EN MEMORIA por-proceso (`runner.admitir`): en hosted
    el back sumaba al encolar y el worker restaba al terminar, en memorias SEPARADAS, asi que el
    contador del back solo subia y nunca bajaba — tras `max_jobs+max_cola` generaciones rechazaba
    TODO para siempre aunque la cola real estuviera vacia. Ahora el gate cuenta la cola REAL
    (Postgres, compartida) y se autolibera: tras N >> tope ciclos completos seguimos pudiendo
    encolar. Antes, este bucle reventaba con ColaLlenaError pasada la vuelta `tope`.
    """
    monkeypatch.setenv("KENI_MAX_JOBS", "1")
    monkeypatch.setenv("KENI_MAX_COLA", "1")  # tope = 2
    for i in range(2 * cola.tope_cola() + 3):  # 7 ciclos completos, muy por encima del tope
        gen = generaciones.crear({"tipo": "pipeline", "marca": _MARCA, "etiqueta": f"X{i}"})
        spec = jobspec.construir(
            prompt="p", procesar=jobspec.construir_hashtags(),
            prioridad=jobspec.PRIORIDAD_PIPELINE,  # FONDO: el unico que pasa por el gate
        )
        job_id = cola.encolar(gen["id"], spec)  # no debe lanzar ColaLlenaError nunca
        clavado = cola.reclamar(f"w{i}")
        assert clavado is not None
        cola.terminar(job_id)  # libera la capacidad para la siguiente vuelta
    assert repos.contar_jobs_activos() == 0


def test_reclamar_respeta_prioridad_manual_antes_que_pipeline(entorno):
    """La cola NO es FIFO pura: un lanzamiento MANUAL pasa antes que el lote del pipeline.

    El job de FONDO (spec con `prioridad=PRIORIDAD_PIPELINE`) se encola PRIMERO; aun asi, el
    worker clava antes el MANUAL (default `PRIORIDAD_MANUAL`). A igual prioridad, FIFO.
    """
    g_fondo = generaciones.crear({"tipo": "pipeline", "marca": _MARCA, "etiqueta": "Fondo"})
    spec_fondo = jobspec.construir(
        prompt="fondo", procesar=jobspec.construir_hashtags(),
        prioridad=jobspec.PRIORIDAD_PIPELINE,
    )
    cola.encolar(g_fondo["id"], spec_fondo)
    g_manual = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "Manual"})
    spec_manual = jobspec.construir(prompt="manual", procesar=jobspec.construir_hashtags())
    cola.encolar(g_manual["id"], spec_manual)

    primero = cola.reclamar("w")
    assert primero is not None and primero["gen_id"] == g_manual["id"]
    segundo = cola.reclamar("w")
    assert segundo is not None and segundo["gen_id"] == g_fondo["id"]


def test_jobspec_prioridad_roundtrip_y_default_puro():
    # PURO (sin DB): la prioridad viaja DENTRO del spec y sobrevive al round-trip; un spec
    # VIEJO (sin el campo) o de PROCESO (render/ASR, iniciado por una persona) cae a MANUAL.
    spec = jobspec.construir(
        prompt="p", procesar=jobspec.construir_hashtags(),
        prioridad=jobspec.PRIORIDAD_PIPELINE,
    )
    vuelto = jobspec.deserializar(jobspec.serializar(spec))
    assert jobspec.prioridad(vuelto) == jobspec.PRIORIDAD_PIPELINE
    assert jobspec.prioridad({}) == jobspec.PRIORIDAD_MANUAL  # spec viejo sin campo
    assert jobspec.prioridad({"prioridad": "no-numero"}) == jobspec.PRIORIDAD_MANUAL
    # El default de `construir` es MANUAL (los seams que no fijan prioridad no degradan a nadie).
    assert jobspec.prioridad(jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags())) \
        == jobspec.PRIORIDAD_MANUAL


def test_encolar_gen_id_con_fila_terminada_resucita_el_job(entorno):
    """Re-encolar un gen_id cuya fila vieja ya esta `terminado` corre el trabajo NUEVO.

    REGRESION: el `ON CONFLICT DO NOTHING` devolvia el job viejo (terminado) y el nuevo no
    corria jamas (p. ej. el reintento de un copy del pipeline que fallo). Ahora la fila se
    REVIVE a `pendiente` con el spec nuevo; una fila VIVA sigue intacta (idempotencia).
    """
    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
    spec1 = jobspec.construir(prompt="v1", procesar=jobspec.construir_hashtags())
    j1 = cola.encolar(gen["id"], spec1)
    assert cola.reclamar("w") is not None
    cola.terminar(j1)
    assert repos.contar_jobs_activos() == 0

    spec2 = jobspec.construir(prompt="v2", procesar=jobspec.construir_hashtags())
    cola.encolar(gen["id"], spec2)  # fila `terminado`: debe resucitar, no devolver el viejo
    clavado = cola.reclamar("w2")
    assert clavado is not None
    assert clavado["gen_id"] == gen["id"]
    assert clavado["spec"]["prompt"] == "v2"  # corre el trabajo NUEVO


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
        - timedelta(seconds=config.claude_timeout() + db_jobs._RECLAIM_STALE_MARGEN_S + 60)
    ).isoformat(timespec="seconds")
    con = db._conectar()
    try:
        con.execute("UPDATE jobs SET claimed_at = ? WHERE id = ?", (viejo, primero["id"]))
        con.commit()
    finally:
        con.close()
    rereclamado = cola.reclamar("worker-2")
    assert rereclamado is not None and rereclamado["id"] == primero["id"]


def test_reclamar_pendiente_no_lee_yaml_de_generacion(entorno, monkeypatch):
    """RENDIMIENTO: clavar un job `pendiente` NO lee el YAML de generacion (cero disco bajo lock).

    La guardia anti-duplicado (`_gen_ya_terminal`, que parsea un YAML) SOLO aplica a los
    huerfanos. Un `pendiente` nunca corrio su post-procesado, asi que no debe pagar ese I/O —
    y, sobre todo, no debe hacerlo mientras retiene el `FOR UPDATE` de la fila.
    """
    llamadas = {"n": 0}
    real = db_jobs._gen_ya_terminal
    monkeypatch.setattr(
        db_jobs, "_gen_ya_terminal",
        lambda gid: (llamadas.__setitem__("n", llamadas["n"] + 1), real(gid))[1],
    )
    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
    cola.encolar(gen["id"], jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags()))
    clavado = cola.reclamar("w")
    assert clavado is not None and clavado["gen_id"] == gen["id"]
    assert llamadas["n"] == 0, "clavar un pendiente no debe leer el YAML de generacion"


def test_huerfano_con_registro_terminal_se_cierra_sin_relanzar(entorno):
    """La guardia anti-duplicado: un huerfano cuyo registro YA es terminal se cierra sin correr.

    Tras el commit del claim (fuera del lock) se comprueba el estado del registro; si es
    terminal (su post-procesado ya corrio antes de que el worker muriera), el job se marca
    `terminado` y `reclamar` pasa al siguiente, SIN devolverlo (evita el borrador duplicado).
    """
    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
    cola.encolar(gen["id"], jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags()))
    primero = cola.reclamar("w1")
    assert primero is not None
    # El registro alcanza un estado TERMINAL (el post-procesado ya corrio) y el worker MUERE
    # sin cerrar el job: queda `reclamado` con claimed_at viejo (huerfano).
    generaciones.actualizar(gen["id"], {"estado": generaciones.ESTADO_COMPLETADO})
    _envejecer_claim(primero["id"])
    # El re-reclamo NO lo devuelve (su trabajo ya se hizo) y lo deja cerrado.
    assert cola.reclamar("w2") is None
    assert repos.contar_jobs_activos() == 0


def _envejecer_claim(job_id: str) -> None:
    """Retrasa `claimed_at` mas alla del umbral de huerfano (simula un worker muerto)."""
    viejo = (
        datetime.now()
        - timedelta(seconds=config.claude_timeout() + db_jobs._RECLAIM_STALE_MARGEN_S + 60)
    ).isoformat(timespec="seconds")
    con = db._conectar()
    try:
        con.execute("UPDATE jobs SET claimed_at = ? WHERE id = ?", (viejo, job_id))
        con.commit()
    finally:
        con.close()


def test_huerfano_agota_intentos_y_se_descarta(entorno, monkeypatch):
    """ANTI CRASH-LOOP: un job que mata repetidamente a su worker NO se re-reclama para siempre.

    Con KENI_JOBS_MAX_INTENTOS=2: intento 1 (reclamo normal) + intento 2 (re-reclamo de
    huerfano); al quedar huerfano OTRA vez, el siguiente reclamo lo DESCARTA: cierra el job
    (libera el cupo) y deja el registro en error claro con motivo `interrumpido`.
    """
    monkeypatch.setenv("KENI_JOBS_MAX_INTENTOS", "2")
    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
    cola.encolar(gen["id"], jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags()))

    primero = cola.reclamar("w1")  # intento 1
    assert primero is not None
    _envejecer_claim(primero["id"])
    segundo = cola.reclamar("w2")  # intento 2 (re-reclamo de huerfano)
    assert segundo is not None and segundo["id"] == primero["id"]
    _envejecer_claim(primero["id"])

    assert cola.reclamar("w3") is None  # NO hay tercer intento: descartado
    g = generaciones.obtener(gen["id"])
    assert g["estado"] == generaciones.ESTADO_ERROR
    assert g["motivo"] == generaciones.MOTIVO_INTERRUMPIDO
    assert repos.contar_jobs_activos() == 0  # el job quedo `terminado` (cupo liberado)


def test_reencolar_resetea_intentos(entorno, monkeypatch):
    """El reintento ADMIN (`reencolar_job`) resetea el contador: vuelve a tener sus intentos."""
    monkeypatch.setenv("KENI_JOBS_MAX_INTENTOS", "1")
    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
    cola.encolar(gen["id"], jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags()))
    primero = cola.reclamar("w1")  # unico intento permitido
    _envejecer_claim(primero["id"])
    assert cola.reclamar("w2") is None  # descartado (agoto su unico intento)

    assert repos.reencolar_job(gen["id"])  # decision humana: contador a cero
    de_nuevo = cola.reclamar("w3")
    assert de_nuevo is not None and de_nuevo["id"] == primero["id"]


def test_spec_corrupto_se_reclama_con_spec_none(entorno):
    # spec que NO es un objeto job (tras migrar `spec` a jsonb, el JSON sintacticamente roto ya
    # no puede ni almacenarse; lo que el worker debe tolerar es un JSON valido NO-objeto, p. ej.
    # un numero): se recibe con spec=None y se marca en error.
    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
    repos.encolar_job(gen["id"], "123")
    clavado = cola.reclamar()
    assert clavado is not None and clavado["spec"] is None


# --------------------------------------------------------------------------- #
# jobspec: round-trip + reconstruccion del procesar por kind                  #
# --------------------------------------------------------------------------- #


def test_jobspec_roundtrip(entorno):
    spec = jobspec.construir(
        prompt="el prompt",
        procesar=jobspec.construir_copy(
            prompt_id="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="T",
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
            prompt_id="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="T",
            texto_base="nota", contenido_id="tema-123",
        ),
    )
    vuelto = jobspec.deserializar(jobspec.serializar(spec))
    assert vuelto["procesar"]["contenido_id"] == "tema-123"


def test_jobspec_copy_sin_contenido_id_default_vacio_puro():
    # PURO (sin DB): sin `contenido_id`, el spec lleva "" (back-compat: borrador suelto).
    spec = jobspec.construir_copy(
        prompt_id="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="T",
        texto_base="nota",
    )
    assert spec["contenido_id"] == ""


def test_jobspec_copy_fotos_notas_roundtrip_puro():
    # PURO (sin DB): `fotos_notas` (catálogo de fotos propias por NOTA, mismo orden numerado
    # que vio el modelo) viaja en el spec y sobrevive al round-trip, para que el worker pueda
    # resolver la foto de cada SLIDE del carrusel. Sin él, lista vacía (post de siempre).
    fotos = [
        {"titulo": "Concierto A", "imagen": "https://casa.test/a.jpg"},
        {"titulo": "Concierto B", "imagen": "https://casa.test/b.jpg"},
    ]
    spec = jobspec.construir(
        prompt="p",
        procesar=jobspec.construir_copy(
            prompt_id="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="T",
            texto_base="nota", imagen_fuente=fotos[0]["imagen"], fotos_notas=fotos,
        ),
    )
    vuelto = jobspec.deserializar(jobspec.serializar(spec))
    assert vuelto["procesar"]["fotos_notas"] == fotos
    sin = jobspec.construir_copy(
        prompt_id="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="T",
        texto_base="nota",
    )
    assert sin["fotos_notas"] == []


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
            prompt_id="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="Titulo",
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
    # Sin `copy_in` en la pieza, la publicacion nace con copy_in == "" (no rompe).
    assert resultado["publicaciones"][0]["copy_in"] == ""


def test_reconstruir_procesar_copy_guarda_copy_in(entorno):
    # El copy_in (texto EN imagen) viaja en la misma pieza que el copy y se persiste como
    # campo propio de la publicacion (distinto del contenido), editable luego en C.
    spec = jobspec.construir(
        prompt="p",
        procesar=jobspec.construir_copy(
            prompt_id="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="Titulo",
            texto_base="nota",
        ),
    )
    procesar = jobspec.reconstruir_procesar(spec)
    salida = (
        'Texto del copy\n\n```json\n'
        '{"piezas": [{"red": "x", "texto": "Hola X", "copy_in": "TITULAR EN LA IMAGEN"}]}\n```'
    )
    resultado = procesar(salida, None)
    pub = resultado["publicaciones"][0]
    assert pub["contenido"] == "Hola X"
    assert pub["copy_in"] == "TITULAR EN LA IMAGEN"
    # Persistido y editable: una relectura desde el repo lo conserva.
    recargada = repos.obtener_publicacion(pub["id"])
    assert recargada["copy_in"] == "TITULAR EN LA IMAGEN"


def test_no_hornea_placa_al_crear_marca_visual(entorno, monkeypatch):
    # Render ON-DEMAND: al crear el borrador NO se hornea ninguna placa (no se llama al
    # compositor). La pieza nace con `imagen` vacío y su `imagen_url` apunta al render
    # on-demand `/compuesta`, derivado de la receta (marca + copy_in). Así no se duplica un
    # PNG por cada pieza con el mismo logo/pleca y solo cambia el texto.
    from keni_consola.dominio import estudio_imagen

    def _no_debe_componer(*a, **k):
        raise AssertionError("crear el borrador NO debe hornear la placa (render on-demand)")

    monkeypatch.setattr(estudio_imagen, "componer", _no_debe_componer)

    spec = jobspec.construir(
        prompt="p",
        procesar=jobspec.construir_copy(
            prompt_id="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="Titulo",
            texto_base="nota",
        ),
    )
    procesar = jobspec.reconstruir_procesar(spec)
    salida = '```json\n{"piezas": [{"red": "x", "texto": "Hola X", "copy_in": "DATO CLAVE"}]}\n```'
    resultado = procesar(salida, None)

    pub = resultado["publicaciones"][0]
    assert pub["imagen"] == ""  # nada horneado al crear
    # Sin foto ni plantilla de estudio (el test no siembra ninguna), no hay imagen servible -> "".
    # (La placa de marca por SPEC se retiró; solo componen plantillas de la galería del estudio.)
    assert pub["imagen_url"] == ""


def test_crear_marca_sin_plantilla_sin_imagen(entorno):
    # Marca sin identidad visual (piso-15): sin receta de placa; el borrador nace sin imagen
    # y, sin foto ni fuente, su `imagen_url` queda vacío (no apunta a /compuesta).
    spec = jobspec.construir(
        prompt="p",
        procesar=jobspec.construir_copy(
            prompt_id="copy-desde-nota", marca="piso-15", redes_ids=["x"], titulo_dado="Titulo",
            texto_base="nota",
        ),
    )
    procesar = jobspec.reconstruir_procesar(spec)
    salida = '```json\n{"piezas": [{"red": "x", "texto": "Hola", "copy_in": "X"}]}\n```'
    resultado = procesar(salida, None)
    pub = resultado["publicaciones"][0]
    assert pub["imagen"] == "" and pub["imagen_url"] == ""


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
            prompt_id="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="Titulo",
            texto_base="nota", contenido_id=tema["id"],
        ),
    )
    procesar = jobspec.reconstruir_procesar(spec)
    salida = '```json\n{"piezas": [{"red": "x", "texto": "Hola X"}]}\n```'
    resultado = procesar(salida, None)

    assert len(resultado["publicaciones"]) == 1
    # El borrador cuelga del tema: es una fila por plataforma de ESE contenido.
    plats = repos.listar_contenido_plataforma(tema["id"])
    assert len(plats) == 1
    assert plats[0]["copy"] == "Hola X"
    assert not plats[0]["falta_copy"]
    # Aparece en /api/publicaciones (toda fila por plataforma de un contenido es publicacion) ...
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
            prompt_id="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="T",
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
            prompt_id="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="T",
            texto_base="nota",
        ),
    )
    procesar = jobspec.reconstruir_procesar(spec)
    procesar('```json\n{"piezas": [{"red": "x", "texto": "Suelto"}]}\n```', None)
    # El tema NO recibio ninguna fila por plataforma (el borrador no se nido en el).
    assert repos.listar_contenido_plataforma(tema["id"]) == []
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
            prompt_id="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="T",
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

    Es el camino del desacoplo entero, salvo el binario real: el back encola (via el gate de
    cola COMPARTIDO), el worker reclama, reconstruye el `procesar` de hashtags desde el spec y
    corre el runner #137; el registro queda `completado` con el resultado parseado.
    """
    monkeypatch.setattr(generaciones.shutil, "which", lambda _n: "/usr/bin/claude")
    monkeypatch.setattr(
        generaciones.runner, "lanzar_proc", _fake_lanzar_proc_factory(_LINEAS_OK_HASHTAGS)
    )

    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "Tags"})
    spec = jobspec.construir(prompt="sugiere", procesar=jobspec.construir_hashtags())
    # El encolado pasa el gate de cola COMPARTIDO (como el endpoint real).
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
    # La cola COMPARTIDA quedo drenada (el job paso a `terminado`, libera capacidad).
    assert repos.contar_jobs_activos() == 0


@pytest.mark.timeout(20)
def test_worker_spec_corrupto_marca_error_y_libera_cupo(entorno):
    """Un job con spec corrupto NO llama a `claude`: queda en error y LIBERA la cola.

    El worker marca el registro en error y `cola.terminar` saca el job de la cola, asi su
    cupo (que ocupaba como `pendiente`) se libera y no satura el gate compartido.
    """
    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
    repos.encolar_job(gen["id"], "123")  # JSON valido pero NO un objeto job (spec=None)
    job = cola.reclamar()
    worker.procesar_job(job, "w")
    g = generaciones.obtener(gen["id"])
    assert g["estado"] == generaciones.ESTADO_ERROR
    assert repos.contar_jobs_activos() == 0


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
def test_worker_inproceso_procesa_un_job(entorno, monkeypatch, pool_limpio):
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

    # `pool_limpio` hace el detener()+join determinista en el teardown (este pool arranca
    # KENI_MAX_JOBS hilos por defecto): asi no deja hilos vivos para el siguiente test.
    pool_limpio(worker.iniciar_worker_inproceso())
    assert _esperar_terminal(gen["id"]) == generaciones.ESTADO_COMPLETADO
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
    # Join determinista: que `procesar_job` termine (y desregistre su entrada de
    # `_JOBS_EN_CURSO`) ANTES de acabar el test; sin esto el hilo daemon sobrevivia unos
    # instantes, el TRUNCATE le borraba la generacion y quedaba como job fantasma del
    # siguiente test (`assert 4 == 3` en el pool).
    hilo.join(timeout=10)
    assert not hilo.is_alive(), "procesar_job no termino: fugaria un job en curso al siguiente test"


@pytest.mark.timeout(20)
def test_vigia_cancelacion_sobrevive_errores_transitorios(monkeypatch):
    """Un blip al sondear la cola NO deja el job incancelable: el vigia SIGUE sondeando.

    REGRESION: ante cualquier excepcion el vigia hacia `return` y el job quedaba imposible
    de cancelar el resto de su ejecucion (hasta el wall-timeout). Ahora loguea y continua:
    el primer sondeo revienta (blip de BD) y el segundo ve el flag y cancela.
    """
    intentos = {"n": 0}

    def _cancelado_flaky(_job_id):
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise RuntimeError("blip transitorio de la BD")
        return True

    canceladas: list[str] = []
    monkeypatch.setattr(cola, "cancelado", _cancelado_flaky)
    monkeypatch.setattr(generaciones, "cancelar", lambda gid: canceladas.append(gid))
    monkeypatch.setattr(worker, "_SONDEO_CANCELACION_S", 0.05)

    parar = threading.Event()
    hilo = threading.Thread(target=worker._vigilar_cancelacion, args=("j1", "g1", parar))
    hilo.start()
    hilo.join(timeout=10)
    assert not hilo.is_alive(), "el vigia debio terminar al ver el flag (tras el blip)"
    assert canceladas == ["g1"]
    assert intentos["n"] >= 2  # sobrevivio al primer error y siguio sondeando


def test_sanear_qa_si_fallo_devuelve_el_tema_a_recriba(entorno):
    """Un job de QA-FUENTE que termina en ERROR resetea el sentinel `en_curso` del tema.

    CIERRA EL ZOMBI: la fase QA marca `en_curso` ANTES de lanzar y solo el `procesar` (exito)
    escribe el veredicto real; si la generacion muere, el tema quedaba excluido para siempre
    de la re-criba (y contando en el cupo en vuelo de su marca).
    """
    from keni_consola import pipeline_contenido as pc

    tema = repos.crear_contenido(
        clase="contenido", titulo="Zombi QA", marca=_MARCA, origen=pc.ORIGEN_PIPELINE,
        qa_veredicto=pc.QA_EN_CURSO,
    )
    spec = {
        "procesar": jobspec.construir_qa_fuente(
            marca=_MARCA, titulo="Zombi QA", autor=None, contenido_id=tema["id"],
        )
    }
    gen = generaciones.crear({"tipo": "pipeline", "marca": _MARCA, "etiqueta": "QA"})

    # Registro aun NO en error: el saneo no toca el sentinel (la QA podria seguir viva).
    generaciones.actualizar(gen["id"], {"estado": generaciones.ESTADO_COMPLETADO})
    worker._sanear_qa_si_fallo(gen["id"], spec)
    assert repos.obtener_contenido(tema["id"])["qa_veredicto"] == pc.QA_EN_CURSO

    # Registro en ERROR: el saneo devuelve el tema a "" (re-criba en el proximo barrido).
    generaciones.actualizar(gen["id"], {"estado": generaciones.ESTADO_ERROR})
    worker._sanear_qa_si_fallo(gen["id"], spec)
    assert (repos.obtener_contenido(tema["id"])["qa_veredicto"] or "") == ""


def test_procesar_copy_dedup_al_exito_limpia_pendiente_y_etiqueta(entorno):
    """El post-procesado del copy (EXITO) limpia `copy_pendiente` y etiqueta `autogen`.

    DEDUP AL EXITO (no al lanzar): las marcas de dedup las pone el `procesar` cuando los
    borradores YA existen; un copy fallido las conserva y el barrido lo reintenta.
    """
    from keni_consola import autogen_copy

    tema = repos.crear_contenido(
        clase="contenido", titulo="Tema pool", marca=_MARCA, origen="rss",
        copy_pendiente='{"nota": "n", "redes_ids": ["x"]}',
    )
    spec = jobspec.construir(
        prompt="p",
        procesar=jobspec.construir_copy(
            prompt_id="copy-desde-nota", marca=_MARCA, redes_ids=["x"], titulo_dado="T",
            texto_base="nota", contenido_id=tema["id"],
            limpiar_pendiente=True, etiqueta_exito=autogen_copy.ETIQUETA_AUTOGEN,
        ),
    )
    procesar = jobspec.reconstruir_procesar(jobspec.deserializar(jobspec.serializar(spec)))
    procesar('```json\n{"piezas": [{"red": "x", "texto": "Hola"}]}\n```', None)

    actual = repos.obtener_contenido(tema["id"])
    assert (actual["copy_pendiente"] or "") == ""  # dedup del pipeline, al exito
    assert tema["id"] in autogen_copy.ids_ya_generados()  # dedup del autogen (etiqueta)


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
    assert repos.contar_jobs_activos() == 0


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
    # Join determinista (misma razon que en el test de cancelacion cross-proceso): que el
    # hilo desregistre su job de `_JOBS_EN_CURSO` antes de acabar, para no contaminar el
    # siguiente test con un job fantasma.
    hilo.join(timeout=10)
    assert not hilo.is_alive(), "procesar_job no termino: fugaria un job en curso al siguiente test"


def test_spec_no_se_puede_encolar_sin_spec(entorno):
    """`encolar_job_claude` exige un spec (defensa: sin spec el worker no reconstruye)."""
    gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
    with pytest.raises(ValueError):
        _ENCOLAR_REAL(
            gen["id"], prompt="p", cwd=entorno, procesar=lambda s, m: {}, spec=None
        )
    # El gate de cola NO consume cupo si el encolado falla (nunca se inserto el job).
    assert repos.contar_jobs_activos() == 0


# --------------------------------------------------------------------------- #
# CONCURRENCIA: el pool corre KENI_MAX_JOBS jobs EN PARALELO (no de uno en uno) #
# --------------------------------------------------------------------------- #


@pytest.fixture
def pool_limpio():
    """Garantiza que NINGUN pool de worker sobreviva al test (aislamiento entre tests).

    El test registra su `_Pool` (o el `iniciar_worker_inproceso`) via `registrar(...)`; el
    teardown SIEMPRE lo detiene (cancela jobs en vuelo + join determinista) y, como red de
    seguridad, vacia el registro GLOBAL `_JOBS_EN_CURSO` y comprueba que no quedaron hilos
    del pool vivos. Sin esto, un hilo fugado de un test reclamaba jobs del siguiente (la
    pollucion que rompia `test_pool_detener_...` con `assert 4 == 3`).
    """
    pools = []

    def registrar(pool_o_fachada):
        # Acepta un `_Pool` directo o el hilo-fachada de `iniciar_worker_inproceso` (._pool).
        pool = getattr(pool_o_fachada, "_pool", pool_o_fachada)
        pools.append(pool)
        return pool_o_fachada

    yield registrar

    for pool in pools:
        try:
            pool.detener()
        except Exception:  # noqa: BLE001 -- teardown best-effort: igual limpiamos el registro
            pass
    worker._reset_estado_para_tests()
    # Ningun hilo del pool debe seguir vivo tras detener (garantia del apagado determinista).
    for pool in pools:
        assert not any(h.is_alive() for h in pool._hilos), (
            "un hilo del pool sobrevivio a detener(): fuga que contaminaria el siguiente test"
        )
    assert worker._jobs_en_curso() == []


def _fake_lanzar_proc_lento_factory(sleep_s: float):
    """`runner.lanzar_proc` fake: subproceso python que DUERME `sleep_s` y emite OK.

    Mide solapamiento: si N jobs corren EN PARALELO, el tiempo total ≈ sleep_s; si corren
    en serie, ≈ N × sleep_s. Emite el mismo NDJSON OK de hashtags tras dormir.
    """
    import subprocess as _sp

    res = (
        '{"type": "result", "subtype": "success", "result": "#uno\\n#dos", '
        '"usage": {"input_tokens": 1, "output_tokens": 1}}'
    )
    start = '{"type": "stream_event", "event": {"type": "message_start", "message": {}}}'
    guion = (
        "import sys, time\n"
        f"print({start!r}, flush=True)\n"
        f"time.sleep({sleep_s})\n"
        f"print({res!r}, flush=True)\n"
    )

    def _fake(argv, *, cwd, env=None):  # noqa: ANN001
        return _sp.Popen(
            [sys.executable, "-c", guion],
            cwd=cwd, stdout=_sp.PIPE, stderr=_sp.DEVNULL, text=True, bufsize=1,
            start_new_session=True,
        )

    return _fake


@pytest.mark.timeout(40)
@pytest.mark.skipif(os.name != "posix", reason="subproceso real")
def test_worker_inproceso_corre_jobs_en_paralelo(entorno, monkeypatch, pool_limpio):
    """El pool in-proceso (KENI_MAX_JOBS) corre N jobs EN PARALELO: tiempo ≈ slowest, no sum.

    REGRESION del bug serial: el bucle antiguo clavaba 1 job, esperaba su terminal y recien
    entonces clavaba el siguiente => N jobs lentos tardaban N × t. Con el pool de N hilos los
    N jobs se solapan y el total ≈ t (el de un solo job) + holgura.
    """
    n = 4
    sleep_s = 1.5
    monkeypatch.setenv("KENI_MAX_JOBS", str(n))
    monkeypatch.setattr(generaciones.shutil, "which", lambda _n: "/usr/bin/claude")
    monkeypatch.setattr(
        generaciones.runner, "lanzar_proc", _fake_lanzar_proc_lento_factory(sleep_s)
    )

    gens = []
    for _ in range(n):
        gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
        spec = jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags())
        _ENCOLAR_REAL(
            gen["id"], prompt="p", cwd=entorno, procesar=lambda s, m: {}, spec=spec
        )
        gens.append(gen["id"])

    inicio = time.monotonic()
    # `pool_limpio` detiene el pool en el teardown (y verifica que ningun hilo se fuga),
    # asi este test no contamina al siguiente (la fuga que rompia el suite combinado).
    hilo = pool_limpio(worker.iniciar_worker_inproceso())
    for gid in gens:
        assert _esperar_terminal(gid, timeout=30) == generaciones.ESTADO_COMPLETADO
    # Parar el pool YA (dentro del test) para medir bien y dejar limpio antes del assert de
    # tiempo; el teardown del fixture es idempotente (detener() de un pool ya parado no hace nada).
    hilo._pool.detener()  # type: ignore[attr-defined]
    transcurrido = time.monotonic() - inicio

    # En paralelo: muy por debajo de la suma serial (N × sleep_s). Con margen generoso para
    # el arranque de N subprocesos + sondeo de la cola, exigimos < (N-1) × sleep_s, que un
    # bucle serial JAMAS cumpliria (serial ≈ N × sleep_s = 6 s; paralelo ≈ ~2 s).
    assert transcurrido < (n - 1) * sleep_s, (
        f"los {n} jobs no se solaparon (tardaron {transcurrido:.1f}s; serial seria ~{n * sleep_s}s)"
    )


@pytest.mark.timeout(40)
@pytest.mark.skipif(os.name != "posix", reason="subproceso real")
def test_pool_detener_reencola_los_en_vuelo_para_el_worker_post_deploy(entorno, monkeypatch, pool_limpio):
    """`pool.detener()` (apagado/SIGTERM por deploy) DEVUELVE los jobs en vuelo a `pendiente`.

    ANTES se marcaban INTERRUMPIDO y se sacaban de la cola "para que los relanzara el reaper",
    pero NINGUN reaper relanzaba jobs terminados: cada deploy PERDIA los jobs en vuelo y exigia
    relanzarlos a mano. Ahora el apagado gracioso re-encola cada job (mismo spec) y deja su
    registro `ejecutando` (la UI sigue en "Generando..."): el worker post-deploy lo re-reclama
    y lo completa SOLO. La guardia anti-duplicado del reclamo cubre el post-procesado.
    """
    n = 3
    monkeypatch.setenv("KENI_MAX_JOBS", str(n))
    monkeypatch.setattr(generaciones.shutil, "which", lambda _n: "/usr/bin/claude")
    # Jobs LARGOS: estan en vuelo cuando paramos el pool.
    monkeypatch.setattr(
        generaciones.runner, "lanzar_proc", _fake_lanzar_proc_lento_factory(300)
    )

    gens = []
    for _ in range(n):
        gen = generaciones.crear({"tipo": "hashtags", "marca": _MARCA, "etiqueta": "X"})
        spec = jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags())
        _ENCOLAR_REAL(
            gen["id"], prompt="p", cwd=entorno, procesar=lambda s, m: {}, spec=spec
        )
        gens.append(gen["id"])

    hilo = pool_limpio(worker.iniciar_worker_inproceso())
    # Esperar a que los N jobs esten EN VUELO (registrados como en curso en el worker). Que el
    # registro tenga EXACTAMENTE n (ni 1 mas) verifica de paso que ningun pool de un test
    # previo dejo jobs fantasma (la regresion de aislamiento que este fixture cierra).
    # Timeout AMPLIO (red de seguridad, no plazo de rendimiento): normalmente los N jobs entran
    # en vuelo en <1s, pero bajo carga alta (suite -n6 lenta) el hilo worker puede tardar en
    # reclamar; 60s evita el flake sin enmascarar un cuelgue real.
    fin = time.monotonic() + 60
    while time.monotonic() < fin and len(worker._jobs_en_curso()) < n:
        time.sleep(0.05)
    assert len(worker._jobs_en_curso()) == n, "los N jobs deberian estar en vuelo"

    # Apagado determinista: para el pool, cancela los `claude` en vuelo, hace join y RE-ENCOLA.
    hilo._pool.detener()  # type: ignore[attr-defined]

    # Fuera del registro de en-curso, pero el TRABAJO no se pierde: el registro sigue
    # `ejecutando` (revivido, sin motivo de error) y el job esta de vuelta como `pendiente`.
    assert worker._jobs_en_curso() == []
    for gid in gens:
        g = generaciones.obtener(gid)
        assert g["estado"] == generaciones.ESTADO_EJECUTANDO
        assert (g.get("motivo") or "") == ""
        assert (g.get("error") or "") == ""
    assert repos.contar_jobs_activos() == n  # los N jobs volvieron a la cola

    # RE-RECLAMABLES YA (sin envejecer claimed_at): el "worker post-deploy" los clava.
    reclamado = cola.reclamar("w-post-deploy")
    assert reclamado is not None and reclamado["gen_id"] in gens
    cola.terminar(reclamado["id"])  # higiene: no dejar la fila reclamada al siguiente assert
    assert repos.contar_jobs_activos() == n - 1
