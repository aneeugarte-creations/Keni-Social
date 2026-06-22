"""Tests del pipeline de contenido ADMITIR→VERIFICAR(fuente)→REDACTAR (ADITIVO, gateado por `KENI_PIPELINE_REDACTAR`).

REDISEÑO QPC: Verificar se movió a ANTES del copy y por PIEZA (tema/fuente). El barrido es ahora
ADMITIR (crea temas SIN copy) → VERIFICAR de la FUENTE (verificación permisiva por tema) → REDACTAR (copy SOLO de los
temas `no_verificado`). Todo OFFLINE: ni red (og:image mockeada), ni `claude` (`lanzar_copy` y
la generación de Verificar mockeados), ni feeds reales (items canned). Cubre:
  (a) gateado OFF por defecto -> el barrido NO produce nada;
  (b) con el flag, ADMITIR selecciona <= cap por marca, crea temas SIN copy y marca el item usado;
  (c) se emiten entradas de actividad de etapa ADMITIR (y, al lanzar, VERIFICAR/REDACTAR);
  (d) una fuente `problema` NO genera copy y marca el tema ❗; una `no_verificado` SÍ genera
      copy y las piezas heredan el aviso ⚠️;
  (e) el cap por barrido (VERIFICAR y REDACTAR) se respeta.

Las funciones PURAS (`verificacion_lexica`, `_extraer_og_image`) se prueban sin DB.
Los flujos con persistencia usan la fixture `entorno` (Postgres de pruebas; se salta si no hay).
"""

from __future__ import annotations

import json

from keni_consola import config, generaciones, redes, repos
from keni_consola import pipeline_contenido as pc

from .conftest import _cliente, lanzador_generacion_completa

_URL_OK = "https://ejemplo.test/feed.xml"

# Salidas canned de Verificar la fuente (semáforo + bloque json estructurado).
_VERIFICACION_OK = (
    "🟢 Fuente apta.\n\n"
    '```json\n{"veredicto": "🟢", "resumen": "Sin problemas de peso", "hallazgos": []}\n```\n'
)
_VERIFICACION_RECHAZADO = (
    "🔴 Problema de peso.\n\n"
    '```json\n{"veredicto": "🔴", "resumen": "Dato falso evidente", '
    '"hallazgos": [{"tipo": "dato", "gravedad": "error", "fragmento": "x", '
    '"explicacion": "es falso", "sugerencia": "no publicar"}]}\n```\n'
)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _mock_lanzar_copy(monkeypatch):
    """Parchea `gen_dom.lanzar_copy` para capturar las llamadas (sin `claude`)."""
    llamadas: list[dict] = []

    def fake(**kw):
        llamadas.append(kw)
        return {"id": f"gen-{len(llamadas)}"}

    monkeypatch.setattr(pc.gen_dom, "lanzar_copy", fake)
    return llamadas


def _mock_og_image(monkeypatch, url=""):
    """Parchea la resolución de og:image (sin red)."""
    monkeypatch.setattr(pc, "_FETCH_OG_IMAGE", lambda enlace: url)


def _envejecer_intento(tema_id, campo):
    """Retrasa el timestamp del último intento de la etapa (saca el tema del backoff)."""
    pend = json.loads(repos.obtener_publicacion(tema_id)["copy_pendiente"])
    pend[f"{campo}_ts"] = "2020-01-01T00:00:00"
    repos.actualizar_publicacion(tema_id, {"copy_pendiente": json.dumps(pend)})


def _temas_sin_verdicto(marca=None):
    """Temas del pipeline sin verificación de verificación (pendientes). Local del test: el barrido F3
    selecciona por CLUSTER, así que el filtro por-tema ya no vive en producción."""
    return [t for t in pc.temas_pipeline(marca) if not (t.get("verificacion_fuente") or "").strip()]


def _inicializar_cluster(
    cid, *, marca="unotv", titulo="Historia X", score=0.5, estado="nuevo",
    resumen="México: el gobierno informa de seguridad en la CDMX", ultimo_visto=None,
    verificacion="corroborada", n_fuentes=2, categoria="mx", breaking=0,
    verificacion_fuente="", primera_fuente="",
    idioma="", traducido=0, titulo_es="", resumen_es="",
    tema_macro="", subtema="",
):
    """Siembra un cluster del pool (Ola B) para los tests de promoción ADMITIR→tema.

    Por defecto el cluster SUPERA el umbral de producción automática (`noticias_umbral`):
    FRESCO (`ultimo_visto` ≈ ahora), corroborado y con encaje de marca unotv por el resumen.
    Los tests del propio umbral pasan valores que lo incumplen a propósito.

    `verificacion_fuente`: estado de la verificación del cluster. Por defecto "" (sin verificar, el estado del que
    parte Verificar en investigación). La ADMISIÓN solo promueve las VERIFICADAS, así que los tests
    que llaman DIRECTO a la promoción (sin pasar por la fase Verificar) deben inicializar el cluster ya
    verificado (`VERIFICACION_VERIFICADO`) — es el camino real, no el atajo sin filtro.

    `primera_fuente`: id de la fuente PRIMARIA de la historia (el canal Portal mira si esa fuente
    es `propia`). Por defecto "" (sin fuente -> no es propia).
    """
    from datetime import UTC, datetime

    repos.upsert_noticia_cluster({
        "id": cid, "titulo": titulo, "resumen": resumen, "marca": marca,
        "categoria": categoria, "geo": "MX", "clave": f"t:{cid}", "n_items": 1,
        "n_fuentes": n_fuentes, "idiomas": ["es"], "senal": 100, "score": score,
        "breaking": breaking, "primer_visto": "2026-06-01T00:00:00+00:00",
        "ultimo_visto": ultimo_visto
        or datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds"),
        "estado": estado, "verificacion": verificacion, "primera_fuente": primera_fuente,
        "idioma": idioma, "traducido": traducido, "titulo_es": titulo_es, "resumen_es": resumen_es,
        "tema_macro": tema_macro, "subtema": subtema,
    })
    if verificacion_fuente:
        repos.marcar_cluster_verificacion(cid, verificacion_fuente)
    return repos.obtener_noticia_cluster(cid)


# --------------------------------------------------------------------------- #
# Funciones PURAS (sin DB)                                                     #
# --------------------------------------------------------------------------- #


def test_extraer_og_image():
    html = '<head><meta property="og:image" content="https://x.test/foto.jpg"></head>'
    assert pc._extraer_og_image(html) == "https://x.test/foto.jpg"


def test_extraer_og_image_ausente():
    assert pc._extraer_og_image("<head></head>") == ""
    assert pc._extraer_og_image("") == ""


# --------------------------------------------------------------------------- #
# Cuerpo del artículo + limpieza del snippet RSS (enriquecer la nota)          #
# --------------------------------------------------------------------------- #


def test_limpiar_snippet_decodifica_y_quita_boilerplate():
    # Caso REAL de UnoTV: entidad sin decodificar + cola de WordPress.
    crudo = (
        "Normalistas mantienen cerrada la autopista [&#8230;] "
        "The post Normalistas bloquean la caseta appeared first on UnoTV ."
    )
    limpio = pc._limpiar_snippet(crudo)
    assert "The post" not in limpio
    assert "appeared first on" not in limpio
    assert "&#8230;" not in limpio and "[…]" not in limpio
    assert limpio.startswith("Normalistas mantienen cerrada la autopista")


def test_limpiar_snippet_vacio():
    assert pc._limpiar_snippet("") == ""


def test_extraer_texto_articulo_jsonld():
    cuerpo = "Primer párrafo del cuerpo. " * 20  # supera _ART_MIN_TEXTO
    html = (
        '<html><head><script type="application/ld+json">'
        '{"@type": "NewsArticle", "headline": "T", "articleBody": ' + json.dumps(cuerpo) + "}"
        "</script></head><body><p>ruido</p></body></html>"
    )
    texto = pc._extraer_texto_articulo(html)
    assert texto.startswith("Primer párrafo del cuerpo.")
    assert "ruido" not in texto


def test_extraer_texto_articulo_parrafos_fallback():
    parrafo = "Este es un párrafo de cuerpo con suficiente longitud para no ser cruft."
    html = (
        "<html><body><article>"
        "<p>corto</p>"  # < _ART_MIN_P_CHARS: se descarta
        f"<p>{parrafo}</p><p>{parrafo}</p><p>{parrafo}</p>"
        "</article></body></html>"
    )
    texto = pc._extraer_texto_articulo(html)
    assert parrafo in texto
    assert "corto" not in texto


def test_extraer_texto_articulo_sin_cuerpo_es_vacio():
    assert pc._extraer_texto_articulo("<html><body><p>x</p></body></html>") == ""
    assert pc._extraer_texto_articulo("") == ""


def test_nota_de_cluster_incluye_texto_de_cada_fuente():
    items = [
        {"fuente_nombre": "UnoTV", "titulo": "Bloqueo en caseta", "url": "https://uno.test/a",
         "resumen": "Normalistas cierran la autopista."},
        {"fuente_nombre": "Infobae", "titulo": "Refuerzan seguridad", "url": "https://info.test/b",
         "resumen": "Autoridades vigilan la zona."},
    ]
    cuerpos = {"https://uno.test/a": "Cuerpo UnoTV largo.", "https://info.test/b": "Cuerpo Infobae largo."}
    nota = pc._nota_de_cluster("Caseta bajo vigilancia", "Resumen del cluster", items, cuerpos)
    # Las dos fuentes aportan medio, resumen y cuerpo (no solo el link).
    assert "UnoTV" in nota and "Infobae" in nota
    assert "Cuerpo UnoTV largo." in nota and "Cuerpo Infobae largo." in nota
    assert "https://uno.test/a" in nota and "https://info.test/b" in nota
    assert "sintetiza y cruza" in nota


def test_nota_de_cluster_sin_cuerpos_cae_a_resumenes():
    items = [{"fuente_nombre": "UnoTV", "titulo": "T", "url": "https://uno.test/a", "resumen": "Resumen A"}]
    nota = pc._nota_de_cluster("Título", "Resumen", items, None)
    assert "Resumen A" in nota and "https://uno.test/a" in nota


def test_fetch_cuerpo_gateado_off_no_toca_la_red(monkeypatch):
    monkeypatch.delenv("KENI_PIPELINE_FETCH_FUENTE", raising=False)
    llamado = {"n": 0}

    def _boom(enlace):
        llamado["n"] += 1
        return "no debería"

    monkeypatch.setattr(pc, "_FETCH_ARTICULO", _boom)
    assert pc._fetch_cuerpo("https://ejemplo.test/n") == ""
    assert llamado["n"] == 0


def test_fetch_cuerpo_gateado_on_usa_el_seam(monkeypatch):
    monkeypatch.setenv("KENI_PIPELINE_FETCH_FUENTE", "1")
    monkeypatch.setattr(pc, "_FETCH_ARTICULO", lambda enlace: "  Cuerpo del artículo.  ")
    assert pc._fetch_cuerpo("https://ejemplo.test/n") == "Cuerpo del artículo."
    # Enlace vacío: ni se intenta.
    assert pc._fetch_cuerpo("") == ""


def test_en_backoff_puro_segun_intentos_y_timestamp():
    """`en_backoff` (PURO sobre el dict): espera tras un intento RECIENTE; sin ts/intentos no."""
    from keni_consola.tiempo import ahora_iso

    reciente = json.dumps({"verificar_intentos": 1, "verificar_intentos_ts": ahora_iso()})
    assert pc.en_backoff({"id": "t", "copy_pendiente": reciente}, "verificar_intentos") is True
    viejo = json.dumps({"verificar_intentos": 1, "verificar_intentos_ts": "2020-01-01T00:00:00"})
    assert pc.en_backoff({"id": "t", "copy_pendiente": viejo}, "verificar_intentos") is False
    # Temas previos al backoff (intentos sin timestamp) y temas sin intentos: sin espera.
    legacy = json.dumps({"verificar_intentos": 2})
    assert pc.en_backoff({"id": "t", "copy_pendiente": legacy}, "verificar_intentos") is False
    assert pc.en_backoff({"id": "t", "copy_pendiente": ""}, "verificar_intentos") is False


def test_verificacion_lexica_listo_sin_observaciones():
    r = pc.verificacion_lexica({"red": "x", "contenido": "Copy corto y válido."})
    assert r["verificacion"] == "listo"
    assert r["observaciones"] == []


def test_verificacion_lexica_copy_vacio():
    r = pc.verificacion_lexica({"red": "x", "contenido": "   "})
    assert r["verificacion"] == "revisar"
    assert any("vacío" in o for o in r["observaciones"])


def test_verificacion_lexica_supera_limite_de_red():
    limite = next(red.limite for red in redes.REDES if red.id == "x")
    assert limite is not None
    r = pc.verificacion_lexica({"red": "x", "contenido": "a" * (limite + 1)})
    assert r["verificacion"] == "revisar"
    assert any("límite" in o for o in r["observaciones"])


# --------------------------------------------------------------------------- #
# MACRO-EVENTO (Fase B): UN carrusel para toda la familia (mock de repos, sin DB)#
# --------------------------------------------------------------------------- #


def _fake_repos_familia(monkeypatch, *, familia, items_por_cid):
    """Parchea `_admitir.repos` (+ helpers de etiquetado/marca/redes) para probar la rama macro.

    Sin Postgres: `clusters_por_tema_macro` devuelve `familia`, `items_de_cluster` el lote por id,
    `crear_publicacion` captura kwargs y `actualizar_noticia_cluster`/`marcar_items_cluster_usados`
    registran la absorción. Devuelve el registro de llamadas.
    """
    from types import SimpleNamespace

    from keni_consola.pipeline_contenido import _admitir

    reg: dict = {"crear": [], "actualizar": [], "marcar_items": []}

    def crear_publicacion(**kw):
        reg["crear"].append(kw)
        return {"id": "tema-macro-1"}

    def actualizar_noticia_cluster(cid, *, estado=None, publicacion_id=None):
        reg["actualizar"].append((cid, estado, publicacion_id))
        return None

    def marcar_items_cluster_usados(cid, publicacion_id):
        reg["marcar_items"].append((cid, publicacion_id))

    fake = SimpleNamespace(
        clusters_por_tema_macro=lambda tema, marca, *, solo_nuevos=True: list(familia),
        clusters_por_subtema=lambda tema, subtema, marca, *, solo_nuevos=True: list(familia),
        items_de_cluster=lambda cid, *, limite=200: list(items_por_cid.get(cid, [])),
        cuerpos_de_cluster=lambda cid, *, limite=200: {},
        obtener_fuente_rss=lambda fid: {"propia": True},
        # El contexto «ya en el feed del evento» (no repetir ángulos) no aplica en estos tests.
        listar_publicacion=lambda **kw: [],
        crear_publicacion=crear_publicacion,
        actualizar_noticia_cluster=actualizar_noticia_cluster,
        marcar_items_cluster_usados=marcar_items_cluster_usados,
    )
    monkeypatch.setattr(_admitir, "repos", fake)
    monkeypatch.setattr(_admitir.marcas, "es_marca", lambda m: True)
    monkeypatch.setattr(_admitir.redes, "redes_de_formato", lambda formato: ["x"])
    monkeypatch.setattr(_admitir, "_auto_etiquetar_linea", lambda *a, **k: None)
    # La clave de plan resuelve la LÍNEA contra la BD (bootstrap_lineas); sin BD aquí, la
    # dejamos en el slug (estos tests cubren el carrusel, no el mapeo a línea del plan).
    monkeypatch.setattr(_admitir, "_categoria_plan", lambda marca, cluster: _admitir.categoria_efectiva(cluster))
    return reg


