"""Backups locales del panel de ADMIN (estado.json del keni-backup del host, montado :ro).

GET /api/sistema/backups. La sonda `sonda_backups` la comparten el endpoint admin y el
doctor (`/api/estado`, chequeo `infra:backups`).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ._comun import _es_admin, _rechazo_no_admin

# Umbral de atraso del backup: timer diario + margen (mismo criterio que keni-alertas).
_BACKUP_ATRASO_SEG = 26 * 3600.0

# Env con el directorio de backups montado SOLO LECTURA en el contenedor (compose:
# /var/backups/keni-social -> /backups). Vacio/ausente => seccion degradada, nunca 500.
_ENV_BACKUPS_DIR = "KENI_BACKUPS_DIR"


def sonda_backups() -> dict:
    """SONDA del estado de los backups locales del host (observabilidad pura).

    Lee el `estado.json` que escribe `deploy/backup/keni-backup.sh` en cada run (ok/fallo,
    verificacion, bytes, duracion) y sondea el dump mas reciente de `postgres/` para
    calcular la edad real (robusto aunque estado.json falte o sea de un run fallido).
    `atrasado` = ningun dump en las ultimas 26h (timer diario + margen, igual que
    keni-alertas). Degradada sin el mount/env (`configurado: false`), nunca propaga. La
    comparten el endpoint admin (`GET /api/sistema/backups`) y el doctor (`/api/estado`,
    chequeo `infra:backups`).
    """
    raiz = os.environ.get(_ENV_BACKUPS_DIR, "")
    base = {
        "configurado": False,
        "estado": None,
        "dumps": 0,
        "ultimo_dump": None,
        "atrasado": False,
        "error": None,
    }
    if not raiz or not os.path.isdir(raiz):
        return base
    base["configurado"] = True

    import json as _json

    try:
        with open(os.path.join(raiz, "estado.json"), encoding="utf-8") as f:
            base["estado"] = _json.load(f)
    except FileNotFoundError:
        pass  # primer run aun sin estado.json: los dumps de abajo siguen contando
    except Exception as e:  # noqa: BLE001 -- JSON roto/permisos: degradar legible
        base["error"] = f"estado.json ilegible: {e}"

    try:
        dir_pg = os.path.join(raiz, "postgres")
        dumps = [
            e
            for e in os.scandir(dir_pg)
            if e.is_file() and e.name.startswith("keni-") and e.name.endswith(".dump")
        ]
        base["dumps"] = len(dumps)
        if dumps:
            ultimo = max(dumps, key=lambda e: e.stat().st_mtime)
            st = ultimo.stat()
            edad = max(0.0, datetime.now(UTC).timestamp() - st.st_mtime)
            base["ultimo_dump"] = {
                "fichero": ultimo.name,
                "bytes": st.st_size,
                "modificado": datetime.fromtimestamp(st.st_mtime, UTC)
                .replace(tzinfo=None)
                .isoformat(timespec="seconds"),
                "edad_seg": edad,
            }
            base["atrasado"] = edad > _BACKUP_ATRASO_SEG
        else:
            base["atrasado"] = True
    except FileNotFoundError:
        base["atrasado"] = True
    except Exception as e:  # noqa: BLE001 -- sonda defensiva: el panel nunca se cae
        base["error"] = base["error"] or f"no se pudo listar postgres/: {e}"
    return base


async def backups(request: Request) -> Response:
    """GET /api/sistema/backups: estado de los backups locales (solo admin).

    Sirve tal cual la `sonda_backups` compartida (contrato intacto con el frontend).
    """
    if not _es_admin(request):
        return _rechazo_no_admin()
    # `sonda_backups` lee del disco (open/scandir/stat): fuera del event loop.
    return JSONResponse(await run_in_threadpool(sonda_backups))
