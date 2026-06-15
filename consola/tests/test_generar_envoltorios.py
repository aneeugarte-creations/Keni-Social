"""Envoltorios del copy migrados a la Biblioteca (`prompt/envoltorios/*`). PURO, sin BD.

Regla de producto: TODOS los prompts de IA se gestionan desde la Biblioteca. Estos tests
fijan el contrato de la migración de los bloques de `dominio.generar`:

  - REGRESIÓN DE ORO (byte-idéntico): con la semilla sin editar, cada instrucción compuesta
    es EXACTAMENTE la misma que producía el código hardcodeado previo (literales capturados
    de la versión anterior). Si la semilla o el ensamblaje divergen, esto revienta.
  - La SEMILLA es la ÚNICA fuente del texto: ya no hay `_FALLBACK_*` duplicado en código (solo
    «sin emojis» conserva un respaldo MÍNIMO, `INSTRUCCION_SIN_EMOJIS`).
  - Un doc EDITADO en el store gana (el texto sale de la Biblioteca, los valores del código).
  - Sin doc NI semilla, los envoltorios estructurales degradan a vacío con warning (camino
    inalcanzable: lo cubre el test de cobertura semilla↔código).
"""

from __future__ import annotations

import pytest

from keni_consola import libtexto
from keni_consola.dominio import generar


@pytest.fixture(autouse=True)
def _store_tmp(monkeypatch, tmp_path):
    """Store de la Biblioteca FALSO y VACÍO en tmp: el cuerpo efectivo cae a la SEMILLA."""
    monkeypatch.setenv("KENI_TEXTO_DIR", str(tmp_path / "texto"))


# --------------------------------------------------------------------------- #
# Literales de ORO: salida EXACTA del código hardcodeado previo a la migración #
# --------------------------------------------------------------------------- #

_GOLD_SIN_EMOJIS = 'No uses emojis en el copy.'

_GOLD_REDES_X_FB = 'Genera el copy SOLO para estas redes: X, Facebook. Límites técnicos de caracteres (no los excedas): X máx 25000 caracteres, Facebook sin tope técnico. Mantén tu formato y tu auto-verificación habituales. Además, al FINAL de toda tu respuesta, añade un único bloque de código cercado ```json con esta forma exacta: {"piezas": [{"red": "<id>", "texto": "<copy de esa red>", "copy_in": "<texto que va DENTRO de la imagen>"}, ...]}, usando como <id> únicamente estos valores: "x", "facebook". Incluye exactamente UNA pieza por cada red pedida (nunca dos de la misma red). Si la pieza de una red es un HILO o un CARRUSEL, va numerada DENTRO de su "texto": en un hilo, un tuit por párrafo con prefijo "1/n ", "2/n "… y cada tuit dentro del límite de la red; en un carrusel, las slides separadas por una línea con solo "---". El `copy_in` es el texto que va SOBRE la imagen (titular/claim corto), distinto del `texto` que la acompaña; respeta la línea editorial de texto-en-imagen de la marca adjunta, sale siempre sin emojis y deja "" si la pieza no lleva imagen.'  # noqa: E501 -- literal de ORO byte-exacto

_GOLD_CU_MIXTO = 'Este copy se publicará TAL CUAL en estas redes: Instagram, X, Facebook. Escribe UN SOLO copy que sirva igual para todas (NO una variante por red) y UN SOLO texto-en-imagen. Para que valga en todas, el copy no excede el límite técnico más estricto de esas redes: 2200 caracteres. NO añadas hashtags: el equipo los pone aparte por grupos donde corresponde. Mantén tu formato y tu auto-verificación habituales. Además, al FINAL de toda tu respuesta, añade un único bloque de código cercado ```json con esta forma exacta: {"texto": "<el copy>", "copy_in": "<texto que va DENTRO de la imagen: titular/claim corto, sin emojis; \\"\\" si no lleva imagen>", "tipo": "<post|carrusel>"}. El `copy_in` es el texto SOBRE la imagen (en un carrusel, el titular PARAGUAS de la PORTADA), distinto del `texto`; respeta la línea editorial de texto-en-imagen de la marca adjunta. DECIDE además el `tipo` de salida y decláralo en el json: "post" para un único post de foto (lo normal), o "carrusel" si el tema es un EXPLAINER o una LISTA de varios elementos (p. ej. "cuántos son y dónde están", varias claves, pasos o datos) que luciría mejor repartido en varias tarjetas que en una sola foto. Ante la duda, "post". NO incluyas "slides": las fotos de cada tarjeta las añade el equipo después.'  # noqa: E501 -- literal de ORO byte-exacto

