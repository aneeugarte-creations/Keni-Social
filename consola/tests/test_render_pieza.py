"""Tests OFFLINE de `dominio.render_pieza`: resolución de la imagen on-demand desde la receta.

No tocan Node ni la BD: mockean `estudio_imagen.componer_desde_plantilla`/`_bytes`,
`estudio_imagen.marca_tiene_plantilla` (el spec, BARATO) y `repos.listar/obtener_plantilla_diseno`.
Verifican la PRECEDENCIA de la receta (imagen bespoke > placa oculta > plantilla del estudio >
foto cruda) y la URL servible que decide la serialización. SOLO componen plantillas de la galería
del estudio: la placa de marca por SPEC (legada) ya NO se compone —si la marca tiene spec pero no
hay plantilla de estudio resoluble, `/compuesta` sirve la FOTO cruda.
"""

from __future__ import annotations

from keni_consola import media, repos
from keni_consola.dominio import estudio_imagen, render_pieza


def _sin_plantilla_de_marca(monkeypatch, valor=False):
    """Controla si la marca tiene plantilla de ESTUDIO (`valor=True`) o no -> decide `tiene_receta`.

    Parchea `render_pieza.marca_tiene_plantilla_estudio`, que es lo que `tiene_receta` usa cuando la
    pieza no fija una `plantilla_diseno_id` explícita. (Ese helper consulta el almacén en prod; aquí
    lo cortocircuitamos para no tocar BD.)
    """
    monkeypatch.setattr(render_pieza, "marca_tiene_plantilla_estudio", lambda marca: valor)


def _sin_plantillas_estudio(monkeypatch):
    """La marca no tiene plantillas de estudio: `_plantilla_efectiva` no halla la por defecto."""
    monkeypatch.setattr(repos, "listar_plantillas_diseno", lambda **k: [])


# --------------------------------------------------------------------------- #
# tiene_receta                                                                 #
# --------------------------------------------------------------------------- #


def test_tiene_receta_placa_oculta_es_falso(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, True)
    assert render_pieza.tiene_receta({"placa_oculta": True, "marca": "unotv"}) is False


def test_tiene_receta_por_plantilla_del_estudio(monkeypatch):
    # No necesita mirar la marca: con plantilla del estudio ya hay receta.
    _sin_plantilla_de_marca(monkeypatch, False)
    assert render_pieza.tiene_receta({"plantilla_diseno_id": "pl-1", "marca": "x"}) is True


def test_tiene_receta_por_placa_de_marca(monkeypatch):
    # Sin `plantilla_diseno_id` explícito: hay receta si la marca tiene placa configurada (spec).
    _sin_plantilla_de_marca(monkeypatch, True)
    assert render_pieza.tiene_receta({"marca": "unotv"}) is True


def test_tiene_receta_marca_sin_plantilla(monkeypatch):
    # Marca sin placa (spec): sin receta -> publica la foto cruda.
    _sin_plantilla_de_marca(monkeypatch, False)
    assert render_pieza.tiene_receta({"marca": "piso-15"}) is False


# --------------------------------------------------------------------------- #
# imagen_compuesta_id                                                          #
# --------------------------------------------------------------------------- #


def test_imagen_bespoke_se_respeta(monkeypatch):
    # `imagen` horneada SIN receta viva (editor pro / legacy): se devuelve tal cual sin recomponer.
    _sin_plantilla_de_marca(monkeypatch, False)

    def _boom(*a, **k):
        raise AssertionError("no debe componer si ya hay imagen")

    monkeypatch.setattr(estudio_imagen, "componer", _boom)
    assert render_pieza.imagen_compuesta_id({"imagen": "horneada.png"}) == "horneada.png"


def test_receta_viva_gana_a_imagen_vieja(monkeypatch):
    # Pieza NO publicada con receta (marca con plantilla de estudio por defecto) + un PNG viejo
    # horneado: la RECETA manda, se RECOMPONE vía `componer_desde_plantilla` (el feed refleja la
    # plantilla actual, no la placa vieja). Es el bug del feed.
    _sin_plantilla_de_marca(monkeypatch, True)
    monkeypatch.setattr(
        repos, "listar_plantillas_diseno",
        lambda **k: [{"id": "verde", "nombre": "UnoTV - Verde", "documento": "{\"v\":1}"}],
    )
    monkeypatch.setattr(
        estudio_imagen, "componer_desde_plantilla",
        lambda *a, **k: {"id": "fresca.png", "url": "/api/media/fresca.png"},
    )
    pub = {"id": "p1", "imagen": "vieja.png", "marca": "unotv", "red": "x",
           "copy_in": "T", "foto": "f.jpg", "foto_encuadre": "", "estado": "en_revision"}
    assert render_pieza.imagen_compuesta_id(pub) == "fresca.png"
    assert render_pieza.imagen_url_de(pub) == "/api/publicaciones/p1/compuesta"


