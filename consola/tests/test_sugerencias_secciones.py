"""Tests del motor de SUGERENCIAS DE SECCIONES (`dominio/sugerencias_secciones.py`). PURO, sin BD.

Mina términos recurrentes en las candidatas que el clasificador deja SIN sección: si un tema se
repite y ninguna línea lo captura, se propone como sección nueva. Ignora lo ya clasificado y lo
ya cubierto por keywords; un bigrama (más específico) gana y suprime sus palabras sueltas.
"""

from __future__ import annotations

from keni_consola.dominio import sugerencias_secciones as ss

# Dos líneas con keywords: para clasificar (y excluir) lo que ya tiene sección.
_ETIQUETAS = [
    {"id": "ligamx", "keywords": "liga mx, cruz azul"},
    {"id": "boxeo", "keywords": "canelo, box"},
]


def _cl(cid: str, titulo: str) -> dict:
    return {"id": cid, "titulo": titulo, "resumen": ""}


def test_sugiere_tema_recurrente_sin_seccion():
    clusters = [
        _cl("1", "El padel mexicano crece con un torneo nuevo"),
        _cl("2", "Premier Padel anuncia su llegada al pais"),
        _cl("3", "La final de padel llena las gradas"),
        _cl("4", "Padel: la disciplina suma adeptos"),
    ]
    res = ss.sugerir(clusters, _ETIQUETAS, minimo=3)
    sug = {s["termino"]: s for s in res}
    assert "padel" in sug
    assert sug["padel"]["n"] == 4
    assert sug["padel"]["ejemplos"]  # trae titulares de ejemplo


def test_bigrama_gana_y_suprime_sus_palabras():
    clusters = [
        _cl("1", "Roland Garros arranca con sorpresas"),
        _cl("2", "Cuadro de Roland Garros confirmado"),
        _cl("3", "Roland Garros define a sus favoritas"),
    ]
    terms = [s["termino"] for s in ss.sugerir(clusters, _ETIQUETAS, minimo=3)]
    assert "roland garros" in terms
    assert "roland" not in terms and "garros" not in terms


def test_ignora_historias_ya_clasificadas():
    # 'Canelo' casa la línea Boxeo: aunque se repita, su término NO se mina (ya tiene sección).
    clusters = [_cl(str(i), "Canelo Alvarez confirma una nueva pelea") for i in range(5)]
    assert ss.sugerir(clusters, _ETIQUETAS, minimo=3) == []


def test_excluye_palabras_que_ya_son_token_de_keyword():
    # 'liga' es palabra de la keyword 'liga mx': historias con 'liga' (pero sin la frase) quedan
    # sin clasificar, y aun así 'liga' NO se sugiere (la taxonomía ya la cubre).
    clusters = [
        _cl("1", "La liga arranca con sorpresas"),
        _cl("2", "Comienza la liga en el norte"),
        _cl("3", "La liga suma un patrocinador"),
        _cl("4", "Toda la liga se moviliza"),
    ]
    terms = [s["termino"] for s in ss.sugerir(clusters, _ETIQUETAS, minimo=3)]
    assert "liga" not in terms


def test_respeta_el_minimo_y_el_tope():
    # Un tema con 2 menciones no llega al minimo=3.
    clusters = [_cl("1", "Surf en Oaxaca"), _cl("2", "Mas surf en Oaxaca")]
    assert ss.sugerir(clusters, _ETIQUETAS, minimo=3) == []
    # El tope recorta el nº de sugerencias devueltas.
    muchos = []
    for tema in ("alfa", "beta", "gamma"):
        muchos += [_cl(f"{tema}{i}", f"{tema} torneo abierto") for i in range(3)]
    assert len(ss.sugerir(muchos, _ETIQUETAS, minimo=3, tope=2)) == 2