_GOLD_CU_AMPLIAS = 'Este copy se publicará TAL CUAL en estas redes: Instagram, Facebook. Escribe UN SOLO copy que sirva igual para todas (NO una variante por red) y UN SOLO texto-en-imagen. Para que valga en todas, el copy no excede el límite técnico más estricto de esas redes: 2200 caracteres. NO añadas hashtags: el equipo los pone aparte por grupos donde corresponde. Mantén tu formato y tu auto-verificación habituales. Además, al FINAL de toda tu respuesta, añade un único bloque de código cercado ```json con esta forma exacta: {"texto": "<el copy>", "copy_in": "<texto que va DENTRO de la imagen: titular/claim corto, sin emojis; \\"\\" si no lleva imagen>", "tipo": "<post|carrusel>"}. El `copy_in` es el texto SOBRE la imagen (en un carrusel, el titular PARAGUAS de la PORTADA), distinto del `texto`; respeta la línea editorial de texto-en-imagen de la marca adjunta. DECIDE además el `tipo` de salida y decláralo en el json: "post" para un único post de foto (lo normal), o "carrusel" si el tema es un EXPLAINER o una LISTA de varios elementos (p. ej. "cuántos son y dónde están", varias claves, pasos o datos) que luciría mejor repartido en varias tarjetas que en una sola foto. Ante la duda, "post". NO incluyas "slides": las fotos de cada tarjeta las añade el equipo después.'  # noqa: E501 -- literal de ORO byte-exacto

_GOLD_SOLO_FB = 'Este copy se publicará TAL CUAL en estas redes: Facebook. Escribe UN SOLO copy que sirva igual para todas (NO una variante por red) y UN SOLO texto-en-imagen. NO añadas hashtags: el equipo los pone aparte por grupos donde corresponde. Mantén tu formato y tu auto-verificación habituales. Además, al FINAL de toda tu respuesta, añade un único bloque de código cercado ```json con esta forma exacta: {"texto": "<el copy>", "copy_in": "<texto que va DENTRO de la imagen: titular/claim corto, sin emojis; \\"\\" si no lleva imagen>", "tipo": "<post|carrusel>"}. El `copy_in` es el texto SOBRE la imagen (en un carrusel, el titular PARAGUAS de la PORTADA), distinto del `texto`; respeta la línea editorial de texto-en-imagen de la marca adjunta. DECIDE además el `tipo` de salida y decláralo en el json: "post" para un único post de foto (lo normal), o "carrusel" si el tema es un EXPLAINER o una LISTA de varios elementos (p. ej. "cuántos son y dónde están", varias claves, pasos o datos) que luciría mejor repartido en varias tarjetas que en una sola foto. Ante la duda, "post". NO incluyas "slides": las fotos de cada tarjeta las añade el equipo después.'  # noqa: E501 -- literal de ORO byte-exacto