def test_publicada_conserva_imagen_congelada(monkeypatch):
    # Una pieza PUBLICADA conserva su `imagen` CONGELADA (registro exacto de lo posteado), aunque
    # tenga receta: NO se recompone.
    _sin_plantilla_de_marca(monkeypatch, True)

    def _boom(*a, **k):
        raise AssertionError("una pieza publicada no debe recomponer")

    monkeypatch.setattr(estudio_imagen, "componer", _boom)
    pub = {"id": "p1", "imagen": "posteada.png", "marca": "unotv", "red": "x",
           "copy_in": "T", "foto": "f.jpg", "estado": "publicado"}
    assert render_pieza.imagen_compuesta_id(pub) == "posteada.png"
    assert render_pieza.imagen_url_de(pub) == "/api/media/posteada.png"


def test_placa_oculta_devuelve_foto(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, True)
    pub = {"imagen": "", "placa_oculta": True, "foto": "foto.jpg", "marca": "unotv"}
    assert render_pieza.imagen_compuesta_id(pub) == "foto.jpg"


def test_sin_receta_devuelve_foto(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, False)
    pub = {"imagen": "", "foto": "foto.jpg", "marca": "piso-15"}
    assert render_pieza.imagen_compuesta_id(pub) == "foto.jpg"


def test_sin_plantilla_de_estudio_devuelve_foto(monkeypatch):
    # Marca CON spec (tiene_receta True) pero SIN plantilla de estudio resoluble: ya NO se compone
    # la placa por SPEC (retirada) -> devuelve la FOTO cruda, sin llamar a `estudio_imagen.componer`.
    _sin_plantilla_de_marca(monkeypatch, True)
    _sin_plantillas_estudio(monkeypatch)

    def _boom(*a, **k):
        raise AssertionError("no debe componer la placa por SPEC (retirada)")

    monkeypatch.setattr(estudio_imagen, "componer", _boom)
    pub = {"imagen": "", "foto": "f.jpg", "marca": "unotv", "red": "instagram", "copy_in": "TITULAR"}
    assert render_pieza.imagen_compuesta_id(pub) == "f.jpg"


def test_sin_plantilla_explicita_usa_la_por_defecto_de_la_marca(monkeypatch):
    # Sin `plantilla_diseno_id`, el render usa la plantilla de estudio POR DEFECTO de la marca
    # (la MISMA que el editor: la primera del listado), NO la placa por SPEC. Así feed == editor.
    _sin_plantilla_de_marca(monkeypatch, True)
    monkeypatch.setattr(
        repos, "listar_plantillas_diseno",
        lambda **k: [{"id": "verde", "nombre": "UnoTV - Verde", "documento": "{\"v\":1}"}],
    )

    def _no_spec(*a, **k):
        raise AssertionError("no debe usar la placa por SPEC si hay plantilla de estudio")

    monkeypatch.setattr(estudio_imagen, "componer", _no_spec)
    capt = {}

    def _desde(documento, *, copy_in, fotos):
        capt.update(documento=documento, copy_in=copy_in, fotos=fotos)
        return {"id": "verde.png", "url": "/api/media/verde.png"}

    monkeypatch.setattr(estudio_imagen, "componer_desde_plantilla", _desde)
    pub = {"id": "p1", "imagen": "", "marca": "unotv", "red": "instagram",
           "copy_in": "T", "foto": "f.jpg", "foto_encuadre": "", "estado": "en_revision"}
    assert render_pieza.imagen_compuesta_id(pub) == "verde.png"
    assert capt["documento"] == "{\"v\":1}" and capt["copy_in"] == "T"
    # Sin collage: el hueco único deriva de la foto legada.
    assert capt["fotos"] == [{"objeto": "f.jpg", "foco": None, "zoom": 0.0}]


def test_prefiere_plantilla_llamada_placa_de_marca(monkeypatch):
    # Si existe una plantilla "Placa de marca", se prefiere sobre la primera (igual que el editor).
    _sin_plantilla_de_marca(monkeypatch, True)
    monkeypatch.setattr(
        repos, "listar_plantillas_diseno",
        lambda **k: [
            {"id": "verde", "nombre": "UnoTV - Verde", "documento": "{\"v\":1}"},
            {"id": "placa", "nombre": "Placa de marca", "documento": "{\"v\":2}"},
        ],
    )
    capt = {}
    monkeypatch.setattr(
        estudio_imagen, "componer_desde_plantilla",
        lambda documento, **k: capt.update(documento=documento) or {"id": "x.png", "url": "/x"},
    )
    pub = {"id": "p1", "imagen": "", "marca": "unotv", "red": "x", "copy_in": "", "foto": "f.jpg"}
    render_pieza.imagen_compuesta_id(pub)
    assert capt["documento"] == "{\"v\":2}"  # la "Placa de marca", no la primera


