#!/usr/bin/env python3
"""Tests unitarios para las funciones de deteccion de copyright/agencia e inferencia de pais.

Funciones bajo prueba (PURAS: no tocan red ni disco):
  - detectar_copyright(texto_ocr, titulo, descripcion, dominio_origen)
  - inferir_pais_origen(texto_ocr, titulo, descripcion, idioma_plataforma)
  - _detectar_idioma_unicode(texto)

Ejecutar con:
  pytest consola/src/keni_consola/motores/verifica_video/test_copyright_pais.py -v
  # o directamente:
  python3 consola/src/keni_consola/motores/verifica_video/test_copyright_pais.py
"""

from __future__ import annotations

from pathlib import Path

# analiza-video.py usa guion en el nombre (no es un modulo Python valido directamente).
# Importamos con importlib para no renombrar el archivo original.
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "analiza_video",
    Path(__file__).resolve().parent / "analiza-video.py",
)
assert _spec is not None, "No se encontro analiza-video.py junto a este test"
_mod = _ilu.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

detectar_copyright = _mod.detectar_copyright
inferir_pais_origen = _mod.inferir_pais_origen
_detectar_idioma_unicode = _mod._detectar_idioma_unicode


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _copyright(texto_ocr="", titulo="", descripcion="", dominio=""):
    return detectar_copyright(
        texto_ocr=texto_ocr,
        titulo=titulo,
        descripcion=descripcion,
        dominio_origen=dominio,
    )


def _pais(texto_ocr="", titulo="", descripcion="", idioma_plataforma=""):
    return inferir_pais_origen(
        texto_ocr=texto_ocr,
        titulo=titulo,
        descripcion=descripcion,
        idioma_plataforma=idioma_plataforma,
    )


# --------------------------------------------------------------------------- #
# detectar_copyright: casos SIN agencia                                       #
# --------------------------------------------------------------------------- #

def test_copyright_limpio_devuelve_sin_indicios():
    res = _copyright("un perro corriendo por el parque", "Video viral de perro", "")
    assert res["tiene_indicios"] is False
    assert res["agencias_detectadas"] == []
    assert "ausencia no garantiza" in res["resumen"]


def test_copyright_texto_vacio_devuelve_sin_indicios():
    res = _copyright("", "", "", "")
    assert res["tiene_indicios"] is False


# --------------------------------------------------------------------------- #
# detectar_copyright: watermark en OCR -> nivel alto                          #
# --------------------------------------------------------------------------- #

def test_copyright_storyful_en_ocr():
    res = _copyright(texto_ocr="Footage provided by STORYFUL - all rights reserved")
    assert res["tiene_indicios"] is True
    agencias = [d["agencia"] for d in res["agencias_detectadas"]]
    assert "Storyful" in agencias
    niveles = {d["agencia"]: d["nivel_confianza"] for d in res["agencias_detectadas"]}
    assert niveles["Storyful"] == "alto"
    assert "ATENCION" in res["resumen"]


def test_copyright_reuters_en_ocr():
    res = _copyright(texto_ocr="reuters.com watermark corner")
    assert res["tiene_indicios"] is True
    agencias = [d["agencia"] for d in res["agencias_detectadas"]]
    assert "Reuters" in agencias
    niveles = {d["agencia"]: d["nivel_confianza"] for d in res["agencias_detectadas"]}
    assert niveles["Reuters"] == "alto"


def test_copyright_viralhog_en_ocr():
    res = _copyright(texto_ocr="ViralHog 2024 watermark esquina inferior")
    assert res["tiene_indicios"] is True
    agencias = [d["agencia"] for d in res["agencias_detectadas"]]
    assert "ViralHog" in agencias


def test_copyright_ap_video_en_ocr():
    """AP VIDEO es el watermark usual en clips de Associated Press."""
    res = _copyright(texto_ocr="AP VIDEO footage of the protest")
    assert res["tiene_indicios"] is True
    agencias = [d["agencia"] for d in res["agencias_detectadas"]]
    assert "AP / Associated Press" in agencias


def test_copyright_afp_en_ocr():
    res = _copyright(texto_ocr="Images courtesy AFP 2025")
    assert res["tiene_indicios"] is True
    agencias = [d["agencia"] for d in res["agencias_detectadas"]]
    assert "AFP" in agencias


def test_copyright_getty_en_ocr():
    res = _copyright(texto_ocr="© Getty Images / corbis bettmann")
    assert res["tiene_indicios"] is True
    agencias = [d["agencia"] for d in res["agencias_detectadas"]]
    assert "Getty Images" in agencias


def test_copyright_jukin_en_ocr():
    res = _copyright(texto_ocr="Licensed via Jukin Media")
    assert res["tiene_indicios"] is True
    agencias = [d["agencia"] for d in res["agencias_detectadas"]]
    assert "Jukin Media" in agencias


