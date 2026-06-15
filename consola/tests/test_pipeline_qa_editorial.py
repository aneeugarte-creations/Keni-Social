"""Tests de la QA de la FUENTE (pre-copy) por DOCUMENTO de Texto del pipeline.

El equipo NO usa skills: la QA se hace adjuntando un DOCUMENTO de la Texto con los criterios.
Regla del dueño: "si el documento existe, adjúntalo; si no existe, créalo y adjúntalo." La QA
corre ANTES del copy y por TEMA (fuente): criba la NOTA de origen y persiste un veredicto
ESTRUCTURADO (`no_verificado`/`problema`) sobre el TEMA. Aquí cubrimos, OFFLINE (mock de claude):
  - `asegurar_documento_qa` crea el documento si falta (idempotente).
  - `lanzar_qa_fuente` enlaza una generación a la etapa QA (`gen_id`) y deja el tema `en_curso`.
  - el `procesar` (vía lanzador completo) persiste el veredicto estructurado sobre el tema.

Usa la fixture `entorno` (Postgres aislado + Texto en tmp) y construye el cliente con un
lanzador de generación inyectado (NUNCA se llama a `claude`).
"""

from __future__ import annotations

from keni_consola import generaciones, libtexto, repos
from keni_consola import pipeline_contenido as pc
from keni_consola.pipeline_contenido import ORIGEN_PIPELINE

from .conftest import _cliente, lanzador_generacion_completa


def _tema(titulo: str = "Tema QA", marca: str = "unotv") -> dict:
    """Crea un tema del pipeline con su nota de origen en `descripcion`, y lo devuelve."""
    return repos.crear_contenido(
        clase="contenido", titulo=titulo, marca=marca, origen=ORIGEN_PIPELINE,
        descripcion="Nota de origen: título + resumen + enlace.",
    )


def test_asegurar_documento_qa_lo_crea_si_falta(entorno):
    """El documento de criterios se CREA si no está en el store (idempotente)."""
    assert libtexto.obtener(pc.PROMPT_QA_ID) is None
    devuelto = pc.asegurar_documento_qa()
    assert devuelto == pc.PROMPT_QA_ID
    doc = libtexto.obtener(pc.PROMPT_QA_ID)
    assert doc is not None
    assert doc.cuerpo.strip()  # tiene criterios
    # Es la criba de la FUENTE (pre-copy), NO el QA de copy: `PROMPT_QA_ID` = prompt/validacion.
    assert pc.PROMPT_QA_ID == "prompt/validacion"
    assert "CRIBA PREVIA" in doc.cuerpo
    # Idempotente: una segunda llamada no duplica.
    pc.asegurar_documento_qa()
    docs = [d for d in libtexto.listar(tipo="prompt") if d.id == pc.PROMPT_QA_ID]
    assert len(docs) == 1


def test_lanzar_qa_fuente_enlaza_generacion_y_marca_en_curso(entorno):
    """`lanzar_qa_fuente` lanza una generación, la enlaza a la etapa QA y deja el tema en_curso."""
    cliente = _cliente()  # noqa: F841 -- el lanzador noop deja la generación en `ejecutando`
    tema = _tema()
    gen = pc.lanzar_qa_fuente(tema, autor=None)
    assert gen is not None
    gen_id = gen["id"]

    # El tema queda en_curso (no se re-lanzará en la fase QA).
    actual = repos.obtener_contenido(tema["id"])
    assert (actual.get("qa_veredicto") or "") == pc.QA_EN_CURSO

    # El marcador de etapa QA enlaza la generación por `gen_id` (su stream se ve en el detalle).
    marcadores = [
        g for g in generaciones.listar(limite=None)
        if g.get("tipo") == pc.TIPO_ACTIVIDAD
        and (g.get("contenido_id") or "") == tema["id"]
    ]
    assert any((m.get("gen_id") or "") == gen_id for m in marcadores)

    # El detalle del pipeline surface el stream de la etapa QA.
    d = cliente.get(f"/api/pipelines/{tema['id']}")
    assert d.status_code == 200
    por_etapa = d.json()["generaciones_por_etapa"]
    assert "QA" in por_etapa
    assert por_etapa["QA"]["id"] == gen_id


def test_qa_fuente_persiste_veredicto_no_verificado(entorno):
    """Una criba 🟢 sin hallazgos -> veredicto `no_verificado` persistido en el tema."""
    salida = (
        "🟢 Fuente apta.\n\n"
        '```json\n{"veredicto": "🟢", "resumen": "OK", "hallazgos": []}\n```\n'
    )
    cliente = _cliente(lanzar_generacion=lanzador_generacion_completa(salida))  # noqa: F841
    tema = _tema()
    gen = pc.lanzar_qa_fuente(tema, autor=None)
    assert gen is not None
    actual = repos.obtener_contenido(tema["id"])
    assert (actual.get("qa_veredicto") or "") == pc.VERDICTO_NO_VERIFICADO