def test_en_rotacion_manda_sobre_la_por_defecto(monkeypatch):
    # Una pieza SIN `plantilla_diseno_id` (legada, creada antes de marcar la rotación): si la marca
    # tiene una plantilla EN ROTACIÓN, el render adopta ESA —no la "Placa de marca" ni la primera—.
    _sin_plantilla_de_marca(monkeypatch, True)
    monkeypatch.setattr(
        repos, "listar_plantillas_diseno",
        lambda **k: [
            {"id": "placa", "nombre": "Placa de marca", "documento": "{\"v\":1}", "rotar": False, "activo": True},
            {"id": "rot", "nombre": "Claro - Azul", "documento": "{\"v\":9}", "rotar": True, "activo": True},
        ],
    )
    capt = {}
    monkeypatch.setattr(
        estudio_imagen, "componer_desde_plantilla",
        lambda documento, **k: capt.update(documento=documento) or {"id": "x.png", "url": "/x"},
    )
    pub = {"id": "p1", "imagen": "", "marca": "claro-sports", "red": "x", "copy_in": "", "foto": "f.jpg"}
    render_pieza.imagen_compuesta_id(pub)
    assert capt["documento"] == "{\"v\":9}"  # la EN ROTACIÓN, no la "Placa de marca"


def test_en_rotacion_inactiva_no_cuenta(monkeypatch):
    # Una plantilla con `rotar=1` pero INACTIVA no se elige como default (igual que la rotación al
    # crear, que pide `activo=1`): cae a la "Placa de marca" / primera.
    _sin_plantilla_de_marca(monkeypatch, True)
    monkeypatch.setattr(
        repos, "listar_plantillas_diseno",
        lambda **k: [
            {"id": "placa", "nombre": "Placa de marca", "documento": "{\"v\":1}", "rotar": False, "activo": True},
            {"id": "rot", "nombre": "Claro - Azul", "documento": "{\"v\":9}", "rotar": True, "activo": False},
        ],
    )
    capt = {}
    monkeypatch.setattr(
        estudio_imagen, "componer_desde_plantilla",
        lambda documento, **k: capt.update(documento=documento) or {"id": "x.png", "url": "/x"},
    )
    pub = {"id": "p1", "imagen": "", "marca": "claro-sports", "red": "x", "copy_in": "", "foto": "f.jpg"}
    render_pieza.imagen_compuesta_id(pub)
    assert capt["documento"] == "{\"v\":1}"  # la inactiva se ignora -> "Placa de marca"


def test_plantilla_del_estudio_compone_desde_plantilla(monkeypatch):
    monkeypatch.setattr(repos, "obtener_plantilla_diseno", lambda pid: {"documento": "{}"})
    capt = {}

    def _desde(documento, *, copy_in, fotos):
        capt.update(copy_in=copy_in, fotos=fotos)
        return {"id": "doc.png", "url": "/api/media/doc.png"}

    monkeypatch.setattr(estudio_imagen, "componer_desde_plantilla", _desde)
    pub = {"imagen": "", "plantilla_diseno_id": "pl-1", "foto": "f.jpg",
           "copy_in": "X", "marca": "unotv", "foto_encuadre": ""}
    assert render_pieza.imagen_compuesta_id(pub) == "doc.png"
    assert capt == {"copy_in": "X", "fotos": [{"objeto": "f.jpg", "foco": None, "zoom": 0.0}]}


def test_fotos_de_pieza_collage_desde_json(monkeypatch):
    # Con el campo `fotos` (JSON), se devuelve una foto por hueco (collage); ignora la foto legada.
    pub = {"fotos": '[{"objeto":"a.jpg","foco":[0.3,0.7],"zoom":1.5},{"objeto":"b.jpg"}]',
           "foto": "vieja.jpg"}
    fotos = render_pieza.fotos_de_pieza(pub)
    assert fotos == [
        {"objeto": "a.jpg", "foco": [0.3, 0.7], "zoom": 1.5},
        {"objeto": "b.jpg", "foco": None, "zoom": 0.0},
    ]


