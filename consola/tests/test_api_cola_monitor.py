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
    spec = jobspec.construir(prompt="p", procesar=jobspec.construir_prompt_lib())
    cola.encolar(gen["id"], spec)
    return gen["id"]


def _encolar_huerfano(gen_id: str = "gen-fantasma") -> str:
    """Encola un job cuyo `gen_id` NO tiene registro de generacion (job huerfano). Devuelve el gen_id."""
    spec = jobspec.construir(prompt="p", procesar=jobspec.construir_prompt_lib())
    cola.encolar(gen_id, spec)
    return gen_id


# --------------------------------------------------------------------------- #
# Snapshot en vivo                                                            #
# --------------------------------------------------------------------------- #


def test_cola_snapshot_contrato(entorno):
    gen_id = _encolar("Verificar · UnoTV")
    r = _cli_token().get("/api/actividad/cola")
    assert r.status_code == 200
    data = r.json()
    # Capacidad y conteo. La cola NO tiene tope (R-NO-LIMIT): la capacidad es solo la concurrencia.
    assert set(data["capacidad"]) == {"max_jobs"}
    assert data["capacidad"]["max_jobs"] >= 1
    assert "max_cola" not in data["capacidad"] and "tope" not in data["capacidad"]
    assert "cola_llena" not in data  # ya no existe el concepto de cola llena
    assert data["conteo"]["pendientes"] >= 1
    assert data["conteo"]["activos"] == data["conteo"]["pendientes"] + data["conteo"]["reclamados"]
    # El job pendiente aparece en `esperando` con su etiqueta enriquecida desde el registro.
    esperando = data["esperando"]
    assert any(j["gen_id"] == gen_id and j["etiqueta"] == "Verificar · UnoTV" for j in esperando)
    # Cada job en proceso trae su `proceso` (ADR 0011); un `tipo='copy'` es produccion.
    job = next(j for j in esperando if j["gen_id"] == gen_id)
    assert job["proceso"] == generaciones.PROCESO_PRODUCCION
    # Desglose del pool compartido por proceso + admision de verificación (contrato del Monitor de 2 loops).
    assert set(data["por_proceso"]) == {
        generaciones.PROCESO_INVESTIGACION, generaciones.PROCESO_PRODUCCION,
    }
    assert data["por_proceso"][generaciones.PROCESO_PRODUCCION]["pendientes"] >= 1
    assert {"en_proceso", "tope_por_marca", "marcas"} <= set(data["admision_verificacion"])
    # Daemons: lista no vacia con el limpiador SIEMPRE activo.
    porclave = {d["clave"]: d for d in data["daemons"]}
    assert "limpiador" in porclave
    assert porclave["limpiador"]["activo"] is True
    # Toggles REALES en el Monitor: un daemon con clave de catálogo no peligrosa es editable y trae
    # su `clave_ajuste`; el limpiador (sin toggle) y `publicar_real` (peligroso) NO son editables.
    assert porclave["media_gc"]["editable"] is True
    assert porclave["media_gc"]["clave_ajuste"] == "KENI_MEDIA_GC"
    assert porclave["limpiador"]["editable"] is False
    assert porclave["limpiador"]["clave_ajuste"] == ""
    assert porclave["publicar_real"]["editable"] is False  # peligroso: read-only en el Monitor
    # El interruptor general y las etapas (Admitir/Redactar) ya NO son daemons: viven en la sección
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

    La capacidad/conteo se queda global a proposito (la cola es infra compartida).
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
    """Cada job en proceso expone su `prioridad` de cola (mayor = adelanta al lote de fondo).

    La prioridad viaja DENTRO del spec (`jobspec.prioridad`): manual > pipeline. El Monitor
    la usa para señalar qué espera "por delante" en la cola.
    """
    gen = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "Manual prioritario"})
    spec = jobspec.construir(prompt="p", procesar=jobspec.construir_prompt_lib(), prioridad=10)
    cola.encolar(gen["id"], spec)
    data = _cli_token().get("/api/actividad/cola").json()
    job = next(j for j in data["esperando"] if j["gen_id"] == gen["id"])
    assert job["prioridad"] == 10


