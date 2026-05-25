"""Tests del parser de piezas por red y de la generacion por red de Skills.

TODO OFFLINE: NUNCA se llama a `claude` real; el runner se mockea o se prueban
funciones puras (`parsear_salida`, `normalizar_redes`, `construir_prompt`).

Fixtures cubiertos por `parsear_salida`:
  - salida CON bloque json valido (piezas correctas)
  - salida SIN bloque json (resultado tal cual, sin piezas)
  - salida con json MALFORMADO (resultado tal cual, sin piezas)
"""

from __future__ import annotations

from keni_consola import redes
from keni_consola.api import skills

from .conftest import _cliente, lanzador_generacion_completa

# --------------------------------------------------------------------------- #
# Fixtures de salida cruda (lo que devolveria `claude`)                        #
# --------------------------------------------------------------------------- #

_SALIDA_CON_JSON = """✅ Copy listo para publicar.

## X
Titular fuerte y al grano.

## Instagram
Gancho visual + contexto.

```json
{"piezas": [{"red": "x", "texto": "Titular fuerte y al grano."},
            {"red": "instagram", "texto": "Gancho visual + contexto."}]}
```
"""

_SALIDA_SIN_JSON = """⚠️ Revisa antes de publicar.

## X
Un solo bloque de texto sin json al final.
"""

# Sin bloque json Y sin encabezados de plataforma reconocibles: ni JSON ni
# fallback aplican, asi que `piezas` debe quedar vacio.
_SALIDA_SIN_JSON_NI_ENCABEZADOS = """⚠️ Revisa antes de publicar.

Un parrafo corrido sin ningun encabezado de red, solo prosa.
"""

_SALIDA_JSON_MALFORMADO = """❌ No publicar.

## X
Texto.

```json
{"piezas": [{"red": "x", "texto": "falta cierre}
```
"""


# --------------------------------------------------------------------------- #
# parsear_salida: bloque json valido                                          #
# --------------------------------------------------------------------------- #


def test_parsear_con_json_valido_extrae_piezas():
    res = skills.parsear_salida(_SALIDA_CON_JSON, ["x", "instagram"])
    assert res["verdicto"] == "listo"
    piezas = res["piezas"]
    assert [p["red"] for p in piezas] == ["x", "instagram"]
    assert piezas[0]["contenido"] == "Titular fuerte y al grano."
    assert piezas[0]["caracteres"] == len("Titular fuerte y al grano.")
    # el bloque json se QUITA del resultado limpio
    assert "```json" not in res["resultado"]
    assert "piezas" not in res["resultado"]
    assert "Gancho visual" in res["resultado"]


def test_parsear_respeta_orden_fijo_de_redes():
    """Aunque el json venga en otro orden, las piezas salen en el orden pedido."""
    salida = (
        "✅ ok\n\n```json\n"
        '{"piezas": [{"red": "instagram", "texto": "ig"}, {"red": "x", "texto": "tw"}]}\n'
        "```\n"
    )
    res = skills.parsear_salida(salida, ["x", "instagram"])
    assert [p["red"] for p in res["piezas"]] == ["x", "instagram"]


def test_parsear_ignora_redes_fuera_de_las_pedidas():
    salida = (
        "✅ ok\n\n```json\n"
        '{"piezas": [{"red": "x", "texto": "tw"}, {"red": "tiktok", "texto": "tk"}]}\n'
        "```\n"
    )
    res = skills.parsear_salida(salida, ["x"])  # solo se pidio X
    assert [p["red"] for p in res["piezas"]] == ["x"]


def test_parsear_usa_el_ultimo_bloque_json():
    """Si hay varios bloques json, el de las piezas es el ULTIMO."""
    salida = (
        "```json\n{\"otro\": 1}\n```\n\n"
        "✅ ok\n\n```json\n{\"piezas\": [{\"red\": \"x\", \"texto\": \"final\"}]}\n```\n"
    )
    res = skills.parsear_salida(salida, ["x"])
    assert res["piezas"][0]["contenido"] == "final"
    # el primer bloque (no-piezas) se queda en el resultado
    assert '{"otro": 1}' in res["resultado"]


# --------------------------------------------------------------------------- #
# parsear_salida: sin bloque / json malformado                                #
# --------------------------------------------------------------------------- #


