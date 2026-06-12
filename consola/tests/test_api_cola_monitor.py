"""Tests de la API del MONITOR DE COLA (/api/actividad/cola*). OFFLINE.

Cubre el contrato del snapshot en vivo (capacidad/conteo/en_curso/esperando/daemons), la
serie por dia (encolados vs resultados) y las acciones ADMIN (purgar/reencolar) con su cerrojo
de rol (editor / token de mantenimiento -> 403). Nada toca `claude` ni red: encolamos jobs a
mano en la cola (SQLite del entorno aislado) y leemos el registro de generacion (YAML).
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, cola, generaciones, repos
from keni_consola.dominio import jobspec

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"
_MARCA = "unotv"


def _app():
    return app_modulo.crear_app(token=TOKEN_PRUEBA)


def _cli() -> TestClient:
    return TestClient(_app())


def _login(c: TestClient, usuario: str, password: str):
    return c.post(
        "/api/auth/login", json={"usuario": usuario, "password": password}, headers=_ORIGIN
    )


def _cli_como(rol: str) -> TestClient:
    """TestClient autenticado por SESION con un usuario del rol dado (admin/editor)."""
    auth.crear_usuario("u", CLAVE, rol)
    c = _cli()
    assert _login(c, "u", CLAVE).status_code == 200
    return c


def _cli_token() -> TestClient:
    """TestClient que entra por el TOKEN de mantenimiento (pasa /api, NO es admin)."""
    c = _cli()
    c.headers.update({"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    return c


def _encolar(etiqueta: str = "Copy de nota", marca: str = _MARCA) -> str:
    """Crea una generacion + encola su job (pendiente). Devuelve el gen_id."""
    gen = generaciones.crear({"tipo": "copy", "marca": marca, "etiqueta": etiqueta})
    spec = jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags())
    cola.encolar(gen["id"], spec)
    return gen["id"]


# --------------------------------------------------------------------------- #
# Snapshot en vivo                                                            #
# --------------------------------------------------------------------------- #


def test_cola_snapshot_contrato(entorno):
    gen_id = _encolar("QA fuente · UnoTV")
    r = _cli_token().get("/api/actividad/cola")
    assert r.status_code == 200
    data = r.json()
    # Capacidad y conteo.
    assert data["capacidad"]["tope"] == data["capacidad"]["max_jobs"] + data["capacidad"]["max_cola"]
    assert data["conteo"]["pendientes"] >= 1
    assert data["conteo"]["activos"] == data["conteo"]["pendientes"] + data["conteo"]["reclamados"]
    assert data["cola_llena"] is False
    # El job pendiente aparece en `esperando` con su etiqueta enriquecida desde el registro.
    esperando = data["esperando"]
    assert any(j["gen_id"] == gen_id and j["etiqueta"] == "QA fuente · UnoTV" for j in esperando)
    # Cada job en vuelo trae su `proceso` (ADR 0011); un `tipo='copy'` es produccion.
    job = next(j for j in esperando if j["gen_id"] == gen_id)
    assert job["proceso"] == generaciones.PROCESO_PRODUCCION
    # Desglose del pool compartido por proceso + embudo de QA (contrato del Monitor de 2 loops).
    assert set(data["por_proceso"]) == {
        generaciones.PROCESO_INVESTIGACION, generaciones.PROCESO_PRODUCCION,
    }
    assert data["por_proceso"][generaciones.PROCESO_PRODUCCION]["pendientes"] >= 1
    assert {"en_vuelo", "tope_por_marca", "marcas"} <= set(data["embudo_qa"])
    # Daemons: lista no vacia con el reaper SIEMPRE activo.
    porclave = {d["clave"]: d for d in data["daemons"]}
    assert "reaper" in porclave
    assert porclave["reaper"]["activo"] is True
    # Toggles REALES en el Monitor: un daemon con clave de catálogo no peligrosa es editable y trae
    # su `clave_ajuste`; el reaper (sin toggle) y `publicar_real` (peligroso) NO son editables.
    assert porclave["media_gc"]["editable"] is True
    assert porclave["media_gc"]["clave_ajuste"] == "KENI_MEDIA_GC"
    assert porclave["reaper"]["editable"] is False
    assert porclave["reaper"]["clave_ajuste"] == ""
    assert porclave["publicar_real"]["editable"] is False  # peligroso: read-only en el Monitor
    # El interruptor general y las etapas (Selección/Copy) ya NO son daemons: viven en la sección
    # «Máquina de contenido» del Monitor (no en este panel de daemons de fondo).
    assert "maquina" not in porclave
    assert "ingesta" not in porclave
    assert "pipeline" not in porclave


def test_cola_snapshot_marca_reclamado_como_procesando(entorno):
    _encolar()
    # Un worker clava el job: pasa a `reclamado` -> cuenta como `procesando`.
    clavado = cola.reclamar("worker-1")
    assert clavado is not None
    data = _cli_token().get("/api/actividad/cola").json()
    assert data["conteo"]["reclamados"] == 1
    assert data["procesando"] == 1
    assert "worker-1" in data["workers_activos"]
    assert any(j["gen_id"] == clavado["gen_id"] for j in data["en_curso"])


def test_cola_filtra_por_marca(entorno):
    """`?marca=` acota las LISTAS en_curso/esperando a esa marca; los KPIs siguen GLOBALES.

    Es el bug del Monitor: estando en claro-sports se veian TODOS los jobs de unotv (el
    endpoint no admitia marca y el front no la pasaba). La capacidad/conteo se queda global
    a proposito (la cola es infra compartida).
    """
    g_uno = _encolar("Copy UnoTV", marca="unotv")
    g_claro = _encolar("Copy Claro", marca="claro-sports")

    # Sin filtro: las dos marcas en la lista de espera.
    data = _cli_token().get("/api/actividad/cola").json()
    assert data["marca"] == ""
    assert {j["gen_id"] for j in data["esperando"]} >= {g_uno, g_claro}

    # Con filtro: SOLO la marca pedida en las listas; el conteo global no cambia.
    data = _cli_token().get("/api/actividad/cola?marca=claro-sports").json()
    assert data["marca"] == "claro-sports"
    assert {j["gen_id"] for j in data["esperando"]} == {g_claro}
    assert all(j["marca"] == "claro-sports" for j in data["esperando"])
    assert data["conteo"]["pendientes"] == 2  # KPI global: la infra es compartida

    # Marca invalida -> 400 en espanol (mismo contrato que /api/actividad).
    r = _cli_token().get("/api/actividad/cola?marca=no-existe")
    assert r.status_code == 400
    assert "Marca" in r.json()["error"]


def test_cola_jobs_traen_prioridad(entorno):
    """Cada job en vuelo expone su `prioridad` de cola (mayor = adelanta al lote de fondo).

    La prioridad viaja DENTRO del spec (`jobspec.prioridad`): manual > pipeline. El Monitor
    la usa para señalar qué espera "por delante" en la cola.
    """
    gen = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "Manual prioritario"})
    spec = jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags(), prioridad=10)
    cola.encolar(gen["id"], spec)
    data = _cli_token().get("/api/actividad/cola").json()
    job = next(j for j in data["esperando"] if j["gen_id"] == gen["id"])
    assert job["prioridad"] == 10


# --------------------------------------------------------------------------- #
# Serie por dia                                                               #
# --------------------------------------------------------------------------- #


def test_cola_series_contrato(entorno):
    _encolar()
    r = _cli_token().get("/api/actividad/cola/series?dias=7")
    assert r.status_code == 200
    data = r.json()
    assert data["dias"] == 7
    # Hay al menos un dia con un encolado (el de hoy).
    assert sum(d["n"] for d in data["encolados"]) >= 1
    assert isinstance(data["resultados"], list)


def test_serie_excluye_marcadores_y_desglosa_por_proceso(entorno):
    """La serie NO cuenta los marcadores de etapa (coste 0) y separa investigacion/produccion.

    Era el bug del Monitor: `_resultados_por_dia` contaba los miles de `pipeline_etapa` (CI/QA/CD,
    sin tokens) y "completados" no cuadraba ni con los encolados ni con el gasto. Aqui se sellan
    tres generaciones COMPLETADAS hoy —un marcador (excluido), una criba QA (investigacion, con
    tokens) y un copy (produccion, con tokens)— y se comprueba que la serie cuenta SOLO las dos
    reales, cada una en su proceso y con su gasto.
    """
    # Marcador de etapa: completado pero SIN coste -> debe quedar fuera de la serie.
    generaciones.crear({
        "tipo": "pipeline_etapa", "marca": _MARCA, "etiqueta": "QA · criba",
        "estado": generaciones.ESTADO_COMPLETADO, "fecha_fin": generaciones.ahora_iso(),
    })
    # Criba QA real (investigacion) con tokens.
    generaciones.crear({
        "tipo": "pipeline", "marca": _MARCA, "etiqueta": "Validación · tema",
        "proceso": generaciones.PROCESO_INVESTIGACION,
        "estado": generaciones.ESTADO_COMPLETADO, "fecha_fin": generaciones.ahora_iso(),
        "metricas": {"tokens_in": 100, "tokens_out": 20, "total_cost_usd": 0.01},
    })
    # Copy real (produccion) con tokens.
    generaciones.crear({
        "tipo": "copy", "marca": _MARCA, "etiqueta": "Copy de nota",
        "estado": generaciones.ESTADO_COMPLETADO, "fecha_fin": generaciones.ahora_iso(),
        "metricas": {"tokens_in": 500, "tokens_out": 300, "total_cost_usd": 0.05},
    })

    data = _cli_token().get("/api/actividad/cola/series?dias=7").json()
    total_completados = sum(d["completados"] for d in data["resultados"])
    assert total_completados == 2  # las dos reales; el marcador NO cuenta

    inv = sum(d["por_proceso"]["investigacion"]["completados"] for d in data["resultados"])
    prod = sum(d["por_proceso"]["produccion"]["completados"] for d in data["resultados"])
    assert (inv, prod) == (1, 1)
    # El gasto se acumula del lado correcto (los 120/800 tokens de cada generacion).
    assert sum(d["por_proceso"]["investigacion"]["tokens"] for d in data["resultados"]) == 120
    assert sum(d["por_proceso"]["produccion"]["tokens"] for d in data["resultados"]) == 800


# --------------------------------------------------------------------------- #
# Acciones admin: purgar / reencolar (cerrojo de rol)                         #
# --------------------------------------------------------------------------- #


def test_purgar_libera_la_cola_admin(entorno):
    _encolar()
    _encolar()
    assert repos.contar_jobs_activos() == 2
    r = _cli_como("admin").post("/api/actividad/cola/purgar", headers=_ORIGIN)
    assert r.status_code == 200
    assert r.json()["purgados"] == 2
    # La cola quedo libre: vuelve a haber capacidad.
    assert repos.contar_jobs_activos() == 0


def test_purgar_requiere_admin(entorno):
    _encolar()
    assert _cli_como("editor").post("/api/actividad/cola/purgar", headers=_ORIGIN).status_code == 403
    assert _cli_token().post("/api/actividad/cola/purgar", headers=_ORIGIN).status_code == 403
    # El editor/token no purgaron nada.
    assert repos.contar_jobs_activos() == 1


def test_lanzar_urgente_encola_con_prioridad_breaking(entorno, monkeypatch):
    """`dominio.generar.lanzar(urgente=True)` en tipo de FONDO encola a PRIORIDAD_BREAKING.

    Es el carril de las historias CURADAS desde el panel (breaking empujada por un humano):
    su copy adelanta al lote de fondo sin pisar los lanzamientos manuales (10 > 5 > 0).
    Se captura el SPEC en el seam de encolado (`encolar_job_claude`): en tests el worker
    in-proceso correría el job al instante y la fila no quedaría observable en la cola.
    """
    from keni_consola.dominio import generar as dom_generar

    specs: dict[str, dict] = {}

    def captura(gen_id, *, prompt, cwd, procesar, dir_temporal=None, spec=None):
        specs[gen_id] = spec or {}

    monkeypatch.setattr(dom_generar.generaciones, "encolar_job_claude", captura)
    spec_proc = jobspec.construir_hashtags()
    comunes = dict(
        titulo="t", marca=_MARCA, prompt="p",
        procesar=jobspec.reconstruir_procesar({"procesar": spec_proc}),
        procesar_spec=spec_proc,
    )
    urgente = dom_generar.lanzar(tipo="autogen", urgente=True, clave_idem="k1", **comunes)
    fondo = dom_generar.lanzar(tipo="autogen", clave_idem="k2", **comunes)
    manual = dom_generar.lanzar(tipo="copy", clave_idem="k3", **comunes)
    assert jobspec.prioridad(specs[urgente["id"]]) == jobspec.PRIORIDAD_BREAKING
    assert jobspec.prioridad(specs[fondo["id"]]) == jobspec.PRIORIDAD_PIPELINE
    assert jobspec.prioridad(specs[manual["id"]]) == jobspec.PRIORIDAD_MANUAL


def test_priorizar_adelanta_job_pendiente_admin(entorno):
    """Priorizar sube el job ESPERANDO a URGENTE: adelanta a TODO lo pendiente, también a
    otros manuales (antes manual→manual empataba y decidía el id aleatorio: flake + botón
    del Monitor sin efecto entre manuales)."""
    primero = _encolar("Fondo viejo")
    segundo = _encolar("Breaking esperando")
    r = _cli_como("admin").post(
        "/api/actividad/cola/priorizar", json={"gen_id": segundo}, headers=_ORIGIN
    )
    assert r.status_code == 200 and r.json()["priorizado"] is True
    # El priorizado adelanta: el siguiente claim se lleva al segundo, no al primero (FIFO roto).
    job = cola.reclamar("w")
    assert job is not None and job["gen_id"] == segundo
    assert cola.reclamar("w2")["gen_id"] == primero


def test_priorizar_job_reclamado_404(entorno):
    """Un job ya RECLAMADO (corriendo) no se prioriza: 404 explicable."""
    gen_id = _encolar()
    cola.reclamar("w")
    r = _cli_como("admin").post(
        "/api/actividad/cola/priorizar", json={"gen_id": gen_id}, headers=_ORIGIN
    )
    assert r.status_code == 404


def test_priorizar_requiere_admin(entorno):
    gen_id = _encolar()
    assert _cli_como("editor").post(
        "/api/actividad/cola/priorizar", json={"gen_id": gen_id}, headers=_ORIGIN
    ).status_code == 403


def test_reencolar_reintenta_job_terminado_admin(entorno):
    gen_id = _encolar()
    # Simula un job ya procesado: clavado + terminado (sale de la cola activa).
    job = cola.reclamar("w")
    cola.terminar(job["id"])
    generaciones.actualizar(gen_id, {"estado": generaciones.ESTADO_ERROR})
    assert repos.contar_jobs_activos() == 0

    r = _cli_como("admin").post(
        "/api/actividad/cola/reencolar", json={"gen_id": gen_id}, headers=_ORIGIN
    )
    assert r.status_code == 200 and r.json()["reencolado"] is True
    # El job volvio a la cola (pendiente) y el registro se reabrio a `ejecutando`.
    assert repos.contar_jobs_activos() == 1
    assert generaciones.obtener(gen_id)["estado"] == generaciones.ESTADO_EJECUTANDO


def test_reencolar_gen_inexistente_404(entorno):
    r = _cli_como("admin").post(
        "/api/actividad/cola/reencolar", json={"gen_id": "no-existe"}, headers=_ORIGIN
    )
    assert r.status_code == 404


def test_reencolar_requiere_admin(entorno):
    gen_id = _encolar()
    r = _cli_como("editor").post(
        "/api/actividad/cola/reencolar", json={"gen_id": gen_id}, headers=_ORIGIN
    )
    assert r.status_code == 403
