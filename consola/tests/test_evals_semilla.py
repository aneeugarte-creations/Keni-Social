"""Red de regresión del harness de EVALS (artefacto: el hueco "no hay eval de calidad de IA").

Garantiza que los casos golden SEMILLA mantienen su veredicto esperado: un cambio que degrade
la MAQUINARIA DE VERIFICACIÓN (lint de `patrones_marca`, gate `_revisar`, límites de red) o los
PERFILES MEDIDOS de marca (`patrones_semilla/*.json`) flipa algún caso y este test lo caza. NO
toca BD ni red (determinista, barato) — corre en cualquier pipeline sin Postgres.

Alcance HONESTO: este test NO genera copy con el modelo, así que NO ve ediciones del TEXTO de un
prompt (eso es el modo "live" del harness, fuera de CI). Es la red de la capa medible/determinista.
"""

from __future__ import annotations

import pytest
from keni_consola.evals import cargar_casos, correr_casos
from keni_consola.evals.checks import DIMENSIONES, correr_dimensiones
from keni_consola.evals.juez import acuerdo_con_humano
from keni_consola.evals.modelo import FALLA, PASA, CasoEval, ErrorCaso, caso_de_dict


def _casos():
    return cargar_casos()  # consola/evals/casos por defecto


def test_hay_casos_semilla_de_ambos_signos():
    """El set semilla debe tener casos que PASAN y casos que FALLAN (si no, no prueba nada)."""
    casos = _casos()
    assert len(casos) >= 6, "se esperaban al menos 6 casos semilla"
    assert any(c.espera == PASA for c in casos), "falta al menos un caso que deba PASAR"
    assert any(c.espera == FALLA for c in casos), "falta al menos un caso que deba FALLAR"


def test_casos_semilla_cuadran_todos():
    """Veredicto efectivo == expectativa golden para TODOS los casos (score 100%).

    Esta es la afirmación central: las piezas marcadas `pasa` pasan los checks deterministas y
    las marcadas `falla` los fallan EN LA DIMENSIÓN declarada (`falla_esperada_en`)."""
    reporte = correr_casos(_casos())
    discrepancias = [
        (r.caso.id, r.caso.espera, r.veredicto, r.dimensiones_fallidas)
        for r in reporte.discrepancias
    ]
    assert reporte.score == 1.0, f"casos semilla que ya no cuadran: {discrepancias}"


def test_cada_caso_falla_en_su_dimension_declarada():
    """Un caso `falla` con `falla_esperada_en` debe fallar EXACTAMENTE por esa dimensión (que el
    caso no pase a fallar por una razón distinta a la que documenta)."""
    for r in correr_casos(_casos()).resultados:
        objetivo = r.caso.falla_esperada_en
        if r.caso.espera == FALLA and objetivo:
            assert objetivo in r.dimensiones_fallidas, (
                f"{r.caso.id}: debía fallar en {objetivo!r}, falló en {r.dimensiones_fallidas}"
            )


# --- Unit de cada dimensión (lock del comportamiento de los checks reusados) ---------------- #


def _caso(**kw) -> CasoEval:
    base = {"id": "t", "marca": "unotv", "red": "facebook", "copy": "x"}
    base.update(kw)
    return caso_de_dict(base)


def test_check_limite_red_corta_por_tramo():
    # Instagram (2200) es el tope duro más estricto entre las redes.
    res = {d.nombre: d for d in correr_dimensiones(_caso(red="instagram", copy="a" * 2300))}
    assert res["limite_red"].fallo  # 2300 > 2200 (límite duro de Instagram)
    assert not [d for d in correr_dimensiones(_caso(red="instagram", copy="a" * 2000)) if d.nombre == "limite_red" and d.fallo]


def test_check_prohibidos_es_insensible_a_acentos_y_por_palabra():
    # "Fiscalia" prohibido casa "Fiscalía" (sin acento); "reo" NO casa "correo" (palabra entera).
    c = _caso(copy="La FISCALÍA del estado emitió un comunicado oficial sobre el correo recibido.",
              prohibidos=["fiscalia", "reo"])
    res = {d.nombre: d for d in correr_dimensiones(c)}
    assert res["prohibidos"].fallo
    assert "fiscalia" in res["prohibidos"].avisos[0]
    assert "reo" not in res["prohibidos"].avisos[0]


def test_check_idioma_marca_ingles_pero_respeta_español():
    ingles = _caso(copy="The local police confirmed the new operation will start next week here.")
    espanol = _caso(copy="La policía local confirmó que el nuevo operativo arranca la próxima semana.")
    assert next(d for d in correr_dimensiones(ingles) if d.nombre == "idioma").fallo
    assert not next(d for d in correr_dimensiones(espanol) if d.nombre == "idioma").fallo


def test_check_voz_reusa_patrones_marca():
    # Sin perfil para la red => sin avisos (degradación honesta). Con telegrama en unotv/fb => falla.
    largo_corto = _caso(copy="Muy corto.")
    assert next(d for d in correr_dimensiones(largo_corto) if d.nombre == "voz").fallo


# --- Calibración del juez (andamiaje) ------------------------------------------------------- #


def test_acuerdo_juez_perfecto_y_con_falsos_positivos():
    casos = _casos()
    # Un juez ORÁCULO (devuelve la etiqueta humana) tiene acuerdo 1.0 y 0 falsos positivos.
    oraculo = acuerdo_con_humano(lambda c: c.espera, casos)
    assert oraculo.acuerdo == 1.0
    assert oraculo.falsos_positivos == 0
    # Un juez que SIEMPRE dice 'pasa' deja pasar todo lo que el humano rechaza (falsos positivos).
    todo_pasa = acuerdo_con_humano(lambda c: PASA, casos)
    assert todo_pasa.falsos_positivos == sum(1 for c in casos if c.espera == FALLA)


# --- Validación del cargador (un caso roto debe ROMPER, no colarse) -------------------------- #


def test_cargador_rechaza_caso_sin_campos_obligatorios():
    with pytest.raises(ErrorCaso):
        caso_de_dict({"id": "x", "marca": "unotv"})  # falta red y copy


def test_cargador_rechaza_espera_invalida():
    with pytest.raises(ErrorCaso):
        caso_de_dict({"id": "x", "marca": "unotv", "red": "facebook", "copy": "y", "espera": "quiza"})


def test_dimensiones_registradas_son_estables():
    # Contrato del set de casos: si se renombra/borra una dimensión, hay que migrar los casos.
    assert set(DIMENSIONES) == {"limite_red", "voz", "coherencia", "prohibidos", "idioma"}