def _cluster_familia(cid, *, score, tema_macro="Mundial 2026", subtema="Partidos"):
    return {
        "id": cid, "marca": "unotv", "titulo": f"Ángulo {cid}", "tema_macro": tema_macro,
        "subtema": subtema,
        "resumen": f"Resumen de {cid}", "categoria": "mx", "breaking": 0,
        "verificacion_fuente": "no_verificado", "verificar_hallazgos": "",
        "primer_visto": "2026-06-01T00:00:00+00:00", "score": score,
    }


def _item_propio(cid):
    return {
        "url": f"https://casa.test/{cid}", "url_canonica": f"https://casa.test/{cid}",
        "fuente_id": f"f-{cid}", "fuente_nombre": "Casa", "titulo": f"Nota {cid}",
        "resumen": f"Cuerpo de {cid}", "imagen": f"https://casa.test/{cid}.jpg",
        "publicado_en": "2026-06-10T00:00:00+00:00",
    }


def test_macro_evento_crea_un_solo_carrusel_y_absorbe_la_familia(monkeypatch):
    """La familia de un macro-evento se promueve como UNA pieza carrusel que absorbe a los hermanos."""
    from keni_consola.pipeline_contenido import _admitir

    familia = [
        _cluster_familia("c1", score=0.9),
        _cluster_familia("c2", score=0.8),
        _cluster_familia("c3", score=0.7),
    ]
    items_por_cid = {c["id"]: [_item_propio(c["id"])] for c in familia}
    reg = _fake_repos_familia(monkeypatch, familia=familia, items_por_cid=items_por_cid)

    tema = _admitir.crear_tema_de_cluster(familia[0], items_por_cid["c1"], claves_vistas=set())

    assert tema == {"id": "tema-macro-1"}
    # UNA sola publicación, titulada por el EVENTO.
    assert len(reg["crear"]) == 1
    kw = reg["crear"][0]
    # El carrusel es de UNA faceta coherente: titulado por (evento — subtema).
    assert kw["titulo"] == "Mundial 2026 — Partidos"
    # La pieza queda ESTAMPADA con su (evento, subtema): gobierna la cadencia aguas arriba.
    assert kw["tema_macro"] == "Mundial 2026"
    assert kw["subtema"] == "Partidos"
    # Carrusel: n_notas = nº de sub-historias (3) en el copy_pendiente.
    pend = json.loads(kw["copy_pendiente"])
    assert pend["n_notas"] == 3
    assert len(pend["fotos_notas"]) == 3
    # Absorción: las 3 sub-historias quedan usado + enlazadas a la pieza.
    assert {c for c, _e, _p in reg["actualizar"]} == {"c1", "c2", "c3"}
    assert all(estado == "usado" and pid == "tema-macro-1" for _c, estado, pid in reg["actualizar"])
    assert {c for c, _p in reg["marcar_items"]} == {"c1", "c2", "c3"}


def test_macro_evento_guarda_de_carrera_cluster_ya_absorbido(monkeypatch):
    """Si el cluster pasado NO está en la familia fresca (ya absorbido), no se crea pieza duplicada."""
    from keni_consola.pipeline_contenido import _admitir

    # La familia fresca solo tiene c2/c3: c1 ya fue absorbido por una promoción anterior.
    familia = [_cluster_familia("c2", score=0.8), _cluster_familia("c3", score=0.7)]
    items_por_cid = {c["id"]: [_item_propio(c["id"])] for c in familia}
    reg = _fake_repos_familia(monkeypatch, familia=familia, items_por_cid=items_por_cid)

    c1 = _cluster_familia("c1", score=0.9)
    tema = _admitir.crear_tema_de_cluster(c1, [_item_propio("c1")], claves_vistas=set())

    assert tema is None
    assert reg["crear"] == []  # ninguna publicación nueva


def test_contexto_feed_evento_lista_piezas_previas(monkeypatch):
    """El productor recibe las piezas YA en el feed del mismo evento, para no repetir ángulos."""
    from keni_consola.pipeline_contenido import _admitir

    piezas = [
        {"titulo": "Mundial 2026 — Partidos", "tema_macro": "Mundial 2026"},
        {"titulo": "Estreno de cine", "tema_macro": ""},                  # otro evento -> fuera
        {"titulo": "Mundial 2026 — Espectáculo", "tema_macro": "Mundial 2026"},
    ]
    monkeypatch.setattr(_admitir.repos, "listar_publicacion", lambda **kw: list(piezas))
    bloque = _admitir._contexto_feed_evento("unotv", "Mundial 2026")
    assert "YA EN EL FEED" in bloque and "NO repitas" in bloque
    assert "Mundial 2026 — Partidos" in bloque
    assert "Mundial 2026 — Espectáculo" in bloque
    assert "Estreno de cine" not in bloque


def test_contexto_feed_evento_vacio_sin_evento_o_sin_piezas(monkeypatch):
    """Sin macro-evento, o sin piezas previas, el bloque es "" (no cambia la nota)."""
    from keni_consola.pipeline_contenido import _admitir

    assert _admitir._contexto_feed_evento("unotv", "") == ""
    monkeypatch.setattr(_admitir.repos, "listar_publicacion", lambda **kw: [])
    assert _admitir._contexto_feed_evento("unotv", "Mundial 2026") == ""


def test_clusters_por_tema_macro_filtra_marca_estado_y_ordena(entorno):
    """`clusters_por_tema_macro`: misma marca + tema_macro, `solo_nuevos`, orden por score desc."""
    _inicializar_cluster("m1", titulo="A", score=0.9, estado="nuevo")
    _inicializar_cluster("m2", titulo="B", score=0.7, estado="nuevo")
    _inicializar_cluster("m3", titulo="C", score=0.8, estado="usado")
    _inicializar_cluster("m4", titulo="D", score=0.6, estado="nuevo", marca="claro-sports")
    _inicializar_cluster("otro", titulo="E", score=0.95, estado="nuevo")
    repos.marcar_clusters_tema_macro(["m1", "m2", "m3", "m4"], "Mundial 2026")

    nuevos = repos.clusters_por_tema_macro("Mundial 2026", "unotv", solo_nuevos=True)
    assert [c["id"] for c in nuevos] == ["m1", "m2"]  # m3 usado fuera; m4 otra marca; orden score desc

    todos = repos.clusters_por_tema_macro("Mundial 2026", "unotv", solo_nuevos=False)
    assert [c["id"] for c in todos] == ["m1", "m3", "m2"]  # incluye el usado, score desc
    assert repos.clusters_por_tema_macro("", "unotv") == []


def test_clusters_por_subtema_filtra_evento_faceta_marca_y_ordena(entorno):
    """`clusters_por_subtema`: mismo (tema_macro, subtema) + marca, `solo_nuevos`, score desc."""
    _inicializar_cluster("p1", titulo="México vs Sudáfrica", score=0.9,
                         tema_macro="Mundial 2026", subtema="Partidos")
    _inicializar_cluster("p2", titulo="Argentina vs Argelia", score=0.7,
                         tema_macro="Mundial 2026", subtema="Partidos")
    _inicializar_cluster("show", titulo="Concierto inaugural", score=0.95,
                         tema_macro="Mundial 2026", subtema="Espectáculo")
    _inicializar_cluster("p-otra", titulo="Partido", score=0.99,
                         tema_macro="Mundial 2026", subtema="Partidos", marca="claro-sports")

    partidos = repos.clusters_por_subtema("Mundial 2026", "Partidos", "unotv", solo_nuevos=True)
    assert [c["id"] for c in partidos] == ["p1", "p2"]  # solo esa faceta y marca, score desc
    assert repos.clusters_por_subtema("Mundial 2026", "", "unotv") == []  # subtema vacío -> []


# --------------------------------------------------------------------------- #
# (a) GATEADO OFF por defecto -> el barrido NO produce nada                    #
# --------------------------------------------------------------------------- #


def test_gateado_off_no_arranca_el_daemon():
    """Sin `KENI_PIPELINE_REDACTAR`, el flag está OFF (def): el `bucle_gateado` no barrería."""
    assert config.pipeline_activo() is False


def test_iniciar_pipeline_no_genera_sin_flag(entorno, monkeypatch):
    """El daemon arranca pero, gateado OFF, NO crea temas (el barrido no corre)."""
    llamadas = _mock_lanzar_copy(monkeypatch)

    from keni_consola import daemon_util

    daemon_util.bucle_gateado(
        activo_fn=config.pipeline_activo,
        intervalo_seg_fn=lambda: 3600.0,
        sweep_fn=pc.ejecutar_barrido,
        log=pc._log,
        _max_vueltas=1,
    )
    assert llamadas == []
    assert _etapas_de_actividad() == []
    # No se creó ningún tema del pipeline.
    assert pc.temas_pipeline() == []


# --------------------------------------------------------------------------- #
# (b)+(c) ADMITIR: crea temas SIN copy, dedup, y etapa ADMITIR en actividad    #
# --------------------------------------------------------------------------- #


def _etapas_de_actividad():
    """Etiquetas de las generaciones-marcador del pipeline (tipo 'pipeline_etapa'), recientes 1º."""
    return [
        g["etiqueta"]
        for g in generaciones.listar(limite=None)
        if g["tipo"] == pc.TIPO_ACTIVIDAD
    ]


def test_fotos_notas_de_cluster_solo_propias_con_su_titulo(entorno, monkeypatch):
    """`_fotos_notas_de_cluster`: foto propia POR NOTA (con su título), sin duplicar; ajenas fuera."""
    from keni_consola.pipeline_contenido import _admitir

    propia = repos.crear_fuente_rss("Casa", _URL_OK, marca="unotv", propia=True)
    ajena = repos.crear_fuente_rss("Tercero", "https://otro.test/feed.xml", marca="unotv")
    items = [
        {"fuente_id": propia["id"], "titulo": "Concierto A", "imagen": "https://casa.test/a.jpg", "url": "https://casa.test/1"},
        {"fuente_id": ajena["id"], "titulo": "Robada", "imagen": "https://otro.test/robada.jpg", "url": "https://otro.test/1"},
        {"fuente_id": propia["id"], "titulo": "Concierto A bis", "imagen": "https://casa.test/a.jpg", "url": "https://casa.test/1b"},
        {"fuente_id": propia["id"], "titulo": "Concierto B", "imagen": "https://casa.test/b.jpg", "url": "https://casa.test/2"},
        {"fuente_id": propia["id"], "titulo": "Sin foto", "imagen": "", "url": "https://casa.test/3"},
    ]
    assert _admitir._fotos_notas_de_cluster(items) == [
        {"titulo": "Concierto A", "imagen": "https://casa.test/a.jpg"},
        {"titulo": "Concierto B", "imagen": "https://casa.test/b.jpg"},
    ]
    # La PORTADA del tema es la primera foto propia.
    assert _admitir._imagen_de_cluster(items) == "https://casa.test/a.jpg"


def test_imagen_de_cluster_og_image_solo_como_rescate(entorno, monkeypatch):
    """Sin foto en NINGÚN item propia, la portada se resuelve por og:image (un solo fetch)."""
    from keni_consola.pipeline_contenido import _admitir

    propia = repos.crear_fuente_rss("Casa", _URL_OK, marca="unotv", propia=True)
    _mock_og_image(monkeypatch, "https://casa.test/og.jpg")
    items = [
        {"fuente_id": propia["id"], "imagen": "", "url": "https://casa.test/1"},
        {"fuente_id": propia["id"], "imagen": "", "url": "https://casa.test/2"},
    ]
    assert _admitir._imagen_de_cluster(items) == "https://casa.test/og.jpg"
    # Sin fuentes propias, "" (no se toca la red ni se usa la foto de un tercero).
    ajena = repos.crear_fuente_rss("Tercero", "https://otro.test/feed.xml", marca="unotv")
    assert _admitir._imagen_de_cluster(
        [{"fuente_id": ajena["id"], "imagen": "https://otro.test/x.jpg", "url": "https://otro.test/1"}]
    ) == ""


def test_imagen_de_cluster_sigue_iterando_si_el_primero_no_resuelve_og(entorno, monkeypatch):
    """Bug 2: si el PRIMER item propia no resuelve og:image, sigue probando los demás propios."""
    from keni_consola.pipeline_contenido import _admitir

    propia = repos.crear_fuente_rss("Casa", _URL_OK, marca="unotv", propia=True)
    # El primer artículo (/1) no trae og:image; el segundo (/2) sí.
    monkeypatch.setattr(
        pc, "_FETCH_OG_IMAGE",
        lambda enlace: "https://casa.test/2.jpg" if enlace.endswith("/2") else "",
    )
    items = [
        {"fuente_id": propia["id"], "imagen": "", "url": "https://casa.test/1"},
        {"fuente_id": propia["id"], "imagen": "", "url": "https://casa.test/2"},
    ]
    assert _admitir._imagen_de_cluster(items) == "https://casa.test/2.jpg"


def test_redactar_pasa_fotos_notas_y_n_notas_al_copy(entorno, monkeypatch):
    """REDACTAR: `fotos_notas`/`n_notas` del copy_pendiente viajan a `lanzar_copy` (habilitan el carrusel)."""
    monkeypatch.setenv("KENI_PIPELINE_REDACTAR", "1")
    llamadas = _mock_lanzar_copy(monkeypatch)
    fotos = [
        {"titulo": "Concierto A", "imagen": "https://casa.test/a.jpg"},
        {"titulo": "Concierto B", "imagen": "https://casa.test/b.jpg"},
    ]
    tema = _tema_pipeline(
        titulo="Panel de conciertos",
        verificacion_fuente=pc.VERIFICACION_VERIFICADO,
        copy_pendiente=json.dumps({
            "nota": "Nota", "redes_ids": ["x", "instagram", "facebook"],
            "imagen": "https://casa.test/a.jpg",
            "fotos_notas": fotos, "n_notas": 4,
            "tipo_contenido": "fuente",
        }),
    )
    pc.lanzar_redactar_de_tema(repos.obtener_publicacion(tema["id"]), autor=None)
    assert len(llamadas) == 1
    assert llamadas[0]["imagen_fuente"] == "https://casa.test/a.jpg"
    assert llamadas[0]["fotos_notas"] == fotos
    assert llamadas[0]["n_notas"] == 4


