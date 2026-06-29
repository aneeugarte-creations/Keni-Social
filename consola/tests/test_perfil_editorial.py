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
    # Plantilla de la Prompts (inicial): se sustituyen marca y línea editorial; ningún
    # marcador `{{...}}` queda crudo y se conserva el contrato JSON {"keywords": [...]}.
    p = pe._construir_prompt("unotv", "Cubrimos política y deportes.")
    assert "unotv" in p
    assert "Cubrimos política y deportes." in p
    assert "{{" not in p
    assert "keywords" in p


# --------------------------------------------------------------------------- #
# Camino ENCOLADO (job del worker): gate, marcador en vuelo y post-procesado    #
# --------------------------------------------------------------------------- #


def test_necesita_refresco_sin_cache_y_fresco(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path)
    # Sin cache: hace falta refrescar.
    assert pe.necesita_refresco("unotv", ttl_horas=24) is True
    # Tras refrescar (cache fresco, mismo hash, dentro de TTL): ya NO hace falta.
    pe.refrescar_si_corresponde("unotv", ttl_horas=24, ejecutor=_ejecutor(["mexico"]))
    assert pe.necesita_refresco("unotv", ttl_horas=24) is False


def test_necesita_refresco_ttl_caducado_y_editorial_cambiada(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path, texto="v1")
    ayer = datetime.now(UTC) - timedelta(hours=48)
    pe.refrescar_si_corresponde("unotv", ttl_horas=24, ahora=ayer, ejecutor=_ejecutor(["viejo"]))
    # TTL caducado (48h > 24h): hace falta.
    assert pe.necesita_refresco("unotv", ttl_horas=24) is True
    # Editorial distinta (hash cambia): hace falta aunque estuviera dentro del TTL.
    monkeypatch.setattr(pe, "_texto_editorial", lambda _m: "v2 distinta")
    assert pe.necesita_refresco("unotv", ttl_horas=24) is True


def test_necesita_refresco_sin_editorial_es_falso(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path, texto="")
    assert pe.necesita_refresco("x", ttl_horas=24) is False


def test_marcador_en_vuelo_bloquea_y_se_reabre_por_ttl(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path)
    ahora = datetime.now(UTC)
    assert pe.refresco_en_curso("unotv", ahora=ahora, ttl_min=30) is False
    pe.marcar_refresco_encolado("unotv", ahora=ahora)
    # Recién marcado: en vuelo (no re-encolar).
    assert pe.refresco_en_curso("unotv", ahora=ahora, ttl_min=30) is True
    # Marcador más viejo que el TTL: ATASCADO -> se re-abre (no bloquea).
    tarde = ahora + timedelta(minutes=31)
    assert pe.refresco_en_curso("unotv", ahora=tarde, ttl_min=30) is False
    # Limpieza explícita (encolado rechazado): vuelve a estar libre.
    pe.marcar_refresco_encolado("unotv", ahora=tarde)
    pe.limpiar_refresco_encolado("unotv")
    assert pe.refresco_en_curso("unotv", ahora=tarde, ttl_min=30) is False


def test_marcar_en_vuelo_no_pisa_keywords(monkeypatch, tmp_path):
    """Marcar el refresco en curso NO borra el perfil cacheado (las lecturas siguen vigentes)."""
    _preparar(monkeypatch, tmp_path)
    pe.refrescar_si_corresponde("unotv", ttl_horas=24, ejecutor=_ejecutor(["mexico"]))
    pe.marcar_refresco_encolado("unotv")
    assert pe.palabras("unotv") == frozenset({"mexico"})  # marcador convive con keywords


def test_construir_prompt_perfil_vacio_sin_editorial(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path, texto="")
    assert pe.construir_prompt_perfil("x") == ""
    _preparar(monkeypatch, tmp_path, texto="Cubrimos deportes.")
    assert "deportes" in pe.construir_prompt_perfil("unotv")


def test_construir_procesar_perfil_escribe_cache_y_limpia_marcador(monkeypatch, tmp_path):
    """El post-procesado del JOB parsea la salida, ESCRIBE el cache y limpia el marcador en vuelo."""
    _preparar(monkeypatch, tmp_path)
    pe.marcar_refresco_encolado("unotv")  # job en vuelo
    procesar = pe.construir_procesar_perfil("unotv")
    res = procesar(json.dumps({"keywords": ["Liga MX", "Boxeo"]}), None)
    assert res == {"keywords": 2, "marca": "unotv"}
    assert pe.palabras("unotv") == frozenset({"liga mx", "boxeo"})  # normalizado
    # La entrada se reemplaza entera: el marcador en vuelo desaparece (el siguiente barrido lo ve fresco).
    assert pe.refresco_en_curso("unotv", ttl_min=30) is False
    assert pe.necesita_refresco("unotv", ttl_horas=24) is False


def test_jobspec_reconstruye_el_procesar_de_perfil(monkeypatch, tmp_path):
    """El worker reconstruye el post-procesado desde el spec (`construir_perfil`)."""
    from keni_consola.dominio import jobspec

    _preparar(monkeypatch, tmp_path)
    spec = jobspec.construir_perfil(marca="unotv")
    assert spec == {"kind": jobspec.PROC_PERFIL, "marca": "unotv"}
    procesar = jobspec.reconstruir_procesar({"procesar": spec})
    procesar(json.dumps({"keywords": ["mexico"]}), None)
    assert pe.palabras("unotv") == frozenset({"mexico"})


def test_construir_procesar_perfil_sin_keywords_no_toca_cache(monkeypatch, tmp_path):
    """Salida sin keywords usables: NO escribe el cache (el marcador queda -> reintento por TTL)."""
    _preparar(monkeypatch, tmp_path)
    pe.refrescar_si_corresponde("unotv", ttl_horas=24, ahora=datetime.now(UTC) - timedelta(hours=48),
                                ejecutor=_ejecutor(["viejo"]))
    pe.marcar_refresco_encolado("unotv")
    procesar = pe.construir_procesar_perfil("unotv")
    res = procesar("sin json util", None)
    assert res == {"keywords": 0, "marca": "unotv"}
    assert pe.palabras("unotv") == frozenset({"viejo"})  # conserva el perfil previo
    assert pe.refresco_en_curso("unotv", ttl_min=30) is True  # marcador intacto (reintento por TTL)