_GOLD_CU_CARRUSEL = 'Este copy se publicará TAL CUAL en estas redes: Instagram, X, Facebook. Escribe UN SOLO copy que sirva igual para todas (NO una variante por red) y UN SOLO texto-en-imagen. Para que valga en todas, el copy no excede el límite técnico más estricto de esas redes: 2200 caracteres. NO añadas hashtags: el equipo los pone aparte por grupos donde corresponde. Mantén tu formato y tu auto-verificación habituales. Además, al FINAL de toda tu respuesta, añade un único bloque de código cercado ```json con esta forma exacta: {"texto": "<el copy>", "copy_in": "<texto que va DENTRO de la imagen: titular/claim corto, sin emojis; \\"\\" si no lleva imagen>", "tipo": "<post|carrusel>"}. El `copy_in` es el texto SOBRE la imagen (en un carrusel, el titular PARAGUAS de la PORTADA), distinto del `texto`; respeta la línea editorial de texto-en-imagen de la marca adjunta. DECIDE además el `tipo` de salida y decláralo en el json: esta HISTORIA agrupa 4 notas relacionadas. Elige "carrusel" SOLO si gana contándose como PANEL (una tarjeta por sub-historia: agenda de conciertos, partidos del día, lista de medidas…): la PORTADA lleva el titular paraguas (ese es el `copy_in`) y añades "slides": [{"titular": "<titular corto de ESA sub-historia, sin emojis, misma línea editorial de texto-en-imagen>", "foto": <número del catálogo o 0 si ninguna>}, …] con una entrada por sub-historia (2 a 9). Si la historia es UNA sola noticia contada por varios medios, elige "post" y NO incluyas "slides". Ante la duda, "post". FOTOS DISPONIBLES (de nuestras propias notas; asigna cada una al slide de SU sub-historia, por número):\n  1. Nota A\n  2. (sin título)'  # noqa: E501 -- literal de ORO byte-exacto


_FOTOS = [
    {"titulo": "Nota A", "imagen": "a.jpg"},
    {"titulo": "", "imagen": "b.jpg"},
]


# --------------------------------------------------------------------------- #
# Regresión de oro: semilla sin editar => composición byte-idéntica a la previa #
# --------------------------------------------------------------------------- #


def test_oro_sin_emojis_byte_identico():
    assert generar.instruccion_sin_emojis() == _GOLD_SIN_EMOJIS


def test_oro_instruccion_redes_byte_identica():
    assert generar.instruccion_redes(["x", "facebook"]) == _GOLD_REDES_X_FB


def test_oro_copy_unico_mixto_byte_identico():
    # Copy unificado: un solo `texto` acotado al límite más estricto entre las redes pedidas
    # (Instagram = 2200), sin versión corta aparte.
    assert generar.instruccion_copy_unico(["instagram", "x", "facebook"]) == _GOLD_CU_MIXTO


def test_oro_copy_unico_amplias_byte_identico():
    # Solo amplias con tope: UN copy + frase del límite más estricto.
    assert generar.instruccion_copy_unico(["instagram", "facebook"]) == _GOLD_CU_AMPLIAS


def test_oro_copy_unico_sin_tope_byte_identico():
    # Solo Facebook (sin tope técnico): UN copy sin frase de límite.
    assert generar.instruccion_copy_unico(["facebook"]) == _GOLD_SOLO_FB


def test_oro_copy_unico_con_carrusel_byte_identico():
    # Historia de 4 notas con catálogo de fotos: decisión post|carrusel incluida.
    instr = generar.instruccion_copy_unico(
        ["instagram", "x", "facebook"], n_notas=4, fotos_notas=_FOTOS
    )
    assert instr == _GOLD_CU_CARRUSEL


# --------------------------------------------------------------------------- #
# La SEMILLA es la ÚNICA fuente del texto (ya no hay _FALLBACK_* duplicado)     #
# --------------------------------------------------------------------------- #