def test_redactar_pendiente_viejo_sin_panel_no_ofrece_carrusel(entorno, monkeypatch):
    """Compat: un copy_pendiente anterior al carrusel sigue funcionando (n_notas=1, sin fotos)."""
    monkeypatch.setenv("KENI_PIPELINE_REDACTAR", "1")
    llamadas = _mock_lanzar_copy(monkeypatch)
    tema = _tema_pipeline(
        titulo="Pendiente legado",
        verificacion_fuente=pc.VERIFICACION_VERIFICADO,
        copy_pendiente=json.dumps({
            "nota": "Nota", "redes_ids": ["x"], "imagen": "https://casa.test/a.jpg",
        }),
    )
    pc.lanzar_redactar_de_tema(repos.obtener_publicacion(tema["id"]), autor=None)
    assert llamadas[0]["fotos_notas"] == []
    assert llamadas[0]["n_notas"] == 1


# --------------------------------------------------------------------------- #
# (d) VERIFICAR la fuente: problema NO genera copy (❗); no_verificado SÍ (⚠️)  #
# --------------------------------------------------------------------------- #


def _tema_pipeline(titulo="Tema", marca="unotv", **campos):
    # `copy_pendiente` lo fija ADMITIR (`crear_tema_de_cluster`) en producción: parámetros del copy a lanzar
    # SOLO si Verificar la fuente pasa. La fase Redactar exige que esté presente; lo inicializamos aquí.
    campos.setdefault(
        "copy_pendiente",
        json.dumps({"nota": "Nota de origen a verificar.", "redes_ids": ["x"]}),
    )
    return repos.crear_publicacion(
        clase="contenido", titulo=titulo, marca=marca, origen=pc.ORIGEN_PIPELINE,
        descripcion="Nota de origen a verificar.", **campos,
    )


def test_verificar_cluster_problema_no_se_admite(entorno, monkeypatch):
    """ADR 0011: Verificar corre sobre la HISTORIA; una `problema` NO se materializa como contenido."""
    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")
    monkeypatch.setenv("KENI_PIPELINE_VERIFICAR", "1")
    monkeypatch.setenv("KENI_PIPELINE_MAX", "5")
    cliente = _cliente(lanzar_generacion=lanzador_generacion_completa(_VERIFICACION_RECHAZADO))  # noqa: F841
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    _inicializar_cluster("c-malo", titulo="Historia dudosa", score=0.8)

    # Un tick de investigación: Verificar (síncrona en test) marca el cluster, la admisión decide.
    res = pc._ejecutar_investigacion()

    assert repos.obtener_noticia_cluster("c-malo")["verificacion_fuente"] == pc.VERIFICACION_RECHAZADO
    assert res["temas"] == []  # 'problema' NO cruza a producción
    assert pc.temas_pipeline() == []
    # La historia sigue en el pool (visible con su verificación), sin promover.
    assert repos.obtener_noticia_cluster("c-malo")["estado"] == "nuevo"


def test_verificar_cluster_ok_se_admite_heredando_veredicto(entorno, monkeypatch):
    """ADR 0011: una historia que pasa Verificar se admite y el TEMA HEREDA el verificación del cluster."""
    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")
    monkeypatch.setenv("KENI_PIPELINE_VERIFICAR", "1")
    monkeypatch.setenv("KENI_PIPELINE_MAX", "5")
    cliente = _cliente(lanzar_generacion=lanzador_generacion_completa(_VERIFICACION_OK))  # noqa: F841
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    _inicializar_cluster("c-ok", titulo="Historia verificada", score=0.8)

    res = pc._ejecutar_investigacion()

    assert repos.obtener_noticia_cluster("c-ok")["verificacion_fuente"] == pc.VERIFICACION_VERIFICADO
    assert len(res["temas"]) == 1
    tema = res["temas"][0]
    # El contenido nace VERIFICADO (frontera "Verificar = investigación" alineada en los datos).
    assert repos.obtener_publicacion(tema["id"])["verificacion_fuente"] == pc.VERIFICACION_VERIFICADO
    assert repos.obtener_noticia_cluster("c-ok")["estado"] == "usado"


def test_verificar_cluster_acotada_por_el_admision(entorno, monkeypatch):
    """ADR 0011: la verificación se acota al ADMISION (tope en proceso) — no recorre todo el pool por tick."""
    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")
    monkeypatch.setenv("KENI_PIPELINE_VERIFICAR", "1")
    monkeypatch.setenv("KENI_PIPELINE_EN_PROCESO_MAX", "1")  # admision de 1
    cliente = _cliente(lanzar_generacion=lanzador_generacion_completa(_VERIFICACION_OK))  # noqa: F841
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    for i in range(3):
        _inicializar_cluster(f"c{i}", titulo=f"Historia {i}", score=0.9 - i * 0.1)

    verificados = pc.ejecutar_verificar_clusters(autor=None)

    # Con tope en proceso = 1, solo se verificación 1 historia en este tick (la mejor del ranking).
    assert len(verificados) == 1
    assert verificados[0]["id"] == "c0"


def test_verificar_clusters_omite_fuente_propia(entorno, monkeypatch):
    """La fase Verificar OMITE las historias de fuente PROPIA (las maneja el canal Portal aparte):
    quedan sin verificar (''); solo las AJENAS pasan por verificación."""
    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")
    monkeypatch.setenv("KENI_PIPELINE_VERIFICAR", "1")  # Validación ON para la marca
    monkeypatch.setenv("KENI_PIPELINE_EN_PROCESO_MAX", "5")
    cliente = _cliente(lanzar_generacion=lanzador_generacion_completa(_VERIFICACION_OK))  # noqa: F841
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    propia = repos.crear_fuente_rss("Portal propio", _URL_OK, marca="unotv", propia=True)
    ajena = repos.crear_fuente_rss("Tercero", "https://otro.test/feed.xml", marca="unotv")
    _inicializar_cluster("c-propia", titulo="Nota del portal", score=0.9, primera_fuente=propia["id"])
    _inicializar_cluster("c-ajena", titulo="Nota de tercero", score=0.8, primera_fuente=ajena["id"])

    pc.ejecutar_verificar_clusters(autor=None)

    # La PROPIA no la toca Verificar (la maneja el canal Portal): sigue sin verificar.
    assert (repos.obtener_noticia_cluster("c-propia").get("verificacion_fuente") or "") == ""
    # La AJENA pasa por `claude -p` (lanzador síncrono de tests -> verificado).
    assert repos.obtener_noticia_cluster("c-ajena")["verificacion_fuente"] == pc.VERIFICACION_VERIFICADO


def test_portal_admite_fuente_propia_directo(entorno, monkeypatch):
    """Canal PORTAL: admite DIRECTO la historia de fuente PROPIA como tema `origen='portal'`/`saltada`
    aunque su score sea muy BAJO (sin umbral ni verificación); la AJENA no entra al Portal."""
    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    propia = repos.crear_fuente_rss("Portal propio", _URL_OK, marca="unotv", propia=True)
    ajena = repos.crear_fuente_rss("Tercero", "https://otro.test/feed.xml", marca="unotv")
    _inicializar_cluster("c-propia", titulo="Nota del portal", score=0.05, primera_fuente=propia["id"])
    _inicializar_cluster("c-ajena", titulo="Nota de tercero", score=0.05, primera_fuente=ajena["id"])

    res = pc.ejecutar_portal()

    titulos = [t["titulo"] for t in res["temas"]]
    assert "Nota del portal" in titulos and "Nota de tercero" not in titulos
    tema = next(t for t in pc.temas_pipeline() if t["titulo"] == "Nota del portal")
    assert tema["origen"] == pc.ORIGEN_PORTAL
    assert tema["verificacion_fuente"] == pc.VERIFICACION_SALTADA  # directo, sin verificar
    # La propia queda `usado` (no se re-admite); la ajena sigue en el pool.
    assert repos.obtener_noticia_cluster("c-propia")["estado"] == "usado"
    assert repos.obtener_noticia_cluster("c-ajena")["estado"] == "nuevo"


def test_portal_admite_cluster_con_item_propio_aunque_primera_fuente_ajena(entorno, monkeypatch):
    """Bug 3B: la pertenencia al Portal es por ALGÚN item de fuente PROPIA, no por `primera_fuente`.

    Si una agencia abrió la historia (la canónica fusionada quedó con `primera_fuente` AJENA) pero
    UnoTV también la cubrió, el cluster SIGUE siendo del Portal: lo decide tener un item propio."""
    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    _mock_og_image(monkeypatch, "https://casa.test/og.jpg")
    propia = repos.crear_fuente_rss("Portal propio", _URL_OK, marca="unotv", propia=True)
    ajena = repos.crear_fuente_rss("Agencia", "https://otro.test/feed.xml", marca="unotv")
    # Score bajo y `primera_fuente` AJENA: por el camino viejo (filtro por primera_fuente + corte
    # por score) NO entraba al Portal.
    _inicializar_cluster(
        "c-mixto", titulo="Nota cubierta por ambos", score=0.03, primera_fuente=ajena["id"]
    )
    repos.crear_noticias_items([
        {"fuente_id": ajena["id"], "fuente_nombre": "Agencia", "marca": "unotv",
         "titulo": "Versión agencia", "url": "https://otro.test/1",
         "url_canonica": "otro.test/1", "clave": "k-ajena", "cluster_id": "c-mixto"},
        {"fuente_id": propia["id"], "fuente_nombre": "Portal propio", "marca": "unotv",
         "titulo": "Versión UnoTV", "url": "https://casa.test/1",
         "url_canonica": "casa.test/1", "clave": "k-propia", "cluster_id": "c-mixto"},
    ])

    # Camino normal: lo OMITE (no doble admisión), porque tiene un item propio. Se comprueba
    # ANTES de admitir (la admisión lo deja `usado` y sale del set de `nuevo`).
    assert "c-mixto" in repos.ids_clusters_con_fuente_propia("unotv")

    res = pc.ejecutar_portal()

    assert "Nota cubierta por ambos" in [t["titulo"] for t in res["temas"]]


def test_claves_dedup_marca_ventana_portal_mas_corta(entorno):
    """La ventana de dedup del Portal es `_DIAS_DEDUP_PORTAL`; la general, `_DIAS_DEDUP`.

    Un contenido de hace 30 días entra en la ventana general (lo ve el dedup normal) pero queda
    FUERA de la corta del Portal (no lo ve): un titular recurrente vuelve a admitirse en el Portal.
    """
    from datetime import timedelta

    from keni_consola.dominio import dedup as _dedup
    from keni_consola.pipeline_contenido._admitir import _claves_dedup_marca
    from keni_consola.pipeline_contenido._comun import _DIAS_DEDUP_PORTAL
    from keni_consola.tiempo import hoy_utc

    creado = (hoy_utc() - timedelta(days=30)).isoformat()
    repos.crear_publicacion(
        clase="contenido", titulo="Resultados de la jornada", marca="unotv", creado=creado,
    )
    clave = _dedup.clave("Resultados de la jornada")

    assert clave in _claves_dedup_marca("unotv")  # ventana general (60 días): lo ve
    assert clave not in _claves_dedup_marca("unotv", dias=_DIAS_DEDUP_PORTAL)  # corta: no


def test_portal_readmite_titular_recurrente_fuera_de_ventana_corta(entorno, monkeypatch):
    """Portal: un titular que ya salió hace 30 días (dentro de los 60 generales pero fuera de la
    ventana corta del Portal) SÍ vuelve a admitirse; una colisión del mismo día sigue deduplicándose."""
    from datetime import timedelta

    from keni_consola.tiempo import hoy_utc

    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    propia = repos.crear_fuente_rss("Portal propio", _URL_OK, marca="unotv", propia=True)
    # Ya publicado hace 30 días: dentro de los 60 generales, fuera de la ventana corta del Portal.
    repos.crear_publicacion(
        clase="contenido", titulo="Clima de hoy", marca="unotv",
        creado=(hoy_utc() - timedelta(days=30)).isoformat(),
    )
    # Recién creado hoy: dentro de la ventana corta -> debe deduplicarse.
    repos.crear_publicacion(clase="contenido", titulo="Resultados de la jornada", marca="unotv")
    _inicializar_cluster("c-recurrente", titulo="Clima de hoy", score=0.05,
                         primera_fuente=propia["id"])
    _inicializar_cluster("c-duplicado", titulo="Resultados de la jornada", score=0.05,
                         primera_fuente=propia["id"])

    res = pc.ejecutar_portal()

    titulos = [t["titulo"] for t in res["temas"]]
    assert "Clima de hoy" in titulos  # fuera de la ventana corta: vuelve a entrar
    assert "Resultados de la jornada" not in titulos  # colisión del día: deduplicada


def test_copy_fallido_se_reintenta_tras_el_backoff(entorno, monkeypatch):
    """DEDUP AL ÉXITO + BACKOFF: un copy fallido se RELANZA, pero solo PASADA la espera creciente.

    El doble lanzamiento mientras el job está EN PROCESO lo evita la clave de idempotencia de
    `dominio.generar.lanzar` (no este filtro). El barrido SALTA el tema mientras dura el
    backoff del intento (`_BACKOFF_ETAPA_SEG`).
    """
    monkeypatch.setenv("KENI_PIPELINE_REDACTAR", "1")
    llamadas = _mock_lanzar_copy(monkeypatch)
    tema = _tema_pipeline(titulo="Reintento", verificacion_fuente=pc.VERIFICACION_VERIFICADO)

    pc.ejecutar_redactar(autor=None)
    assert len(llamadas) == 1
    # El lanzamiento NO limpió `copy_pendiente` (lo limpia el post-procesado al ÉXITO).
    assert (repos.obtener_publicacion(tema["id"])["copy_pendiente"] or "").strip()

    # El copy "falló" (no nació pieza), pero el tick INMEDIATO no relanza: backoff en curso.
    pc.ejecutar_redactar(autor=None)
    assert len(llamadas) == 1

    # Pasada la espera (timestamp envejecido), el barrido sí lo reintenta.
    _envejecer_intento(tema["id"], "redactar_intentos")
    pc.ejecutar_redactar(autor=None)
    assert len(llamadas) == 2

    # Éxito (pieza creada): deja de relanzarse.
    repos.crear_pieza_fila(publicacion_id=tema["id"], red="x", copy="Listo")
    _envejecer_intento(tema["id"], "redactar_intentos")
    pc.ejecutar_redactar(autor=None)
    assert len(llamadas) == 2


def test_verificar_no_relanza_tema_ya_verificado(entorno, monkeypatch):
    """Un tema con verificación ya no se re-verificación (idempotente)."""
    _tema_pipeline(titulo="Ya verificado", verificacion_fuente=pc.VERIFICACION_VERIFICADO)
    assert _temas_sin_verdicto() == []


