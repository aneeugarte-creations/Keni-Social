"""API Estado: autodiagnostico del sistema en JSON.

Envuelve el `doctor` ya existente (`keni_metricas.doctor`) y devuelve sus
resultados como JSON: una lista de chequeos (estado normalizado a ok/aviso/error,
nombre, detalle e icono), un resumen humano y el siguiente paso accionable. NO
reimplementa ninguna comprobacion: solo orquesta, FILTRA al dominio de la consola
y serializa.

Dominio de la consola: la consola lee y publica metricas/contenido; NO transcribe
clips localmente. Por eso se descartan los chequeos de la cadena clip-a-copy
(`whisper-cli`, `ffmpeg`, modelo de whisper): son herramientas locales de la skill
de transcripcion, no de la consola, y verlos en rojo en la consola desorientaba
(el indicador salia ambar/rojo por algo ajeno a su dominio). El `doctor` sigue
informando de todo para la CLI; aqui solo se muestra lo que la consola gobierna.

El doctor solo informa de presencia/ausencia de credenciales (NUNCA imprime el
valor de un secreto), asi que este endpoint tampoco expone nada sensible.

`ejecutar_chequeos` se expone como nombre de modulo para poder inyectarlo/mockearlo
en los tests (set determinista, offline, sin tocar red ni binarios).
"""

from __future__ import annotations

from keni_metricas import doctor
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

# Inyectable: los tests reasignan esto a un stub determinista.
ejecutar_chequeos = doctor.ejecutar_chequeos

# Mapa Estado del doctor -> cadena que consume el SPA.
_ESTADO_A_STR = {
    doctor.Estado.OK: "ok",
    doctor.Estado.AVISO: "aviso",
    doctor.Estado.ERROR: "error",
}

# Chequeos del `doctor` que NO pertenecen al dominio de la consola: son de la
# cadena clip-a-copy (transcripcion local con whisper.cpp). Se filtran por nombre.
_NOMBRES_FUERA_DE_DOMINIO = frozenset(
    {"binario whisper-cli", "binario ffmpeg", "modelo whisper"}
)


def _estado_str(estado: object) -> str:
    """Normaliza un Estado del doctor a "ok"/"aviso"/"error" (cae a "aviso")."""
    return _ESTADO_A_STR.get(estado, "aviso")


def _es_dominio_consola(resultado: object) -> bool:
    """True si el chequeo pertenece al dominio que gobierna la consola.

    Filtra por nombre exacto (`binario whisper-cli`, `binario ffmpeg`,
    `modelo whisper`). Cualquier chequeo desconocido se conserva: preferimos
    mostrar de mas a ocultar un problema real de la consola.
    """
    return str(getattr(resultado, "nombre", "")) not in _NOMBRES_FUERA_DE_DOMINIO


async def estado(request: Request) -> Response:
    try:
        resultados = [r for r in ejecutar_chequeos() if _es_dominio_consola(r)]
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse(
            {"error": "No se pudo ejecutar el autodiagnóstico. Vuelve a intentarlo en un momento."},
            status_code=500,
        )

    chequeos = [
        {
            "estado": _estado_str(r.estado),
            "nombre": str(r.nombre),
            "detalle": str(r.detalle),
            "icono": str(getattr(r.estado, "value", "")),
        }
        for r in resultados
    ]
    return JSONResponse(
        {
            "resultados": chequeos,
            "resumen": doctor.resumen_humano(resultados),
            "siguiente_paso": doctor.cierre_accionable(resultados),
        }
    )


RUTAS = [Route("/api/estado", estado)]
