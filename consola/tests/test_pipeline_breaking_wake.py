"""PRIORIDAD del pipeline: una última hora despierta el loop de PRODUCCIÓN (no sólo polling).

Cuando la fase de INVESTIGACIÓN admite un tema `breaking`, no debe esperar al siguiente tick de
15s para que se le redacte el copy: pide un barrido inmediato del loop de producción vía el flag
cross-proceso `barrido_solicitado` (mecanismo existente, `db_latidos.solicitar_barrido`). El tick
de 15s sigue de fallback. OFFLINE: la fase se stubea para no tocar feeds/red.
"""

from __future__ import annotations

from keni_consola import db_latidos, marcas
from keni_consola.pipeline_contenido import _barrido

# --------------------------------------------------------------------------- #
# El seam `_despertar_daemon` enruta al mecanismo existente y nunca lanza      #
# --------------------------------------------------------------------------- #


def test_despertar_daemon_solicita_barrido(monkeypatch):
    llamadas: list[str] = []
    monkeypatch.setattr(db_latidos, "solicitar_barrido", lambda d: llamadas.append(d) or True)
    _barrido._despertar_daemon("produccion")
    assert llamadas == ["produccion"]


def test_despertar_daemon_nunca_lanza(monkeypatch):
    def _boom(_d):
        raise RuntimeError("BD caída")

    monkeypatch.setattr(db_latidos, "solicitar_barrido", _boom)
    _barrido._despertar_daemon("produccion")  # no debe propagar (best-effort)


# --------------------------------------------------------------------------- #
# Integración: admitir un breaking despierta producción; uno normal no         #
# --------------------------------------------------------------------------- #


def _stub_investigacion(monkeypatch, *, categoria: str):
    """Stubea la fase de investigación para que admita UN tema con la `categoria` dada."""
    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")
    monkeypatch.setattr(_barrido._admitir, "caducar_temas_viejos", lambda: None)
    monkeypatch.setattr(_barrido._admitir, "caducar_qa_clusters_en_curso", lambda: None)
    monkeypatch.setattr(_barrido, "ejecutar_verificar_clusters", lambda *, autor=None: [])
    monkeypatch.setattr(_barrido._admitir, "temas_en_vuelo", lambda marca: 0)
    monkeypatch.setattr(_barrido._admitir, "cupos_categoria_restantes", lambda marca: None)
    monkeypatch.setattr(_barrido._admitir, "cupo_produccion_restante", lambda marca: None)
    marca0 = list(marcas.ids())[0]

    def _promover(marca, **kw):
        if marca == marca0:
            return [{"id": "t-1", "marca": marca, "categoria": categoria}]
        return []

    monkeypatch.setattr(_barrido, "promover_clusters_marca", _promover)
    despertados: list[str] = []
    monkeypatch.setattr(_barrido, "_despertar_daemon", lambda d: despertados.append(d))
    return despertados


def test_breaking_admitido_despierta_produccion(entorno, monkeypatch):
    despertados = _stub_investigacion(monkeypatch, categoria="breaking")
    res = _barrido._ejecutar_investigacion()
    assert any(t.get("categoria") == "breaking" for t in res["temas"])
    assert despertados == ["produccion"]  # despertó el loop de producción una vez


def test_admision_normal_no_despierta(entorno, monkeypatch):
    despertados = _stub_investigacion(monkeypatch, categoria="mx")
    res = _barrido._ejecutar_investigacion()
    assert res["temas"]  # se admitió un tema...
    assert despertados == []  # ...pero al no ser breaking, no se fuerza barrido (basta el tick)