def test_fotos_de_pieza_legado_hueco_unico(monkeypatch):
    # Sin `fotos`, el hueco único se deriva de `foto` + `foto_encuadre`.
    pub = {"fotos": "", "foto": "f.jpg", "foto_encuadre": '{"foco":[0.5,0.5],"zoom":2.0}'}
    assert render_pieza.fotos_de_pieza(pub) == [{"objeto": "f.jpg", "foco": [0.5, 0.5], "zoom": 2.0}]


def test_plantilla_borrada_cae_a_la_foto_cruda(monkeypatch):
    # Si la plantilla EXPLÍCITA elegida ya no existe (`obtener_plantilla_diseno` -> None),
    # `_plantilla_efectiva` no resuelve ninguna plantilla de estudio y el render cae a la FOTO
    # cruda (ya NO existe la placa de marca por SPEC). Con `plantilla_diseno_id` puesto, hay receta
    # (no se mira la marca) pero la plantilla no compone.
    monkeypatch.setattr(repos, "obtener_plantilla_diseno", lambda pid: None)
    pub = {"imagen": "", "plantilla_diseno_id": "pl-borrada", "foto": "f.jpg",
           "marca": "unotv", "red": "x", "copy_in": "Y"}
    assert render_pieza.imagen_compuesta_id(pub) == "f.jpg"


# --------------------------------------------------------------------------- #
# imagen_url_de (decisión barata, sin componer)                                #
# --------------------------------------------------------------------------- #


def test_url_imagen_horneada(monkeypatch):
    # Imagen horneada SIN receta viva (bespoke/legacy): se sirve desde media.
    _sin_plantilla_de_marca(monkeypatch, False)
    assert render_pieza.imagen_url_de({"id": "p1", "imagen": "h.png"}) == "/api/media/h.png"


def test_url_receta_apunta_a_compuesta(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, True)
    pub = {"id": "p1", "imagen": "", "marca": "unotv"}
    assert render_pieza.imagen_url_de(pub) == "/api/publicaciones/p1/compuesta"


def test_url_compuesta_lleva_sufijo_cache_por_actualizado(monkeypatch):
    # Con `actualizado`, la URL del render lleva `?v=...` (cache-bust): cambia al editar la pieza
    # (p. ej. subir foto), forzando al feed a recargar la imagen en vez de servir la cacheada.
    _sin_plantilla_de_marca(monkeypatch, True)
    base = {"id": "p1", "imagen": "", "marca": "unotv"}
    u1 = render_pieza.imagen_url_de({**base, "actualizado": "2026-06-04T10:00:00"})
    u2 = render_pieza.imagen_url_de({**base, "actualizado": "2026-06-04T11:30:00"})
    assert u1.startswith("/api/publicaciones/p1/compuesta?v=")
    assert u1 != u2  # otro `actualizado` => otra URL => el navegador recarga


def test_url_solo_foto(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, False)
    pub = {"id": "p1", "imagen": "", "marca": "piso-15", "foto": "f.jpg"}
    assert render_pieza.imagen_url_de(pub) == "/api/media/f.jpg"


def test_url_fuente_externa(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, False)
    pub = {"id": "p1", "imagen": "", "marca": "piso-15", "foto": "",
           "imagen_fuente": "https://x/foto.jpg"}
    assert render_pieza.imagen_url_de(pub) == "https://x/foto.jpg"


# --------------------------------------------------------------------------- #
# render_bytes (efímero, sin persistir) — el camino de /compuesta              #
# --------------------------------------------------------------------------- #


def test_render_bytes_plantilla_por_defecto_compone_sin_persistir(monkeypatch):
    # Marca con plantilla de estudio POR DEFECTO: el render efímero compone vía
    # `componer_desde_plantilla_bytes` y NO persiste nada en el almacén.
    _sin_plantilla_de_marca(monkeypatch, True)
    monkeypatch.setattr(
        repos, "listar_plantillas_diseno",
        lambda **k: [{"id": "verde", "nombre": "UnoTV - Verde", "documento": "{\"v\":1}"}],
    )

    def _no_persiste(*a, **k):
        raise AssertionError("render_bytes NO debe persistir")

    monkeypatch.setattr(estudio_imagen, "componer_desde_plantilla_bytes", lambda *a, **k: b"PNG")
    monkeypatch.setattr(media, "guardar_bytes_contenido", _no_persiste)
    pub = {"id": "p1", "imagen": "", "marca": "unotv", "red": "x", "copy_in": "T",
           "foto": "f.jpg", "foto_encuadre": ""}
    assert render_pieza.render_bytes(pub) == (b"PNG", "image/png")