def test_parsear_sin_json_ni_encabezados_devuelve_salida_sin_piezas():
    # Sin JSON y sin encabezados reconocibles: ni JSON ni fallback => piezas=[].
    res = skills.parsear_salida(_SALIDA_SIN_JSON_NI_ENCABEZADOS, ["x"])
    assert res["piezas"] == []
    assert res["verdicto"] == "revisar"  # el ⚠️ se deriva ANTES de quitar emojis
    # El resultado se devuelve sin emojis (se quito el ⚠️ del inicio).
    assert res["resultado"] == skills.quitar_emojis(_SALIDA_SIN_JSON_NI_ENCABEZADOS)
    assert "⚠" not in res["resultado"]


def test_parsear_json_malformado_cae_al_fallback_por_encabezados():
    # JSON invalido => no se quita el bloque del texto, pero el FALLBACK por
    # encabezados reparte el cuerpo bajo "## X" a la red x.
    res = skills.parsear_salida(_SALIDA_JSON_MALFORMADO, ["x"])
    assert res["verdicto"] == "no_publicar"  # el ❌ se deriva ANTES de quitar emojis
    assert [p["red"] for p in res["piezas"]] == ["x"]
    assert "Texto." in res["piezas"][0]["contenido"]
    # con json malformado, el bloque sigue presente en el texto (no se quito)
    assert "```json" in res["resultado"]


def test_parsear_verdicto_vacio_si_no_hay_simbolo():
    res = skills.parsear_salida("Sin simbolo de veredicto.\n## X\ntexto", ["x"])
    assert res["verdicto"] == ""


def test_parsear_piezas_no_lista_no_crashea():
    salida = "✅ ok\n\n```json\n{\"piezas\": \"no soy lista\"}\n```\n"
    res = skills.parsear_salida(salida, ["x"])
    assert res["piezas"] == []
    assert "```json" not in res["resultado"]  # json valido => bloque removido


# --------------------------------------------------------------------------- #
# normalizar_redes                                                            #
# --------------------------------------------------------------------------- #


def test_normalizar_redes_none_devuelve_las_cinco():
    assert skills.normalizar_redes(None) == redes.ids()
    assert len(skills.normalizar_redes(None)) == 5


def test_normalizar_redes_vacia_o_basura_devuelve_las_cinco():
    assert skills.normalizar_redes([]) == redes.ids()
    assert skills.normalizar_redes(["zzz", "nope"]) == redes.ids()


def test_normalizar_redes_filtra_y_ordena():
    # llega desordenado y con basura; sale en orden fijo y sin la basura
    assert skills.normalizar_redes(["instagram", "x", "zzz"]) == ["x", "instagram"]


def test_normalizar_redes_dedup():
    assert skills.normalizar_redes(["x", "x", "x"]) == ["x"]


# --------------------------------------------------------------------------- #
# construir_prompt: instruccion ADITIVA                                       #
# --------------------------------------------------------------------------- #


def test_prompt_sin_redes_no_anade_instruccion(entorno):
    p = skills.construir_prompt("copy-desde-nota", "unotv", "una nota")
    assert "json" not in p.lower()
    assert "una nota" in p


def test_prompt_con_redes_anade_bloque_json_y_redes(entorno):
    p = skills.construir_prompt("copy-desde-nota", "unotv", "una nota", ["x", "instagram"])
    assert "una nota" in p  # el copy base no cambia
    assert "```json" in p
    assert '"x"' in p and '"instagram"' in p


# --------------------------------------------------------------------------- #
# Endpoint /api/skills/ejecutar (generacion EN BACKGROUND, lanzador mockeado)  #
# --------------------------------------------------------------------------- #
#
# El endpoint ya NO es sincrono: crea una generacion y la lanza en background. En tests
# inyectamos `lanzar_generacion=lanzador_generacion_completa(salida)`, una fake que
# completa la generacion SINCRONAMENTE corriendo el `procesar` REAL con `salida` canned.
# Asi la respuesta del POST ya trae la generacion COMPLETADA y su `resultado`.


def _resultado(respuesta) -> dict:  # noqa: ANN001
    """`resultado` de la generacion COMPLETADA que devuelve un POST a /ejecutar*."""
    cuerpo = respuesta.json()
    gen = cuerpo["generacion"]
    assert gen["estado"] == "completado", gen
    return gen["resultado"]