def test_copyright_newsflare_en_ocr():
    res = _copyright(texto_ocr="NEWSFLARE exclusive footage")
    assert res["tiene_indicios"] is True
    agencias = [d["agencia"] for d in res["agencias_detectadas"]]
    assert "Newsflare" in agencias


# --------------------------------------------------------------------------- #
# detectar_copyright: mencion en titulo/descripcion -> nivel medio            #
# --------------------------------------------------------------------------- #

def test_copyright_storyful_en_titulo_nivel_medio():
    res = _copyright(titulo="Storyful: dramatic flood scene")
    assert res["tiene_indicios"] is True
    nivel = res["agencias_detectadas"][0]["nivel_confianza"]
    assert nivel == "medio"
    # Resumen no debe decir ATENCION (ese es solo para nivel alto)
    assert "Menciones" in res["resumen"] or "mencion" in res["resumen"].lower()


def test_copyright_reuters_en_descripcion_nivel_medio():
    res = _copyright(descripcion="Video provided by Reuters news agency")
    assert res["tiene_indicios"] is True
    nivel = res["agencias_detectadas"][0]["nivel_confianza"]
    assert nivel == "medio"


# --------------------------------------------------------------------------- #
# detectar_copyright: no duplica agencia si aparece en varias fuentes         #
# --------------------------------------------------------------------------- #

def test_copyright_no_duplica_agencia():
    res = _copyright(
        texto_ocr="reuters watermark visible",
        titulo="Reuters footage of event",
        descripcion="Courtesy Reuters",
    )
    agencias = [d["agencia"] for d in res["agencias_detectadas"]]
    assert agencias.count("Reuters") == 1


# --------------------------------------------------------------------------- #
# detectar_copyright: multiples agencias en el mismo video                    #
# --------------------------------------------------------------------------- #

def test_copyright_multiples_agencias():
    res = _copyright(
        texto_ocr="STORYFUL footage rights reserved",
        descripcion="Video provided by AFP via Reuters",
    )
    agencias = [d["agencia"] for d in res["agencias_detectadas"]]
    assert len(agencias) >= 2


# --------------------------------------------------------------------------- #
# detectar_copyright: insensible a mayusculas/minusculas                      #
# --------------------------------------------------------------------------- #

def test_copyright_case_insensitive():
    res = _copyright(texto_ocr="STORYFUL")
    assert res["tiene_indicios"] is True
    res2 = _copyright(texto_ocr="storyful")
    assert res2["tiene_indicios"] is True
    res3 = _copyright(texto_ocr="StOrYfUl")
    assert res3["tiene_indicios"] is True


# --------------------------------------------------------------------------- #
# _detectar_idioma_unicode                                                    #
# --------------------------------------------------------------------------- #

def test_idioma_unicode_tailandes():
    texto_thai = "สวัสดีครับ นี่คือวิดีโอจากประเทศไทย"
    resultado = _detectar_idioma_unicode(texto_thai)
    assert resultado == "th"


def test_idioma_unicode_japones():
    texto_jp = "東京で大きな火災が発生しました"
    resultado = _detectar_idioma_unicode(texto_jp)
    assert resultado in ("ja", "zh")  # CJK compartido; hiragana pesa mas


def test_idioma_unicode_coreano():
    texto_ko = "서울에서 대형 화재 발생"
    resultado = _detectar_idioma_unicode(texto_ko)
    assert resultado == "ko"


def test_idioma_unicode_arabe():
    texto_ar = "أخبار عاجلة من القاهرة"
    resultado = _detectar_idioma_unicode(texto_ar)
    assert resultado == "ar"


def test_idioma_unicode_ruso():
    texto_ru = "Новости из Москвы"
    resultado = _detectar_idioma_unicode(texto_ru)
    assert resultado == "ru"


def test_idioma_unicode_ucraniano():
    # Texto rico en letras exclusivas del ucraniano (і/І, ї/Ї, є/Є, ґ/Ґ).
    # La distincion ruso/ucraniano con Unicode-only requiere suficiente densidad
    # de letras exclusivas para superar el peso del Cirilico compartido.
    # Texto deliberadamente denso en exclusivas para que la heuristica funcione.
    texto_uk = "Підтвердження: є підтвердження, що Київ — столиця України, зі звітів. Ї є і ґ."
    resultado = _detectar_idioma_unicode(texto_uk)
    assert resultado == "uk", (
        f"Esperado 'uk', obtenido '{resultado}'. "
        "Nota: la distincion ruso/ucraniano por Unicode requiere letras exclusivas (і, ї, є, ґ); "
        "textos cortos o sin ellas devuelven 'ru' como fallback del cirilico."
    )


def test_idioma_unicode_solo_latin_devuelve_none():
    # Sin escritura no-latina no podemos determinar el idioma
    resultado = _detectar_idioma_unicode("Hello world esto es texto latino")
    assert resultado is None


def test_idioma_unicode_vacio_devuelve_none():
    assert _detectar_idioma_unicode("") is None
    assert _detectar_idioma_unicode("   ") is None


# --------------------------------------------------------------------------- #
# inferir_pais_origen: sin señales suficientes                                #
# --------------------------------------------------------------------------- #