def test_cola_conteo_marca_cuadra_con_listas(entorno):
    """Con filtro de marca, `conteo_marca` CUADRA con las listas; sin filtro es None.

    El KPI global (`conteo`) sigue siendo de toda la cola; el bloque nuevo `conteo_marca` se deriva
    de los MISMOS jobs enriquecidos de la marca, asi que la UI puede mostrar conteos que casen con
    `en_curso`/`esperando` en vez de mezclar un total global con listas por marca.
    """
    _encolar("Copy UnoTV", marca="unotv")
    _encolar("Copy UnoTV 2", marca="unotv")
    _encolar("Copy Claro", marca="claro-sports")

    # Sin filtro: conteo_marca null (manda el global).
    data = _cli_token().get("/api/actividad/cola").json()
    assert data["conteo_marca"] is None

    # Con filtro: conteo_marca == longitudes de las listas de esa marca.
    data = _cli_token().get("/api/actividad/cola?marca=unotv").json()
    assert data["conteo_marca"] == {
        "pendientes": len(data["esperando"]),
        "reclamados": len(data["en_curso"]),
    }
    assert data["conteo_marca"]["pendientes"] == 2
    # El KPI global no se acota por marca: las 3 piezas siguen contando.
    assert data["conteo"]["pendientes"] == 3


def test_cola_huerfanos_en_snapshot(entorno):
    """Un job sin registro de generacion aparece en `huerfanos` y se marca `huerfano` en la lista."""
    _encolar_huerfano()
    data = _cli_token().get("/api/actividad/cola").json()
    assert data["huerfanos"]["pendientes"] == 1
    assert data["huerfanos"]["reclamados"] == 0
    # El job huerfano viaja en la lista de espera con su flag (marca/proceso sin registro real).
    huerfano = next(j for j in data["esperando"] if j["gen_id"] == "gen-fantasma")
    assert huerfano["huerfano"] is True
    assert huerfano["marca"] == ""


def test_cola_desglose_contrato(entorno):
    """`/cola/desglose` agrupa por marca x proceso x estado y aisla los huerfanos."""
    _encolar("Copy UnoTV", marca="unotv")
    _encolar("Copy Claro", marca="claro-sports")
    _encolar_huerfano()
    # Un job reclamado: debe contarse como `reclamados` en alguna marca o en huerfanos.
    clavado = cola.reclamar("w")
    assert clavado is not None

    data = _cli_token().get("/api/actividad/cola/desglose").json()
    por_marca = {b["marca"]: b for b in data["marcas"]}
    assert "unotv" in por_marca and "claro-sports" in por_marca
    # Ambos procesos SIEMPRE presentes; el copy es produccion.
    bloque = por_marca["unotv"]
    assert set(bloque["por_proceso"]) == {
        generaciones.PROCESO_INVESTIGACION, generaciones.PROCESO_PRODUCCION,
    }
    assert bloque["por_proceso"][generaciones.PROCESO_PRODUCCION]["pendientes"] >= 0
    assert set(bloque["total"]) == {"pendientes", "reclamados"}
    # Huerfano contado aparte, nunca en una marca.
    assert data["huerfanos"]["pendientes"] == 1
    assert "gen-fantasma" not in por_marca
    # El unico reclamado del entorno cuadra entre marcas + huerfanos.
    total_reclamados = (
        sum(b["total"]["reclamados"] for b in data["marcas"])
        + data["huerfanos"]["reclamados"]
    )
    assert total_reclamados == 1


def test_cola_preview_redactar(entorno):
    """`/cola/preview` cuenta los temas autogenerables sin copy que ENTRARIAN a Redactar por marca,
    ignorando el gate por marca (sin encolar nada). Marca invalida -> 400."""
    tema = repos.crear_publicacion(
        clase="contenido", titulo="Noticia rss", marca="unotv", origen="rss",
    )
    repos.crear_pieza_fila(publicacion_id=tema["id"], red="x", falta_copy=True)

    # Sin filtro: la marca con un tema redactable aparece con redactar>=1.
    data = _cli_token().get("/api/actividad/cola/preview").json()
    por_marca = {b["marca"]: b["redactar"] for b in data["marcas"]}
    assert por_marca.get("unotv") == 1

    # Con filtro: solo esa marca, mismo conteo.
    solo = _cli_token().get("/api/actividad/cola/preview?marca=unotv").json()
    assert solo["marcas"] == [{"marca": "unotv", "redactar": 1}]

    # Marca invalida -> 400 (mismo contrato que el resto del hub).
    assert _cli_token().get("/api/actividad/cola/preview?marca=no-existe").status_code == 400


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


