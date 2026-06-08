"""Rotación automática de plantillas por marca (los 6 colores de UnoTV, p. ej.). OFFLINE.

Cubre la asignación que hace `crear_contenido_plataforma`: cuando la marca tiene un GRUPO de
plantillas con `rotar=1` (≥2, del `tipo` que toca al formato), cada pieza nueva se lleva la
SIGUIENTE del grupo (round-robin) y TODAS sus redes comparten color. Dormido si <2.
"""

from __future__ import annotations

from keni_consola import repos


def _plantillas_de(contenido_id: str) -> list[str]:
    return [p["plantilla_diseno_id"] for p in repos.listar_contenido_plataforma(contenido_id)]


def _pieza_foto(marca: str = "unotv", titulo: str = "x") -> str:
    return repos.crear_contenido(marca=marca, titulo=titulo, formato="foto")["id"]


def _dos_colores(marca: str = "unotv") -> tuple[str, str]:
    """Dos plantillas de foto en rotación, con `creado` explícito para orden ESTABLE (a antes que b)."""
    a = repos.crear_plantilla_diseno(
        marca=marca, nombre="A", tipo="foto", rotar=True, creado="2024-01-01T00:00:00"
    )
    b = repos.crear_plantilla_diseno(
        marca=marca, nombre="B", tipo="foto", rotar=True, creado="2024-01-01T00:00:01"
    )
    return a["id"], b["id"]


def test_round_robin_y_mismo_color_en_todas_las_redes(entorno):
    a, b = _dos_colores()

    # Pieza 1: la 1ª del pool, y las 3 redes comparten color.
    c1 = _pieza_foto(titulo="1")
    for red in ("facebook", "instagram", "x"):
        repos.crear_contenido_plataforma(contenido_id=c1, red=red)
    assert _plantillas_de(c1) == [a, a, a]

    # Pieza 2: la SIGUIENTE del pool.
    c2 = _pieza_foto(titulo="2")
    repos.crear_contenido_plataforma(contenido_id=c2, red="facebook")
    assert _plantillas_de(c2) == [b]

    # Pieza 3: vuelve al principio (wrap-around).
    c3 = _pieza_foto(titulo="3")
    repos.crear_contenido_plataforma(contenido_id=c3, red="facebook")
    assert _plantillas_de(c3) == [a]


def test_dormida_con_menos_de_dos_en_rotacion(entorno):
    # Una sola plantilla en rotación: no hay grupo, no se asigna nada (comportamiento de siempre).
    repos.crear_plantilla_diseno(marca="unotv", nombre="solo", tipo="foto", rotar=True)
    c = _pieza_foto()
    p = repos.crear_contenido_plataforma(contenido_id=c, red="facebook")
    assert p["plantilla_diseno_id"] == ""


def test_ignora_plantillas_sin_rotar(entorno):
    # 2 plantillas pero NINGUNA marcada rotar: no rota.
    repos.crear_plantilla_diseno(marca="unotv", nombre="A", tipo="foto", rotar=False)
    repos.crear_plantilla_diseno(marca="unotv", nombre="B", tipo="foto", rotar=False)
    c = _pieza_foto()
    p = repos.crear_contenido_plataforma(contenido_id=c, red="facebook")
    assert p["plantilla_diseno_id"] == ""


def test_respeta_plantilla_explicita(entorno):
    _dos_colores()
    c = _pieza_foto()
    p = repos.crear_contenido_plataforma(
        contenido_id=c, red="facebook", plantilla_diseno_id="fijada-por-el-usuario"
    )
    assert p["plantilla_diseno_id"] == "fijada-por-el-usuario"


def test_solo_rota_el_tipo_acorde_al_formato(entorno):
    # Pool de FOTO; pieza de VIDEO (busca tipo 'miniatura') -> no asigna.
    _dos_colores()
    c = repos.crear_contenido(marca="unotv", titulo="v", formato="video")["id"]
    p = repos.crear_contenido_plataforma(contenido_id=c, red="facebook")
    assert p["plantilla_diseno_id"] == ""


def test_no_mezcla_marcas(entorno):
    # La rotación de unotv no afecta a otra marca sin grupo.
    _dos_colores(marca="unotv")
    c = repos.crear_contenido(marca="claro-sports", titulo="cs", formato="foto")["id"]
    p = repos.crear_contenido_plataforma(contenido_id=c, red="facebook")
    assert p["plantilla_diseno_id"] == ""
