"""Validación PRE-PERSISTENCIA de piezas de copy (`dominio.copy`).

Una pieza con red desconocida, texto vacío o que excede el límite técnico de su red
(`keni_shared.limites_plataforma`; en hilos/carruseles, por intervalo) NO crea borrador: se
descarta SOLO esa pieza, se loguea WARN y, si hay tema, se deja una nota en él. Las piezas
válidas del mismo lote se crean igual.

Los helpers de intervalos/motivo son PUROS (sin DB); la creación de borradores usa Postgres
(fixture `entorno`).
"""

from __future__ import annotations

from keni_consola import repos
from keni_consola.dominio import copy as dom_copy

_MARCA = "unotv"


# --------------------------------------------------------------------------- #
# Intervalos publicables (contrato de piezas compuestas) — PURO                     #
# --------------------------------------------------------------------------- #


def test_pieza_simple_es_un_unico_tramo():
    assert dom_copy._intervalos_publicables("Hola X") == ["Hola X"]


def test_hilo_se_parte_por_tuits_numerados():
    texto = "1/3 Gancho del hilo\n2/3 Desarrollo\ncon segunda línea\n3/3 Cierre con CTA"
    intervalos = dom_copy._intervalos_publicables(texto)
    assert intervalos == ["1/3 Gancho del hilo", "2/3 Desarrollo\ncon segunda línea", "3/3 Cierre con CTA"]


def test_carrusel_se_parte_por_separador():
    texto = "Slide 1: gancho\n---\nSlide 2: dato\n---\nSlide 3: CTA"
    assert dom_copy._intervalos_publicables(texto) == ["Slide 1: gancho", "Slide 2: dato", "Slide 3: CTA"]


def test_una_sola_linea_numerada_no_es_hilo():
    # "1/2 de la población…" como apertura de una pieza simple NO debe partirse.
    texto = "1/2 de la población vio el partido"
    assert dom_copy._intervalos_publicables(texto) == [texto]


# --------------------------------------------------------------------------- #
# Motivo de invalidez — PURO                                                   #
# --------------------------------------------------------------------------- #


def test_motivo_red_desconocida():
    assert "red desconocida" in dom_copy._motivo_invalida({"red": "threads", "contenido": "hola"})
    assert "red desconocida" in dom_copy._motivo_invalida({"red": 3, "contenido": "hola"})


def test_motivo_texto_vacio():
    assert "texto vacío" in dom_copy._motivo_invalida({"red": "x", "contenido": "  "})
    assert "texto vacío" in dom_copy._motivo_invalida({"red": "x", "contenido": None})


def test_motivo_excede_limite_de_la_red():
    # X = 25000; un cuerpo por encima del tope invalida la pieza.
    motivo = dom_copy._motivo_invalida({"red": "x", "contenido": "a" * 25001})
    assert "límite 25000" in motivo


def test_hilo_valida_por_tuit_no_por_total():
    # Un hilo de 3 tuits ≤25000 supera los 25000 totales y AUN ASI es válido (límite por intervalo).
    hilo = "\n".join(f"{i}/3 " + "a" * 10000 for i in (1, 2, 3))
    assert len(hilo) > 25000
    assert dom_copy._motivo_invalida({"red": "x", "contenido": hilo}) is None
    # Pero un tuit individual pasado de 25000 invalida la pieza.
    roto = "1/2 " + "a" * 25001 + "\n2/2 corto"
    assert "límite 25000" in dom_copy._motivo_invalida({"red": "x", "contenido": roto})


def test_sin_tope_tecnico_no_invalida_por_longitud():
    assert dom_copy._motivo_invalida({"red": "facebook", "contenido": "a" * 100_000}) is None


def test_pieza_valida_no_tiene_motivo():
    assert dom_copy._motivo_invalida({"red": "x", "contenido": "Hola X"}) is None


# --------------------------------------------------------------------------- #
# Inyección de HASHTAGS de la línea al final del copy — PURO                     #
# --------------------------------------------------------------------------- #


def test_inyecta_hashtags_al_final():
    out = dom_copy._inyectar_hashtags("Texto del post", ["Nacional", "Finanzas"], red="instagram")
    assert out == "Texto del post #Nacional #Finanzas"


def test_inyecta_hashtags_sin_tags_no_toca():
    assert dom_copy._inyectar_hashtags("Texto", [], red="x") == "Texto"


def test_inyecta_hashtags_dedup_case_insensitive():
    # «#Nacional» ya está (aunque con otro casing): no se duplica; sí se añade el que falta.
    out = dom_copy._inyectar_hashtags("Algo #nacional aquí", ["Nacional", "Finanzas"], red="instagram")
    assert out == "Algo #nacional aquí #Finanzas"


def test_inyecta_hashtags_respeta_el_limite_de_la_red():
    # En X (límite 25000) un texto casi al tope solo admite los hashtags que QUEPAN.
    base = "a" * 24990  # 24990 chars; " #Nacional" (10) cabe (=25000), " #Finanzas" ya no
    out = dom_copy._inyectar_hashtags(base, ["Nacional", "Finanzas"], red="x")
    assert out == f"{base} #Nacional"
    assert len(out) <= 25000


def test_inyecta_hashtags_si_ninguno_cabe_deja_el_texto_igual():
    base = "a" * 25000  # ya en el tope de X: no cabe ningún hashtag
    assert dom_copy._inyectar_hashtags(base, ["Nacional"], red="x") == base


