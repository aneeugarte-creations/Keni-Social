"""Tests de la verificación de la FUENTE (pre-copy) por DOCUMENTO de Texto del pipeline.

El equipo NO usa skills: la verificación se hace adjuntando un DOCUMENTO de la Texto con los criterios.
Regla del dueño: "si el documento existe, adjúntalo; si no existe, créalo y adjúntalo." La verificación
corre ANTES del copy y sobre la HISTORIA (cluster, ADR 0011 F3): verifica la NOTA de origen y
persiste un verificación ESTRUCTURADO (`no_verificado`/`problema`) en el cluster. Aquí cubrimos,
OFFLINE (mock de claude):
  - `asegurar_documento_verificacion` crea el documento si falta (idempotente).
  - `lanzar_verificar_cluster` enlaza una generación, deja el cluster `en_curso` y corre barato.
  - el `procesar` (vía lanzador completo) persiste el verificación estructurado sobre el cluster.

Usa la fixture `entorno` (Postgres aislado + Texto en tmp) y construye el cliente con un
lanzador de generación inyectado (NUNCA se llama a `claude`).
"""

from __future__ import annotations

from datetime import UTC, datetime

from keni_consola import libtexto, repos
from keni_consola import pipeline_contenido as pc

from .conftest import _cliente, lanzador_generacion_completa


def _cluster(
    cid: str = "c-verificación",
    *,
    marca: str = "unotv",
    titulo: str = "Historia verificación",
    resumen: str = "México: el gobierno informa de seguridad en la CDMX",
) -> dict:
    """Siembra un cluster del pool (sin items): la nota de verificación = título + resumen."""
    repos.upsert_noticia_cluster({
        "id": cid, "titulo": titulo, "resumen": resumen, "marca": marca,
        "categoria": "mx", "geo": "MX", "clave": f"t:{cid}", "n_items": 1,
        "n_fuentes": 2, "idiomas": ["es"], "senal": 100, "score": 0.5,
        "breaking": 0, "primer_visto": "2026-06-01T00:00:00+00:00",
        "ultimo_visto": datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds"),
        "estado": "nuevo", "verificacion": "corroborada",
    })
    return repos.obtener_noticia_cluster(cid)


def test_asegurar_documento_verificacion_lo_crea_si_falta(entorno):
    """El documento de criterios se CREA si no está en el store (idempotente)."""
    assert libtexto.obtener(pc.PROMPT_VERIFICACION_ID) is None
    devuelto = pc.asegurar_documento_verificacion()
    assert devuelto == pc.PROMPT_VERIFICACION_ID
    doc = libtexto.obtener(pc.PROMPT_VERIFICACION_ID)
    assert doc is not None
    assert doc.cuerpo.strip()  # tiene criterios
    # Es la verificación de la FUENTE (pre-copy), NO el verificación de copy: `PROMPT_VERIFICACION_ID` = prompt/verificar.
    assert pc.PROMPT_VERIFICACION_ID == "prompt/verificar"
    assert "VERIFICACIÓN PREVIA" in doc.cuerpo
    # Idempotente: una segunda llamada no duplica.
    pc.asegurar_documento_verificacion()
    docs = [d for d in libtexto.listar(tipo="prompt") if d.id == pc.PROMPT_VERIFICACION_ID]
    assert len(docs) == 1


def test_lanzar_verificacion_cluster_enlaza_generacion_y_marca_en_curso(entorno):
    """`lanzar_verificar_cluster` lanza una generación y deja el cluster en_curso (lanzador noop)."""
    cliente = _cliente()  # noqa: F841 -- el lanzador noop deja la generación en `ejecutando`
    cluster = _cluster()
    gen = pc.lanzar_verificar_cluster(cluster, autor=None)
    assert gen is not None

    # El cluster queda en_curso (no se re-lanzará en la fase Verificar) hasta que el procesar lo selle.
    actual = repos.obtener_noticia_cluster(cluster["id"])
    assert (actual.get("verificacion_fuente") or "") == pc.VERIFICACION_EN_CURSO


def test_verificacion_cluster_persiste_veredicto_no_verificado(entorno):
    """Una verificación 🟢 sin hallazgos -> verificación `no_verificado` persistido en el cluster."""
    salida = (
        "🟢 Fuente apta.\n\n"
        '```json\n{"veredicto": "🟢", "resumen": "OK", "hallazgos": []}\n```\n'
    )
    cliente = _cliente(lanzar_generacion=lanzador_generacion_completa(salida))  # noqa: F841
    cluster = _cluster()
    gen = pc.lanzar_verificar_cluster(cluster, autor=None)
    assert gen is not None
    actual = repos.obtener_noticia_cluster(cluster["id"])
    assert (actual.get("verificacion_fuente") or "") == pc.VERIFICACION_NO_VERIFICADO


