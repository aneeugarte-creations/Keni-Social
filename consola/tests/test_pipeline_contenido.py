"""Tests del pipeline de contenido CI→CD→QA (ADITIVO, gateado por `KENI_PIPELINE`).

Todo OFFLINE: ni red (og:image mockeada), ni `claude` (`lanzar_copy` mockeado), ni feeds
reales (la lectura de items se parchea con items canned). Cubre:
  (a) gateado OFF por defecto -> el barrido NO produce nada;
  (b) con el flag, selecciona <= cap por marca, llama a `lanzar_copy` con la marca/imagen
      correctas y marca el item usado (dedup -> un segundo barrido lo salta);
  (c) se emiten entradas de actividad de etapa CI y CD;
  (d) la pasada QA registra una etapa QA y persiste el veredicto de un borrador completado.

Las funciones PURAS (`items_ingeribles`, `qa_lexico`, `_extraer_og_image`) se prueban sin DB.
Los flujos con persistencia usan la fixture `entorno` (Postgres de pruebas; se salta si no hay).
"""

from __future__ import annotations

from keni_consola import config, generaciones, redes, repos
from keni_consola import pipeline_contenido as pc

_URL_OK = "https://ejemplo.test/feed.xml"


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _item(**kw):
    base = {
        "titulo": "Un tema fresco",
        "resumen": "Por qué importa",
        "enlace": "https://ejemplo.test/nota",
        "fecha": "",
        "clave": "k1",
        "imagen": "",
    }
    base.update(kw)
    return base


def _mock_lanzar_copy(monkeypatch):
    """Parchea `gen_dom.lanzar_copy` para capturar las llamadas (sin `claude`)."""
    llamadas: list[dict] = []

    def fake(**kw):
        llamadas.append(kw)
        return {"id": f"gen-{len(llamadas)}"}

    monkeypatch.setattr(pc.gen_dom, "lanzar_copy", fake)
    return llamadas


def _mock_feed(monkeypatch, items):
    """Parchea la lectura de items del feed para devolver `items` canned (sin red)."""
    monkeypatch.setattr(pc, "_leer_items_fuente", lambda fuente: list(items))


def _mock_og_image(monkeypatch, url=""):
    """Parchea la resolución de og:image (sin red)."""
    monkeypatch.setattr(pc, "_FETCH_OG_IMAGE", lambda enlace: url)


# --------------------------------------------------------------------------- #
# Funciones PURAS (sin DB)                                                     #
# --------------------------------------------------------------------------- #


def test_items_ingeribles_filtra_usados_y_capa():
    items = [_item(clave="a"), _item(clave="b"), _item(clave="c")]
    elegidos = pc.items_ingeribles(items, vistas={"b"}, maximo=5)
    assert [i["clave"] for i in elegidos] == ["a", "c"]


def test_items_ingeribles_respeta_cap():
    items = [_item(clave=f"k{i}") for i in range(5)]
    elegidos = pc.items_ingeribles(items, vistas=set(), maximo=2)
    assert [i["clave"] for i in elegidos] == ["k0", "k1"]


def test_items_ingeribles_omite_sin_clave_o_sin_titulo():
    items = [_item(clave=""), _item(titulo="  "), _item(clave="ok")]
    elegidos = pc.items_ingeribles(items, vistas=set(), maximo=5)
    assert [i["clave"] for i in elegidos] == ["ok"]


def test_extraer_og_image():
    html = '<head><meta property="og:image" content="https://x.test/foto.jpg"></head>'
    assert pc._extraer_og_image(html) == "https://x.test/foto.jpg"


def test_extraer_og_image_ausente():
    assert pc._extraer_og_image("<head></head>") == ""
    assert pc._extraer_og_image("") == ""


def test_qa_lexico_listo_sin_observaciones():
    r = pc.qa_lexico({"red": "x", "contenido": "Copy corto y válido."})
    assert r["verdicto"] == "listo"
    assert r["observaciones"] == []


def test_qa_lexico_copy_vacio():
    r = pc.qa_lexico({"red": "x", "contenido": "   "})
    assert r["verdicto"] == "revisar"
    assert any("vacío" in o for o in r["observaciones"])


