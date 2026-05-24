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


def test_no_viola_negacion_no_usar_bandera_con_escudo():
    # "no usar" es una de las advertencias de contexto -> no se considera propuesta
    s = "Recuerda: no usar bandera con escudo en el arte."
    assert not checks.viola_bandera_con_escudo(s)


def test_no_viola_bandera_y_escudo_fuera_de_la_ventana_de_proximidad():
    # la heuristica solo mira una ventana de 60 chars desde "bandera"; si "escudo"
    # cae mas lejos, no hay combinacion peligrosa detectable -> no viola.
    relleno = "decorando el plano " * 4  # empuja "escudo" mas alla de 60 chars
    s = f"Usa la bandera de fondo {relleno}y al final aparece el escudo."
    # sanity check: el gap supera la ventana de 60 chars que mira la heuristica
    assert s.index("escudo") - s.index("bandera") > 60
    assert not checks.viola_bandera_con_escudo(s)


def test_normaliza_quita_acentos_y_baja_a_minusculas():
    # _normaliza es la base de la deteccion robusta: minusculas + sin acentos
    assert checks._normaliza("Canción ESCUDÓ áéíóúñ") == "cancion escudo aeioun"
    # y por eso "BANDERA con ESCUDO" (mayusculas/acentos) sigue violando
    assert checks.viola_bandera_con_escudo("Pon la BANDERA con el ESCUDO nacional.")


# --- espanolismos (tropicalizacion) ---

def test_espanolismos_detecta_vale_vosotros_coche():
    s = "Vale, vosotros subid el coche al taller."
    hallados = checks.detecta_espanolismos(s)
    assert "vale" in hallados
    assert "vosotros" in hallados
    assert "coche" in hallados


def test_espanolismos_insensible_a_acentos_y_mayusculas():
    # mismo termino con acento y/o mayusculas debe detectarse igual
    assert checks.detecta_espanolismos("MÓVIL") == ["movil"]
    assert checks.detecta_espanolismos("Móvil y ZUMO") == ["movil", "zumo"]


def test_espanolismos_copy_mexicano_sin_falsos_positivos():
    # copy ya tropicalizado: nada que marcar
    s = (
        "Sale, ustedes suban el carro al taller. Agarren su celular y su jugo, "
        "que esto se va a poner bueno."
    )
    assert checks.detecta_espanolismos(s) == []


def test_espanolismos_casa_palabra_completa_no_subcadena():
    # "valeroso" contiene "vale", "sosos" contiene "os": NO deben marcarse
    s = "Un gesto valeroso de jugadores sosos no es espanolismo."
    assert checks.detecta_espanolismos(s) == []


def test_espanolismos_no_repite_termino():
    s = "Vale, vale y otra vez vale."
    assert checks.detecta_espanolismos(s) == ["vale"]


def test_espanolismos_ambiguos_no_disparan_el_gate():
    # piso/tio/coger son ambiguos en MX -> conservador: no se marcan
    s = "Mi tío barrió el piso y fue a coger el balón."
    assert checks.detecta_espanolismos(s) == []


def test_espanolismos_preserva_orden_de_aparicion():
    # casa formas base de la lista (molar/flipar/guay), no flexiones (mola/flipo)
    assert checks.detecta_espanolismos("guay y luego vale") == ["guay", "vale"]
    assert checks.detecta_espanolismos("vale y luego guay") == ["vale", "guay"]


def test_espanolismos_casa_forma_base_no_flexion():
    # el detector es conservador: marca "molar"/"flipar" (lema), no "mola"/"flipo"
    assert checks.detecta_espanolismos("eso mola y yo flipo") == []
    assert checks.detecta_espanolismos("eso es de flipar y molar") == ["flipar", "molar"]


# --- extraer_secciones: encabezados de plataforma ---

def test_extraer_secciones_carrusel_es_se_mapea_a_carrusel():
    # encabezado en espanol "Carrusel" -> clave normalizada "carrusel"
    s = "## Carrusel\n1/3 slide uno\n2/3 slide dos\n\n## Instagram\nhola"
    secciones = checks.extraer_secciones(s)
    assert "carrusel" in secciones
    assert secciones["carrusel"].startswith("1/3")


def test_extraer_secciones_carousel_en_se_mapea_a_carrusel():
    # encabezado en ingles "Carousel" -> clave normalizada "carrusel".
    # checks.py mapea a "carrusel" los encabezados que empiezan por
    # "carrus" (es), "carrou" (fr) o "carou" (en/"carousel").
    s = "## Carousel\nSlide A\nmas texto\n\n## Instagram\nhola"
    secciones = checks.extraer_secciones(s)
    assert "carrusel" in secciones
    assert "carousel" not in secciones
    assert secciones["carrusel"].startswith("Slide A")


# --- limites: sin seccion de la plataforma -> [] (no se afirma violacion) ---

def test_excede_limite_x_sin_seccion_x_no_afirma():
    # no hay seccion X identificable -> no se puede afirmar violacion -> []
    assert checks.excede_limite_x("## Instagram\nhola mundo") == []


def test_excede_limite_youtube_sin_seccion_youtube_no_afirma():
    assert checks.excede_limite_youtube("## Instagram\nhola") == []


def test_excede_limite_tuits_sin_hilo_ni_x_no_afirma():
    assert checks.excede_limite_tuits("## Instagram\nhola") == []


# --- YouTube: titulo sin "Titulo:" usa la primera linea ---

def test_titulo_youtube_sin_etiqueta_usa_primera_linea():
    # sin linea "Titulo:", se mide la primera linea de copy de la seccion
    primera = "p" * 71
    s = f"## YouTube\n{primera}\nDescripción: algo"
    problemas = checks.excede_limite_youtube(s)
    assert problemas and "71" in problemas[0]


def test_titulo_youtube_sin_etiqueta_primera_linea_corta_pasa():
    s = "## YouTube\nTitulo corto y valido\nDescripción: algo"
    assert checks.excede_limite_youtube(s) == []


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
