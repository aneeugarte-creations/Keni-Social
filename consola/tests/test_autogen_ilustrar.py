"""Tests de la auto-generacion de ARTE (sin DB ni red).

`topics_sin_arte` decide que temas del tablero se auto-ilustran. Es la logica de riesgo
(filtros + dedup + cap); se prueba en aislamiento con dicts en memoria. `prompt_arte` y
`lanzar_para_topic` se cubren con el generador de imagen y los repos PARCHEADOS, asi que
ningun test toca la red ni la base de datos.
"""

from __future__ import annotations

from keni_consola import autogen_ilustrar as aa


def _item(**kw):
    base = {
        "id": "c1",
        "clase": "contenido",
        "estado": "pendiente",
        "marca": "claro-sports",
        "titulo": "Un tema",
        "descripcion": "",
    }
    base.update(kw)
    return base


def _plat(**kw):
    base = {"id": "p1", "copy": "Texto listo", "imagen": ""}
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# Seleccion pura: topics_sin_arte                                              #
# --------------------------------------------------------------------------- #


def test_selecciona_tema_con_copy_sin_imagen():
    elegidos = aa.topics_sin_arte(
        [_item()],
        plataformas_por_item={"c1": [_plat()]},
        ya_procesados=set(),
        maximo=3,
    )
    assert [e["id"] for e in elegidos] == ["c1"]


def test_omite_si_no_hay_copy():
    elegidos = aa.topics_sin_arte(
        [_item()],
        plataformas_por_item={"c1": [_plat(copy="")]},
        ya_procesados=set(),
        maximo=3,
    )
    assert elegidos == []


def test_omite_si_ya_tiene_imagen():
    elegidos = aa.topics_sin_arte(
        [_item()],
        plataformas_por_item={"c1": [_plat(imagen="foto.png")]},
        ya_procesados=set(),
        maximo=3,
    )
    assert elegidos == []


def test_omite_si_no_tiene_plataformas():
    elegidos = aa.topics_sin_arte(
        [_item()],
        plataformas_por_item={},
        ya_procesados=set(),
        maximo=3,
    )
    assert elegidos == []


def test_omite_clase_tarea():
    elegidos = aa.topics_sin_arte(
        [_item(clase="tarea")],
        plataformas_por_item={"c1": [_plat()]},
        ya_procesados=set(),
        maximo=3,
    )
    assert elegidos == []


def test_omite_estado_cerrado():
    elegidos = aa.topics_sin_arte(
        [_item(estado="hecha")],
        plataformas_por_item={"c1": [_plat()]},
        ya_procesados=set(),
        maximo=3,
    )
    assert elegidos == []


def test_omite_titulo_vacio():
    elegidos = aa.topics_sin_arte(
        [_item(titulo="   ")],
        plataformas_por_item={"c1": [_plat()]},
        ya_procesados=set(),
        maximo=3,
    )
    assert elegidos == []


def test_dedup_por_id_ya_procesado():
    elegidos = aa.topics_sin_arte(
        [_item(id="c1")],
        plataformas_por_item={"c1": [_plat()]},
        ya_procesados={"c1"},
        maximo=3,
    )
    assert elegidos == []


def test_acepta_si_alguna_plataforma_cumple():
    # Una plataforma ya ilustrada y otra con copy sin imagen: el tema entra.
    elegidos = aa.topics_sin_arte(
        [_item()],
        plataformas_por_item={
            "c1": [_plat(id="p1", imagen="ya.png"), _plat(id="p2", copy="Otro", imagen="")]
        },
        ya_procesados=set(),
        maximo=3,
    )
    assert [e["id"] for e in elegidos] == ["c1"]


def test_respeta_cap_maximo_y_orden():
    items = [_item(id=f"c{i}") for i in range(5)]
    plats = {f"c{i}": [_plat(id=f"p{i}")] for i in range(5)}
    elegidos = aa.topics_sin_arte(
        items, plataformas_por_item=plats, ya_procesados=set(), maximo=2
    )
    assert [e["id"] for e in elegidos] == ["c0", "c1"]


def test_score_ordena_que_se_ilustra_primero_antes_del_cap():
    """Flujo C: el SCORE ordena el arte (que se ilustra PRIMERO). Con cap=1 entra el de mayor
    score (compromiso), no el primero en orden de entrada."""
    from datetime import date

    items = [_item(id="normal", prioridad="baja"), _item(id="must", prioridad="baja")]
    plats = {"normal": [_plat(id="pn")], "must": [_plat(id="pm")]}
    elegidos = aa.topics_sin_arte(
        items,
        plataformas_por_item=plats,
        ya_procesados=set(),
        maximo=1,
        etiquetas_por_item={"must": ["compromiso"]},
        hoy=date(2026, 6, 1),
    )
    assert [e["id"] for e in elegidos] == ["must"]