def test_render_bytes_sin_plantilla_de_estudio_sirve_foto(monkeypatch):
    # Marca CON spec pero SIN plantilla de estudio resoluble: ya NO se compone la placa por SPEC
    # -> sirve los BYTES de la foto cruda (no `componer_bytes`), sin persistir nada.
    _sin_plantilla_de_marca(monkeypatch, True)
    _sin_plantillas_estudio(monkeypatch)

    def _boom(*a, **k):
        raise AssertionError("no debe componer la placa por SPEC (retirada)")

    monkeypatch.setattr(estudio_imagen, "componer_bytes", _boom)
    monkeypatch.setattr(media, "leer_media", lambda n: b"FOTO" if n == "f.jpg" else None)
    monkeypatch.setattr(media, "mime_de", lambda n: "image/jpeg")
    pub = {"id": "p1", "imagen": "", "marca": "unotv", "red": "x", "copy_in": "T", "foto": "f.jpg"}
    assert render_pieza.render_bytes(pub) == (b"FOTO", "image/jpeg")


def test_render_bytes_plantilla(monkeypatch):
    monkeypatch.setattr(repos, "obtener_plantilla_diseno", lambda pid: {"documento": "{}"})
    monkeypatch.setattr(estudio_imagen, "componer_desde_plantilla_bytes", lambda *a, **k: b"DOC")
    pub = {"id": "p1", "imagen": "", "plantilla_diseno_id": "pl-1", "foto": "f.jpg",
           "copy_in": "X", "marca": "unotv", "foto_encuadre": ""}
    assert render_pieza.render_bytes(pub) == (b"DOC", "image/png")


def test_render_bytes_imagen_bespoke_passthrough(monkeypatch):
    # `imagen` ya horneada SIN receta viva: se sirven sus bytes tal cual, sin recomponer ni persistir.
    _sin_plantilla_de_marca(monkeypatch, False)
    monkeypatch.setattr(media, "leer_media", lambda n: b"BYTES" if n == "h.png" else None)
    monkeypatch.setattr(media, "mime_de", lambda n: "image/png")
    assert render_pieza.render_bytes({"id": "p1", "imagen": "h.png"}) == (b"BYTES", "image/png")


def test_render_bytes_solo_foto(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, False)
    monkeypatch.setattr(media, "leer_media", lambda n: b"FOTO" if n == "f.jpg" else None)
    monkeypatch.setattr(media, "mime_de", lambda n: "image/jpeg")
    pub = {"id": "p1", "imagen": "", "marca": "piso-15", "foto": "f.jpg"}
    assert render_pieza.render_bytes(pub) == (b"FOTO", "image/jpeg")


def test_render_bytes_none_sin_imagen(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, False)
    pub = {"id": "p1", "imagen": "", "marca": "piso-15", "foto": ""}
    assert render_pieza.render_bytes(pub) is None


# --------------------------------------------------------------------------- #
# firma_receta (ETag): cambia sii cambia la salida                             #
# --------------------------------------------------------------------------- #


def test_firma_estable_y_sensible(monkeypatch):
    # Sin plantilla de estudio (la firma no mira el SPEC): depende de los campos de la receta.
    _sin_plantillas_estudio(monkeypatch)
    base = {"id": "p1", "imagen": "", "marca": "unotv", "red": "x", "foto": "f.jpg",
            "copy_in": "A", "foto_encuadre": "", "placa_oculta": False, "plantilla_diseno_id": ""}
    f1 = render_pieza.firma_receta(dict(base))
    f2 = render_pieza.firma_receta(dict(base))
    f3 = render_pieza.firma_receta({**base, "copy_in": "B"})
    assert f1 == f2 and f1 != f3


def test_firma_cambia_si_cambia_la_plantilla_por_defecto(monkeypatch):
    # Editar el documento de la plantilla de estudio POR DEFECTO invalida la caché HTTP.
    base = {"id": "p1", "imagen": "", "marca": "unotv", "red": "x", "foto": "f.jpg",
            "copy_in": "A", "foto_encuadre": "", "placa_oculta": False, "plantilla_diseno_id": ""}
    monkeypatch.setattr(
        repos, "listar_plantillas_diseno",
        lambda **k: [{"id": "verde", "nombre": "UnoTV - Verde", "documento": "{\"v\":1}"}],
    )
    f1 = render_pieza.firma_receta(dict(base))
    monkeypatch.setattr(
        repos, "listar_plantillas_diseno",
        lambda **k: [{"id": "verde", "nombre": "UnoTV - Verde", "documento": "{\"v\":2}"}],
    )
    f2 = render_pieza.firma_receta(dict(base))
    assert f1 != f2