def test_temas_para_copy_devuelve_todos_los_listos(entorno):
    """FLUJO CONTINUO: REDACTAR ve TODOS los temas listos (verificados+pendiente de copy), sin ventana."""
    # Viejos no_verificado pero YA copiados (copy_pendiente vacío -> no pasan el filtro de Redactar).
    _tema_pipeline(titulo="Viejo 1", id="v1", verificacion_fuente=pc.VERIFICACION_VERIFICADO, copy_pendiente="")
    _tema_pipeline(titulo="Viejo 2", id="v2", verificacion_fuente=pc.VERIFICACION_VERIFICADO, copy_pendiente="")
    _tema_pipeline(titulo="Nuevo A", id="n1", verificacion_fuente=pc.VERIFICACION_VERIFICADO)
    _tema_pipeline(titulo="Nuevo B", id="n2", verificacion_fuente=pc.VERIFICACION_VERIFICADO)
    assert {t["id"] for t in pc.temas_para_redactar()} == {"n1", "n2"}


def test_redactar_sin_tope_lanza_todos_los_listos(entorno, monkeypatch):
    """FLUJO CONTINUO: la fase Redactar redacta TODOS los temas listos en un tick (sin cap por etapa)."""
    monkeypatch.setenv("KENI_PIPELINE_REDACTAR", "1")
    llamadas = _mock_lanzar_copy(monkeypatch)
    import json

    pend = json.dumps({"nota": "n", "redes_ids": ["x"]})
    for i in range(4):
        _tema_pipeline(
            titulo=f"C{i}", id=f"tcd{i}",
            verificacion_fuente=pc.VERIFICACION_VERIFICADO, copy_pendiente=pend,
        )

    lanzados = pc.ejecutar_redactar(autor=None)
    assert len(lanzados) == 4
    assert len(llamadas) == 4


def test_redactar_reintentos_agotados_marca_requiere_humano_sin_lanzar(entorno, monkeypatch):
    """REINTENTOS ACOTADOS en Redactar: un copy que ya agotó sus intentos sale TERMINAL a revisión humana."""
    import json

    monkeypatch.setenv("KENI_PIPELINE_REDACTAR", "1")
    llamadas = _mock_lanzar_copy(monkeypatch)
    pend = json.dumps({"nota": "n", "redes_ids": ["x"], "redactar_intentos": pc._MAX_INTENTOS_ETAPA})
    tema = _tema_pipeline(titulo="Copy agotado", verificacion_fuente=pc.VERIFICACION_VERIFICADO, copy_pendiente=pend)

    lanzados = pc.ejecutar_redactar(autor=None)

    assert lanzados == [] and llamadas == []
    refrescado = repos.obtener_publicacion(tema["id"])
    assert refrescado["verificacion_fuente"] == pc.VERIFICACION_REQUIERE_HUMANO  # fallo de SISTEMA, no rechazo
    assert "falló" in (refrescado["verificar_hallazgos"] or "")
    assert pc.temas_en_proceso("unotv") == 0  # terminal: libera la admisión de su marca


def test_redactar_reintento_anota_intentos_acumulados(entorno, monkeypatch):
    """Cada relanzamiento de copy suma su intento (el tope corta el bucle de reintentos)."""
    import json

    monkeypatch.setenv("KENI_PIPELINE_REDACTAR", "1")
    llamadas = _mock_lanzar_copy(monkeypatch)
    tema = _tema_pipeline(titulo="Suma intentos", verificacion_fuente=pc.VERIFICACION_VERIFICADO)

    pc.ejecutar_redactar(autor=None)  # 1er intento (el copy mockeado "falla": no nace pieza)
    _envejecer_intento(tema["id"], "redactar_intentos")  # fuera del backoff: el barrido reintenta
    pc.ejecutar_redactar(autor=None)  # 2º intento

    assert len(llamadas) == 2
    pend = json.loads(repos.obtener_publicacion(tema["id"])["copy_pendiente"])
    assert pend["redactar_intentos"] == 2


# --------------------------------------------------------------------------- #
# 1 toggle = 1 etapa: Noticias/Verificar/Redactar independientes por marca      #
# --------------------------------------------------------------------------- #


def test_verificar_off_no_admite_historia_ajena(entorno, monkeypatch):
    """RECOLECTAR ON + VERIFICAR OFF: una historia de fuente AJENA NO se verifica NI se admite; queda
    sin verificar en el pool para que el humano la decida (nada ajeno se auto-produce sin verificar)."""
    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")
    monkeypatch.delenv("KENI_PIPELINE_VERIFICAR", raising=False)  # Verificar off
    monkeypatch.delenv("KENI_PIPELINE_REDACTAR", raising=False)
    monkeypatch.setenv("KENI_PIPELINE_MAX", "5")
    llamadas = _mock_lanzar_copy(monkeypatch)
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    _inicializar_cluster("c1", titulo="Historia caliente", score=0.8)  # fuente ajena (sin primera_fuente propia)

    resumen = pc.ejecutar_barrido()

    # Verificar OFF + fuente ajena: no se admite (sin tema) ni se genera copy.
    assert resumen["temas"] == []
    assert pc.temas_pipeline() == []
    assert llamadas == []
    # El cluster queda SIN verificar en el pool (no 'saltada', no 'usado'): lo decide el humano.
    cl = repos.obtener_noticia_cluster("c1")
    assert (cl.get("verificacion_fuente") or "") == ""
    assert cl["estado"] != "usado"


def test_dos_loops_investigacion_y_produccion_separan_fases(entorno, monkeypatch):
    """ADR 0011: `ejecutar_investigacion` cubre ADMITIR+VERIFICAR y `ejecutar_produccion` REDACTAR+ILUSTRAR+avance.

    El barrido combinado (`_ejecutar_barrido`) es la unión exacta de ambos, así el disparo a
    demanda y los tests siguen viendo el resumen completo aunque en producción cada proceso
    corra en su propio hilo/lock/cadencia.
    """
    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")
    monkeypatch.delenv("KENI_PIPELINE_REDACTAR", raising=False)  # Redactar off
    monkeypatch.setenv("KENI_PIPELINE_MAX", "5")
    _mock_lanzar_copy(monkeypatch)
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    # Cluster ya verificado: ADMITIR lo promueve sin pasar por la fase de verificación.
    _inicializar_cluster("c1", titulo="Historia caliente", score=0.8, verificacion_fuente=pc.VERIFICACION_VERIFICADO)

    # INVESTIGACIÓN: admite (ADMITIR) + verificación (VERIFICAR). Solo expone {temas, verificados}.
    inv = pc._ejecutar_investigacion()
    assert set(inv) == {"temas", "verificados"}
    assert len(inv["temas"]) == 1
    assert any(t["titulo"] == "Historia caliente" for t in pc.temas_pipeline())

    # PRODUCCIÓN: copy (CD) + Ilustrar + stock + avance. Expone {lanzados, artes, stock, avances}.
    # La sugerencia de hashtags ya no es un paso del tick: la encadena el post-proceso del copy.
    prod = pc._ejecutar_produccion()
    assert set(prod) == {"lanzados", "artes", "stock", "avances"}

    # El combinado es la unión de las claves de ambos procesos.
    combinado = pc._ejecutar_barrido()
    assert set(combinado) == {"temas", "verificados", "lanzados", "artes", "stock", "avances"}


def test_promover_omite_extranjera_sin_traducir(entorno, monkeypatch):
    """Una historia EXTRANJERA (`idioma='en'`) sin traducir NO se promueve (saldría en inglés);
    espera a Traducir. La misma traducida (`traducido=1`) SÍ se promueve."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    _inicializar_cluster(
        "en-crudo", titulo="Trump tells G7 summit", score=0.9, idioma="en", traducido=0,
        verificacion_fuente=pc.VERIFICACION_VERIFICADO,
    )
    _inicializar_cluster(
        "en-trad", titulo="Trump at the G7 summit", titulo_es="Trump en la cumbre del G7",
        score=0.9, idioma="en", traducido=1, verificacion_fuente=pc.VERIFICACION_VERIFICADO,
    )

    elegidos = {c["id"] for c in pc.clusters_para_promover("unotv", maximo=5)}

    assert "en-trad" in elegidos  # ya traducida -> entra
    assert "en-crudo" not in elegidos  # extranjera sin traducir -> espera


def test_promover_omite_faceta_de_evento_ya_cubierta_hoy(entorno, monkeypatch):
    """Cadencia por evento: una faceta (evento, subtema) que YA tiene pieza hoy NO se vuelve a
    auto-producir; otra faceta del MISMO evento SÍ entra (sin tope numérico, por subtema)."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    _inicializar_cluster(
        "partidos", titulo="México vence a Sudáfrica en el debut", score=0.9,
        tema_macro="Mundial 2026", subtema="Partidos", verificacion_fuente=pc.VERIFICACION_VERIFICADO,
    )
    _inicializar_cluster(
        "show", titulo="Concierto en la inauguración del torneo", score=0.8,
        tema_macro="Mundial 2026", subtema="Espectáculo", verificacion_fuente=pc.VERIFICACION_VERIFICADO,
    )
    # Ya salió hoy una pieza de la faceta «Partidos» (cualquier productor cuenta).
    repos.crear_publicacion(
        titulo="Mundial 2026 — Partidos", marca="unotv",
        tema_macro="Mundial 2026", subtema="Partidos",
    )

    elegidos = {c["id"] for c in pc.clusters_para_promover("unotv", maximo=5)}

    assert "partidos" not in elegidos  # faceta ya cubierta hoy -> espera a mañana
    assert "show" in elegidos  # otra faceta del mismo evento -> entra


def test_promover_usa_titulo_es_del_cluster_traducido(entorno, monkeypatch):
    """ADMITIR usa el título TRADUCIDO (`titulo_es`) del cluster, no el original en inglés, para
    que el tema (y el breaking que sale al feed) no salga en inglés."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    # Historia EXTRANJERA pero relevante para MX: la TRADUCCIÓN (`*_es`) es la que lleva el encaje
    # de marca, así que supera el umbral por su texto en español, no por el original en inglés.
    _inicializar_cluster(
        "en-trad", titulo="Fed decision shakes Mexican markets",
        titulo_es="La decisión de la Fed sacude los mercados de México",
        resumen="US rate move hits emerging markets",
        resumen_es="El gobierno de México sigue de cerca el impacto de la decisión en la economía del país",
        score=0.9, idioma="en", traducido=1, verificacion_fuente=pc.VERIFICACION_VERIFICADO,
    )

    temas = pc.promover_clusters_marca("unotv", maximo=2)

    assert len(temas) == 1
    assert temas[0]["titulo"] == "La decisión de la Fed sacude los mercados de México"
    assert "Fed decision shakes" not in (temas[0].get("descripcion") or "")[:80]  # la nota arranca en ES


def test_texto_es_extranjero_distingue_ingles_de_espanol():
    """El detector mira el TEXTO real, no el metadato: inglés -> True, español/ambiguo -> False."""
    from keni_consola.pipeline_contenido import _admitir

    assert _admitir._texto_es_extranjero("Markets tumble as the Fed signals higher rates") is True
    assert _admitir._texto_es_extranjero("El gobierno de México anuncia medidas de seguridad") is False
    assert _admitir._texto_es_extranjero("") is False  # sin señal: no se fuerza traducción
    # Títulos CORTOS en español: langdetect devuelve ruido ('no'/'de'/…), pero sin evidencia de
    # inglés NO son extranjeros (regresión: antes se excluían/traducían noticias españolas).
    assert _admitir._texto_es_extranjero("Urgente persistida") is False
    assert _admitir._texto_es_extranjero("Urgente") is False
    assert _admitir._texto_es_extranjero("Nacional") is False


def test_falta_traduccion_idioma_vacio_decide_por_texto():
    """Con `idioma` vacío, `_falta_traduccion` decide por el TEXTO del título (Hueco A): un titular
    en inglés sin idioma queda pendiente; uno en español no bloquea."""
    from keni_consola.pipeline_contenido import _admitir

    assert _admitir._falta_traduccion(
        {"idioma": "", "titulo": "Tribes decry the New Mexico rule on newborns", "traducido": 0}
    ) is True
    assert _admitir._falta_traduccion(
        {"idioma": "", "titulo": "El gobierno anuncia nuevas medidas en la capital", "traducido": 0}
    ) is False


def test_crear_tema_tropicaliza_titulo_ingles_con_idioma_vacio(entorno, monkeypatch):
    """RED DE SEGURIDAD (Hueco A): un cluster con título en INGLÉS e `idioma` vacío y sin `titulo_es`
    se tropicaliza EN EL ACTO al materializar el tema — el feed nunca recibe el título en inglés."""
    from keni_consola.pipeline_contenido import _admitir

    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    # La traducción real (Haiku) se mockea: devuelve la tropicalización a ES MX.
    monkeypatch.setattr(
        _admitir, "traducir_par_ahora",
        lambda titulo, resumen: ("Los niños indígenas pertenecen a sus comunidades", "Resumen en español"),
    )
    cluster = _inicializar_cluster(
        "en-vacio",
        titulo="Tribes decry the New Mexico rule on drug-exposed newborns in Native communities",
        idioma="", titulo_es="", score=0.7,
    )

    tema = pc.crear_tema_de_cluster(cluster, [], claves_vistas=set())

    assert tema is not None
    assert tema["titulo"] == "Los niños indígenas pertenecen a sus comunidades"  # ES, no inglés
    # La traducción se PERSISTE en el cluster (mismo destino que el paso Traducir del daemon).
    assert repos.obtener_noticia_cluster("en-vacio")["titulo_es"] == "Los niños indígenas pertenecen a sus comunidades"


def test_crear_tema_tropicaliza_titulo_ingles_mal_etiquetado_es(entorno, monkeypatch):
    """RED DE SEGURIDAD (Hueco B): un titular en INGLÉS mal etiquetado `idioma='es'` (override de
    preset) también se tropicaliza al materializar — la decisión es por TEXTO, no por metadato."""
    from keni_consola.pipeline_contenido import _admitir

    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    monkeypatch.setattr(
        _admitir, "traducir_par_ahora",
        lambda titulo, resumen: ("Los mercados caen tras la señal de la Fed", "Resumen"),
    )
    cluster = _inicializar_cluster(
        "es-malo",
        titulo="Markets tumble as the Fed signals higher rates for longer",
        idioma="es", titulo_es="", score=0.7,
    )

    tema = pc.crear_tema_de_cluster(cluster, [], claves_vistas=set())

    assert tema is not None
    assert tema["titulo"] == "Los mercados caen tras la señal de la Fed"


def test_crear_tema_no_traduce_titulo_ya_en_espanol(entorno, monkeypatch):
    """Un título en español con `idioma` vacío NO dispara traducción (no se gasta Haiku en balde):
    el texto ya es español, se usa tal cual."""
    from keni_consola.pipeline_contenido import _admitir

    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    llamado = {"n": 0}

    def _no_debe_traducir(titulo, resumen):
        llamado["n"] += 1
        return ("NO DEBERÍA", "")

    monkeypatch.setattr(_admitir, "traducir_par_ahora", _no_debe_traducir)
    cluster = _inicializar_cluster(
        "es-ok",
        titulo="El gobierno de México anuncia nuevas medidas de seguridad en la capital",
        idioma="", titulo_es="", score=0.7,
    )

    tema = pc.crear_tema_de_cluster(cluster, [], claves_vistas=set())

    assert tema is not None
    assert tema["titulo"].startswith("El gobierno de México")
    assert llamado["n"] == 0  # texto español: no se tradujo


def test_promover_clusters_top_n_por_score(entorno, monkeypatch):
    """`promover_clusters_marca` promueve las top-N historias por score y las marca usado."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    # Verificadas (estado real tras Verificar): la admisión SIEMPRE verificación — solo promueve verificadas.
    _inicializar_cluster("baja", titulo="Score bajo", score=0.1, verificacion_fuente=pc.VERIFICACION_VERIFICADO)
    _inicializar_cluster("alta", titulo="Score alto", score=0.9, verificacion_fuente=pc.VERIFICACION_VERIFICADO)
    _inicializar_cluster("media", titulo="Score medio", score=0.5, verificacion_fuente=pc.VERIFICACION_VERIFICADO)

    temas = pc.promover_clusters_marca("unotv", maximo=2)

    # Solo las 2 de mayor score (alta, media); todas con origen pipeline y copy pendiente.
    assert {t["titulo"] for t in temas} == {"Score alto", "Score medio"}
    assert all(t["origen"] == pc.ORIGEN_PIPELINE for t in temas)
    assert all((t.get("copy_pendiente") or "").strip() for t in temas)
    assert repos.obtener_noticia_cluster("alta")["estado"] == "usado"
    assert repos.obtener_noticia_cluster("baja")["estado"] == "nuevo"  # no promovida