def test_qa_lexico_supera_limite_de_red():
    limite = next(red.limite for red in redes.REDES if red.id == "x")
    assert limite is not None
    r = pc.qa_lexico({"red": "x", "contenido": "a" * (limite + 1)})
    assert r["verdicto"] == "revisar"
    assert any("límite" in o for o in r["observaciones"])


# --------------------------------------------------------------------------- #
# (a) GATEADO OFF por defecto -> el barrido NO produce nada                    #
# --------------------------------------------------------------------------- #


def test_gateado_off_no_arranca_el_daemon():
    """Sin `KENI_PIPELINE`, el flag está OFF (def): el `bucle_gateado` no barrería."""
    assert config.pipeline_activo() is False


def test_iniciar_pipeline_no_genera_sin_flag(entorno, monkeypatch):
    """El daemon arranca pero, gateado OFF, NO llama a `lanzar_copy` (el barrido no corre).

    Aislamos el riesgo a nivel de daemon: con el flag ausente el hilo no debe producir nada
    aunque haya un feed activo con items frescos.
    """
    llamadas = _mock_lanzar_copy(monkeypatch)
    repos.crear_fuente_rss("Diario", _URL_OK, marca="unotv")
    _mock_feed(monkeypatch, [_item()])
    _mock_og_image(monkeypatch, "")

    # Un solo tick del bucle gateado: con el flag OFF, `ejecutar_barrido` no debe correr.
    from keni_consola import daemon_util

    daemon_util.bucle_gateado(
        activo_fn=config.pipeline_activo,
        intervalo_seg_fn=lambda: 3600.0,
        sweep_fn=pc.ejecutar_barrido,
        log=pc._log,
        _max_vueltas=1,
    )
    assert llamadas == []
    # Tampoco se sembró ninguna actividad de etapa.
    assert _etapas_de_actividad() == []


# --------------------------------------------------------------------------- #
# (b)+(c) CON el flag: ingesta + creación, dedup, y etapas CI/CD en actividad  #
# --------------------------------------------------------------------------- #


def _etapas_de_actividad():
    """Etiquetas de las generaciones-marcador del pipeline (tipo 'pipeline'), recientes 1º."""
    return [
        g["etiqueta"]
        for g in generaciones.listar(limite=None)
        if g["tipo"] == pc.TIPO_ACTIVIDAD
    ]


def test_barrido_con_flag_ingesta_genera_y_dedup(entorno, monkeypatch):
    monkeypatch.setenv("KENI_PIPELINE", "1")
    monkeypatch.setenv("KENI_PIPELINE_MAX", "2")
    llamadas = _mock_lanzar_copy(monkeypatch)
    # Sin usuarios -> autor anónimo (no rompe); evitamos depender de bootstrap.
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)

    fuente = repos.crear_fuente_rss("Diario", _URL_OK, marca="unotv")
    items = [_item(clave="a", titulo="Tema A"), _item(clave="b", titulo="Tema B"),
             _item(clave="c", titulo="Tema C")]
    _mock_feed(monkeypatch, items)
    _mock_og_image(monkeypatch, "")

    resumen = pc.ejecutar_barrido()

    # (b) selecciona <= cap (2) por marca y llama a lanzar_copy con la marca correcta.
    # Solo `unotv` tiene feed; las demás marcas no producen llamadas.
    assert len(llamadas) == 2
    assert all(c["marca"] == "unotv" for c in llamadas)
    assert {c["titulo"] for c in llamadas} == {"Tema A", "Tema B"}
    assert len(resumen["lanzados"]) == 2

    # dedup: los items A y B quedaron marcados usados.
    vistas = repos.claves_vistas(fuente["id"])
    assert {"a", "b"} <= vistas

    # (c) hay una etapa CI y al menos dos CD en la actividad.
    etapas = _etapas_de_actividad()
    assert any(e.startswith("CI · ") for e in etapas)
    assert sum(1 for e in etapas if e.startswith("CD · ")) == 2

    # dedup efectiva: un SEGUNDO barrido salta A/B (ya usados) y procesa el restante (C).
    llamadas.clear()
    pc.ejecutar_barrido()
    assert [c["titulo"] for c in llamadas] == ["Tema C"]