def test_orden_por_defecto_conserva_entrada():
    """Sin `etiquetas_por_item`/`hoy`, conserva el orden del tablero."""
    items = [_item(id="a"), _item(id="b")]
    plats = {"a": [_plat(id="pa")], "b": [_plat(id="pb")]}
    elegidos = aa.topics_sin_arte(
        items, plataformas_por_item=plats, ya_procesados=set(), maximo=3
    )
    assert [e["id"] for e in elegidos] == ["a", "b"]


# --------------------------------------------------------------------------- #
# prompt_arte                                                                  #
# --------------------------------------------------------------------------- #


def test_prompt_es_el_tema_titulo_y_descripcion():
    # `prompt_arte` es el mensaje de USUARIO (el tema): título + descripción, sin la directiva
    # (esa va en el mensaje de SISTEMA `prompt/ilustrar`, que añade `media.generar_imagen`).
    prompt = aa.prompt_arte(_item(titulo="Final de copa", descripcion="Juega Mexico"))
    assert prompt == "Final de copa. Juega Mexico"


def test_prompt_solo_titulo_si_no_hay_descripcion():
    assert aa.prompt_arte(_item(titulo="Final de copa", descripcion="")) == "Final de copa"


def test_prompt_vacio_si_no_hay_titulo():
    assert aa.prompt_arte(_item(titulo="", descripcion="")) == ""


def test_registrar_arte_sin_contenido_es_noop():
    # Sin `publicacion_id` no hay pipeline al que colgar: no registra nada ni lanza (lo usa el
    # botón manual cuando la imagen no pertenece a una pieza).
    aa.registrar_arte(publicacion_id="", marca="unotv", titulo="T", prompt="p", imagen="x.png")


# --------------------------------------------------------------------------- #
# lanzar_para_topic: encolado. Repos/generar PARCHEADOS #
# --------------------------------------------------------------------------- #


def test_lanzar_para_topic_encola_job(monkeypatch):
    """`lanzar_para_topic` ya NO genera en línea: SELECCIONA la plataforma y ENCOLA un job de arte
    vía `dominio.generar.lanzar_arte`, devolviendo el registro de generación encolado."""
    from keni_consola.dominio import generar as dom_generar

    monkeypatch.setattr(aa.media, "proveedor_configurado", lambda: True)
    monkeypatch.setattr(
        aa.repos, "listar_piezas_fila", lambda cid: [_plat(id="p1")]
    )
    llamadas: list[dict] = []

    def _fake_lanzar_arte(**kw):
        llamadas.append(kw)
        return {"id": "gen-arte-1", "tipo": "autogen"}

    monkeypatch.setattr(dom_generar, "lanzar_arte", _fake_lanzar_arte)

    res = aa.lanzar_para_topic(_item(titulo="Final de copa", descripcion="Juega Mexico"))

    assert res == {"id": "gen-arte-1", "tipo": "autogen"}
    assert len(llamadas) == 1
    assert llamadas[0]["publicacion_id"] == "c1"
    assert llamadas[0]["pieza_id"] == "p1"
    assert llamadas[0]["marca"] == "claro-sports"
    assert llamadas[0]["prompt"] == "Final de copa. Juega Mexico"  # tema = título + descripción


def test_lanzar_para_topic_sin_proveedor_no_encola(monkeypatch):
    from keni_consola.dominio import generar as dom_generar

    monkeypatch.setattr(aa.media, "proveedor_configurado", lambda: False)
    llamado: list = []
    monkeypatch.setattr(dom_generar, "lanzar_arte", lambda **kw: llamado.append(kw))
    res = aa.lanzar_para_topic(_item())
    assert res is None
    assert llamado == []


def test_lanzar_para_topic_sin_plataforma_candidata_no_encola(monkeypatch):
    from keni_consola.dominio import generar as dom_generar

    monkeypatch.setattr(aa.media, "proveedor_configurado", lambda: True)
    monkeypatch.setattr(
        aa.repos, "listar_piezas_fila", lambda cid: [_plat(imagen="ya.png")]
    )
    llamado: list = []
    monkeypatch.setattr(dom_generar, "lanzar_arte", lambda **kw: llamado.append(kw))
    res = aa.lanzar_para_topic(_item())
    assert res is None
    assert llamado == []


# --------------------------------------------------------------------------- #
# ejecutar_arte_job: EJECUTOR del worker (genera + adjunta + registra)         #
# --------------------------------------------------------------------------- #


def _spec_arte(**kw):
    base = {
        "kind": "imagen",
        "publicacion_id": "c1",
        "pieza_id": "p1",
        "marca": "claro-sports",
        "titulo": "Final de copa",
        "prompt": "Final de copa. Juega Mexico",
    }
    base.update(kw)
    return base


