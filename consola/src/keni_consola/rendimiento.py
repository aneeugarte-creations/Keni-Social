"""Agregador EN MEMORIA de latencias por ruta (observabilidad del panel Sistema).

QUÉ RESUELVE (audit 2026-06): el rendimiento real de la API solo se veía buceando en el
log de peticiones (una línea por request). Esto agrega EN CALIENTE lo que ya mide el
middleware `RegistroPeticiones` —sin trabajo extra por petición más allá de un append a
un deque— y lo expone en `/api/sistema/rendimiento`: por ruta normalizada, peticiones,
errores 5xx y percentiles de latencia al primer byte (p50/p95/max) sobre una ventana
deslizante de las últimas `_MAX_MUESTRAS` peticiones.

DISEÑO:
  - LATENCIA = tiempo hasta `http.response.start` (primer byte), NO la duración total:
    una conexión SSE abierta horas no debe contaminar los percentiles.
  - Rutas NORMALIZADAS (`/api/contenido/abc123` -> `/api/contenido/{id}`) para acotar la
    cardinalidad; tope duro de `_MAX_RUTAS` rutas (al llegar, las nuevas van a "(otras)").
  - Por proceso y en memoria: se reinicia con el deploy (suficiente para operar; la
    persistencia histórica no es el objetivo). Thread-safe con un lock simple.
  - Registrar JAMÁS lanza: cualquier fallo se traga (la observabilidad no rompe el request).
"""

from __future__ import annotations

import re
import threading
from collections import deque
from typing import Any

from .tiempo import ahora_iso

# Ventana de muestras por ruta (deslizante) y tope de rutas distintas.
_MAX_MUESTRAS = 256
_MAX_RUTAS = 200
_RUTA_DESBORDE = "(otras)"

# Un segmento es un ID si: hex largo (>=8), numérico, o UUID con guiones. Cubre los ids
# reales del sistema (uuid4().hex[:12], snowflakes numéricos) sin tocar segmentos de verbo.
_RE_ID = re.compile(r"^(?:[0-9a-f]{8,}|\d+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$", re.IGNORECASE)


class _Ruta:
    __slots__ = ("muestras", "n", "err_5xx", "ultimo_ms")

    def __init__(self) -> None:
        self.muestras: deque[float] = deque(maxlen=_MAX_MUESTRAS)
        self.n = 0
        self.err_5xx = 0
        self.ultimo_ms = 0.0


_lock = threading.Lock()
_rutas: dict[str, _Ruta] = {}
_desde: str = ahora_iso()


def normalizar_ruta(path: str) -> str:
    """Colapsa los segmentos-ID de una ruta a `{id}` (acota la cardinalidad)."""
    partes = path.split("/")
    return "/".join("{id}" if _RE_ID.match(p) else p for p in partes)


def registrar(metodo: str, path: str, estado: int, ttfb_ms: float) -> None:
    """Registra una petición servida. BEST-EFFORT: nunca lanza."""
    try:
        clave = f"{metodo} {normalizar_ruta(path)}"
        with _lock:
            r = _rutas.get(clave)
            if r is None:
                if len(_rutas) >= _MAX_RUTAS:
                    clave = _RUTA_DESBORDE
                    r = _rutas.setdefault(clave, _Ruta())
                else:
                    r = _rutas[clave] = _Ruta()
            r.n += 1
            r.ultimo_ms = ttfb_ms
            r.muestras.append(ttfb_ms)
            if estado >= 500:
                r.err_5xx += 1
    except Exception:  # noqa: BLE001 -- la observabilidad no rompe el request
        pass


def _percentil(ordenadas: list[float], q: float) -> float:
    if not ordenadas:
        return 0.0
    i = min(len(ordenadas) - 1, max(0, round(q * (len(ordenadas) - 1))))
    return ordenadas[i]


def resumen() -> dict[str, Any]:
    """Snapshot agregado para el panel: una entrada por ruta + el instante de arranque."""
    with _lock:
        copia = [(clave, list(r.muestras), r.n, r.err_5xx, r.ultimo_ms) for clave, r in _rutas.items()]
    filas = []
    for clave, muestras, n, err_5xx, ultimo_ms in copia:
        orden = sorted(muestras)
        filas.append(
            {
                "ruta": clave,
                "n": n,
                "err_5xx": err_5xx,
                "p50_ms": round(_percentil(orden, 0.50), 1),
                "p95_ms": round(_percentil(orden, 0.95), 1),
                "max_ms": round(orden[-1], 1) if orden else 0.0,
                "ultimo_ms": round(ultimo_ms, 1),
            }
        )
    filas.sort(key=lambda f: -f["n"])
    return {"desde": _desde, "rutas": filas}


def reiniciar() -> None:
    """Vacía el agregador (tests / acción explícita)."""
    global _desde
    with _lock:
        _rutas.clear()
        _desde = ahora_iso()