def _captura_prompt(salida: str):
    """Lanzador que COMPLETA la generacion y ademas captura el prompt construido."""
    base = lanzador_generacion_completa(salida)
    capturado: dict[str, str] = {}

    def lanzar(gen_id, *, prompt, cwd, procesar, dir_temporal=None):  # noqa: ANN001
        capturado["prompt"] = prompt
        base(gen_id, prompt=prompt, cwd=cwd, procesar=procesar, dir_temporal=dir_temporal)

    return lanzar, capturado


def test_endpoint_ejecutar_devuelve_piezas_y_verdicto(entorno):
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_CON_JSON))
    r = cli.post(
        "/api/skills/ejecutar",
        json={
            "skill": "copy-desde-nota",
            "marca": "unotv",
            "valores": {"fuente": "una nota"},
            "redes": ["x", "instagram"],
        },
    )
    assert r.status_code == 200
    res = _resultado(r)
    assert res["verdicto"] == "listo"
    assert [p["red"] for p in res["piezas"]] == ["x", "instagram"]
    assert res["historial_id"]
    assert "```json" not in res["resultado"]


def test_endpoint_ejecutar_sin_redes_usa_las_cinco(entorno):
    lanzar, capturado = _captura_prompt(_SALIDA_SIN_JSON_NI_ENCABEZADOS)
    r = _cliente(lanzar_generacion=lanzar).post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "unotv", "valores": {"fuente": "una nota"}},
    )
    assert r.status_code == 200
    # el prompt debe mencionar las 5 redes por nombre
    for nombre in ("X", "Instagram", "Facebook", "TikTok", "YouTube"):
        assert nombre in capturado["prompt"]
    # sin json NI encabezados => piezas vacias
    assert _resultado(r)["piezas"] == []


def test_endpoint_ejecutar_archivo_redes_csv(entorno):
    lanzar, capturado = _captura_prompt(_SALIDA_CON_JSON)
    r = _cliente(lanzar_generacion=lanzar).post(
        "/api/skills/ejecutar-archivo",
        data={"skill": "copy-desde-nota", "marca": "unotv", "redes": "x,instagram"},
        files={"archivo": ("nota.txt", b"una nota de prueba", "text/plain")},
    )
    assert r.status_code == 200
    res = _resultado(r)
    assert [p["red"] for p in res["piezas"]] == ["x", "instagram"]
    # CSV parseado: solo X e Instagram en el prompt (no las 5)
    assert "TikTok" not in capturado["prompt"]


# --------------------------------------------------------------------------- #
# derivar_titulo (helper puro)                                                #
# --------------------------------------------------------------------------- #


def test_derivar_titulo_primera_linea_no_vacia():
    assert skills.derivar_titulo("\n\n  Titular de la nota  \nresto") == "Titular de la nota"


def test_derivar_titulo_recorta_a_80_chars():
    largo = "x" * 200
    titulo = skills.derivar_titulo(largo)
    # 80 chars + el caracter de elipsis
    assert titulo.endswith("…")
    assert len(titulo) == 81


def test_derivar_titulo_sin_contenido_cae_a_borrador_con_fecha():
    titulo = skills.derivar_titulo("   \n\n  ")
    assert titulo.startswith("Borrador ")


# --------------------------------------------------------------------------- #
# Auto-guardado: generacion crea N publicaciones (una por pieza)              #
# --------------------------------------------------------------------------- #


def _listar_publicaciones(cli):
    return cli.get("/api/publicaciones").json()["publicaciones"]


def test_ejecutar_autocrea_una_publicacion_por_pieza(entorno):
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_CON_JSON))
    r = cli.post(
        "/api/skills/ejecutar",
        json={
            "skill": "copy-desde-nota",
            "marca": "unotv",
            "valores": {"fuente": "Mi nota importante\nsegunda linea"},
            "redes": ["x", "instagram"],
        },
    )
    assert r.status_code == 200
    res = _resultado(r)
    # 2 piezas => 2 publicaciones recien creadas en el resultado.
    pubs = res["publicaciones"]
    assert len(pubs) == 2
    assert [p["red"] for p in pubs] == ["x", "instagram"]
    # Forma completa serializada (igual que en api/publicaciones).
    primera = pubs[0]
    for clave in ("id", "titulo", "marca", "marca_nombre", "red", "red_nombre",
                  "contenido", "estado", "veredicto", "origen", "imagen_url"):
        assert clave in primera
    assert primera["estado"] == "borrador"
    assert primera["veredicto"] == "listo"
    assert primera["marca"] == "unotv"
    # origen = historial_id
    assert primera["origen"] == res["historial_id"]
    assert primera["contenido"] == "Titular fuerte y al grano."
    # Titulo SIEMPRE derivado de la 1a linea del campo de texto (nunca lo da el cliente).
    assert primera["titulo"] == "Mi nota importante"
    # Persistidas de verdad: el listado las devuelve.
    assert len(_listar_publicaciones(cli)) == 2