def test_pais_sin_senales_devuelve_insuficiente():
    res = _pais("a dog running in a park", "Cute dog video")
    assert res["confianza"] == "insuficiente"
    assert res["pais_hipotesis"] is None
    assert res["fuentes_confirmacion"] == []
    assert "No se encontraron" in res["nota"]


def test_pais_texto_vacio_devuelve_insuficiente():
    res = _pais("", "", "", "")
    assert res["confianza"] == "insuficiente"


# --------------------------------------------------------------------------- #
# inferir_pais_origen: topónimos                                              #
# --------------------------------------------------------------------------- #

def test_pais_topónimo_tailandia():
    res = _pais(titulo="Inundaciones en Bangkok, Tailandia")
    assert res["pais_hipotesis"] is not None
    assert "Tailandia" in res["pais_hipotesis"] or res["codigo_iso"] == "TH"
    assert res["confianza"] in ("alta", "media")
    assert len(res["fuentes_confirmacion"]) >= 2


def test_pais_topónimo_bangkok():
    res = _pais(titulo="Flooding in Bangkok")
    assert res["codigo_iso"] == "TH"


def test_pais_topónimo_ucrania():
    res = _pais(titulo="Footage from Kyiv under attack")
    assert res["codigo_iso"] == "UA"


def test_pais_topónimo_mexico():
    res = _pais(titulo="Terremoto en la CDMX causa panico")
    assert res["codigo_iso"] == "MX"


def test_pais_topónimo_brasil():
    res = _pais(titulo="Enchentes em São Paulo Brasil")
    assert res["codigo_iso"] == "BR"


def test_pais_topónimo_japon():
    res = _pais(titulo="Earthquake near Tokyo Japan")
    assert res["codigo_iso"] == "JP"


# --------------------------------------------------------------------------- #
# inferir_pais_origen: escritura no-latina en OCR/titulo                     #
# --------------------------------------------------------------------------- #

def test_pais_escritura_thai_en_ocr():
    """OCR con escritura tailandesa -> hipotesis Tailandia."""
    texto_thai = "สวัสดีครับ การสั่นสะเทือน"  # "Hola, terremoto" en tailandes
    res = _pais(texto_ocr=texto_thai)
    assert res["codigo_iso"] == "TH"
    assert res["pais_hipotesis"] is not None
    assert len(res["fuentes_confirmacion"]) >= 2


def test_pais_escritura_coreana_en_titulo():
    texto_ko = "서울 대형 화재"
    res = _pais(titulo=texto_ko)
    assert res["codigo_iso"] == "KR"


def test_pais_escritura_arabe_en_ocr():
    texto_ar = "أخبار عاجلة من القاهرة"
    res = _pais(texto_ocr=texto_ar)
    # AR puede ser ambiguo (region arabe) pero debe detectar algo
    assert res["confianza"] != "insuficiente"
    assert res["codigo_iso"] is not None


# --------------------------------------------------------------------------- #
# inferir_pais_origen: fuentes de confirmacion                               #
# --------------------------------------------------------------------------- #

def test_pais_fuentes_tienen_url_valida():
    res = _pais(titulo="Floods in Tokyo Japan")
    for fuente in res["fuentes_confirmacion"]:
        assert "url" in fuente
        assert fuente["url"].startswith("http")
        assert "descripcion" in fuente
        assert "tipo" in fuente


def test_pais_fuentes_contienen_termino_busqueda():
    """El termino de busqueda debe aparecer en al menos una de las URLs."""
    titulo = "earthquake Tokyo"
    res = _pais(titulo=titulo)
    # Al menos una URL debe contener algo relacionado con el termino
    urls = [f["url"] for f in res["fuentes_confirmacion"]]
    assert any("earthquake" in u or "Tokyo" in u or "tokyo" in u for u in urls)


def test_pais_insuficiente_no_genera_fuentes():
    res = _pais("random text without location clues", "video viral")
    assert res["fuentes_confirmacion"] == []


# --------------------------------------------------------------------------- #
# inferir_pais_origen: topónimo en descripcion                               #
# --------------------------------------------------------------------------- #

def test_pais_topónimo_en_descripcion():
    res = _pais(descripcion="Footage captured near Buenos Aires, Argentina")
    assert res["codigo_iso"] == "AR"


# --------------------------------------------------------------------------- #
# inferir_pais_origen: confianza aumenta con topónimos multiples             #
# --------------------------------------------------------------------------- #

def test_pais_confianza_alta_con_multiples_topónimos():
    res = _pais(
        titulo="Inundaciones en Bangkok",
        descripcion="Flooding in Thailand near Bangkok city center",
    )
    assert res["codigo_iso"] == "TH"
    # Multiples topónimos deben subir la confianza
    assert res["confianza"] in ("alta", "media")


# --------------------------------------------------------------------------- #
# mini-runner (sin pytest)                                                    #
# --------------------------------------------------------------------------- #

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