def test_promover_clusters_marca_filtra_sin_verificar_por_defecto(entorno, monkeypatch):
    """El filtro de Verificar es OBLIGATORIO por defecto (ADR 0011): un cluster SIN verificar (verificación
    '') NO se promueve aunque gane en score/umbral — no existe un camino que promueva sin verificar.
    """
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    _inicializar_cluster("sin_verificar", titulo="Aún sin Verificar", score=0.9)  # verificacion_fuente='' por defecto
    _inicializar_cluster("verificada", titulo="Ya verificada", score=0.5,
                     verificacion_fuente=pc.VERIFICACION_VERIFICADO)

    temas = pc.promover_clusters_marca("unotv", maximo=5)  # SIN verificacion_estados: cae al filtro por defecto

    assert {t["titulo"] for t in temas} == {"Ya verificada"}  # la sin verificar NO cruza
    assert repos.obtener_noticia_cluster("sin_verificar")["estado"] == "nuevo"  # se queda en el pool


def test_crear_tema_de_cluster_dedup_no_repromueve(entorno, monkeypatch):
    """Una historia cuyo título ya está en el tablero reciente no crea un segundo tema."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    cluster = _inicializar_cluster("c1", titulo="Historia repetida", score=0.7)
    # Inicializamos la clave del título como ya vista para forzar el dedup.
    from keni_consola.dominio import dedup as _dedup
    claves = {_dedup.clave("Historia repetida")}

    tema = pc.crear_tema_de_cluster(cluster, [], claves_vistas=claves)

    assert tema is None  # duplicado: no se crea
    assert repos.obtener_noticia_cluster("c1")["estado"] == "usado"  # pero se marca usado


# --------------------------------------------------------------------------- #
# Serial POR MARCA: el gate de ADMITIR no promueve más historias mientras la marca #
# tenga cola EN PROCESO (sin verificar / sin copy). Cada item entra y se completa.  #
# --------------------------------------------------------------------------- #


def test_crear_tema_de_cluster_copia_fuente_y_fecha_de_la_nota(entorno, monkeypatch):
    """La promoción ADMITIR→tema COPIA la procedencia de la nota original al `contenido`.

    `fuente_nombre` viene del item más reciente del cluster, y `fecha_fuente` prefiere su
    `publicado_en` (cuando el medio publicó la nota). Se copian porque el GC de noticias
    puede borrar el cluster y la pieza debe conservar fuente y fecha para la UI.
    """
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    cluster = _inicializar_cluster("cf1", titulo="Historia con medio", score=0.7)
    items = [{
        "titulo": "Historia con medio", "url": "https://record.com.mx/nota-1",
        "url_canonica": "record.com.mx/nota-1", "fuente_nombre": "Récord",
        "publicado_en": "2026-06-09T21:21:00+00:00", "imagen": "",
    }]

    tema = pc.crear_tema_de_cluster(cluster, items, claves_vistas=set())

    assert tema is not None
    guardado = repos.obtener_publicacion(tema["id"])
    assert (guardado.get("fuente_nombre") or "") == "Récord"
    assert (guardado.get("fecha_fuente") or "") == "2026-06-09T21:21:00+00:00"
    assert (guardado.get("url_fuente") or "") == "record.com.mx/nota-1"


def test_crear_tema_de_cluster_fecha_cae_a_primer_visto(entorno, monkeypatch):
    """Si el medio no traía fecha (`publicado_en` vacío), `fecha_fuente` cae al `primer_visto`
    del cluster (cuándo capturó la historia el Radar). Sin items, también."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    cluster = _inicializar_cluster("cf2", titulo="Historia sin fecha de medio", score=0.7)
    items = [{
        "titulo": "Historia sin fecha de medio", "url": "https://medio.test/n",
        "url_canonica": "medio.test/n", "fuente_nombre": "Medio", "publicado_en": "",
        "imagen": "",
    }]

    tema = pc.crear_tema_de_cluster(cluster, items, claves_vistas=set())

    assert tema is not None
    guardado = repos.obtener_publicacion(tema["id"])
    # `primer_visto` del cluster inicializado por `_inicializar_cluster`.
    assert (guardado.get("fecha_fuente") or "") == "2026-06-01T00:00:00+00:00"


def test_crear_tema_de_cluster_resuelve_og_image_de_fuente_propia(entorno, monkeypatch):
    """Cluster con item de fuente PROPIA sin foto en el feed: se RESUELVE la og:image del artículo.

    Así la pieza nace con arte (`copy_pendiente.imagen` + `tipo_contenido='fuente'`) en vez de
    "Falta imagen". La og:image solo se resuelve para fuentes propias (derechos)."""
    import json

    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    fuente = repos.crear_fuente_rss("Casa", _URL_OK, marca="unotv", propia=True)
    _mock_og_image(monkeypatch, "https://casa.test/foto-nota.jpg")
    cluster = _inicializar_cluster("cp1", titulo="Historia propia", score=0.7)
    items = [{
        "titulo": "Historia propia", "url": "https://unotv.test/nota", "url_canonica": "unotv.test/nota",
        "fuente_id": fuente["id"], "fuente_nombre": "UnoTV", "publicado_en": "", "imagen": "",
    }]

    tema = pc.crear_tema_de_cluster(cluster, items, claves_vistas=set())

    assert tema is not None
    pend = json.loads(repos.obtener_publicacion(tema["id"])["copy_pendiente"])
    assert pend["imagen"] == "https://casa.test/foto-nota.jpg"
    assert pend["tipo_contenido"] == "fuente"


def test_crear_tema_de_cluster_no_resuelve_og_image_de_fuente_ajena(entorno, monkeypatch):
    """Fuente NO propia (medio ajeno): no resolvemos su og:image (sin derechos). Sin foto en el
    feed, el tema nace sin imagen aunque la resolución estuviera disponible."""
    import json

    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    fuente = repos.crear_fuente_rss("Ajeno", _URL_OK, marca="unotv", propia=False)
    # Si llegara a resolverse, sería esta URL; el test verifica que NO se usa.
    _mock_og_image(monkeypatch, "https://ajeno.test/foto.jpg")
    cluster = _inicializar_cluster("ca1", titulo="Historia ajena", score=0.7)
    items = [{
        "titulo": "Historia ajena", "url": "https://medio.test/nota", "url_canonica": "medio.test/nota",
        "fuente_id": fuente["id"], "fuente_nombre": "Medio", "publicado_en": "", "imagen": "",
    }]

    tema = pc.crear_tema_de_cluster(cluster, items, claves_vistas=set())

    assert tema is not None
    pend = json.loads(repos.obtener_publicacion(tema["id"])["copy_pendiente"])
    assert pend["imagen"] == ""
    assert pend["tipo_contenido"] == ""


def test_crear_tema_de_cluster_no_usa_imagen_de_feed_ajeno(entorno, monkeypatch):
    """Item de fuente AJENA con foto en el feed (media-tag): NO se usa (sin derechos).

    Antes había un fallback a "cualquier imagen ya capturada en los items": colaba fotos de
    medios ajenos en las piezas (y encendía la etapa Ilustrar sin arte). Solo fuentes PROPIAS
    aportan imagen; sin ellas, el tema nace sin foto y el arte lo decide la etapa de Ilustrar IA."""
    import json

    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    fuente = repos.crear_fuente_rss("Ajeno2", _URL_OK, marca="unotv", propia=False)
    cluster = _inicializar_cluster("ca2", titulo="Historia ajena con foto", score=0.7)
    items = [{
        "titulo": "Historia ajena con foto", "url": "https://medio.test/nota2",
        "url_canonica": "medio.test/nota2", "fuente_id": fuente["id"],
        "fuente_nombre": "Medio", "publicado_en": "",
        "imagen": "https://medio.test/foto-ajena.jpg",  # media-tag del feed ajeno
    }]

    tema = pc.crear_tema_de_cluster(cluster, items, claves_vistas=set())

    assert tema is not None
    pend = json.loads(repos.obtener_publicacion(tema["id"])["copy_pendiente"])
    assert pend["imagen"] == ""
    assert pend["tipo_contenido"] == ""


def test_temas_en_proceso_cuenta_pendientes_de_verificar_o_copy(entorno):
    """`temas_en_proceso` cuenta los temas sin terminar las fases de IA (Verificar pendiente o sin copy).

    En proceso: verificación ''/'en_curso' (Verificar pendiente) y 'no_verificado'/'saltada' SIN copy. NO en
    vuelo: 'problema' (terminal) ni 'no_verificado' que YA tiene copy en una pieza por plataforma.
    """
    pend = json.dumps({"nota": "n", "redes_ids": ["x"]})
    _tema_pipeline(titulo="Pendiente verificación", verificacion_fuente="", copy_pendiente=pend)          # +1
    _tema_pipeline(titulo="verificación en curso", verificacion_fuente=pc.VERIFICACION_EN_CURSO, copy_pendiente=pend)  # +1
    _tema_pipeline(titulo="Apto sin copy", verificacion_fuente=pc.VERIFICACION_VERIFICADO, copy_pendiente=pend)  # +1
    _tema_pipeline(titulo="Saltada sin copy", verificacion_fuente=pc.VERIFICACION_SALTADA, copy_pendiente=pend)  # +1
    _tema_pipeline(titulo="Problema", verificacion_fuente=pc.VERIFICACION_RECHAZADO, copy_pendiente=pend)  # terminal: 0
    con_copy = _tema_pipeline(titulo="Apto con copy", verificacion_fuente=pc.VERIFICACION_VERIFICADO, copy_pendiente=pend)
    # Una pieza por plataforma CON copy -> ya pasó la etapa de copy: no cuenta como en proceso.
    repos.crear_pieza_fila(publicacion_id=con_copy["id"], red="x", copy="Copy listo")

    assert pc.temas_en_proceso("unotv") == 4


# --------------------------------------------------------------------------- #
# FRESCURA: caducidad TTL de temas en proceso (ventana deslizante)               #
# --------------------------------------------------------------------------- #


def test_caducidad_libera_el_gate_y_excluye_de_las_fases(entorno):
    """Un tema EN PROCESO que supera el TTL caduca: sale del gate serial (libera hueco para lo
    fresco del ranking) y NINGUNA fase lo retoma (ni Verificar lo verificación ni Redactar le genera copy)."""
    from datetime import datetime, timedelta, timezone

    pend = json.dumps({"nota": "n", "redes_ids": ["x"]})
    _tema_pipeline(titulo="Atascado", verificacion_fuente="", copy_pendiente=pend)
    _tema_pipeline(titulo="Apto viejo", verificacion_fuente=pc.VERIFICACION_VERIFICADO, copy_pendiente=pend)
    assert pc.temas_en_proceso("unotv") == 2

    futuro = datetime.now(timezone.utc) + timedelta(hours=25)  # > TTL (def 24 h)
    assert pc.caducar_temas_viejos(ahora=futuro) == 2

    # Liberan el gate, no se re-verifican ni generan copy, y quedan marcados con el motivo.
    assert pc.temas_en_proceso("unotv") == 0
    assert _temas_sin_verdicto() == []
    assert pc.temas_para_redactar() == []
    temas = {t["titulo"]: t for t in pc.temas_pipeline()}
    assert temas["Atascado"]["verificacion_fuente"] == pc.VERIFICACION_CADUCADA
    assert "Caducada" in (temas["Atascado"].get("notas") or "")


def test_caducidad_respeta_lo_fresco_y_lo_terminal(entorno):
    """La caducidad NO toca lo fresco (dentro del TTL) ni lo que ya salió del vuelo
    ('problema' terminal, o apto CON copy ya generado)."""
    from datetime import datetime, timedelta, timezone

    pend = json.dumps({"nota": "n", "redes_ids": ["x"]})
    _tema_pipeline(titulo="Fresco", verificacion_fuente="", copy_pendiente=pend)
    _tema_pipeline(titulo="Problema viejo", verificacion_fuente=pc.VERIFICACION_RECHAZADO, copy_pendiente=pend)
    con_copy = _tema_pipeline(
        titulo="Con copy", verificacion_fuente=pc.VERIFICACION_VERIFICADO, copy_pendiente=pend
    )
    repos.crear_pieza_fila(publicacion_id=con_copy["id"], red="x", copy="Copy listo")

    # Dentro del TTL: nada caduca (lo en proceso sigue siendo fresco).
    pronto = datetime.now(timezone.utc) + timedelta(hours=1)
    assert pc.caducar_temas_viejos(ahora=pronto) == 0
    # Pasado el TTL: solo caduca el EN PROCESO; terminal y con-copy intactos.
    futuro = datetime.now(timezone.utc) + timedelta(hours=25)
    assert pc.caducar_temas_viejos(ahora=futuro) == 1
    temas = {t["titulo"]: t for t in pc.temas_pipeline()}
    assert temas["Problema viejo"]["verificacion_fuente"] == pc.VERIFICACION_RECHAZADO
    assert temas["Con copy"]["verificacion_fuente"] == pc.VERIFICACION_VERIFICADO