def test_ejecutar_titulo_siempre_derivado_no_del_cliente(entorno):
    """El titulo se deriva del primer campo de texto; un `titulo` del cliente se IGNORA."""
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_CON_JSON))
    r = cli.post(
        "/api/skills/ejecutar",
        json={
            "skill": "copy-desde-nota",
            "marca": "unotv",
            "valores": {"fuente": "Primera linea de la fuente"},
            "redes": ["x"],
            "titulo": "Mi titulo a mano",  # se ignora: el titulo es derivado
        },
    )
    assert r.status_code == 200
    pubs = _resultado(r)["publicaciones"]
    assert pubs[0]["titulo"] == "Primera linea de la fuente"


def test_ejecutar_sin_piezas_no_crea_publicaciones(entorno):
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_SIN_JSON_NI_ENCABEZADOS))
    r = cli.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "unotv", "valores": {"fuente": "una nota"}},
    )
    assert r.status_code == 200
    res = _resultado(r)
    assert res["piezas"] == []
    assert res["publicaciones"] == []
    assert _listar_publicaciones(cli) == []


def test_ejecutar_archivo_autocrea_publicaciones(entorno):
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_CON_JSON))
    r = cli.post(
        "/api/skills/ejecutar-archivo",
        data={"skill": "copy-desde-nota", "marca": "unotv", "redes": "x,instagram"},
        files={"archivo": ("nota.txt", b"Contenido de la nota\nsegunda linea", "text/plain")},
    )
    assert r.status_code == 200
    pubs = _resultado(r)["publicaciones"]
    assert len(pubs) == 2
    # Titulo derivado del texto leido del archivo (1a linea).
    assert all(p["titulo"] == "Contenido de la nota" for p in pubs)
    assert len(_listar_publicaciones(cli)) == 2


def test_ejecutar_campo_requerido_faltante_da_400(entorno):
    """Un campo requerido ausente => 400 con mensaje claro, sin lanzar generacion."""
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_CON_JSON))
    r = cli.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "unotv", "valores": {}, "redes": ["x"]},
    )
    assert r.status_code == 400
    assert "obligatorio" in r.json()["error"].lower()


def test_ejecutar_skill_inexistente_da_400(entorno):
    cli = _cliente()
    r = cli.post(
        "/api/skills/ejecutar",
        json={"skill": "no-existe", "marca": "unotv", "valores": {"fuente": "x"}},
    )
    assert r.status_code == 400


def test_ejecutar_marca_no_permitida_da_400(entorno):
    cli = _cliente()
    r = cli.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "marca-pirata", "valores": {"fuente": "x"}},
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Salida `documento`: resultado con `documento`, SIN publicaciones            #
# --------------------------------------------------------------------------- #

_SALIDA_DOCUMENTO = """⚠️ REVISAR ANTES DE PUBLICAR

# Brief del tema
- Punto uno con su dato.
- Punto dos.

Recomendacion: cubrir en unotv primero.
"""


def test_ejecutar_documento_devuelve_documento_sin_publicaciones(entorno):
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_DOCUMENTO))
    r = cli.post(
        "/api/skills/ejecutar",
        json={"skill": "resumen-tendencia", "marca": "unotv",
              "valores": {"fuentes": "Tema X\ncon contexto"}},
    )
    assert r.status_code == 200
    res = _resultado(r)
    # Forma de salida documento.
    assert "documento" in res
    assert res["verdicto"] == "revisar"  # del ⚠️ inicial
    assert res["piezas"] == []
    assert res["publicaciones"] == []
    assert res["historial_id"]
    # El documento sale SIN emojis (el ⚠️ se quito).
    assert "⚠" not in res["documento"]
    assert "Brief del tema" in res["documento"]
    # NO se auto-creo ninguna publicacion.
    assert _listar_publicaciones(cli) == []
    # El historial guarda el documento como resultado, sin piezas.
    detalle = cli.get(f"/api/skills/historial/{res['historial_id']}").json()
    assert detalle["piezas"] == []


