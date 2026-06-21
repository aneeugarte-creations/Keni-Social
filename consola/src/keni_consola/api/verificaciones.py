"""API Verificacion: datar un video viral (nuevo vs reciclado) como WORKFLOW PROPIO.

Workflow INDEPENDIENTE de "Generar copy": el usuario pega el enlace de un video y la
consola corre el motor LOCAL `verifica-video/analiza-video.py` (yt-dlp + ffmpeg +
tesseract) en SEGUNDO PLANO, devolviendo la EVIDENCIA para datar el video: fecha de
subida, fechas/anos en pantalla (OCR) y enlaces de BUSQUEDA INVERSA listos para clic.

  - `POST /api/verificar`  (JSON `{enlace, contexto?}`) -> `{generacion}` (estado
    "ejecutando"); el frontend SONDEA `GET /api/generaciones/{id}` y, al completar,
    recoge `resultado = {verificacion: <reporte>}`.

NO da un dictamen automatico: junta evidencia y deja la confirmacion (busqueda
inversa) al humano. Reutiliza la infra de generaciones en background (mismo sondeo
que imagen): `lanzar_job_imagen` es el runner generico de un callable en un hilo.

SEGURIDAD: sin shell (argv como lista); el motor corre con el python de la consola y
solo lee metadatos publicos; los errores salen como JSON en espanol, sin tracebacks.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import generaciones
from .._http_json import leer_json
from ..seguridad import autor_de_peticion

# Wall-timeout del motor (descargar el video + OCR pueden tardar). Generoso pero acotado.
_TIMEOUT_S = 420

# Binarios del motor LOCAL de verificacion. `yt-dlp` es el UNICO IMPRESCINDIBLE: da la fecha
# de SUBIDA y el origen (autor/plataforma), que es el objetivo MINIMO ("identificar dónde se
# subió/de dónde es"). `ffmpeg`/`ffprobe`/`tesseract` enriquecen (fotogramas + OCR de fechas en
# pantalla) pero NO son obligatorios: sin ellos el motor degrada con gracia (menos evidencia).
_BINARIO_IMPRESCINDIBLE = "yt-dlp"
_BINARIOS_OPCIONALES = ("ffmpeg", "ffprobe", "tesseract")


def binarios_disponibles() -> dict[str, bool]:
    """Mapa binario -> ¿esta en el PATH? (health-check; no ejecuta nada, item E).

    Modulo-nivel para que la API lo exponga y los tests lo monkeypatcheen sin tocar el PATH.
    """
    nombres = (_BINARIO_IMPRESCINDIBLE, *_BINARIOS_OPCIONALES)
    return {nombre: shutil.which(nombre) is not None for nombre in nombres}


def _diagnostico_binarios() -> dict[str, object]:
    """Resumen del health-check: ¿se puede verificar? + que binarios faltan (item E).

    `puede_verificar` es True si esta el binario IMPRESCINDIBLE (`yt-dlp`): basta para datar la
    subida y el origen aunque falten los opcionales. `degradado` indica que falta algun opcional
    (no habra OCR/fotogramas, pero el analisis no se rompe).
    """
    estado = binarios_disponibles()
    faltan_opcionales = [b for b in _BINARIOS_OPCIONALES if not estado.get(b)]
    return {
        "binarios": estado,
        "puede_verificar": estado.get(_BINARIO_IMPRESCINDIBLE, False),
        "degradado": bool(faltan_opcionales),
        "faltan_opcionales": faltan_opcionales,
    }


def _ruta_motor() -> Path:
    """Ruta al motor `analiza-video.py` (relocalizado al paquete, `motores/verifica_video/`)."""
    return Path(__file__).resolve().parent.parent / "motores" / "verifica_video" / "analiza-video.py"


def analizar(enlace: str, contexto: str) -> dict[str, object]:
    """Corre el motor local y devuelve `{verificacion: <reporte>}`. Lanza en error.

    Modulo-nivel (no anidada) para que los tests puedan monkeypatchearla y NO ejecutar
    yt-dlp/ffmpeg/tesseract de verdad.
    """
    motor = _ruta_motor()
    if not motor.is_file():
        raise RuntimeError(
            "No se encontró el motor de verificación (verifica-video/analiza-video.py)."
        )
    # Health-check de binarios (item E): sin el IMPRESCINDIBLE no hay forma de datar el video,
    # asi que cortamos con un mensaje claro ANTES de lanzar el subproceso (degradacion con
    # gracia: no revienta con un traceback ni deja un tmp colgado). Los opcionales que falten
    # NO bloquean; el motor entrega menos evidencia pero igual data la subida.
    diag = _diagnostico_binarios()
    if not diag["puede_verificar"]:
        raise RuntimeError(
            f"Falta «{_BINARIO_IMPRESCINDIBLE}», imprescindible para verificar videos. "
            "Instálalo (p. ej. 'pipx install yt-dlp') y vuelve a intentarlo."
        )
    salida = Path(tempfile.mkdtemp(prefix="keni-verificacion-"))
    cmd = [sys.executable, str(motor), enlace, "--salida", str(salida)]
    if contexto:
        cmd += ["--contexto", contexto]
    try:
        proc = subprocess.run(  # noqa: S603 -- argv lista, sin shell; enlace como argumento
            cmd, capture_output=True, text=True, timeout=_TIMEOUT_S, check=False
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"El análisis tardó demasiado (más de {_TIMEOUT_S} s) y se canceló."
        ) from e

    ruta_reporte: str | None = None
    for linea in proc.stdout.splitlines():
        if linea.startswith("REPORTE="):
            ruta_reporte = linea[len("REPORTE="):].strip()
    if not ruta_reporte or not Path(ruta_reporte).is_file():
        detalle = (proc.stderr or "").strip()[-300:]
        faltan = _diagnostico_binarios()["faltan_opcionales"]
        pista = (
            f"Faltan binarios opcionales ({', '.join(faltan)}): el análisis es más pobre."
            if faltan
            else "Revisa que yt-dlp, ffmpeg y tesseract estén instalados."
        )
        raise RuntimeError("El análisis no produjo un reporte. " + (detalle or pista))
    try:
        reporte = json.loads(Path(ruta_reporte).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise RuntimeError("No se pudo leer el reporte de verificación.") from e

    # El texto OCR crudo no aporta a la UI y abulta el registro: lo quitamos.
    if isinstance(reporte.get("ocr"), dict):
        reporte["ocr"].pop("texto", None)
    return {"verificacion": reporte}


async def verificar(request: Request) -> Response:
    """Lanza la verificacion de un video EN SEGUNDO PLANO (JSON `{enlace, contexto?}`)."""
    datos = await leer_json(request)
    enlace = datos.get("enlace")
    if not isinstance(enlace, str) or not enlace.strip():
        return JSONResponse(
            {"error": "Pega el enlace del video (o la ruta a un archivo) que quieres verificar."},
            status_code=400,
        )
    enlace = enlace.strip()
    contexto_crudo = datos.get("contexto")
    contexto = contexto_crudo.strip() if isinstance(contexto_crudo, str) else ""

    def _generar() -> dict[str, object]:
        return analizar(enlace, contexto)

    # Atribucion por usuario (Fase 1): la verificacion la dispara el usuario actual.
    autor = autor_de_peticion(request) or {}
    gen = generaciones.crear(
        {
            "tipo": "verificacion",
            "marca": "",
            "etiqueta": f"Verificación · {enlace[:48]}",
            "autor_id": autor.get("id", ""),
            "autor_nombre": autor.get("usuario", ""),
        }
    )
    try:
        generaciones.lanzar_job_imagen(gen["id"], generar=_generar)
    except Exception:  # noqa: BLE001 -- nunca traceback crudo; reflejamos el error en el registro
        generaciones.actualizar(
            gen["id"],
            {
                "estado": generaciones.ESTADO_ERROR,
                "error": "No se pudo iniciar la verificación.",
                "fecha_fin": generaciones.ahora_iso(),
            },
        )
    return JSONResponse({"generacion": generaciones.obtener(gen["id"]) or gen})


async def estado_verificacion(request: Request) -> Response:
    """`GET /api/verificar/estado` -> health-check de binarios del motor (item E).

    La UI lo consulta para avisar ANTES de pegar un enlace si el motor puede verificar
    (yt-dlp presente) y si va degradado (faltan ffmpeg/tesseract: sin OCR/fotogramas).
    """
    return JSONResponse(_diagnostico_binarios())


RUTAS = [
    Route("/api/verificar", verificar, methods=["POST"]),
    Route("/api/verificar/estado", estado_verificacion, methods=["GET"]),
]