def test_caducado_libera_hueco_para_lo_fresco_del_ranking(entorno, monkeypatch):
    """Tras caducar el backlog, la admisión vuelve a tener cupo: entra lo fresco del ranking
    (la historia top de HOY), no lo que quedó atascado ayer (sin colas intermedias)."""
    from datetime import datetime, timedelta, timezone

    from keni_consola.pipeline_contenido import _admitir

    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")
    monkeypatch.setenv("KENI_PIPELINE_EN_PROCESO_MAX", "1")
    monkeypatch.delenv("KENI_PIPELINE_REDACTAR", raising=False)
    pend = json.dumps({"nota": "n", "redes_ids": ["x"]})
    _tema_pipeline(titulo="Backlog vencido", verificacion_fuente="", copy_pendiente=pend)
    # Cluster ya verificado: ADMITIR lo promueve en cuanto se libere cupo (el foco del test es la caducidad).
    _inicializar_cluster("hot", titulo="Lo fresco de hoy", score=0.9, verificacion_fuente=pc.VERIFICACION_VERIFICADO)
    # Con el backlog en proceso, el cupo (1) está agotado: no entra nada.
    assert pc._ejecutar_barrido()["temas"] == []
    # Caduca el backlog (reloj adelantado > TTL) y el siguiente tick admite lo fresco.
    assert _admitir.caducar_temas_viejos(
        ahora=datetime.now(timezone.utc) + timedelta(hours=25)
    ) == 1
    res = pc._ejecutar_barrido()
    assert [t["titulo"] for t in res["temas"]] == ["Lo fresco de hoy"]


def test_admitir_serial_no_promueve_si_marca_llena(entorno, monkeypatch):
    """Gate SERIAL: si la marca ya tiene >= cupo en proceso, ADMITIR no promueve clusters nuevos."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")  # recolectar_activo: ADMITIR corre
    monkeypatch.setenv("KENI_PIPELINE_EN_PROCESO_MAX", "2")
    # 2 temas en proceso (pendientes de Verificar) -> cupo 0 para unotv.
    pend = json.dumps({"nota": "n", "redes_ids": ["x"]})
    _tema_pipeline(titulo="En proceso 1", verificacion_fuente="", copy_pendiente=pend)
    _tema_pipeline(titulo="En proceso 2", verificacion_fuente="", copy_pendiente=pend)
    _inicializar_cluster("hot", titulo="Historia caliente", score=0.9)

    res = pc._ejecutar_barrido()

    assert res["temas"] == []  # cupo agotado: no se promueve nada
    assert repos.obtener_noticia_cluster("hot")["estado"] == "nuevo"  # el cluster sigue disponible


def test_admitir_serial_promueve_solo_hasta_el_cupo(entorno, monkeypatch):
    """Gate SERIAL: con cupo parcial, ADMITIR promueve como mucho `cupo` historias (no `pipeline_max`)."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")
    monkeypatch.setenv("KENI_PIPELINE_MAX", "3")  # pipeline_max alto: el límite real es el cupo
    monkeypatch.setenv("KENI_PIPELINE_EN_PROCESO_MAX", "3")
    # 2 en proceso -> cupo 1: solo entra 1 historia aunque haya 3 clusters y pipeline_max=3.
    pend = json.dumps({"nota": "n", "redes_ids": ["x"]})
    _tema_pipeline(titulo="En proceso 1", verificacion_fuente="", copy_pendiente=pend)
    _tema_pipeline(titulo="En proceso 2", verificacion_fuente="", copy_pendiente=pend)
    ver = pc.VERIFICACION_VERIFICADO  # admisión solo promueve verificadas (no hay atajo `saltada`)
    _inicializar_cluster("c1", titulo="Hist 1", score=0.9, verificacion_fuente=ver)
    _inicializar_cluster("c2", titulo="Hist 2", score=0.8, verificacion_fuente=ver)
    _inicializar_cluster("c3", titulo="Hist 3", score=0.7, verificacion_fuente=ver)

    res = pc._ejecutar_barrido()

    assert len(res["temas"]) == 1  # cupo=1, no min(3, pipeline_max)
    assert res["temas"][0]["titulo"] == "Hist 1"  # la de mayor score


# --------------------------------------------------------------------------- #
# Volumen: PLAN EDITORIAL DIARIO (cupos por categoría, lo mejor de cada tipo) o,    #
# sin plan, cupo diario simple (24 h móviles).                                       #
# --------------------------------------------------------------------------- #


def test_cupo_dia_corta_la_admision(entorno, monkeypatch):
    """Sin plan, con el cupo DIARIO (24 h móviles) agotado, ADMITIR no admite más."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")
    monkeypatch.setenv("KENI_CUPO_DIA", "1")
    pend = json.dumps({"nota": "n", "redes_ids": ["x"]})
    t = _tema_pipeline(
        titulo="Producido hoy", verificacion_fuente=pc.VERIFICACION_VERIFICADO, copy_pendiente=pend
    )
    repos.crear_pieza_fila(publicacion_id=t["id"], red="x", copy="Copy listo")
    _inicializar_cluster("hot", titulo="Historia caliente", score=0.9)

    res = pc._ejecutar_barrido()

    assert res["temas"] == []
    assert repos.obtener_noticia_cluster("hot")["estado"] == "nuevo"


def test_plan_llena_cupos_por_categoria_con_lo_mejor(entorno, monkeypatch):
    """Con plan, cada LÍNEA se lleva SUS mejores historias y las demás no compiten."""
    from keni_consola import bootstrap_lineas

    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")
    monkeypatch.setenv("KENI_PIPELINE_MAX", "10")
    # El plan se clava por LÍNEA (id de etiqueta vertical): los feeds 'mx'/'internacional' se
    # re-clavan a sus líneas Nacional/Internacional; la deportiva ('futbol') cae fuera del plan.
    bootstrap_lineas.inicializar_lineas()
    nacional = repos.obtener_etiqueta_por_nombre("Nacional", "vertical", "unotv")
    internacional = repos.obtener_etiqueta_por_nombre("Internacional", "vertical", "unotv")
    monkeypatch.setenv("KENI_PLAN_DIA", f"{nacional['id']}:1,{internacional['id']}:1")
    ver = pc.VERIFICACION_VERIFICADO  # admisión solo promueve verificadas (no hay atajo `saltada`)
    _inicializar_cluster("mx1", titulo="Nacional floja", score=0.5, categoria="mx", verificacion_fuente=ver)
    _inicializar_cluster("mx2", titulo="Nacional top", score=0.9, categoria="mx", verificacion_fuente=ver)
    _inicializar_cluster(
        "int1", titulo="Internacional unica historia", score=0.4, categoria="internacional",
        resumen="México observa la cumbre internacional", verificacion_fuente=ver,
    )
    _inicializar_cluster(
        "dep1", titulo="Deportiva fuera de plan", score=0.95, categoria="futbol", verificacion_fuente=ver
    )

    res = pc._ejecutar_barrido()

    titulos = {t["titulo"] for t in res["temas"]}
    # La mejor de mx + la única de internacional; la deportiva (sin cupo en el plan) NO entra.
    assert titulos == {"Nacional top", "Internacional unica historia"}
    assert repos.obtener_noticia_cluster("dep1")["estado"] == "nuevo"
    assert repos.obtener_noticia_cluster("mx1")["estado"] == "nuevo"


def test_plan_breaking_consume_slot_breaking(entorno, monkeypatch):
    """Una historia BREAKING compite por el cupo 'breaking', no por el de su categoría."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")
    monkeypatch.setenv("KENI_PIPELINE_MAX", "10")
    monkeypatch.setenv("KENI_PLAN_DIA", "breaking:1")
    ver = pc.VERIFICACION_VERIFICADO  # admisión solo promueve verificadas (no hay atajo `saltada`)
    _inicializar_cluster(
        "br1", titulo="Ultima hora corroborada", score=0.8, categoria="mx", breaking=1, verificacion_fuente=ver
    )
    _inicializar_cluster("mx9", titulo="Nacional normal", score=0.9, categoria="mx", verificacion_fuente=ver)

    res = pc._ejecutar_barrido()

    assert [t["titulo"] for t in res["temas"]] == ["Ultima hora corroborada"]


