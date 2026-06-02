"""Tests del QA EDITORIAL por DOCUMENTO de Biblioteca del pipeline (Feature 2).

El equipo NO usa skills: el QA editorial se hace adjuntando un DOCUMENTO de la Biblioteca con
los criterios de revisión. Regla del dueño: "si el documento existe, adjúntalo; si no existe,
créalo y adjúntalo." Aquí cubrimos, OFFLINE (mockeando el lanzamiento de claude):
  - `asegurar_documento_qa` crea el documento si falta (idempotente).
  - `lanzar_qa_editorial` enlaza una generación a la etapa QA (`gen_id`) y deja la pieza
    `en_curso` (la etapa QA se ve "en curso" hasta que el veredicto se reconcilia).
  - `reconciliar_qa_en_curso` persiste el veredicto real cuando el QA editorial completa.

Usa la fixture `entorno` (Postgres aislado + Biblioteca en tmp) y construye el cliente con un
lanzador de generación inyectado (NUNCA se llama a `claude`).
"""

from __future__ import annotations

from keni_consola import biblioteca, generaciones, repos
from keni_consola import pipeline_contenido as pc
from keni_consola.pipeline_contenido import ORIGEN_PIPELINE

from .conftest import _cliente, lanzador_generacion_completa


def _tema_y_borrador(copy: str = "Copy de prueba para el QA.", marca: str = "unotv") -> dict:
    """Crea un tema del pipeline + un borrador (publicación) nidado, y lo devuelve."""
    tema = repos.crear_contenido(
        clase="contenido", titulo="Tema QA", marca=marca, origen=ORIGEN_PIPELINE
    )
    pub = repos.crear_contenido_plataforma(
        contenido_id=tema["id"], red="x", estado="borrador", copy=copy,
    )
    return pub


def test_asegurar_documento_qa_lo_crea_si_falta(entorno):
    """El documento de criterios se CREA si no está en el store (idempotente)."""
    # Aislamos la semilla para que NO exista cuerpo efectivo previo: así probamos la creación
    # con criterios por defecto. (Si la semilla existe, también se materializa; ambos casos OK.)
    assert biblioteca.obtener(pc.PROMPT_QA_ID) is None
    devuelto = pc.asegurar_documento_qa()
    assert devuelto == pc.PROMPT_QA_ID
    doc = biblioteca.obtener(pc.PROMPT_QA_ID)
    assert doc is not None
    assert doc.cuerpo.strip()  # tiene criterios
    # Idempotente: una segunda llamada no duplica.
    pc.asegurar_documento_qa()
    docs = [d for d in biblioteca.listar(tipo="prompt") if d.id == pc.PROMPT_QA_ID]
    assert len(docs) == 1


def test_lanzar_qa_editorial_enlaza_generacion_y_marca_en_curso(entorno):
    """`lanzar_qa_editorial` lanza una generación, la enlaza a la etapa QA y deja la pieza en_curso."""
    # Cliente con un lanzador que deja la generación en `ejecutando` (QA en vuelo).
    cliente = _cliente()  # noqa: F841 -- construir la app inyecta el lanzador noop global
    pub = _tema_y_borrador()
    gen = pc.lanzar_qa_editorial(pub, autor=None)
    assert gen is not None
    gen_id = gen["id"]

    # La pieza queda en_curso (no se re-lanzará en la pasada QA).
    actual = repos.obtener_publicacion(pub["id"])
    assert (actual.get("veredicto") or "") == pc.QA_EN_CURSO

    # El marcador de etapa QA enlaza la generación por `gen_id` (Feature 1: su stream se ve).
    marcadores = [
        g for g in generaciones.listar(limite=None)
        if g.get("tipo") == pc.TIPO_ACTIVIDAD
        and (g.get("contenido_id") or "") == pub["contenido_id"]
    ]
    assert any((m.get("gen_id") or "") == gen_id for m in marcadores)

    # El detalle del pipeline surface el stream de la etapa QA.
    d = cliente.get(f"/api/pipelines/{pub['contenido_id']}")
    assert d.status_code == 200
    por_etapa = d.json()["generaciones_por_etapa"]
    assert "QA" in por_etapa
    assert por_etapa["QA"]["id"] == gen_id


def test_reconciliar_qa_en_curso_persiste_veredicto(entorno):
    """Cuando el QA editorial completa (veredicto editorial atado a la pieza), el sweep lo persiste.

    El lanzador `lanzador_generacion_completa` corre el `procesar` REAL del QA con una salida
    canned (semáforo 🟢 = listo), que registra el veredicto atado a la pieza
    (`registrar_veredicto_qa`). Tras eso, `reconciliar_qa_en_curso` lo mapea al veredicto de la
    pieza ('listo').
    """
    salida = (
        "🟢 LISTO PARA APROBAR\n\nEl copy cumple la línea editorial.\n\n"
        '```json\n{"veredicto": "🟢", "resumen": "Todo correcto", "hallazgos": []}\n```\n'
    )
    cliente = _cliente(lanzar_generacion=lanzador_generacion_completa(salida))  # noqa: F841
    pub = _tema_y_borrador()
    gen = pc.lanzar_qa_editorial(pub, autor=None)
    assert gen is not None
    # Con el lanzador "completo", el procesar ya corrió y persistió el veredicto editorial.
    reconciliados = pc.reconciliar_qa_en_curso()
    ids = {r["id"] for r in reconciliados}
    assert pub["id"] in ids
    actual = repos.obtener_publicacion(pub["id"])
    assert (actual.get("veredicto") or "") == "listo"


def test_validar_borrador_prefiere_editorial(entorno):
    """`validar_borrador` lanza el QA editorial (no el léxico) cuando el documento existe."""
    cliente = _cliente()  # noqa: F841
    pub = _tema_y_borrador()
    r = pc.validar_borrador(pub)
    assert r is not None
    assert r["verdicto"] == pc.QA_EN_CURSO
    assert r["modo"] == "editorial"
    actual = repos.obtener_publicacion(pub["id"])
    assert (actual.get("veredicto") or "") == pc.QA_EN_CURSO