def test_verificacion_cluster_persiste_veredicto_problema(entorno):
    """Una verificación 🔴 con hallazgo de error -> verificación `problema` + hallazgos persistidos."""
    salida = (
        "🔴 Problema de peso.\n\n"
        '```json\n{"veredicto": "🔴", "resumen": "Dato falso", '
        '"hallazgos": [{"tipo": "dato", "gravedad": "error", "explicacion": "inventado"}]}\n```\n'
    )
    cliente = _cliente(lanzar_generacion=lanzador_generacion_completa(salida))  # noqa: F841
    cluster = _cluster()
    gen = pc.lanzar_verificar_cluster(cluster, autor=None)
    assert gen is not None
    actual = repos.obtener_noticia_cluster(cluster["id"])
    assert (actual.get("verificacion_fuente") or "") == pc.VERIFICACION_PROBLEMA
    assert "inventado" in (actual.get("verificar_hallazgos") or "")


def test_endurecer_verificacion_fuente_barato_por_defecto(monkeypatch):
    """La verificación de la fuente corre BARATA por defecto: Haiku + esfuerzo low + timeout 180 s.

    Es un filtro PERMISIVO (no redacción): no necesita el modelo/esfuerzo/timeout globales.
    Cada override es configurable por env y, vaciándolos todos, no se endurece nada (None).
    """
    from keni_consola.pipeline_contenido import _verificar

    for var in ("KENI_VERIFICACION_FUENTE_MODELO", "KENI_VERIFICACION_FUENTE_ESFUERZO", "KENI_VERIFICACION_FUENTE_TIMEOUT"):
        monkeypatch.delenv(var, raising=False)
    assert _verificar._endurecer_verificacion_fuente() == {"modelo": "haiku", "esfuerzo": "low", "timeout": 180}

    # Overrides por env: otro modelo / sin override (cae al global correspondiente).
    monkeypatch.setenv("KENI_VERIFICACION_FUENTE_MODELO", "sonnet")
    monkeypatch.setenv("KENI_VERIFICACION_FUENTE_TIMEOUT", "60")
    endurecido = _verificar._endurecer_verificacion_fuente()
    assert endurecido["modelo"] == "sonnet" and endurecido["timeout"] == 60

    monkeypatch.setenv("KENI_VERIFICACION_FUENTE_MODELO", "")
    monkeypatch.setenv("KENI_VERIFICACION_FUENTE_ESFUERZO", "")
    monkeypatch.setenv("KENI_VERIFICACION_FUENTE_TIMEOUT", "0")
    assert _verificar._endurecer_verificacion_fuente() is None


def test_verificacion_en_curso_ttl_configurable_con_minimo(monkeypatch):
    """El TTL del reparador de `en_curso` atascada es configurable, con suelo de 5 min.

    El suelo evita que un TTL absurdo resetee QAs VIVAS (debe superar el timeout de la verificación).
    """
    from keni_consola import config

    monkeypatch.delenv("KENI_VERIFICACION_EN_CURSO_TTL_MIN", raising=False)
    assert config.verificacion_en_curso_ttl_seg() == 30 * 60  # def 30 min
    monkeypatch.setenv("KENI_VERIFICACION_EN_CURSO_TTL_MIN", "45")
    assert config.verificacion_en_curso_ttl_seg() == 45 * 60
    monkeypatch.setenv("KENI_VERIFICACION_EN_CURSO_TTL_MIN", "1")
    assert config.verificacion_en_curso_ttl_seg() == 5 * 60  # suelo


def test_lanzar_verificacion_cluster_lanza_con_endurecer_barato(entorno, monkeypatch):
    """`lanzar_verificar_cluster` pasa el `endurecer` barato (modelo/esfuerzo/timeout) al lanzador."""
    from keni_consola.pipeline_contenido import _verificar

    cliente = _cliente()  # noqa: F841 -- inicializa stores; el lanzador real se intercepta abajo
    capturado: dict = {}

    def _fake_lanzar(**kw):
        capturado.update(kw)
        return {"id": "gen-verificación-c1"}

    monkeypatch.setattr(_verificar.gen_dom, "lanzar", _fake_lanzar)
    cluster = _cluster()

    gen = pc.lanzar_verificar_cluster(cluster, autor=None)

    assert gen is not None and gen["id"] == "gen-verificación-c1"
    assert capturado["tipo"] == "pipeline"  # trabajo de la máquina: un solo tipo en Actividad
    assert capturado["endurecer"] == {"modelo": "haiku", "esfuerzo": "low", "timeout": 180}