def test_ejecutar_arte_job_genera_adjunta_y_completa(monkeypatch):
    """El ejecutor genera la imagen, la adjunta a la pieza (`falta_imagen=False`), etiqueta el tema
    y marca la generación `completado` con el resultado."""
    monkeypatch.setattr(aa.media, "proveedor_configurado", lambda: True)
    monkeypatch.setattr(aa.media, "generar_imagen", lambda prompt: b"PNGBYTES")
    monkeypatch.setattr(aa.media, "guardar_bytes", lambda datos, ext="png": "arte.png")
    monkeypatch.setattr(aa.repos, "listar_piezas_fila", lambda cid: [_plat(id="p1")])
    cambios = {}
    monkeypatch.setattr(
        aa.repos, "actualizar_pieza_fila",
        lambda pid, campos: cambios.update({"pid": pid, "campos": campos}) or {"id": pid},
    )
    monkeypatch.setattr(aa.repos, "listar_etiquetas", lambda: [])
    monkeypatch.setattr(aa.repos, "crear_etiqueta", lambda *, nombre: {"id": "et1", "nombre": nombre})
    asignadas: list = []
    monkeypatch.setattr(aa.repos, "asignar_etiqueta", lambda cid, eid: asignadas.append((cid, eid)))
    monkeypatch.setattr(aa, "registrar_arte", lambda **kw: None)
    estados: list[dict] = []
    monkeypatch.setattr(aa.generaciones, "actualizar", lambda gid, campos: estados.append(campos))

    aa.ejecutar_arte_job("g1", _spec_arte())

    assert cambios["pid"] == "p1"
    # El arte IA declara `imagen_origen='ia'` y la normalización limpia cualquier metadata de
    # licencia STALE (de una foto de stock previa), dejando la pieza publicable en el eje de licencia.
    assert cambios["campos"] == {
        "imagen": "arte.png",
        "imagen_origen": "ia",
        "imagen_proveedor": "",
        "imagen_autor": "",
        "imagen_licencia": "",
        "imagen_credito_url": "",
        "imagen_autorizada": False,
        "falta_imagen": False,
    }
    assert asignadas == [("c1", "et1")]
    assert estados[-1]["estado"] == aa.generaciones.ESTADO_COMPLETADO
    assert estados[-1]["resultado"] == {
        "publicacion_id": "c1", "pieza_id": "p1", "imagen": "arte.png",
    }


def test_ejecutar_arte_job_registra_actividad(monkeypatch):
    """El arte deja constancia: una generación `tipo='pipeline'` con su PROMPT + la etapa ILUSTRAR
    correlacionada al tema (gen_id), visible en Actividad IA y el detalle del pipeline."""
    monkeypatch.setattr(aa.media, "proveedor_configurado", lambda: True)
    monkeypatch.setattr(aa.media, "generar_imagen", lambda prompt: b"PNGBYTES")
    monkeypatch.setattr(aa.media, "guardar_bytes", lambda datos, ext="png": "arte.png")
    monkeypatch.setattr(aa.repos, "listar_piezas_fila", lambda cid: [_plat(id="p1")])
    monkeypatch.setattr(aa.repos, "actualizar_pieza_fila", lambda pid, campos: {"id": pid})
    monkeypatch.setattr(aa.repos, "listar_etiquetas", lambda: [])
    monkeypatch.setattr(aa.repos, "crear_etiqueta", lambda *, nombre: {"id": "et1", "nombre": nombre})
    monkeypatch.setattr(aa.repos, "asignar_etiqueta", lambda cid, eid: None)
    monkeypatch.setattr(aa.generaciones, "actualizar", lambda gid, campos: None)
    gens: list[dict] = []
    monkeypatch.setattr(aa.generaciones, "crear", lambda d: gens.append(d) or {"id": "g1"})
    import keni_consola.pipeline_contenido as pc
    etapas: list[tuple] = []
    monkeypatch.setattr(pc, "registrar_etapa", lambda *a, **k: etapas.append((a, k)))

    aa.ejecutar_arte_job("g1", _spec_arte())

    assert len(gens) == 1
    assert gens[0]["tipo"] == "pipeline"  # arte de la máquina: tipo pipeline
    assert gens[0]["publicacion_id"] == "c1"
    assert gens[0]["prompt"]  # el prompt REAL del arte
    assert len(etapas) == 1
    assert etapas[0][0][0] == "ILUSTRAR"  # registrar_etapa(ETAPA_ILUSTRAR, ...)
    assert etapas[0][1]["gen_id"] == "g1"