def test_plan_descuenta_lo_ya_generado_hoy(entorno, monkeypatch):
    """El cupo de una categoría descuenta lo GENERADO en 24 h (contenido.categoria persistida)."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")
    monkeypatch.setenv("KENI_PLAN_DIA", "mx:1")
    # Generado previo de la línea mx (la categoría vive EN el contenido, no en el cluster),
    # CON post real (es_publicacion=1): un tema sin post no consumiría cupo (no cuenta).
    ya = repos.crear_publicacion(
        clase="contenido", titulo="Ya generada", marca="unotv", categoria="mx"
    )
    repos.crear_pieza_fila(
        publicacion_id=ya["id"], red="facebook", marca="unotv", copy="P", es_publicacion=True
    )
    _inicializar_cluster("hoy", titulo="Nacional nueva", score=0.9, categoria="mx")

    res = pc._ejecutar_barrido()

    assert res["temas"] == []  # cupo mx (1) ya consumido por el generado previo
    assert repos.obtener_noticia_cluster("hoy")["estado"] == "nuevo"


def test_promocion_persiste_categoria_en_el_contenido(entorno, monkeypatch):
    """Al promover, la LÍNEA (id) queda en `contenido.categoria` ('breaking' si lo era).

    El scheduler programa por LÍNEA: una historia de feed 'mx' se promueve con la categoría
    re-clavada al id de su línea (Nacional); la última hora conserva la señal 'breaking'.
    """
    from keni_consola import bootstrap_lineas

    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    bootstrap_lineas.inicializar_lineas()
    nacional = repos.obtener_etiqueta_por_nombre("Nacional", "vertical", "unotv")
    # El plan declara la línea 'breaking' para que la última hora consuma SU cupo y salga a la
    # vez que la nacional (sin él competiría por el cupo de su línea y la desplazaría).
    monkeypatch.setenv("KENI_PLAN_DIA", f"{nacional['id']}:1,breaking:1")
    _inicializar_cluster("cat1", titulo="Nacional persistida", score=0.9, categoria="mx",
                     verificacion_fuente=pc.VERIFICACION_VERIFICADO)
    _inicializar_cluster("cat2", titulo="Urgente persistida", score=0.9, categoria="mx", breaking=1,
                     verificacion_fuente=pc.VERIFICACION_VERIFICADO)

    temas = pc.promover_clusters_marca(
        "unotv", maximo=2, cupos_categoria={nacional["id"]: 1, "breaking": 1}
    )

    por_titulo = {t["titulo"]: t for t in temas}
    assert por_titulo["Nacional persistida"]["categoria"] == nacional["id"]
    assert por_titulo["Urgente persistida"]["categoria"] == "breaking"


def test_plan_por_marca_gana_al_global(entorno, monkeypatch):
    """`KENI_PLAN_DIA::marca` (store) SUSTITUYE al plan global para esa marca."""
    overrides = {"KENI_PLAN_DIA::unotv": "internacional:2"}
    monkeypatch.setattr("keni_consola.ajustes.obtener", lambda clave: overrides.get(clave))
    monkeypatch.setenv("KENI_PLAN_DIA", "mx:4")
    assert config.plan_dia("unotv") == {"internacional": 2}
    assert config.plan_dia("claro-sports") == {"mx": 4}
    assert config.parsear_plan("mx:4, breaking:2, malformado, x:abc, vacio:0") == {
        "mx": 4, "breaking": 2,
    }


def test_cupo_produccion_restante_none_sin_cupos(entorno, monkeypatch):
    """Cupo diario a 0 -> None (la admisión queda solo con el gate serial)."""
    monkeypatch.setenv("KENI_CUPO_DIA", "0")
    from keni_consola.pipeline_contenido import _admitir

    assert _admitir.cupo_produccion_restante("unotv") is None
    assert _admitir.cupos_categoria_restantes("unotv") is None  # sin plan


def test_plan_breaking_excede_su_cupo_con_tope_extra(entorno, monkeypatch):
    """La última hora EXCEDE el plan: techo efectivo = cupo + KENI_BREAKING_EXTRA_DIA."""
    from keni_consola.pipeline_contenido import _admitir

    monkeypatch.setenv("KENI_PLAN_DIA", "breaking:1")
    monkeypatch.setenv("KENI_BREAKING_EXTRA_DIA", "1")
    # El cupo del plan (1) YA está consumido por una breaking generada hoy: tema CON post
    # real (pieza es_publicacion=1); un tema sin post no consumiría cupo (no cuenta).
    breaking = repos.crear_publicacion(
        clase="contenido", titulo="Breaking previa", marca="unotv", categoria="breaking"
    )
    repos.crear_pieza_fila(
        publicacion_id=breaking["id"], red="facebook", marca="unotv", copy="P", es_publicacion=True
    )
    # Queda el hueco EXTRA: una nueva última hora aún sale al feed.
    assert _admitir.cupos_categoria_restantes("unotv") == {"breaking": 1}
    # Con el extra a 0 el plan vuelve a ser techo duro también para breaking.
    monkeypatch.setenv("KENI_BREAKING_EXTRA_DIA", "0")
    assert _admitir.cupos_categoria_restantes("unotv") == {}


def test_cupos_solo_cuentan_la_jornada_mx_no_dias_previos(entorno, monkeypatch):
    """La admisión cuenta por PARRILLA DEL DÍA (jornada MX): lo de días anteriores reabre cupo.

    A medianoche de México los cupos del plan vuelven a 0; una pieza generada en un día
    anterior (aquí, hace años) ya no consume cupo hoy, así que el auto-feed puede volver a
    llenar el plan de la nueva jornada.
    """
    from keni_consola.pipeline_contenido import _admitir

    monkeypatch.setenv("KENI_PLAN_DIA", "mx:1")
    # Ambos con post real (es_publicacion=1): lo ÚNICO que excluye al viejo es la fecha.
    # De otra jornada: NO consume el cupo de hoy -> queda el hueco íntegro.
    ayer = repos.crear_publicacion(
        clase="contenido", titulo="Nacional de ayer", marca="unotv", categoria="mx",
        creado="2020-01-01T00:00:00",
    )
    repos.crear_pieza_fila(
        publicacion_id=ayer["id"], red="facebook", marca="unotv", copy="P", es_publicacion=True
    )
    assert _admitir.cupos_categoria_restantes("unotv") == {"mx": 1}
    # De hoy: consume el cupo -> sin hueco.
    hoy = repos.crear_publicacion(
        clase="contenido", titulo="Nacional de hoy", marca="unotv", categoria="mx"
    )
    repos.crear_pieza_fila(
        publicacion_id=hoy["id"], red="facebook", marca="unotv", copy="P", es_publicacion=True
    )
    assert _admitir.cupos_categoria_restantes("unotv") == {}


def test_plan_sin_linea_breaking_compite_por_su_feed(entorno, monkeypatch):
    """Si el plan no declara 'breaking', la última hora no queda invisible: compite por el
    cupo de SU LÍNEA (la del feed del que nació)."""
    from keni_consola import bootstrap_lineas

    bootstrap_lineas.inicializar_lineas()
    nacional = repos.obtener_etiqueta_por_nombre("Nacional", "vertical", "unotv")
    monkeypatch.setenv("KENI_PLAN_DIA", f"{nacional['id']}:1")
    _inicializar_cluster("brx", titulo="Ultima hora sin linea propia", score=0.9,
                     categoria="mx", breaking=1, verificacion_fuente=pc.VERIFICACION_VERIFICADO)

    elegidos = pc.clusters_para_promover("unotv", maximo=5, cupos_categoria={nacional["id"]: 1})

    assert [c["id"] for c in elegidos] == ["brx"]


def test_clusters_para_promover_clasifica_por_contenido_si_el_feed_no_mapea(entorno, monkeypatch):
    """Una candidata cuyo slug de feed NO mapea a ninguna línea compite por el cupo de la línea
    que le toca por CONTENIDO (keywords), no por el slug. Es el caso de Fundación (feeds con
    slugs gruesos que no son sus líneas); aquí se reproduce con UnoTV dándole keywords a una
    línea y un feed sin mapeo ('gaming' no es línea de UnoTV).
    """
    from keni_consola import bootstrap_lineas

    bootstrap_lineas.inicializar_lineas()
    intl = repos.obtener_etiqueta_por_nombre("Internacional", "vertical", "unotv")
    repos.actualizar_etiqueta(intl["id"], {"keywords": "groenlandia, vikingos, fosil"})
    # Solo se prueba el enrutado por categoría: se neutralizan los umbrales de score y marca.
    monkeypatch.setenv("KENI_PROMOVER_MIN_MARCA", "0")
    monkeypatch.setenv("KENI_PROMOVER_MIN_SCORE", "0")
    _inicializar_cluster(
        "sci", marca="unotv", categoria="gaming", score=0.9,
        titulo="Hallazgo en Groenlandia revela el rastro de vikingos",
        resumen="Un equipo de investigación presenta el fósil",
        verificacion_fuente=pc.VERIFICACION_VERIFICADO,
    )

    elegidos = pc.clusters_para_promover(
        "unotv", maximo=5, cupos_categoria={intl["id"]: 1}
    )

    assert [c["id"] for c in elegidos] == ["sci"]


def test_temas_para_copy_incluye_verificacion_saltada(entorno):
    """Un tema con Verificar 'saltada' fluye a Redactar igual que 'no_verificado'; un 'problema' no."""
    pend = json.dumps({"nota": "n", "redes_ids": ["x"]})
    _tema_pipeline(titulo="Saltada ok", verificacion_fuente=pc.VERIFICACION_SALTADA, copy_pendiente=pend)
    _tema_pipeline(titulo="Problema", verificacion_fuente=pc.VERIFICACION_RECHAZADO, copy_pendiente=pend)

    titulos = {t["titulo"] for t in pc.temas_para_redactar()}
    assert "Saltada ok" in titulos
    assert "Problema" not in titulos


# --------------------------------------------------------------------------- #
# Fundido de la selección de autogen_redactar en la etapa de copy (news-pool)      #
# --------------------------------------------------------------------------- #


def test_temas_autogen_sin_copy_selecciona_origenes_de_noticias(entorno):
    """La etapa de copy también redacta los temas del news-pool (orígenes de noticias) sin copy.

    Un tema con origen en `ORIGENES_AUTOGEN`, con marca y sin copy entra; el de origen "" no.
    """
    bueno = repos.crear_publicacion(
        clase="contenido", titulo="Noticia rss", marca="unotv", origen="rss",
    )
    repos.crear_publicacion(
        clase="contenido", titulo="Tecleado a mano", marca="unotv", origen="",
    )
    # Una historia USADA desde el panel (curación humana) también entra: si su lanzamiento
    # síncrono falló (cola llena / generación pausada), este es su ÚNICO reintento.
    historia = repos.crear_publicacion(
        clase="contenido", titulo="Breaking curada", marca="unotv", origen="historia",
    )
    ids = {t["id"] for t in pc.temas_autogen_sin_copy()}
    assert bueno["id"] in ids
    assert historia["id"] in ids
    # El tecleado (origen "") NO entra.
    assert len(ids) == 2


def test_temas_autogen_sin_copy_incluye_temas_con_piezas_vacias(entorno):
    """Las altas que PRE-CREAN piezas vacías (botón Crear post/`aportar`, Radar) siguen siendo
    redactables: la selección mira el copy REAL, no la mera existencia de filas. Un tema cuyas
    piezas ya tienen copy NO se reselecciona (no se reescribe lo ya redactado)."""
    sin_copy = repos.crear_publicacion(
        clase="contenido", titulo="Aporte del equipo", marca="unotv", origen="equipo",
    )
    repos.crear_pieza_fila(publicacion_id=sin_copy["id"], red="x", falta_copy=True)
    repos.crear_pieza_fila(publicacion_id=sin_copy["id"], red="instagram", falta_copy=True)

    con_copy = repos.crear_publicacion(
        clase="contenido", titulo="Aporte ya redactado", marca="unotv", origen="equipo",
    )
    repos.crear_pieza_fila(publicacion_id=con_copy["id"], red="x", copy="Copy ya escrito")

    ids = {t["id"] for t in pc.temas_autogen_sin_copy()}
    assert sin_copy["id"] in ids  # piezas vacías -> aún necesita copy
    assert con_copy["id"] not in ids  # ya tiene copy -> no se reescribe


def test_ejecutar_cd_funde_pool_via_autogen_lanzar(entorno, monkeypatch):
    """`ejecutar_redactar` lanza copy de los temas del pool vía `autogen_redactar.lanzar_para_topic`."""
    monkeypatch.setenv("KENI_PIPELINE_REDACTAR", "1")  # etapa Redactar activa (sin el global, ejecutar_redactar no corre)
    from keni_consola import autogen_redactar

    lanzadas: list[str] = []
    monkeypatch.setattr(
        autogen_redactar, "lanzar_para_topic",
        lambda item: lanzadas.append(item["id"]) or {"id": f"g-{item['id']}"},
    )
    repos.crear_publicacion(
        clase="contenido", titulo="Noticia pool", marca="unotv", origen="rss",
    )
    lanzados = pc.ejecutar_redactar(autor=None)
    assert len(lanzadas) == 1
    assert len(lanzados) == 1


def test_ejecutar_cd_salta_pool_de_marca_apagada(entorno, monkeypatch):
    """La exclusión por marca de «Generar copy» (ENV_PIPELINE_REDACTAR) también aplica al pool."""
    monkeypatch.setenv("KENI_PIPELINE_REDACTAR", "1")  # etapa Redactar activa; la exclusión es por marca, no global
    from keni_consola import autogen_redactar

    monkeypatch.setattr(pc.config, "marca_apagada", lambda env, marca: marca == "unotv")
    lanzadas: list[str] = []
    monkeypatch.setattr(
        autogen_redactar, "lanzar_para_topic",
        lambda item: lanzadas.append(item["id"]) or {"id": "g"},
    )
    repos.crear_publicacion(
        clase="contenido", titulo="Apagada", marca="unotv", origen="rss",
    )
    pc.ejecutar_redactar(autor=None)
    assert lanzadas == []


# --------------------------------------------------------------------------- #
# Etapa de ILUSTRAR del pipeline (toggle "Generar arte", KENI_PIPELINE_ILUSTRAR)    #
# --------------------------------------------------------------------------- #


def test_ejecutar_arte_off_por_defecto_no_hace_nada(entorno, monkeypatch):
    """Sin `KENI_PIPELINE_ILUSTRAR`, la etapa de Ilustrar no ilustra (devuelve [])."""
    monkeypatch.delenv(config.ENV_PIPELINE_ILUSTRAR, raising=False)
    monkeypatch.setenv(config.ENV_MAQUINA, "1")
    assert pc.ejecutar_ilustrar() == []


def test_ejecutar_arte_gateado_corre_seleccion_y_lanzamiento(entorno, monkeypatch):
    """Con el toggle + máquina ON y proveedor configurado, ilustra vía autogen_ilustrar."""
    from keni_consola import autogen_ilustrar

    monkeypatch.setenv(config.ENV_MAQUINA, "1")
    monkeypatch.setenv(config.ENV_PIPELINE_ILUSTRAR, "1")
    monkeypatch.setattr(autogen_ilustrar.media, "proveedor_configurado", lambda: True)
    item = {"id": "t1", "titulo": "Tema", "marca": "unotv"}
    monkeypatch.setattr(pc.repos, "listar_publicacion", lambda **_k: [item])
    monkeypatch.setattr(autogen_ilustrar, "_plataformas_por_item", lambda items: {})
    monkeypatch.setattr(autogen_ilustrar, "ids_ya_procesados", lambda: set())
    monkeypatch.setattr(autogen_ilustrar, "_etiquetas_por_item", lambda: {})
    monkeypatch.setattr(autogen_ilustrar, "topics_sin_arte", lambda *a, **k: [item])
    adjuntados: list[str] = []
    monkeypatch.setattr(
        autogen_ilustrar, "lanzar_para_topic",
        lambda it: adjuntados.append(it["id"]) or {"publicacion_id": it["id"]},
    )
    res = pc.ejecutar_ilustrar()
    assert adjuntados == ["t1"]
    assert len(res) == 1


def test_ejecutar_arte_sin_proveedor_no_ilustra(entorno, monkeypatch):
    """Con el toggle ON pero sin proveedor de imagen, la etapa de Ilustrar no hace nada."""
    from keni_consola import media

    monkeypatch.setenv(config.ENV_MAQUINA, "1")
    monkeypatch.setenv(config.ENV_PIPELINE_ILUSTRAR, "1")
    monkeypatch.setattr(media, "proveedor_configurado", lambda: False)
    assert pc.ejecutar_ilustrar() == []


# --------------------------------------------------------------------------- #
# Diversidad en la promoción (MMR suave) + estado protegido en el upsert       #
# --------------------------------------------------------------------------- #


def test_clusters_para_promover_diversifica_titulos_casi_identicos(entorno):
    """Un macro-tema (dos historias casi idénticas) no se come todas las plazas del barrido."""
    _inicializar_cluster("dup1", titulo="Messi gana el premio en París", score=0.9,
                     verificacion_fuente=pc.VERIFICACION_VERIFICADO)
    _inicializar_cluster("dup2", titulo="Messi gana el premio en París hoy", score=0.8,
                     verificacion_fuente=pc.VERIFICACION_VERIFICADO)
    _inicializar_cluster("otra", titulo="Sismo de magnitud en la capital", score=0.5,
                     verificacion_fuente=pc.VERIFICACION_VERIFICADO)

    elegidos = pc.clusters_para_promover("unotv", maximo=2)

    assert [c["id"] for c in elegidos] == ["dup1", "otra"]  # el casi-duplicado cede su plaza


def test_clusters_para_promover_suave_rellena_si_solo_hay_duplicados(entorno):
    """Si todo el pool es el mismo macro-tema, se rellena igual (nunca devuelve menos)."""
    _inicializar_cluster("dup1", titulo="Messi gana el premio en París", score=0.9,
                     verificacion_fuente=pc.VERIFICACION_VERIFICADO)
    _inicializar_cluster("dup2", titulo="Messi gana el premio en París hoy", score=0.8,
                     verificacion_fuente=pc.VERIFICACION_VERIFICADO)
    elegidos = pc.clusters_para_promover("unotv", maximo=2)
    assert {c["id"] for c in elegidos} == {"dup1", "dup2"}


# --------------------------------------------------------------------------- #
# UMBRAL de producción automática: promover cuesta tokens (Verificar+copy con IA); #
# el ruido se queda en el pool aunque haya plazas libres.                       #
# --------------------------------------------------------------------------- #


def test_clusters_para_promover_respeta_el_umbral(entorno):
    """Solo las historias que superan el umbral compiten por plaza; el ruido queda en el pool."""
    from datetime import UTC, datetime, timedelta

    # Todas VERIFICADAS (pasaron la verificación): así el ÚNICO discriminante de la promoción es el
    # umbral, no el filtro de Verificar (que ya verificó a todas por igual).
    _inicializar_cluster("apta", titulo="Sismo sacude la CDMX", score=0.9,
                     verificacion_fuente=pc.VERIFICACION_VERIFICADO)
    # Sin encaje de marca: ni el título ni el resumen casan el vocabulario unotv.
    _inicializar_cluster(
        "irrelevante", titulo="Gossip de celebridades en Hollywood", score=0.8,
        resumen="Rumores del espectáculo extranjero", verificacion_fuente=pc.VERIFICACION_VERIFICADO,
    )
    # Verificación dudosa: jamás dispara producción automática, puntúe lo que puntúe.
    _inicializar_cluster("dudosa", titulo="Increíble suceso en México hoy", score=0.7,
                     verificacion="dudosa", verificacion_fuente=pc.VERIFICACION_VERIFICADO)
    # Vieja sin señales: su score persistido era alto, pero el umbral recalcula AHORA.
    _inicializar_cluster(
        "vieja", titulo="México: nota de hace una semana", score=0.95, n_fuentes=1,
        ultimo_visto=(datetime.now(UTC) - timedelta(days=7)).replace(tzinfo=None)
        .isoformat(timespec="seconds"), verificacion_fuente=pc.VERIFICACION_VERIFICADO,
    )

    elegidos = pc.clusters_para_promover("unotv", maximo=4)

    # Hay 4 plazas, pero solo la apta supera el umbral (el resto NO rellena plazas libres).
    assert [c["id"] for c in elegidos] == ["apta"]


def test_promover_clusters_marca_no_promueve_bajo_umbral(entorno, monkeypatch):
    """El barrido ADMITIR deja en el pool (estado `nuevo`) lo que no supera el umbral: ni tema ni copy."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    _inicializar_cluster("apta", titulo="Sismo sacude la CDMX", score=0.9,
                     verificacion_fuente=pc.VERIFICACION_VERIFICADO)
    _inicializar_cluster(
        "irrelevante", titulo="Gossip de celebridades en Hollywood", score=0.8,
        resumen="Rumores del espectáculo extranjero", verificacion_fuente=pc.VERIFICACION_VERIFICADO,
    )

    temas = pc.promover_clusters_marca("unotv", maximo=2)

    assert [t["titulo"] for t in temas] == ["Sismo sacude la CDMX"]
    assert repos.obtener_noticia_cluster("apta")["estado"] == "usado"
    # La irrelevante sigue `nuevo`: visible en el panel, usable a mano, expirable por edad.
    assert repos.obtener_noticia_cluster("irrelevante")["estado"] == "nuevo"


def test_upsert_cluster_no_revierte_estado_ni_contenido_id(entorno):
    """Anti-TOCTOU daemon↔pipeline: un recalc del daemon (upsert con datos stale) NO puede
    devolver a 'nuevo' una historia ya promovida ni borrar su enlace al tema."""
    _inicializar_cluster("c1", titulo="Historia promovida", score=0.7)
    repos.actualizar_noticia_cluster("c1", estado="usado", publicacion_id="tema-77")

    # El daemon recalcula con una foto VIEJA (estado 'nuevo', sin publicacion_id) y upsertea.
    stale = dict(repos.obtener_noticia_cluster("c1"), estado="nuevo", publicacion_id="", score=0.9)
    repos.upsert_noticia_cluster(stale)

    tras = repos.obtener_noticia_cluster("c1")
    assert tras["estado"] == "usado"          # el estado promovido NO se revierte
    assert tras["publicacion_id"] == "tema-77"  # el enlace al tema NO se pierde
    assert tras["score"] == 0.9               # los agregados sí se actualizan


# --------------------------------------------------------------------------- #
# Encadenado copy→arte por eventos + reparadores y helpers SQL del pipeline      #
# --------------------------------------------------------------------------- #