def test_ejecutar_documento_ignora_redes(entorno):
    """Una skill con aplica_redes=false NO mete la instruccion de redes en el prompt."""
    lanzar, capturado = _captura_prompt(_SALIDA_DOCUMENTO)
    r = _cliente(lanzar_generacion=lanzar).post(
        "/api/skills/ejecutar",
        json={"skill": "resumen-tendencia", "marca": "unotv",
              "valores": {"fuentes": "Tema X"}, "redes": ["x", "instagram"]},
    )
    assert r.status_code == 200
    # Aunque se pasaron redes, la skill no aplica_redes => sin bloque json ni "SOLO para estas redes".
    assert "```json" not in capturado["prompt"]
    assert "SOLO para estas redes" not in capturado["prompt"]


# --------------------------------------------------------------------------- #
# Historial: listado/detalle devuelven piezas + titulo                        #
# --------------------------------------------------------------------------- #


def test_historial_listado_y_detalle_incluyen_piezas_y_titulo(entorno):
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_CON_JSON))
    gen = cli.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "unotv", "valores": {"fuente": "Una nota"},
              "redes": ["x", "instagram"]},
    )
    hid = _resultado(gen)["historial_id"]

    lista = cli.get("/api/skills/historial").json()["historial"]
    assert lista[0]["titulo"] == "Una nota"
    assert [p["red"] for p in lista[0]["piezas"]] == ["x", "instagram"]

    detalle = cli.get(f"/api/skills/historial/{hid}").json()
    assert detalle["titulo"] == "Una nota"
    assert [p["red"] for p in detalle["piezas"]] == ["x", "instagram"]


# --------------------------------------------------------------------------- #
# Recuperar historial -> publicaciones                                        #
# --------------------------------------------------------------------------- #


def test_historial_guardar_con_piezas_crea_una_por_pieza(entorno):
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_CON_JSON))
    gen = cli.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "unotv", "valores": {"fuente": "Una nota"},
              "redes": ["x", "instagram"]},
    )
    hid = _resultado(gen)["historial_id"]
    antes = len(_listar_publicaciones(cli))

    r = cli.post(f"/api/skills/historial/{hid}/guardar", json={})
    assert r.status_code == 200
    pubs = r.json()["publicaciones"]
    assert [p["red"] for p in pubs] == ["x", "instagram"]
    assert all(p["origen"] == hid for p in pubs)
    assert all(p["estado"] == "borrador" for p in pubs)
    # Crea publicaciones NUEVAS (ademas de las auto-guardadas).
    assert len(_listar_publicaciones(cli)) == antes + 2


def test_historial_guardar_con_piezas_filtra_a_redes(entorno):
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_CON_JSON))
    hid = _resultado(cli.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "unotv", "valores": {"fuente": "Una nota"},
              "redes": ["x", "instagram"]},
    ))["historial_id"]

    r = cli.post(f"/api/skills/historial/{hid}/guardar", json={"redes": ["instagram"]})
    assert r.status_code == 200
    pubs = r.json()["publicaciones"]
    assert [p["red"] for p in pubs] == ["instagram"]


def test_historial_guardar_usa_titulo_param(entorno):
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_CON_JSON))
    hid = _resultado(cli.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "unotv", "valores": {"fuente": "Una nota"},
              "redes": ["x"]},
    ))["historial_id"]

    r = cli.post(f"/api/skills/historial/{hid}/guardar", json={"titulo": "Recuperado"})
    assert r.json()["publicaciones"][0]["titulo"] == "Recuperado"


def test_historial_guardar_sin_piezas_requiere_red(entorno):
    # Entrada antigua sin piezas: la insertamos via repos (backend activo).
    from keni_consola import repos

    hid = repos.registrar_historial_skill("copy-desde-nota", "unotv", "✅ texto plano")
    cli = _cliente()
    # Sin red => 400 claro.
    r = cli.post(f"/api/skills/historial/{hid}/guardar", json={})
    assert r.status_code == 400
    assert "red" in r.json()["error"].lower()