def test_barrido_marca_propia_pasa_imagen_fuente(entorno, monkeypatch):
    """Feed de marca PROPIA: la og:image resuelta viaja como `imagen_fuente` a `lanzar_copy`."""
    monkeypatch.setenv("KENI_PIPELINE", "1")
    monkeypatch.setenv("KENI_PIPELINE_MAX", "1")
    llamadas = _mock_lanzar_copy(monkeypatch)
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)

    repos.crear_fuente_rss("Casa", _URL_OK, marca="unotv", propia=True)
    _mock_feed(monkeypatch, [_item(clave="p1", titulo="Nota propia")])
    _mock_og_image(monkeypatch, "https://casa.test/foto.jpg")

    pc.ejecutar_barrido()

    assert len(llamadas) == 1
    assert llamadas[0]["imagen_fuente"] == "https://casa.test/foto.jpg"
    assert llamadas[0]["tipo_contenido"] == "fuente"


def test_barrido_no_propia_sin_imagen(entorno, monkeypatch):
    """Feed NO propio: no se resuelve foto; `imagen_fuente` queda vacío (placa de marca)."""
    monkeypatch.setenv("KENI_PIPELINE", "1")
    monkeypatch.setenv("KENI_PIPELINE_MAX", "1")
    llamadas = _mock_lanzar_copy(monkeypatch)
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)

    repos.crear_fuente_rss("Externo", _URL_OK, marca="unotv", propia=False)
    _mock_feed(monkeypatch, [_item(clave="e1")])
    # Si por error se llamara, devolvería una URL; verificamos que NO se use en no-propia.
    _mock_og_image(monkeypatch, "https://externo.test/foto.jpg")

    pc.ejecutar_barrido()

    assert len(llamadas) == 1
    assert llamadas[0]["imagen_fuente"] == ""
    assert llamadas[0]["tipo_contenido"] == ""


# --------------------------------------------------------------------------- #
# (d) Pasada QA: registra etapa QA y persiste el veredicto                     #
# --------------------------------------------------------------------------- #


def test_qa_valida_borrador_del_pipeline(entorno, monkeypatch):
    """Sin QA editorial disponible (fallback), un borrador del pipeline recibe veredicto léxico + etapa QA.

    El QA editorial (claude -p) se prueba aislado en `test_pipeline_qa_editorial.py`; aquí
    forzamos el FALLBACK léxico (mock de `lanzar_qa_editorial` -> None) para cubrir que la red de
    seguridad determinista sigue persistiendo un veredicto y su etapa.
    """
    monkeypatch.setattr(pc, "lanzar_qa_editorial", lambda pub, *, autor: None)
    # Borrador COMPLETADO del pipeline: lo creamos directamente (como dejaría la fase CD).
    pub = repos.crear_publicacion(
        "unotv", "x", titulo="Tema QA", contenido="Copy válido y corto.",
        estado="borrador", origen=pc.ORIGEN_PIPELINE,
    )
    assert (pub.get("veredicto") or "") == ""

    validados = pc.ejecutar_qa()

    assert [v["id"] for v in validados] == [pub["id"]]
    assert validados[0]["verdicto"] == "listo"

    # El veredicto quedó PERSISTIDO en la pieza.
    refrescada = repos.obtener_publicacion(pub["id"])
    assert refrescada["veredicto"] == "listo"

    # Se registró una etapa QA en la actividad.
    assert any(e.startswith("QA · ") for e in _etapas_de_actividad())


def test_qa_ignora_borradores_de_otro_origen(entorno, monkeypatch):
    """La QA del pipeline NO toca borradores ajenos (otro origen)."""
    monkeypatch.setattr(pc, "lanzar_qa_editorial", lambda pub, *, autor: None)
    pub = repos.crear_publicacion(
        "unotv", "x", titulo="Manual", contenido="Copy manual.",
        estado="borrador", origen="equipo",
    )
    validados = pc.ejecutar_qa()
    assert validados == []
    refrescada = repos.obtener_publicacion(pub["id"])
    assert (refrescada["veredicto"] or "") == ""


def test_qa_no_revalida_con_veredicto_existente(entorno, monkeypatch):
    """Un borrador del pipeline que YA tiene veredicto no se vuelve a procesar (idempotente)."""
    repos.crear_publicacion(
        "unotv", "x", titulo="Ya QA", contenido="Copy.", estado="borrador",
        origen=pc.ORIGEN_PIPELINE, veredicto="listo",
    )
    assert pc.ejecutar_qa() == []