def test_economia_contrato_global_desde_ledger(entorno):
    """/api/actividad/economia sirve el desglose GLOBAL por proceso desde el ledger gasto_ia."""
    # Dos marcas distintas en produccion: el desglose es GLOBAL, deben sumarse.
    repos.registrar_gasto_ia("e1", dia=generaciones.ahora_iso()[:10], proceso="produccion",
                             tipo="copy", marca="unotv", tokens_in=100, tokens_out=40,
                             coste_usd=0.01)
    repos.registrar_gasto_ia("e2", dia=generaciones.ahora_iso()[:10], proceso="produccion",
                             tipo="copy", marca="claro-sports", tokens_in=10, tokens_out=5,
                             coste_usd=0.002)
    repos.registrar_gasto_ia("e3", dia=generaciones.ahora_iso()[:10], proceso="investigacion",
                             tipo="verificacion", marca="unotv", tokens_in=200, tokens_out=20,
                             coste_usd=0.004)

    data = _cli_token().get("/api/actividad/economia?dias=7").json()
    assert data["dias"] == 7
    por_proceso = data["por_proceso"]
    # Las 4 pestañas de Contexto siempre presentes.
    assert set(por_proceso) == {"investigacion", "produccion", "herramientas", "desarrollo"}
    prod = por_proceso["produccion"]
    assert prod["total"]["items"] == 2 and prod["total"]["tokens"] == 155
    # La API expone tokens in/out SEPARADOS (coste distinto): copy 100/40 + 10/5 -> 110/45.
    assert prod["total"]["tokens_in"] == 110 and prod["total"]["tokens_out"] == 45
    assert len(prod["por_dia"]) == 7  # zero-filled a la ventana pedida
    assert prod["por_etapa"][0]["etapa"] == "Redactar"  # tipo copy -> fase Redactar
    assert por_proceso["investigacion"]["total"]["items"] == 1


def test_economia_filtra_por_marca(entorno):
    """`marca` acota el desglose a sus filas; "" agrega todas; marca invalida -> 400."""
    hoy = generaciones.ahora_iso()[:10]
    repos.registrar_gasto_ia("mk1", dia=hoy, proceso="produccion", tipo="copy",
                             marca="unotv", tokens_in=100, tokens_out=40, coste_usd=0.01)
    repos.registrar_gasto_ia("mk2", dia=hoy, proceso="produccion", tipo="copy",
                             marca="claro-sports", tokens_in=10, tokens_out=5, coste_usd=0.002)

    solo = _cli_token().get("/api/actividad/economia?marca=unotv").json()
    assert solo["por_proceso"]["produccion"]["total"]["items"] == 1
    assert solo["por_proceso"]["produccion"]["total"]["tokens"] == 140

    todas = _cli_token().get("/api/actividad/economia").json()
    assert todas["por_proceso"]["produccion"]["total"]["items"] == 2

    assert _cli_token().get("/api/actividad/economia?marca=no-existe").status_code == 400


def test_economia_clampa_dias_al_maximo(entorno):
    """`dias` se clampa al maximo razonable; default 7 cuando falta/invalido."""
    assert _cli_token().get("/api/actividad/economia?dias=9999").json()["dias"] == 31
    assert _cli_token().get("/api/actividad/economia").json()["dias"] == 7


