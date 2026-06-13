"""Recursos de la maquina (CPU / RAM / disco) del panel de ADMIN.

GET /api/sistema/recursos. Degradado: psutil es opcional; si falta, CPU/RAM van a None pero
el disco SIEMPRE sale (via `shutil`, stdlib) -> nunca un 500 por un opcional ausente.
"""

from __future__ import annotations

import shutil

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import rutas
from ._comun import _es_admin, _logger, _rechazo_no_admin

# Umbrales de USO de disco (%) que consume el doctor (`/api/estado`, chequeo `infra:disco`).
# AVISO replica el umbral historico del banner del panel Sistema (>= 85% el volumen va
# justo); ERROR marca un volumen al borde del lleno. Las sondas de este modulo NO los
# aplican (devuelven el porcentaje crudo y el front/doctor juzgan).
UMBRAL_DISCO_AVISO_PCT = 85.0
UMBRAL_DISCO_ERROR_PCT = 95.0


def _uso_disco(ruta: str, etiqueta: str) -> dict | None:
    """Uso de disco del volumen que contiene `ruta` (None si no se puede medir).

    `shutil.disk_usage` es stdlib (no depende de psutil): siempre disponible. Si la ruta
    no existe (p.ej. no hay volumen `/data` en local), devuelve None para omitir el disco.
    """
    try:
        uso = shutil.disk_usage(ruta)
    except OSError:
        return None
    porcentaje = (uso.used / uso.total * 100) if uso.total else 0.0
    return {
        "etiqueta": etiqueta,
        "ruta": ruta,
        "usado": int(uso.used),
        "total": int(uso.total),
        "porcentaje": round(porcentaje, 1),
    }


def _discos() -> list[dict]:
    """Discos relevantes: el volumen de estado (`/data` hosted) y el root.

    El de estado se mide sobre `rutas.data_dir()` (con `KENI_DATA_DIR` apunta al volumen
    `/data`; en local cae a `~/.config`). Evitamos duplicar si root y estado son el mismo
    volumen (misma ruta resuelta).
    """
    discos: list[dict] = []
    rutas_vistas: set[str] = set()
    raiz_estado = str(rutas.data_dir())
    if (d := _uso_disco(raiz_estado, "Estado")) is not None:
        discos.append(d)
        rutas_vistas.add(d["ruta"])
    # El root solo se anade si NO es ya el mismo punto de montaje que el estado. Comparamos
    # por (total, usado) ademas de por ruta: dos rutas distintas del mismo volumen dan el
    # mismo uso, y no queremos pintar el mismo disco dos veces.
    root = _uso_disco("/", "Sistema")
    if root is not None and not any(
        d["total"] == root["total"] and d["usado"] == root["usado"] for d in discos
    ):
        discos.append(root)
    return discos


async def recursos(request: Request) -> Response:
    """GET /api/sistema/recursos: CPU/RAM/disco de la maquina (admin).

    Degradado: psutil es opcional; si falta, CPU/RAM van a None pero el disco SIEMPRE sale
    (stdlib). Nunca un 500 por un opcional ausente.
    """
    if not _es_admin(request):
        return _rechazo_no_admin()

    cpu: dict = {"porcentaje": None, "cores": None}
    ram: dict = {"usado": None, "total": None, "porcentaje": None}
    psutil_ok = False
    try:
        import psutil

        psutil_ok = True
        # interval=None: lectura NO bloqueante (delta desde la llamada previa del proceso).
        # En el primer muestreo puede dar 0.0; el auto-refresco del front lo corrige enseguida.
        cpu = {
            "porcentaje": round(float(psutil.cpu_percent(interval=None)), 1),
            "cores": psutil.cpu_count(logical=True),
        }
        vm = psutil.virtual_memory()
        ram = {
            "usado": int(vm.used),
            "total": int(vm.total),
            "porcentaje": round(float(vm.percent), 1),
        }
    except Exception:  # noqa: BLE001 -- psutil ausente o sonda fallida: degradar, no 500
        _logger.warning("psutil no disponible o fallo al leer CPU/RAM; se degrada.")

    return JSONResponse(
        {
            "cpu": cpu,
            "ram": ram,
            "discos": _discos(),
            "psutil": psutil_ok,
        }
    )