def test_endurecer_qa_fuente_barato_por_defecto(monkeypatch):
    """La criba de la fuente corre BARATA por defecto: Haiku + esfuerzo low + timeout 180 s.

    Es un filtro PERMISIVO (no redacción): no necesita el modelo/esfuerzo/timeout globales.
    Cada override es configurable por env y, vaciándolos todos, no se endurece nada (None).
    """
    from keni_consola.pipeline_contenido import _qa

    for var in ("KENI_QA_FUENTE_MODELO", "KENI_QA_FUENTE_ESFUERZO", "KENI_QA_FUENTE_TIMEOUT"):
        monkeypatch.delenv(var, raising=False)
    assert _qa._endurecer_qa_fuente() == {"modelo": "haiku", "esfuerzo": "low", "timeout": 180}

    # Overrides por env: otro modelo / sin override (cae al global correspondiente).
    monkeypatch.setenv("KENI_QA_FUENTE_MODELO", "sonnet")
    monkeypatch.setenv("KENI_QA_FUENTE_TIMEOUT", "60")
    endurecido = _qa._endurecer_qa_fuente()
    assert endurecido["modelo"] == "sonnet" and endurecido["timeout"] == 60

    monkeypatch.setenv("KENI_QA_FUENTE_MODELO", "")
    monkeypatch.setenv("KENI_QA_FUENTE_ESFUERZO", "")
    monkeypatch.setenv("KENI_QA_FUENTE_TIMEOUT", "0")
    assert _qa._endurecer_qa_fuente() is None


def test_qa_en_curso_ttl_configurable_con_minimo(monkeypatch):
    """El TTL del saneador de `en_curso` zombi es configurable, con suelo de 5 min.

    El suelo evita que un TTL absurdo resetee QAs VIVAS (debe superar el timeout de la criba).
    """
    from keni_consola import config

    monkeypatch.delenv("KENI_QA_EN_CURSO_TTL_MIN", raising=False)
    assert config.qa_en_curso_ttl_seg() == 30 * 60  # def 30 min
    monkeypatch.setenv("KENI_QA_EN_CURSO_TTL_MIN", "45")
    assert config.qa_en_curso_ttl_seg() == 45 * 60
    monkeypatch.setenv("KENI_QA_EN_CURSO_TTL_MIN", "1")
    assert config.qa_en_curso_ttl_seg() == 5 * 60  # suelo


def test_lanzar_qa_fuente_lanza_con_endurecer_barato(entorno, monkeypatch):
    """`lanzar_qa_fuente` pasa el `endurecer` barato (modelo/esfuerzo/timeout) al lanzador."""
    from keni_consola.pipeline_contenido import _qa

    cliente = _cliente()  # noqa: F841 -- inicializa stores; el lanzador real se intercepta abajo
    capturado: dict = {}

    def _fake_lanzar(**kw):
        capturado.update(kw)
        return {"id": "gen-qa-1"}

    monkeypatch.setattr(_qa.gen_dom, "lanzar", _fake_lanzar)
    tema = _tema()

    gen = pc.lanzar_qa_fuente(tema, autor=None)

    assert gen is not None and gen["id"] == "gen-qa-1"
    assert capturado["tipo"] == "pipeline"  # trabajo de la máquina: un solo tipo en Actividad
    assert capturado["endurecer"] == {"modelo": "haiku", "esfuerzo": "low", "timeout": 180}


def test_qa_fuente_persiste_veredicto_problema(entorno):
    """Una criba 🔴 con hallazgo de error -> veredicto `problema` + hallazgos persistidos."""
    salida = (
        "🔴 Problema de peso.\n\n"
        '```json\n{"veredicto": "🔴", "resumen": "Dato falso", '
        '"hallazgos": [{"tipo": "dato", "gravedad": "error", "explicacion": "inventado"}]}\n```\n'
    )
    cliente = _cliente(lanzar_generacion=lanzador_generacion_completa(salida))  # noqa: F841
    tema = _tema()
    gen = pc.lanzar_qa_fuente(tema, autor=None)
    assert gen is not None
    actual = repos.obtener_contenido(tema["id"])
    assert (actual.get("qa_veredicto") or "") == pc.VERDICTO_PROBLEMA
    assert "inventado" in (actual.get("qa_hallazgos") or "")