def test_encadenar_arte_tras_copy_ilustra_ese_tema(entorno, monkeypatch):
    """El post-procesado del copy dispara ILUSTRAR de ESE tema al instante (gates ON)."""
    from keni_consola import autogen_ilustrar, media

    monkeypatch.setenv(config.ENV_MAQUINA, "1")
    monkeypatch.setenv(config.ENV_PIPELINE_ILUSTRAR, "1")
    monkeypatch.setattr(media, "proveedor_configurado", lambda: True)
    monkeypatch.setattr(autogen_ilustrar, "ids_ya_procesados", lambda: set())
    lanzados: list[str] = []
    monkeypatch.setattr(
        autogen_ilustrar, "lanzar_para_topic",
        lambda it: lanzados.append(it["id"]) or {"publicacion_id": it["id"]},
    )
    tema = repos.crear_publicacion(
        clase="contenido", titulo="Ilustrable", marca="unotv", origen=pc.ORIGEN_PIPELINE,
    )

    res = pc.encadenar_ilustrar_tras_redactar(tema["id"])

    assert lanzados == [tema["id"]]
    assert res is not None


def test_encadenar_arte_tras_copy_respeta_gates(entorno, monkeypatch):
    """Con el toggle de arte OFF (o el tema ya ilustrado) el encadenado NO lanza nada."""
    from keni_consola import autogen_ilustrar, media

    # Toggle OFF: ni siquiera consulta el tema.
    monkeypatch.delenv(config.ENV_PIPELINE_ILUSTRAR, raising=False)
    monkeypatch.setenv(config.ENV_MAQUINA, "1")
    assert pc.encadenar_ilustrar_tras_redactar("cualquiera") is None

    # Toggle ON pero tema YA ilustrado (dedup por etiqueta): tampoco.
    monkeypatch.setenv(config.ENV_PIPELINE_ILUSTRAR, "1")
    monkeypatch.setattr(media, "proveedor_configurado", lambda: True)
    tema = repos.crear_publicacion(
        clase="contenido", titulo="Ya ilustrado", marca="unotv", origen=pc.ORIGEN_PIPELINE,
    )
    monkeypatch.setattr(autogen_ilustrar, "ids_ya_procesados", lambda: {tema["id"]})
    monkeypatch.setattr(
        autogen_ilustrar, "lanzar_para_topic",
        lambda it: (_ for _ in ()).throw(AssertionError("no debe ilustrar un tema ya hecho")),
    )
    assert pc.encadenar_ilustrar_tras_redactar(tema["id"]) is None


def test_reparar_verificacion_en_curso_sueltos_resetea_solo_viejos(entorno):
    """El reparador devuelve a re-verificación ('') SOLO los `en_curso` más viejos que el umbral.

    Cierra el ATASCADA: si la verificación muere sin finalizador, el tema quedaba `en_curso` para
    siempre (sin re-verificar y contando en el cupo en proceso de su marca).
    NOTA: el limpiador usa ahora su reparación PER-TEMA (`limpiador_generaciones._reparar_verificacion_en_curso`,
    con WARN por tema y destino según el toggle); esta primitiva SQL en lote sigue en repos.
    """
    from keni_consola import db

    atascada = _tema_pipeline(titulo="Atascada", verificacion_fuente=pc.VERIFICACION_EN_CURSO)
    vivo = _tema_pipeline(titulo="Vivo", verificacion_fuente=pc.VERIFICACION_EN_CURSO)
    # Envejecemos el `actualizado` del atascada más allá del umbral (el del vivo queda reciente).
    con = db._conectar()
    try:
        con.execute(
            "UPDATE publicacion SET actualizado = ? WHERE id = ?",
            ("2020-01-01T00:00:00", atascada["id"]),
        )
        con.commit()
    finally:
        con.close()

    n = repos.reparar_verificacion_en_curso_sueltos("2025-01-01T00:00:00")

    assert n == 1
    assert (repos.obtener_publicacion(atascada["id"])["verificacion_fuente"] or "") == ""  # a re-verificación
    assert repos.obtener_publicacion(vivo["id"])["verificacion_fuente"] == pc.VERIFICACION_EN_CURSO  # intacto


def _envejecer_actualizado(tema_id, fecha="2020-01-01T00:00:00"):
    """Retrasa el `actualizado` de un tema (lo vuelve atascada para los reparadores)."""
    from keni_consola import db

    con = db._conectar()
    try:
        con.execute("UPDATE publicacion SET actualizado = ? WHERE id = ?", (fecha, tema_id))
        con.commit()
    finally:
        con.close()


def test_limpiador_verificacion_atascada_re_verificacion_con_validacion_activa(entorno, monkeypatch):
    """El reparación del limpiador devuelve a re-verificación ('') SOLO los `en_curso` atascadas (per-tema)."""
    from keni_consola import limpiador_generaciones

    monkeypatch.setenv("KENI_PIPELINE_VERIFICAR", "1")
    atascada = _tema_pipeline(titulo="Atascada", verificacion_fuente=pc.VERIFICACION_EN_CURSO)
    vivo = _tema_pipeline(titulo="Vivo", verificacion_fuente=pc.VERIFICACION_EN_CURSO)
    _envejecer_actualizado(atascada["id"])

    n = limpiador_generaciones._reparar_verificacion_en_curso()

    assert n == 1
    assert (repos.obtener_publicacion(atascada["id"])["verificacion_fuente"] or "") == ""  # a re-verificación
    assert repos.obtener_publicacion(vivo["id"])["verificacion_fuente"] == pc.VERIFICACION_EN_CURSO  # intacto


def test_limpiador_verificacion_atascada_saltada_con_validacion_apagada(entorno, monkeypatch):
    """Con la etapa de Verificar APAGADA, el atascada pasa a 'saltada' (REDACTAR lo recoge), no a re-verificación."""
    from keni_consola import limpiador_generaciones

    monkeypatch.delenv("KENI_PIPELINE_VERIFICAR", raising=False)  # etapa off (def)
    atascada = _tema_pipeline(titulo="Atascada sin verificación", verificacion_fuente=pc.VERIFICACION_EN_CURSO)
    _envejecer_actualizado(atascada["id"])

    n = limpiador_generaciones._reparar_verificacion_en_curso()

    assert n == 1
    assert repos.obtener_publicacion(atascada["id"])["verificacion_fuente"] == pc.VERIFICACION_SALTADA


def test_ejecutar_arte_fallo_masivo_emite_un_error_agregado(entorno, monkeypatch, caplog):
    """>50% de lanzamientos de arte fallidos en un ciclo -> UN único ERROR agregado (proveedor)."""
    import logging

    from keni_consola import autogen_ilustrar

    monkeypatch.setenv(config.ENV_MAQUINA, "1")
    monkeypatch.setenv(config.ENV_PIPELINE_ILUSTRAR, "1")
    monkeypatch.setattr(autogen_ilustrar.media, "proveedor_configurado", lambda: True)
    items = [
        {"id": "t1", "titulo": "Tema 1", "marca": "unotv"},
        {"id": "t2", "titulo": "Tema 2", "marca": "unotv"},
    ]
    monkeypatch.setattr(pc.repos, "listar_publicacion", lambda **_k: items)
    monkeypatch.setattr(autogen_ilustrar, "_plataformas_por_item", lambda items: {})
    monkeypatch.setattr(autogen_ilustrar, "ids_ya_procesados", lambda: set())
    monkeypatch.setattr(autogen_ilustrar, "_etiquetas_por_item", lambda: {})
    monkeypatch.setattr(autogen_ilustrar, "topics_sin_arte", lambda *a, **k: list(items))
    monkeypatch.setattr(
        autogen_ilustrar, "lanzar_para_topic",
        lambda it: (_ for _ in ()).throw(RuntimeError("proveedor caído")),
    )

    with caplog.at_level(logging.ERROR, logger="keni_consola.pipeline_contenido"):
        res = pc.ejecutar_ilustrar()

    assert res == []
    agregados = [
        r for r in caplog.records
        if r.levelno == logging.ERROR and "fallido(s) en este barrido" in r.getMessage()
    ]
    assert len(agregados) == 1
    assert "2/2" in agregados[0].getMessage()
    # Correlación: el resumen lista los temas afectados.
    assert "t1" in agregados[0].getMessage() and "t2" in agregados[0].getMessage()


def test_ejecutar_arte_fallo_aislado_sin_error_agregado(entorno, monkeypatch, caplog):
    """Un fallo de arte AISLADO (<=50% del ciclo) no dispara la señal de proveedor caído."""
    import logging

    from keni_consola import autogen_ilustrar

    monkeypatch.setenv(config.ENV_MAQUINA, "1")
    monkeypatch.setenv(config.ENV_PIPELINE_ILUSTRAR, "1")
    monkeypatch.setattr(autogen_ilustrar.media, "proveedor_configurado", lambda: True)
    items = [
        {"id": "t1", "titulo": "Tema 1", "marca": "unotv"},
        {"id": "t2", "titulo": "Tema 2", "marca": "unotv"},
    ]
    monkeypatch.setattr(pc.repos, "listar_publicacion", lambda **_k: items)
    monkeypatch.setattr(autogen_ilustrar, "_plataformas_por_item", lambda items: {})
    monkeypatch.setattr(autogen_ilustrar, "ids_ya_procesados", lambda: set())
    monkeypatch.setattr(autogen_ilustrar, "_etiquetas_por_item", lambda: {})
    monkeypatch.setattr(autogen_ilustrar, "topics_sin_arte", lambda *a, **k: list(items))

    def _solo_t1_falla(it):
        if it["id"] == "t1":
            raise RuntimeError("fallo puntual")
        return {"publicacion_id": it["id"]}

    monkeypatch.setattr(autogen_ilustrar, "lanzar_para_topic", _solo_t1_falla)

    with caplog.at_level(logging.ERROR, logger="keni_consola.pipeline_contenido"):
        res = pc.ejecutar_ilustrar()

    assert len(res) == 1  # t2 sí se ilustró
    assert not [
        r for r in caplog.records
        if r.levelno == logging.ERROR and "fallido(s) en este barrido" in r.getMessage()
    ]


def test_ids_contenido_con_copy_filtra_por_marca(entorno):
    """`ids_publicacion_con_copy` empuja el filtro a SQL: solo ids con pieza con copy redactado."""
    a = repos.crear_publicacion(clase="contenido", titulo="A", marca="unotv")
    b = repos.crear_publicacion(clase="contenido", titulo="B", marca="claro-sports")
    sin_copy = repos.crear_publicacion(clase="contenido", titulo="C", marca="unotv")
    repos.crear_pieza_fila(publicacion_id=a["id"], red="x", copy="hola")
    repos.crear_pieza_fila(publicacion_id=b["id"], red="x", copy="hola")
    repos.crear_pieza_fila(publicacion_id=sin_copy["id"], red="x", copy="")

    assert repos.ids_publicacion_con_copy("unotv") == {a["id"]}
    assert {a["id"], b["id"]} <= repos.ids_publicacion_con_copy()
    assert sin_copy["id"] not in repos.ids_publicacion_con_copy()


def test_listar_contenido_origenes_filtra_en_sql(entorno):
    """`listar_publicaciones_origenes` trae solo los orígenes pedidos y excluye el estado dado."""
    rss = repos.crear_publicacion(clase="contenido", titulo="R", marca="unotv", origen="rss")
    repos.crear_publicacion(clase="contenido", titulo="M", marca="unotv", origen="")
    hecho = repos.crear_publicacion(clase="contenido", titulo="H", marca="unotv", origen="rss")
    repos.actualizar_publicacion(hecho["id"], {"estado": "hecha"})

    ids = {t["id"] for t in repos.listar_publicaciones_origenes(["rss"], excluir_estado="hecha")}
    assert ids == {rss["id"]}
    # Sin exclusión, el 'hecha' también sale; con lista vacía, nada (y sin query).
    assert hecho["id"] in {t["id"] for t in repos.listar_publicaciones_origenes(["rss"])}
    assert repos.listar_publicaciones_origenes([]) == []


def test_lanzar_para_topic_sella_pipeline_y_marcador_redactar(entorno, monkeypatch):
    """El copy de un tema del TABLERO es trabajo del PIPELINE: se lanza `tipo='pipeline'`
    (no el legado "autogen") y deja el marcador de etapa Redactar correlacionado al tema, para que
    Producción lo muestre dentro de la run (stream en el detalle + métricas sumadas)."""
    from keni_consola import autogen_redactar

    capturas: dict[str, object] = {}

    def _fake_lanzar_copy(**kwargs):
        capturas.update(kwargs)
        return {"id": "gen-tablero-1"}

    monkeypatch.setattr(autogen_redactar.dom_generar, "lanzar_copy", _fake_lanzar_copy)
    marcadores: list[tuple] = []
    monkeypatch.setattr(
        pc, "registrar_etapa",
        lambda etapa, marca, detalle, publicacion_id="", gen_id="": marcadores.append(
            (etapa, marca, detalle, publicacion_id, gen_id)
        ),
    )

    item = {"id": "tema-tablero", "marca": "unotv", "origen": "equipo",
            "titulo": "Nota del equipo", "descripcion": "La nota."}
    gen = autogen_redactar.lanzar_para_topic(item)

    assert gen == {"id": "gen-tablero-1"}
    assert capturas["tipo"] == "pipeline"
    assert capturas["publicacion_id"] == "tema-tablero"
    assert capturas["titulo"] == "Nota del equipo"  # etiqueta legible, no "Auto-copy"
    assert len(marcadores) == 1
    etapa, marca, detalle, publicacion_id, gen_id = marcadores[0]
    assert etapa == pc.ETAPA_REDACTAR
    assert marca == "unotv"
    assert publicacion_id == "tema-tablero"
    assert gen_id == "gen-tablero-1"


def test_auto_etiquetar_linea_hereda_la_linea_del_feed(entorno):
    """Sin match del clasificador, la pieza hereda la LÍNEA del feed del que nació."""
    from keni_consola.pipeline_contenido import _admitir

    # Línea de la marca + feed enganchado a ella (sin keywords -> el clasificador no casa).
    linea = repos.crear_etiqueta(nombre="Nacional", clase="vertical", marca="unotv")
    feed = repos.crear_fuente_rss(
        "Diario", "https://e.example/f.xml", marca="unotv", linea_id=linea["id"]
    )
    # _linea_de_feed resuelve fuente_id -> linea_id del feed.
    assert _admitir._linea_de_feed([{"fuente_id": feed["id"]}]) == linea["id"]
    assert _admitir._linea_de_feed([]) == ""
    # Una pieza sin línea por keywords cae a la del feed (no al aviso "Sin línea").
    tema = repos.crear_publicacion(
        clase="contenido", titulo="Nota sin keywords", descripcion="cuerpo", marca="unotv"
    )
    _admitir._auto_etiquetar_linea(tema, "Nota sin keywords", "cuerpo", linea_feed=linea["id"])
    assert tema["id"] in repos.ids_contenido_con_etiqueta(linea["id"])
