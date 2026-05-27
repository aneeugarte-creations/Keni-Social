#!/usr/bin/env python3
"""Pruebas del detector de tropicalizacion POR FLEXIONES (`tropicalizacion.py`, #139).

Verifican la ganancia clave sobre `checks.detecta_espanolismos`: aqui SI se cazan
flexiones ("mola", "flipo", "molaban", "coches", "movil"), no solo el lema exacto,
y se reporta cobertura. CI-safe: Python puro, sin modelo ni red.

Archivo separado a proposito (no toca `test_checks_copy.py`) para minimizar
conflictos con ramas que tocan los mismos ficheros (#131).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tropicalizacion as trop  # noqa: E402
import checks  # noqa: E402


def _formas(texto: str) -> list[str]:
    return [h.forma for h in trop.detecta_flexiones_es_es(texto)]


def _lemas(texto: str) -> list[str]:
    return [h.lema for h in trop.detecta_flexiones_es_es(texto)]


# --- la ganancia central: flexiones que el gate viejo dejaba pasar -----------

def test_caza_flexiones_de_verbo_que_el_gate_viejo_no_veia():
    # checks.detecta_espanolismos NO marca "mola"/"flipo" (solo el lema exacto).
    # El nuevo detector SI, porque indexa las flexiones del verbo.
    assert checks.detecta_espanolismos("eso mola y yo flipo") == []  # comportamiento viejo
    assert _formas("eso mola y yo flipo") == ["mola", "flipo"]        # nuevo


def test_caza_conjugaciones_variadas_de_molar_flipar_currar():
    assert _lemas("ayer molaba un monton") == ["molar"]
    assert _lemas("los vecinos flipaban") == ["flipar"]
    assert _lemas("eso molaria mazo") == ["molar"]
    assert _lemas("hay que currar mas") == ["currar"]
    assert _lemas("flipando con el partido") == ["flipar"]


def test_caza_plural_de_sustantivos():
    # el lema exacto del gate viejo no veria "coches"/"moviles"
    assert _lemas("vende los coches") == ["coche"]
    assert _lemas("dos moviles nuevos") == ["movil"]
    assert _lemas("las patatas fritas") == ["patata"]


def test_caza_genero_y_numero_de_adjetivos():
    assert _lemas("que majo") == ["majo"]
    assert _lemas("una chica muy maja") == ["majo"]
    assert _lemas("unos tipos majos") == ["majo"]


def test_caza_chaval_chavala_y_plurales():
    assert _lemas("el chaval") == ["chaval"]
    assert _lemas("la chavala") == ["chaval"]
    assert _lemas("los chavales") == ["chaval"]


def test_caza_imperativo_con_clitico_de_pillar():
    assert _lemas("pillalo ya") == ["pillar"]
    assert _lemas("pilla eso") == ["pillar"]


# --- robustez: acentos, mayusculas, palabra completa -------------------------

def test_insensible_a_acentos_y_mayusculas():
    assert _formas("MÓVIL") == ["movil"]
    assert _lemas("Móvil y ZUMOS") == ["movil", "zumo"]


def test_casa_palabra_completa_no_subcadena():
    # "valeroso" contiene "vale"; "amamos" contiene "amos" (sufijo verbal);
    # "nosotros" contiene "os" -> NINGUNO debe marcar.
    assert _formas("un gesto valeroso de gente que amamos, nosotros") == []


def test_preserva_orden_y_no_repite():
    assert _formas("vale, mola, y otra vez vale") == ["vale", "mola"]


# --- conservador: ambiguos fuera, copy MX limpio -----------------------------

def test_copy_mexicano_limpio_no_marca_nada():
    s = (
        "Sale, ustedes suban el carro al taller. Agarren su celular y su jugo, "
        "que esto se va a poner bueno. ¡Qué golazo, cuate!"
    )
    assert trop.detecta_flexiones_es_es(s) == []


def test_alucinar_es_ambiguo_y_queda_fuera():
    # "alucinar" tambien se usa en MX (otro sentido) -> excluido del set activo.
    assert "alucinar" in trop.AMBIGUOS_FUERA
    assert _formas("eso es alucinante, me alucina") == []


def test_pretendido_ambiguo_peninsular_no_genera_falso_positivo_en_mx():
    # frases MX comunes que comparten formas con sufijos verbales -ar
    for s in ("nos vemos al rato", "vamos al estadio", "somos campeones"):
        assert trop.detecta_flexiones_es_es(s) == [], s


# --- cobertura ---------------------------------------------------------------

def test_cobertura_supera_la_lista_cerrada_de_12():
    # la red ahora vigila bastante MAS que ~12 lemas y muchas mas formas.
    cob = trop.cobertura()
    assert cob.lemas_totales >= 12
    assert cob.formas_totales > cob.lemas_totales  # hay flexiones, no solo lemas
    # debe cubrir bastantes formas (verbos -ar generan muchas)
    assert cob.formas_totales >= 50


def test_cobertura_registra_lemas_disparados():
    _, cob = trop.evaluar_tropicalizacion("eso mola y vende los coches")
    assert cob.lemas_disparados == ["coche", "molar"]
    # y sobre copy limpio, ninguno
    _, cob2 = trop.evaluar_tropicalizacion("Qué chido el carro nuevo.")
    assert cob2.lemas_disparados == []


def test_amplia_estrictamente_al_gate_viejo_para_los_lemas_compartidos():
    # Para una forma que es EL LEMA exacto (no flexion), ambos detectores
    # coinciden: lo que el gate viejo marca, el nuevo tambien.
    texto = "vale, vosotros, coche, ordenador, movil, zumo, flipar, molar, currar, guay"
    viejo = set(checks.detecta_espanolismos(texto))
    nuevo = set(_lemas(texto))
    assert viejo.issubset(nuevo), f"el nuevo detector deberia cubrir todo lo viejo; faltan {viejo - nuevo}"


# --- mini-runner sin pytest (mismo patron que test_checks_copy.py) -----------

def _main() -> int:
    funcs = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    fallos = 0
    for f in funcs:
        try:
            f()
            print(f"PASS {f.__name__}")
        except AssertionError as e:
            fallos += 1
            print(f"FAIL {f.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            fallos += 1
            print(f"ERROR {f.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(funcs) - fallos}/{len(funcs)} pruebas OK")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_main())