def test_sin_emojis_semilla_coincide_con_su_fallback_minimo():
    """«sin emojis» conserva un respaldo MÍNIMO en código (`INSTRUCCION_SIN_EMOJIS`): debe
    seguir coincidiendo con su semilla. Los envoltorios estructurales (redes/carrusel/copy
    unificado) ya no tienen copia en código; su byte-exactitud la fijan los tests de ORO."""
    assert (
        libtexto.cuerpo_semilla(generar.PROMPT_ENVOLTORIO_SIN_EMOJIS).strip()
        == generar.INSTRUCCION_SIN_EMOJIS
    )


# --------------------------------------------------------------------------- #
# El doc de la Biblioteca GANA; los valores los sigue poniendo el código       #
# --------------------------------------------------------------------------- #


def test_doc_editado_gana_y_se_sustituyen_variables(monkeypatch):
    editados = {
        generar.PROMPT_ENVOLTORIO_REDES: "Solo estas redes: {{ETIQUETAS}} ({{LIMITES}}) ids {{IDS_JSON}}.",
        generar.PROMPT_ENVOLTORIO_SIN_EMOJIS: "Nada de emojis, por favor.",
    }
    monkeypatch.setattr(libtexto, "cuerpo_efectivo", lambda pid: editados.get(pid))
    assert generar.instruccion_sin_emojis() == "Nada de emojis, por favor."
    instr = generar.instruccion_redes(["x"])
    assert instr == 'Solo estas redes: X (X máx 25000 caracteres) ids "x".'


def test_doc_editado_de_carrusel_y_copy_unico(monkeypatch):
    editados = {
        generar.PROMPT_ENVOLTORIO_CARRUSEL: "Panel de {{N_NOTAS}} (máx {{MAX_SLIDES}}). {{CATALOGO_FOTOS}}",
        generar.PROMPT_ENVOLTORIO_COPY_UNICO: "[{{MODO_PUBLICACION}}|{{ETIQUETAS}}|{{VERSIONES}}|{{CIERRE_JSON}}]",
    }
    monkeypatch.setattr(libtexto, "cuerpo_efectivo", lambda pid: editados.get(pid))
    instr = generar.instruccion_copy_unico(["facebook"], n_notas=3)
    # El esqueleto editado gana; el código sigue montando modo/versiones/cierre.
    assert instr.startswith("[ TAL CUAL|Facebook|Escribe UN SOLO copy")
    # El cierre json incluye el bloque de carrusel, que sale del doc editado de carrusel.
    assert "Panel de 3 (máx 9). FOTOS DISPONIBLES: ninguna" in instr
    # Sin marcadores sin sustituir.
    assert "{{" not in instr


# --------------------------------------------------------------------------- #
# Sin doc NI semilla: degradación (con warning). Camino inalcanzable en la       #
# práctica (lo cubre el test de cobertura semilla↔código).                       #
# --------------------------------------------------------------------------- #


@pytest.fixture
def biblioteca_rota(monkeypatch, tmp_path):
    """Ni store ni semilla: `cuerpo_efectivo` revienta y la semilla apunta a un dir vacío."""

    def boom(_pid: str) -> str:
        raise RuntimeError("store roto (simulado)")

    monkeypatch.setattr(libtexto, "cuerpo_efectivo", boom)
    monkeypatch.setenv("KENI_TEXTO_SEMILLA", str(tmp_path / "semilla-vacia"))


def test_sin_doc_ni_semilla_degrada_con_warning(biblioteca_rota, caplog):
    """«sin emojis» conserva su fallback mínimo en código; los envoltorios estructurales
    (sin copia en código) degradan a vacío. Todos dejan warning. El test de cobertura
    semilla↔código garantiza que la semilla SIEMPRE está, así que esto no pasa en producción."""
    with caplog.at_level("WARNING", logger="keni_consola.generar"):
        assert generar.instruccion_sin_emojis() == _GOLD_SIN_EMOJIS  # respaldo mínimo seguro
        assert generar.instruccion_redes(["x", "facebook"]) == ""
        assert generar.instruccion_copy_unico(["instagram", "x", "facebook"]) == ""
    assert any("envoltorio" in r.message for r in caplog.records)
