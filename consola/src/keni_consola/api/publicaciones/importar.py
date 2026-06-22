"""Handler de importación de un calendario al tablero (`/api/publicaciones/importar`).

DOS CAMINOS: tabular SÍNCRONO (.xlsx/.csv) en el back, o IA (PDF/Word/imagen) encolado
al worker. Ver el docstring de `importar` para el detalle.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ._comun import (
    _log,
    _validar_marca,
    autor_de_peticion,
    config,
    generaciones,
    importador_calendario,
    jobspec,
    rutas,
)

# Tope defensivo del archivo de calendario (un calendario real pesa KB, no MB).
_LIMITE_IMPORT = 5 * 1024 * 1024


def _fila_a_dict(fila: importador_calendario.FilaCalendario) -> dict:
    """Serializa una fila parseada para la previsualizacion del cliente."""
    return {
        "titulo": fila.titulo,
        "fecha": fila.fecha,
        "marca": fila.marca_id,
        "redes": fila.redes,
        "prioridad": fila.prioridad,
        "compromiso": fila.compromiso,
        "notas": fila.notas,
    }


def _dir_temporal_import() -> Path:
    """Vuelca el archivo de calendario BAJO el dir de datos COMPARTIDO (back y worker lo ven).

    El camino IA (PDF/Word/imagen) corre en el WORKER (#desacoplo: el back no tiene `claude`).
    back, worker y daemons montan el MISMO volumen `keni-data:/data`, así que un archivo que el
    back escribe bajo `<data>/import-calendario-tmp` lo lee el worker via `--add-dir`. El propio
    `lanzar_job_claude` borra el `dir_temporal` al terminar el job. Mismo helper que `api/insumos`.
    """
    base = rutas.dir_config() / "import-calendario-tmp"
    base.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="cal-", dir=str(base)))


async def importar(request: Request) -> Response:
    """POST /api/publicaciones/importar: sube un calendario al tablero (multipart).

    Campos: `archivo` (obligatorio), `marca` (id canonico opcional, para filas sin marca),
    `previsualizar` ('1' => parsea y devuelve lo que entraria SIN escribir; solo aplica al
    camino TABULAR). Crea contenido `origen='import-calendario'`; las filas obligatorias se
    etiquetan `compromiso`.

    DOS CAMINOS:
      - TABULAR (.xlsx/.csv bien formados): `parsear` es SINCRONO (no usa `claude`) y mantiene
        la previsualización + commit de hoy. Funciona en el back.
      - IA (PDF/Word/imagen/captura/Excel raro): cuando `parsear` no saca filas, el back NO
        ejecuta `claude` (no tiene binario ni token); ENCOLA un job de Haiku al WORKER, que lo
        importa al tablero. Devuelve `{pendiente:true, generacion}` para que el SPA sondee. Los
        items aterrizan como borradores en el tablero (la superficie de revisión).
    """
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001 -- multipart malformado => mensaje claro, sin traza
        return JSONResponse({"error": "Formulario inválido."}, status_code=400)

    archivo = form.get("archivo")
    if not isinstance(archivo, UploadFile):
        return JSONResponse({"error": "Falta el archivo del calendario."}, status_code=400)
    data = await archivo.read()
    if not data:
        return JSONResponse({"error": "El archivo está vacío."}, status_code=400)
    if len(data) > _LIMITE_IMPORT:
        return JSONResponse({"error": "El archivo es demasiado grande."}, status_code=413)

    marca_defecto, err = _validar_marca(form.get("marca"))
    if err:
        return JSONResponse({"error": err}, status_code=400)

    # Camino RÁPIDO y determinista: el parser tabular para .xlsx/.csv bien formados (sin claude).
    nombre = archivo.filename or ""
    try:
        # `parsear` (openpyxl/csv) es trabajo de CPU bloqueante: fuera del event loop.
        filas, errores = await run_in_threadpool(
            importador_calendario.parsear, data, nombre=nombre
        )
    except Exception:  # noqa: BLE001 -- formato no tabular/ilegible: lo encolará al worker abajo
        filas, errores = [], []

    # Si el parser rígido SACÓ filas, es el camino tabular: preview/commit SÍNCRONO como hoy.
    if filas:
        if str(form.get("previsualizar") or "") in ("1", "true", "si", "sí"):
            return JSONResponse({
                "previsualizacion": True,
                "filas": [_fila_a_dict(f) for f in filas],
                "errores": errores,
            })
        resumen = importador_calendario.importar_a_tablero(
            filas, autor=autor_de_peticion(request), marca_defecto=marca_defecto or ""
        )
        return JSONResponse({
            "creados": len(resumen["creados"]),
            "omitidos": resumen["omitidos"],
            "errores": errores,
        })

    # Camino IA (formato no tabular): el back NO ejecuta `claude`. Vuelca el archivo a un
    # temporal del dir COMPARTIDO y ENCOLA un job de Haiku al worker (mismo patrón que
    # `api/insumos.aportar`). No hay previsualización síncrona: los items aterrizan como
    # borradores en el tablero, que es la superficie de revisión.
    return await _importar_con_ia(request, data, nombre=nombre, marca_defecto=marca_defecto or "")


async def _importar_con_ia(
    request: Request, data: bytes, *, nombre: str, marca_defecto: str
) -> Response:
    """Encola la importación AGNÓSTICA de calendario al worker. Devuelve `{pendiente, generacion}`."""
    autor = autor_de_peticion(request)
    dir_temporal = _dir_temporal_import()
    nombre_seguro = Path(nombre or "").name or "calendario"
    ruta = dir_temporal / nombre_seguro
    try:
        await run_in_threadpool(ruta.write_bytes, data)
    except OSError:
        shutil.rmtree(dir_temporal, ignore_errors=True)
        return JSONResponse({"error": "No se pudo preparar el archivo."}, status_code=500)

    prompt = importador_calendario._prompt_extraccion(str(ruta))
    procesar_spec = jobspec.construir_import_calendario(
        marca_defecto=marca_defecto, autor=autor
    )
    spec = jobspec.construir(
        prompt=prompt,
        procesar=procesar_spec,
        dir_temporal=str(dir_temporal),
        # Haiku (config.insumos_modelo()): extracción mecánica de JSON, no necesita modelo grande.
        endurecer={"modelo": config.insumos_modelo()},
    )

    gen = generaciones.crear({
        "tipo": "import-calendario",
        "marca": marca_defecto,
        "etiqueta": f"Importar calendario · {nombre_seguro}",
        "autor_id": (autor or {}).get("id", "") or "",
        "autor_nombre": (autor or {}).get("usuario", "") or "",
    })
    try:
        generaciones.encolar_job_claude(
            gen["id"],
            prompt=prompt,
            cwd=jobspec.cwd_generacion(),
            procesar=jobspec.reconstruir_procesar({"procesar": procesar_spec}),
            dir_temporal=dir_temporal,
            spec=spec,
        )
    except generaciones.ColaLlenaError:
        shutil.rmtree(dir_temporal, ignore_errors=True)
        generaciones.actualizar(gen["id"], {
            "estado": generaciones.ESTADO_ERROR, "motivo": generaciones.MOTIVO_COLA_LLENA,
            "error": "Hay demasiados trabajos en curso; inténtalo en unos segundos.",
            "fecha_fin": generaciones.ahora_iso(),
        })
        return JSONResponse(
            {"pendiente": True, "generacion": generaciones.obtener(gen["id"])},
            status_code=429,
        )
    except Exception:  # noqa: BLE001 -- reflejamos el fallo en la generación, sin traceback al cliente
        _log.exception("no se pudo encolar la importación de calendario %s", gen["id"])
        shutil.rmtree(dir_temporal, ignore_errors=True)
        generaciones.actualizar(gen["id"], {
            "estado": generaciones.ESTADO_ERROR, "error": "No se pudo iniciar la importación.",
            "fecha_fin": generaciones.ahora_iso(),
        })
        return JSONResponse(
            {"pendiente": True, "generacion": generaciones.obtener(gen["id"])},
            status_code=500,
        )

    return JSONResponse({
        "pendiente": True,
        "generacion": generaciones.obtener(gen["id"]) or gen,
    })
