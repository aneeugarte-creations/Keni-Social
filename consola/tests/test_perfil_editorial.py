"""Tests del perfil editorial por marca (`dominio.perfil_editorial`).

OFFLINE: nunca llama a `claude` (se inyecta un ejecutor falso) ni toca el dir real (se redirige
`_ruta_cache` y `_texto_editorial` con monkeypatch). Cubre: extracción + cache, refresco gateado
por hash/TTL (no relanza Haiku si está fresco), refresco al cambiar la editorial, sin-editorial
no llama, y el parseo tolerante de keywords (fences + sin acentos).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from keni_consola.dominio import perfil_editorial as pe


def _ejecutor(keywords):
    """Ejecutor falso: devuelve el JSON que `claude` produciría."""
    def run(_prompt, _carpeta):
        return json.dumps({"keywords": keywords})
    return run


def _preparar(monkeypatch, tmp_path, *, texto="Línea editorial de prueba: deportes, box, liga MX."):
    monkeypatch.setattr(pe, "_ruta_cache", lambda: tmp_path / "perfiles.json")
    monkeypatch.setattr(pe, "_texto_editorial", lambda _m: texto)


def test_refresca_y_cachea(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path)
    kws = pe.refrescar_si_corresponde("claro-sports", ttl_horas=24, ejecutor=_ejecutor(["Liga MX", "box"]))
    assert kws == frozenset({"liga mx", "box"})  # normalizado: minúsculas, sin acentos
    assert pe.palabras("claro-sports") == frozenset({"liga mx", "box"})


def test_fresco_no_relanza_haiku(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path)
    pe.refrescar_si_corresponde("unotv", ttl_horas=24, ejecutor=_ejecutor(["mexico"]))

    llamado: list[int] = []
    def boom(_p, _c):
        llamado.append(1)
        return "{}"
    out = pe.refrescar_si_corresponde("unotv", ttl_horas=24, ejecutor=boom)
    assert llamado == []  # cache fresco (mismo hash + dentro de TTL): sin Haiku
    assert out == frozenset({"mexico"})


def test_al_refrescar_solo_en_refresco_real(monkeypatch, tmp_path):
    """`al_refrescar(marca, kws, prompt, salida)` se llama al refrescar (con el Haiku REAL), NO en cache."""
    _preparar(monkeypatch, tmp_path)
    llamadas: list[tuple[str, list[str], str, str]] = []
    cb = lambda m, kws, prompt, salida: llamadas.append((m, list(kws), prompt, salida))  # noqa: E731
    # 1er refresco (cache vacío): Haiku corre -> callback con marca, keywords, prompt y salida reales.
    pe.refrescar_si_corresponde(
        "unotv", ttl_horas=24, ejecutor=_ejecutor(["mexico", "cdmx"]), al_refrescar=cb
    )
    assert len(llamadas) == 1
    m, kws, prompt, salida = llamadas[0]
    assert (m, kws) == ("unotv", ["mexico", "cdmx"])
    assert "unotv" in prompt  # el prompt real menciona la marca
    assert "mexico" in salida  # la salida real es la respuesta de Haiku (keywords)
    # 2º con cache fresco (mismo hash, dentro de TTL): NO corre Haiku -> NO callback.
    pe.refrescar_si_corresponde(
        "unotv", ttl_horas=24, ejecutor=_ejecutor(["otro"]), al_refrescar=cb
    )
    assert len(llamadas) == 1


def test_ttl_caducado_relanza(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path)
    ayer = datetime.now(UTC) - timedelta(hours=48)
    pe.refrescar_si_corresponde("unotv", ttl_horas=24, ahora=ayer, ejecutor=_ejecutor(["viejo"]))
    # Ahora (48h después) con TTL 24h -> caducó -> re-extrae.
    out = pe.refrescar_si_corresponde("unotv", ttl_horas=24, ejecutor=_ejecutor(["nuevo"]))
    assert out == frozenset({"nuevo"})


def test_cambio_editorial_relanza(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path, texto="v1")
    pe.refrescar_si_corresponde("unotv", ttl_horas=24, ejecutor=_ejecutor(["a"]))
    # Cambia la línea editorial -> cambia el hash -> re-extrae aunque esté dentro del TTL.
    monkeypatch.setattr(pe, "_texto_editorial", lambda _m: "v2 totalmente distinta")
    out = pe.refrescar_si_corresponde("unotv", ttl_horas=24, ejecutor=_ejecutor(["b"]))
    assert out == frozenset({"b"})


def test_sin_editorial_no_llama(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path, texto="")
    llamado: list[int] = []
    out = pe.refrescar_si_corresponde("x", ttl_horas=24, ejecutor=lambda _p, _c: llamado.append(1) or "{}")
    assert out == frozenset() and llamado == []


def test_fallo_haiku_conserva_cache_previo(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path, texto="v1")
    pe.refrescar_si_corresponde("unotv", ttl_horas=24, ejecutor=_ejecutor(["bueno"]))
    monkeypatch.setattr(pe, "_texto_editorial", lambda _m: "v2 cambiada")
    def revienta(_p, _c):
        raise RuntimeError("claude caído")
    out = pe.refrescar_si_corresponde("unotv", ttl_horas=24, ejecutor=revienta)
    assert out == frozenset({"bueno"})  # best-effort: conserva el perfil previo


def test_extraer_keywords_tolera_fences_y_normaliza():
    out = pe._extraer_keywords('```json\n{"keywords": ["Liga MX", "Boxeo", "Selección"]}\n```')
    assert out == ["liga mx", "boxeo", "seleccion"]


def test_palabras_sin_cache_es_vacio(monkeypatch, tmp_path):
    monkeypatch.setattr(pe, "_ruta_cache", lambda: tmp_path / "noexiste.json")
    assert pe.palabras("unotv") == frozenset()


def test_construir_prompt_inserta_marca_editorial_y_contrato():
    # Plantilla de la Biblioteca (semilla): se sustituyen marca y línea editorial; ningún
    # marcador `{{...}}` queda crudo y se conserva el contrato JSON {"keywords": [...]}.
    p = pe._construir_prompt("unotv", "Cubrimos política y deportes.")
    assert "unotv" in p
    assert "Cubrimos política y deportes." in p
    assert "{{" not in p
    assert "keywords" in p