def test_historial_guardar_sin_piezas_con_red_crea_una(entorno):
    from keni_consola import repos

    hid = repos.registrar_historial_skill("copy-desde-nota", "unotv", "✅ contenido viejo")
    cli = _cliente()
    r = cli.post(f"/api/skills/historial/{hid}/guardar", json={"red": "facebook"})
    assert r.status_code == 200
    pubs = r.json()["publicaciones"]
    assert len(pubs) == 1
    assert pubs[0]["red"] == "facebook"
    assert pubs[0]["contenido"] == "✅ contenido viejo"
    assert pubs[0]["veredicto"] == "listo"  # derivado del ✅
    assert pubs[0]["origen"] == hid


def test_historial_guardar_red_invalida_da_400(entorno):
    from keni_consola import repos

    hid = repos.registrar_historial_skill("copy-desde-nota", "unotv", "texto viejo")
    cli = _cliente()
    r = cli.post(f"/api/skills/historial/{hid}/guardar", json={"red": "myspace"})
    assert r.status_code == 400


def test_historial_guardar_404_si_no_existe(entorno):
    cli = _cliente()
    r = cli.post("/api/skills/historial/noexiste/guardar", json={})
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# quitar_emojis (helper puro y determinista)                                  #
# --------------------------------------------------------------------------- #


def test_quitar_emojis_emoji_simple():
    assert skills.quitar_emojis("Hola 😀 mundo") == "Hola mundo"


def test_quitar_emojis_zwj_familia():
    # Familia = secuencia unida por ZWJ (U+200D); debe desaparecer entera.
    familia = "Mira 👨‍👩‍👧‍👦 aqui"
    assert skills.quitar_emojis(familia) == "Mira aqui"


def test_quitar_emojis_bandera():
    # Bandera = dos regional indicators (U+1F1F2 U+1F1FD = MX).
    assert skills.quitar_emojis("Viva 🇲🇽 Mexico") == "Viva Mexico"


def test_quitar_emojis_variation_selector():
    # ⚠ + U+FE0F (variation selector-16): se quitan ambos.
    assert skills.quitar_emojis("Cuidado ⚠️ ahora") == "Cuidado ahora"


def test_quitar_emojis_dingbat_y_check():
    assert skills.quitar_emojis("Listo ✅ y ❌ no") == "Listo y no"


def test_quitar_emojis_texto_sin_emojis_intacto():
    texto = "Texto con acentos: añadió, corazón, mañana."
    assert skills.quitar_emojis(texto) == texto


def test_quitar_emojis_no_toca_urls():
    texto = "Visita https://kenitech.io/ruta?x=1&y=2 hoy"
    assert skills.quitar_emojis(texto) == texto


def test_quitar_emojis_colapsa_dobles_espacios_y_recorta():
    # Al quitar el emoji entre dos espacios queda un doble espacio que se colapsa;
    # los extremos se recortan.
    assert skills.quitar_emojis("  uno 🔥 dos  ") == "uno dos"


def test_quitar_emojis_conserva_saltos_de_linea():
    assert skills.quitar_emojis("linea1 🚀\nlinea2") == "linea1\nlinea2"


def test_quitar_emojis_vacio():
    assert skills.quitar_emojis("") == ""


# --------------------------------------------------------------------------- #
# parsear_salida: quita emojis de piezas y resultado, conserva el verdicto    #
# --------------------------------------------------------------------------- #

_SALIDA_JSON_CON_EMOJIS = """✅ Copy listo 🎉

## X
Titular con fuego 🔥

```json
{"piezas": [{"red": "x", "texto": "Titular con fuego 🔥 y mas 🚀"},
            {"red": "instagram", "texto": "IG con corazon ❤️ aqui"}]}
```
"""


def test_parsear_quita_emojis_de_piezas_pero_conserva_verdicto():
    res = skills.parsear_salida(_SALIDA_JSON_CON_EMOJIS, ["x", "instagram"])
    # El verdicto se deriva del ✅ ANTES de borrar emojis.
    assert res["verdicto"] == "listo"
    piezas = res["piezas"]
    assert piezas[0]["contenido"] == "Titular con fuego y mas"
    assert piezas[1]["contenido"] == "IG con corazon aqui"
    # caracteres = len del contenido YA sin emojis.
    assert piezas[0]["caracteres"] == len("Titular con fuego y mas")
    # Ni el resultado ni las piezas llevan emojis.
    assert "🔥" not in res["resultado"] and "🎉" not in res["resultado"]
    for p in piezas:
        assert "🔥" not in p["contenido"] and "❤" not in p["contenido"]