def test_serie_excluye_marcadores_y_desglosa_por_proceso(entorno):
    """La serie NO cuenta los marcadores de etapa (coste 0) y separa investigacion/produccion.

    Aqui se sellan tres generaciones COMPLETADAS hoy —un marcador (excluido), una verificación Verificar
    (investigacion, con tokens) y un copy (produccion, con tokens)— y se comprueba que la serie
    cuenta SOLO las dos reales, cada una en su proceso y con su gasto.
    """
    # Marcador de etapa: completado pero SIN coste -> debe quedar fuera de la serie.
    generaciones.crear({
        "tipo": "pipeline_etapa", "marca": _MARCA, "etiqueta": "VERIFICAR · verificación",
        "estado": generaciones.ESTADO_COMPLETADO, "fecha_fin": generaciones.ahora_iso(),
    })
    # Verificación Verificar real (investigacion) con tokens.
    generaciones.crear({
        "tipo": "pipeline", "marca": _MARCA, "etiqueta": "Verificar · tema",
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


def test_limpiar_huerfanos_saca_solo_los_huerfanos_admin(entorno):
    """Limpiar huerfanos saca de la cola los PENDIENTES sin registro; respeta los jobs sanos."""
    sano = _encolar()
    _encolar_huerfano("gen-fantasma-1")
    _encolar_huerfano("gen-fantasma-2")
    assert repos.contar_jobs_activos() == 3

    r = _cli_como("admin").post("/api/actividad/cola/limpiar-huerfanos", headers=_ORIGIN)
    assert r.status_code == 200
    assert r.json()["huerfanos_limpiados"] == 2
    # Solo el job con registro vivo sigue en la cola.
    activos = {j["gen_id"] for j in repos.jobs_activos()}
    assert activos == {sano}


def test_limpiar_huerfanos_requiere_admin(entorno):
    _encolar_huerfano()
    assert _cli_como("editor").post(
        "/api/actividad/cola/limpiar-huerfanos", headers=_ORIGIN
    ).status_code == 403
    assert _cli_token().post(
        "/api/actividad/cola/limpiar-huerfanos", headers=_ORIGIN
    ).status_code == 403
    # Nada se limpio: el huerfano sigue en la cola.
    assert repos.contar_jobs_activos() == 1


# --------------------------------------------------------------------------- #
# Gate DIARIO por % del limite semanal: estado expuesto + aceptar +10% (admin)  #
# --------------------------------------------------------------------------- #


def test_cola_expone_gate_diario_por_cuenta(entorno):
    """El snapshot trae el gate diario POR CUENTA bajo `presupuesto.gate_diario_cuentas` (las dos
    cuentas). En vista global (sin marca) `gate_diario` es None. Sin cablear la fuente del %,
    `consumo_hoy_pct` es None y ninguna cuenta pausa (rollout: gate inerte)."""
    presupuesto = _cli_token().get("/api/actividad/cola").json()["presupuesto"]
    assert presupuesto["gate_diario"] is None  # vista global: sin cuenta concreta
    cuentas = presupuesto["gate_diario_cuentas"]
    assert set(cuentas) == {"a", "b"}
    for cuenta, gate in cuentas.items():
        assert gate["cuenta"] == cuenta
        assert {"consumo_hoy_pct", "umbral_pct", "aceptados_hoy", "pausado_por_pct"} <= set(gate)
        assert gate["consumo_hoy_pct"] is None
        assert gate["pausado_por_pct"] is False
        assert gate["aceptados_hoy"] == 0


def test_gate_diario_aceptar_sube_umbral_de_la_cuenta_admin(entorno):
    """Aceptar +10% por cuenta sube el umbral del dia de ESA cuenta (no de la otra)."""
    r = _cli_como("admin").post("/api/actividad/cola/gate-diario/aceptar?cuenta=b", headers=_ORIGIN)
    assert r.status_code == 200
    body = r.json()
    assert body["cuenta"] == "b"
    assert body["aceptados_hoy"] == 1
    # Umbral base ~14,3 + 10 = 24,3 (redondeado a 1 decimal).
    assert body["umbral_pct"] == round(100.0 / 7.0 + 10.0, 1)
    # La otra cuenta (A) sigue en la base: el aceptar fue solo de B.
    cuentas = _cli_token().get("/api/actividad/cola").json()["presupuesto"]["gate_diario_cuentas"]
    assert cuentas["a"]["aceptados_hoy"] == 0
    assert cuentas["b"]["aceptados_hoy"] == 1


def test_gate_diario_aceptar_cuenta_invalida_es_400(entorno):
    """Sin `cuenta` valida el endpoint responde 400 (no muta nada)."""
    assert (
        _cli_como("admin")
        .post("/api/actividad/cola/gate-diario/aceptar", headers=_ORIGIN)
        .status_code
        == 400
    )
    assert (
        _cli_como("admin")
        .post("/api/actividad/cola/gate-diario/aceptar?cuenta=z", headers=_ORIGIN)
        .status_code
        == 400
    )


def test_gate_diario_aceptar_requiere_admin(entorno):
    assert (
        _cli_como("editor")
        .post("/api/actividad/cola/gate-diario/aceptar?cuenta=a", headers=_ORIGIN)
        .status_code
        == 403
    )
    assert (
        _cli_token()
        .post("/api/actividad/cola/gate-diario/aceptar?cuenta=a", headers=_ORIGIN)
        .status_code
        == 403
    )
    # Ningun aceptar caló: las cuentas siguen en la base.
    cuentas = _cli_token().get("/api/actividad/cola").json()["presupuesto"]["gate_diario_cuentas"]
    assert all(g["aceptados_hoy"] == 0 for g in cuentas.values())


def test_lanzar_dos_niveles_manual_y_automatico(entorno, monkeypatch):
    """Gestor de prioridad (`dominio.generar.lanzar`): SOLO dos niveles. Lo lanza la maquina
    (tipo de fondo: autogen/pipeline) -> AUTOMATICO; lo lanza una persona (tipo que no es de
    fondo como copy, o `manual=True`) -> MANUAL. Manual gana. Nada mas.

    Se captura el SPEC en el seam de encolado (`encolar_job_claude`): en tests el worker
    in-proceso correría el job al instante y la fila no quedaría observable en la cola.
    """
    from keni_consola.dominio import generar as dom_generar

    specs: dict[str, dict] = {}

    def captura(gen_id, *, prompt, cwd, procesar, dir_temporal=None, spec=None):
        specs[gen_id] = spec or {}

    monkeypatch.setattr(dom_generar.generaciones, "encolar_job_claude", captura)
    spec_proc = jobspec.construir_prompt_lib()
    comunes = dict(
        titulo="t", marca=_MARCA, prompt="p",
        procesar=jobspec.reconstruir_procesar({"procesar": spec_proc}),
        procesar_spec=spec_proc,
    )
    automatico = dom_generar.lanzar(tipo="autogen", clave_idem="k1", **comunes)
    a_mano = dom_generar.lanzar(tipo="autogen", manual=True, clave_idem="k2", **comunes)
    copy = dom_generar.lanzar(tipo="copy", clave_idem="k3", **comunes)
    assert jobspec.prioridad(specs[automatico["id"]]) == jobspec.PRIORIDAD_AUTOMATICO
    assert jobspec.prioridad(specs[a_mano["id"]]) == jobspec.PRIORIDAD_MANUAL
    assert jobspec.prioridad(specs[copy["id"]]) == jobspec.PRIORIDAD_MANUAL


def test_priorizar_adelanta_job_pendiente_admin(entorno):
    """Priorizar sube un job AUTOMATICO que espera al nivel MANUAL: el worker lo clava antes
    que el resto de lo automatico pendiente. Solo dos niveles (gestor de prioridad), nada mas."""
    def _encolar_auto(etiqueta: str) -> str:
        gen = generaciones.crear({"tipo": "pipeline", "marca": _MARCA, "etiqueta": etiqueta})
        cola.encolar(gen["id"], jobspec.construir(
            prompt="p", procesar=jobspec.construir_prompt_lib(),
            prioridad=jobspec.PRIORIDAD_AUTOMATICO,
        ))
        return gen["id"]

    primero = _encolar_auto("Automatico viejo")
    segundo = _encolar_auto("Automatico esperando")
    r = _cli_como("admin").post(
        "/api/actividad/cola/priorizar", json={"gen_id": segundo}, headers=_ORIGIN
    )
    assert r.status_code == 200 and r.json()["priorizado"] is True
    # El priorizado sube a MANUAL: el siguiente claim se lo lleva, no al primero (FIFO roto).
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