# --------------------------------------------------------------------------- #
# Creación de borradores: descarta inválidas sin romper las válidas (Postgres)  #
# --------------------------------------------------------------------------- #


def test_pieza_invalida_no_crea_borrador_y_respeta_las_validas(entorno):
    creadas = dom_copy.crear_publicaciones_desde_piezas(
        [
            {"red": "x", "contenido": "a" * 25001, "copy_in": ""},  # excede el límite de X (25000)
            {"red": "instagram", "contenido": "", "copy_in": ""},  # texto vacío
            {"red": "facebook", "contenido": "Hola FB", "copy_in": ""},  # válida
        ],
        marca=_MARCA, titulo="T", verdicto="", origen="h1",
    )
    assert [str(p["red"]) for p in creadas] == ["facebook"]
    pubs = repos.listar_piezas(marca=_MARCA)
    assert all(p.get("red") != "x" for p in pubs)


def test_pieza_invalida_deja_nota_en_el_tema(entorno):
    tema = repos.crear_publicacion(clase="contenido", titulo="Tema", marca=_MARCA, notas="previa")
    dom_copy.crear_publicaciones_desde_piezas(
        [{"red": "x", "contenido": "a" * 25001, "copy_in": ""}],
        marca=_MARCA, titulo="T", verdicto="", origen="h1", publicacion_id=tema["id"],
    )
    releido = repos.obtener_publicacion(tema["id"])
    assert "previa" in releido["notas"]  # no pisa las notas existentes
    assert "Copy descartado" in releido["notas"]
    assert "límite 25000" in releido["notas"]


def test_redes_filtro_no_cuenta_como_descarte(entorno):
    # Excluir una red por filtro del llamante NO es una pieza inválida: ni nota ni WARN.
    tema = repos.crear_publicacion(clase="contenido", titulo="Tema", marca=_MARCA)
    dom_copy.crear_publicaciones_desde_piezas(
        [{"red": "x", "contenido": "Hola X", "copy_in": ""}],
        marca=_MARCA, titulo="T", verdicto="", origen="h1",
        redes_filtro={"instagram"}, publicacion_id=tema["id"],
    )
    assert "Copy descartado" not in (repos.obtener_publicacion(tema["id"])["notas"] or "")


# --------------------------------------------------------------------------- #
# Hashtags de la LÍNEA: se inyectan al final del copy de las piezas del tema     #
# --------------------------------------------------------------------------- #


def test_inyecta_hashtags_de_la_linea_en_el_copy(entorno):
    # La línea asignada al tema gobierna los hashtags: se añaden al final de cada pieza.
    tema = repos.crear_publicacion(clase="contenido", titulo="Tema", marca=_MARCA)
    linea = repos.crear_etiqueta(
        nombre="Nacional", clase="vertical", marca=_MARCA, hashtags="Nacional, Finanzas"
    )
    repos.asignar_etiqueta(tema["id"], linea["id"])
    creadas = dom_copy.crear_publicaciones_desde_piezas(
        [{"red": "facebook", "contenido": "Cuerpo del post", "copy_in": ""}],
        marca=_MARCA, titulo="T", verdicto="", origen="h1", publicacion_id=tema["id"],
    )
    assert str(creadas[0]["contenido"]) == "Cuerpo del post #Nacional #Finanzas"


def test_no_inyecta_si_la_linea_no_tiene_hashtags(entorno):
    tema = repos.crear_publicacion(clase="contenido", titulo="Tema", marca=_MARCA)
    linea = repos.crear_etiqueta(nombre="Sin tags", clase="vertical", marca=_MARCA, hashtags="")
    repos.asignar_etiqueta(tema["id"], linea["id"])
    creadas = dom_copy.crear_publicaciones_desde_piezas(
        [{"red": "facebook", "contenido": "Cuerpo", "copy_in": ""}],
        marca=_MARCA, titulo="T", verdicto="", origen="h1", publicacion_id=tema["id"],
    )
    assert str(creadas[0]["contenido"]) == "Cuerpo"


def test_hashtags_de_contenido_junta_las_lineas_sin_duplicar(entorno):
    tema = repos.crear_publicacion(clase="contenido", titulo="Tema", marca=_MARCA)
    a = repos.crear_etiqueta(nombre="Nacional", clase="vertical", marca=_MARCA, hashtags="Nacional")
    b = repos.crear_etiqueta(nombre="UltimaHora", clase="campania", marca=_MARCA, hashtags="Nacional, UnoTV")
    repos.asignar_etiqueta(tema["id"], a["id"])
    repos.asignar_etiqueta(tema["id"], b["id"])
    # 'Nacional' aparece en ambas líneas: una sola vez (dedup case-insensitive), orden estable.
    assert repos.hashtags_de_contenido(tema["id"]) == ["Nacional", "UnoTV"]


def test_normaliza_hashtags_quita_almohadilla_simbolos_y_dedup():
    from keni_consola.api.etiquetas import _normalizar_hashtags

    assert _normalizar_hashtags("#Nacional, nacional, Finanzas") == "Nacional, Finanzas"
    # Sin '#', sin símbolos: cada token se repara (los hashtags no llevan espacios).
    assert _normalizar_hashtags("Mundial-2026!, @x") == "Mundial2026, x"
    assert _normalizar_hashtags(None) == ""