# --------------------------------------------------------------------------- #
# parsear_salida: FALLBACK por encabezados de plataforma (sin JSON valido)    #
# --------------------------------------------------------------------------- #

_SALIDA_FALLBACK_MD = """✅ Listo.

## X
Tweet corto desde el fallback.

## Instagram
Post de IG desde el fallback.

## Facebook
Estado de FB desde el fallback.
"""

_SALIDA_FALLBACK_BOLD = """**Twitter**
Texto para X en negrita.

**Instagram:**
Texto para IG en negrita.
"""

_SALIDA_FALLBACK_DOSPUNTOS = """Twitter:
Texto para X con dos puntos.

YouTube:
Descripcion de YouTube.
"""


def test_fallback_encabezados_markdown_reparte_por_red():
    res = skills.parsear_salida(_SALIDA_FALLBACK_MD, ["x", "instagram", "facebook"])
    assert [p["red"] for p in res["piezas"]] == ["x", "instagram", "facebook"]
    assert res["piezas"][0]["contenido"] == "Tweet corto desde el fallback."
    assert res["piezas"][2]["contenido"] == "Estado de FB desde el fallback."
    assert res["verdicto"] == "listo"


def test_fallback_encabezados_bold_y_alias_twitter():
    # "**Twitter**" -> x ; "**Instagram:**" -> instagram
    res = skills.parsear_salida(_SALIDA_FALLBACK_BOLD, ["x", "instagram"])
    assert [p["red"] for p in res["piezas"]] == ["x", "instagram"]
    assert res["piezas"][0]["contenido"] == "Texto para X en negrita."


def test_fallback_encabezados_dos_puntos():
    res = skills.parsear_salida(_SALIDA_FALLBACK_DOSPUNTOS, ["x", "youtube"])
    assert [p["red"] for p in res["piezas"]] == ["x", "youtube"]
    assert res["piezas"][1]["contenido"] == "Descripcion de YouTube."


def test_fallback_acotado_a_redes_pedidas():
    # El texto trae X, Instagram y Facebook, pero solo se pidio X: el resto se ignora.
    res = skills.parsear_salida(_SALIDA_FALLBACK_MD, ["x"])
    assert [p["red"] for p in res["piezas"]] == ["x"]


def test_fallback_orden_fijo_aunque_encabezados_desordenados():
    salida = "## Instagram\nIG\n\n## X\nTW\n"
    res = skills.parsear_salida(salida, ["x", "instagram"])
    assert [p["red"] for p in res["piezas"]] == ["x", "instagram"]


def test_fallback_quita_emojis_del_cuerpo():
    salida = "## X\nTweet con fuego 🔥 final\n"
    res = skills.parsear_salida(salida, ["x"])
    assert res["piezas"][0]["contenido"] == "Tweet con fuego final"
    assert res["piezas"][0]["caracteres"] == len("Tweet con fuego final")


def test_fallback_sin_encabezados_devuelve_piezas_vacias():
    salida = "Solo prosa corrida, sin ningun encabezado de red reconocible.\n"
    res = skills.parsear_salida(salida, ["x", "instagram"])
    assert res["piezas"] == []


def test_json_valido_tiene_prioridad_sobre_encabezados():
    # Hay encabezados ## X / ## Instagram PERO tambien un JSON valido: gana el JSON.
    salida = (
        "## X\nTexto suelto bajo X\n\n## Instagram\nTexto suelto bajo IG\n\n"
        '```json\n{"piezas": [{"red": "x", "texto": "DESDE JSON"}]}\n```\n'
    )
    res = skills.parsear_salida(salida, ["x", "instagram"])
    assert [p["red"] for p in res["piezas"]] == ["x"]
    assert res["piezas"][0]["contenido"] == "DESDE JSON"


# --------------------------------------------------------------------------- #
# construir_prompt: instruccion ADITIVA "sin emojis"                          #
# --------------------------------------------------------------------------- #


def test_prompt_incluye_instruccion_sin_emojis(entorno):
    p = skills.construir_prompt("copy-desde-nota", "unotv", "una nota", ["x"])
    assert "No uses emojis en el copy." in p


def test_prompt_ruta_incluye_instruccion_sin_emojis(entorno):
    p = skills.construir_prompt_ruta("clip-a-copy", "unotv", "/tmp/clip.mp4")
    assert "No uses emojis en el copy." in p
