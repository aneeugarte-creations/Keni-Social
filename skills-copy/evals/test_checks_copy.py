#!/usr/bin/env python3
"""Pruebas del MOTOR de evaluacion de copy (`checks.py`) con fixtures sinteticos.

Estas pruebas NO usan el modelo: alimentan a las funciones de `checks` con copy
"bueno" y "malo" escrito a mano y comprueban que cada propiedad acepta lo bueno y
caza lo malo. Asi el corredor local (`run.sh` -> `assert_output.py`) hereda una
logica de aserciones ya verificada en CI. Es CI-safe (Python puro).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import checks  # noqa: E402

# Fuente sintetica con datos concretos para probar fidelidad.
FUENTE = (
    "El club confirmó el fichaje del delantero por 40 millones de euros. "
    'El atacante firma por 5 temporadas. "Estoy muy feliz de llegar", dijo el jugador.'
)


def _copy_bueno() -> str:
    post_x = "El delantero llega al club por 40 millones de euros. Firma por 5 temporadas. La afición ya lo espera."
    return f"""## X / Twitter
{post_x}
Caracteres: {checks.contar_code_points(post_x)}

## Instagram
Bombazo: el delantero ya es del club.
#Fichaje #Futbol

## YouTube
Título: El delantero llega al club por 40 millones de euros
Descripción: todos los detalles del fichaje.

## Hilo (X)
1/2 El delantero ya es del club. Llega por 40 millones de euros tras una negociación exprés con el rival directo.
2/2 Firma por 5 temporadas. "Estoy muy feliz de llegar", dijo el jugador. La presentación, la próxima semana.

## Auto-verificación
- ✅ Fechas y números coinciden con la fuente (40 mde, 5 temporadas).
- ✅ Reglas legales: sin bandera con escudo.
- ✅ Límites por plataforma verificados con contar.py.

Veredicto: LISTO PARA APROBAR.
"""


# --- bloque de verificacion ---

def test_verificacion_presente_en_copy_bueno():
    assert checks.tiene_bloque_verificacion(_copy_bueno())


def test_verificacion_ausente_si_no_hay_simbolos():
    assert not checks.tiene_bloque_verificacion("Solo el copy, sin veredicto ni simbolos.")


def test_verificacion_ausente_si_solo_simbolo_sin_veredicto():
    assert not checks.tiene_bloque_verificacion("✅ todo bien pero sin la palabra final")


# --- limites de caracteres ---

def test_copy_bueno_no_excede_limites():
    s = _copy_bueno()
    assert checks.excede_limite_x(s) == []
    assert checks.excede_limite_tuits(s) == []
    assert checks.excede_limite_youtube(s) == []


def test_x_excede_280():
    largo = "x" * 281
    s = f"## X / Twitter\n{largo}\n\n## Instagram\nhola"
    problemas = checks.excede_limite_x(s)
    assert problemas and "281" in problemas[0]


def test_tuit_de_hilo_excede_280():
    tuit_largo = "y" * 281
    s = f"## Hilo (X)\n1/2 {tuit_largo}\n2/2 corto y normal.\n"
    problemas = checks.excede_limite_tuits(s)
    assert problemas, "no detecto el tuit largo"
    assert "1/2" in problemas[0]


def test_titulo_youtube_excede_70():
    titulo = "z" * 71
    s = f"## YouTube\nTítulo: {titulo}\nDescripción: x"
    problemas = checks.excede_limite_youtube(s)
    assert problemas and "71" in problemas[0]


def test_titulo_youtube_exacto_70_pasa():
    titulo = "z" * 70
    s = f"## YouTube\nTítulo: {titulo}\nDescripción: x"
    assert checks.excede_limite_youtube(s) == []


# --- bandera con escudo ---

def test_no_viola_bandera_sin_escudo():
    s = "Usaremos la bandera de México (sin escudo) como fondo."
    assert not checks.viola_bandera_con_escudo(s)


def test_no_viola_cuando_la_verificacion_advierte():
    s = "✅ Reglas legales: no se propone bandera con escudo (prohibido)."
    assert not checks.viola_bandera_con_escudo(s)


def test_viola_bandera_con_escudo():
    s = "Cierra el reel con la bandera con escudo nacional ondeando."
    assert checks.viola_bandera_con_escudo(s)


# --- numeros inventados ---

def test_copy_bueno_sin_numeros_inventados():
    # el 1/2, 2/2 son numeracion de hilo; 40 y 5 estan en la fuente
    assert checks.numeros_inventados(_copy_bueno(), FUENTE) == []


def test_numero_inventado_se_caza():
    s = "## X\nEl delantero marcó 99 goles la temporada pasada.\n\n## Veredicto\n✅"
    problemas = checks.numeros_inventados(s, FUENTE)
    assert any('"99"' in p for p in problemas)


def test_numero_de_la_verificacion_no_cuenta():
    # un numero que solo aparece en el bloque de verificacion no se marca
    s = "## X\nEl delantero llega al club.\n\n## Auto-verificación\n⚠️ Revisar el dato 99 contra la fuente.\nVeredicto: revisar."
    assert checks.numeros_inventados(s, FUENTE) == []


# --- citas inventadas ---

def test_cita_real_no_se_marca():
    s = '## X\nEl jugador habló: "Estoy muy feliz de llegar".\n\nVeredicto: ✅'
    assert checks.citas_inventadas(s, FUENTE) == []


def test_cita_inventada_se_caza():
    s = '## X\nEl jugador dijo: "Vengo a ganar todos los títulos posibles".\n\nVeredicto: ✅'
    problemas = checks.citas_inventadas(s, FUENTE)
    assert problemas, "no detecto la cita inventada"


# --- informe agregado ---

def test_evaluar_copy_bueno_pasa_todo():
    inf = checks.evaluar_copy(_copy_bueno(), FUENTE)
    assert inf.ok, "copy bueno deberia pasar todas las comprobaciones:\n" + inf.texto()


def test_evaluar_copy_malo_falla():
    malo = (
        "## X / Twitter\n" + ("a" * 300) + "\n\n"
        "## YouTube\nTítulo: " + ("b" * 80) + "\n\n"
        "El reel cierra con la bandera con escudo. El delantero marcó 99 goles."
        # sin bloque de verificacion
    )
    inf = checks.evaluar_copy(malo, FUENTE)
    assert not inf.ok
    fallidos = {r.nombre for r in inf.fallos()}
    # debe fallar al menos: X, YouTube, verificacion, bandera, numeros
    assert "X <= 280" in fallidos
    assert "titulo YouTube <= 70" in fallidos
    assert any("auto-verificacion" in n for n in fallidos)
    assert "sin bandera con escudo" in fallidos
    assert "sin numeros ausentes de la fuente" in fallidos


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