def test_ejecutar_arte_job_sin_candidata_no_gasta_proveedor(monkeypatch):
    """IDEMPOTENCIA ante re-claim: si la pieza ya no tiene plataforma con copy sin imagen (un
    intento previo la ilustró, o un humano), COMPLETA sin volver a llamar al proveedor."""
    monkeypatch.setattr(aa.media, "proveedor_configurado", lambda: True)
    llamado: list = []
    monkeypatch.setattr(aa.media, "generar_imagen", lambda prompt: llamado.append(prompt) or b"x")
    monkeypatch.setattr(aa.repos, "listar_piezas_fila", lambda cid: [_plat(imagen="ya.png")])
    estados: list[dict] = []
    monkeypatch.setattr(aa.generaciones, "actualizar", lambda gid, campos: estados.append(campos))

    aa.ejecutar_arte_job("g1", _spec_arte())

    assert llamado == []  # NO se gastó el proveedor
    assert estados[-1]["estado"] == aa.generaciones.ESTADO_COMPLETADO
    assert "omitido" in estados[-1]["resultado"]


def test_ejecutar_arte_job_error_de_proveedor_marca_error(monkeypatch):
    """Un fallo del proveedor (MediaError) deja la generación en `error` con mensaje claro,
    sin etiquetar el tema (el barrido lo reintentará)."""
    monkeypatch.setattr(aa.media, "proveedor_configurado", lambda: True)

    def _explota(prompt):
        raise aa.media.MediaError("El proveedor de imagen no respondió.")

    monkeypatch.setattr(aa.media, "generar_imagen", _explota)
    monkeypatch.setattr(aa.repos, "listar_piezas_fila", lambda cid: [_plat(id="p1")])
    asignadas: list = []
    monkeypatch.setattr(aa.repos, "asignar_etiqueta", lambda cid, eid: asignadas.append((cid, eid)))
    estados: list[dict] = []
    monkeypatch.setattr(aa.generaciones, "actualizar", lambda gid, campos: estados.append(campos))

    aa.ejecutar_arte_job("g1", _spec_arte())

    assert estados[-1]["estado"] == aa.generaciones.ESTADO_ERROR
    assert "proveedor" in estados[-1]["error"].lower()
    assert asignadas == []  # NO se etiquetó: el barrido lo reintenta


# --------------------------------------------------------------------------- #
# Idempotencia del ENCOLADO: re-encolar el mismo arte NO duplica (cola + store) #
# --------------------------------------------------------------------------- #


def test_lanzar_arte_idempotente_no_duplica(entorno):
    """Re-encolar el MISMO arte (mismo tema+marca+prompt) mientras el primero sigue EN PROCESO
    devuelve el MISMO registro y NO encola un segundo job de imagen: ni doble gasto del proveedor
    ni doble subida. Al COMPLETAR, un re-lanzamiento legítimo vuelve a correr (registro nuevo)."""
    from keni_consola import cola, generaciones, repos
    from keni_consola.dominio import generar, jobspec

    args = dict(publicacion_id="c1", marca="claro-sports", titulo="Final", prompt="ilustra la final")
    g1 = generar.lanzar_arte(**args)
    g2 = generar.lanzar_arte(**args)  # re-encolado en proceso (otro barrido / encadenado / limpiador)

    assert g1["id"] == g2["id"]  # comparte el run en proceso (clave de idempotencia estable)
    assert repos.contar_jobs_activos() == 1  # UN solo job para ese arte

    job = cola.reclamar("w")
    assert job is not None and job["gen_id"] == g1["id"]
    assert jobspec.es_kind_proceso(job["spec"]) is True
    assert job["spec"]["kind"] == jobspec.PROC_IMAGEN
    assert job["spec"]["publicacion_id"] == "c1"
    assert cola.reclamar("w") is None  # NO hay un segundo job encolado

    # Al terminar (registro terminal), un re-lanzamiento legítimo (regenerar) vuelve a correr.
    cola.terminar(job["id"])
    generaciones.actualizar(g1["id"], {
        "estado": generaciones.ESTADO_COMPLETADO, "fecha_fin": generaciones.ahora_iso(),
    })
    g3 = generar.lanzar_arte(**args)
    assert g3["id"] != g1["id"]  # tras completar, la clave se recicla: nuevo run


def test_lanzar_arte_distinto_tema_encola_runs_separados(entorno):
    """Dos artes de temas distintos (claves distintas) corren cada uno su propio job."""
    from keni_consola import repos
    from keni_consola.dominio import generar

    g1 = generar.lanzar_arte(publicacion_id="c1", marca="claro-sports", titulo="A", prompt="tema a")
    g2 = generar.lanzar_arte(publicacion_id="c2", marca="claro-sports", titulo="B", prompt="tema b")
    assert g1["id"] != g2["id"]
    assert repos.contar_jobs_activos() == 2
