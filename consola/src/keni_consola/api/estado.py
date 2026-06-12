"""API Estado: autodiagnostico del sistema en JSON (el DOCTOR de la consola).

Dos familias de chequeos en una sola respuesta:

  1. Los del `doctor` de metricas (`keni_metricas.doctor`): entorno, fuente, config,
     credenciales. Se FILTRAN al dominio de la consola (fuera la cadena clip-a-copy:
     `whisper-cli`, `ffmpeg`, modelo de whisper — herramientas locales de transcripcion
     que aqui solo desorientaban) y NO se reimplementan: solo se serializan.
  2. Los OPERATIVOS que antes sintetizaba el front en su banner de alertas (consolidacion):
     disco, backups y S3 (infraestructura) + cola, presupuesto de IA, kill switch y daemons
     (maquina de contenido). NO duplican ninguna sonda: reusan las sondas compartidas de
     `api/sistema.py` (`_discos`, `sonda_backups`, `sonda_s3_salud`, `sonda_daemons`),
     `api/actividad.snapshot_cola` y `presupuesto_ia.estado()`.

CONTRATO de cada chequeo: `{id, estado, nombre, detalle, icono, admin, siguiente_paso}`.
  - `id`: estable ("metricas:<slug>" para los del doctor; "maquina:*" / "infra:*" para los
    operativos). El front puede anclar logica a el sin depender del nombre humano.
  - `estado`: "ok" | "aviso" | "error". `icono` es el emoji equivalente.
  - `detalle`: mensaje humano. `siguiente_paso`: accion concreta cuando NO esta ok (None si ok).
  - `admin`: True para los chequeos de INFRAESTRUCTURA (disco, backups, S3 y los del doctor
    de metricas: su remedio es de operador) y False para los de la MAQUINA de contenido
    (cola, presupuesto, pausa, daemons: le importan a todo el equipo). El front filtra por
    rol con este flag; ningun detalle expone secretos (solo porcentajes/saludes/conteos).

Se mantienen el `resumen` global y el `siguiente_paso` del doctor (calculados sobre TODOS
los chequeos, con las mismas frases de `keni_metricas.doctor`).

Los chequeos operativos son DEFENSIVOS: un fallo de BD/disco degrada ese chequeo a "aviso"
con mensaje legible, nunca tumba el endpoint. `ejecutar_chequeos` se expone como nombre de
modulo para inyectarlo/mockearlo en tests (igual que siempre); las sondas operativas se
parchean en sus modulos (`api.sistema`, `api.actividad`, `presupuesto_ia`).
"""

from __future__ import annotations

from keni_metricas import doctor
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import presupuesto_ia
from . import actividad as api_actividad
from . import sistema as api_sistema

# Inyectable: los tests reasignan esto a un stub determinista.
ejecutar_chequeos = doctor.ejecutar_chequeos

# Mapa Estado del doctor -> cadena que consume el SPA (y su inverso, para reconstruir
# Resultados equivalentes al calcular el resumen global con las frases del doctor).
_ESTADO_A_STR = {
    doctor.Estado.OK: "ok",
    doctor.Estado.AVISO: "aviso",
    doctor.Estado.ERROR: "error",
}
_STR_A_ESTADO = {v: k for k, v in _ESTADO_A_STR.items()}

# Iconos por estado (los chequeos del doctor traen el suyo en el enum; los operativos
# usan estos mismos para que la lista sea homogenea).
_ICONOS = {"ok": "✅", "aviso": "⚠️", "error": "❌"}

# Chequeos del `doctor` que NO pertenecen al dominio de la consola: son de la
# cadena clip-a-copy (transcripcion local con whisper.cpp). Se filtran por nombre.
_NOMBRES_FUERA_DE_DOMINIO = frozenset(
    {"binario whisper-cli", "binario ffmpeg", "modelo whisper"}
)

# Siguiente paso de un chequeo del doctor que no esta ok: su detalle ya trae la accion
# (a menudo el comando exacto); este texto solo remite a el para cumplir el contrato.
_PASO_DOCTOR = "Revisa el detalle del chequeo: suele incluir el comando exacto a ejecutar."


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


def _slug(nombre: str) -> str:
    """Slug estable de un nombre de chequeo del doctor ("binario ffmpeg" -> "binario-ffmpeg")."""
    limpio = "".join(c if c.isalnum() else "-" for c in nombre.lower())
    return "-".join(p for p in limpio.split("-") if p) or "chequeo"


def _chequeo(
    id_: str,
    nombre: str,
    estado: str,
    detalle: str,
    *,
    admin: bool,
    siguiente_paso: str | None = None,
) -> dict:
    """Serializa UN chequeo al contrato del endpoint (paso solo cuando no esta ok)."""
    return {
        "id": id_,
        "estado": estado,
        "nombre": nombre,
        "detalle": detalle,
        "icono": _ICONOS.get(estado, ""),
        "admin": admin,
        "siguiente_paso": siguiente_paso if estado != "ok" else None,
    }


def _chequeo_doctor(r: object) -> dict:
    """Serializa un Resultado del doctor de metricas (id `metricas:<slug>`, admin)."""
    estado = _estado_str(getattr(r, "estado", None))
    nombre = str(getattr(r, "nombre", ""))
    return {
        "id": f"metricas:{_slug(nombre)}",
        "estado": estado,
        "nombre": nombre,
        "detalle": str(getattr(r, "detalle", "")),
        "icono": str(getattr(getattr(r, "estado", None), "value", "")) or _ICONOS.get(estado, ""),
        "admin": True,
        "siguiente_paso": None if estado == "ok" else _PASO_DOCTOR,
    }


# --------------------------------------------------------------------------- #
# Chequeos de la MAQUINA de contenido (admin=False: le importan a todo el equipo)
# --------------------------------------------------------------------------- #


def _chequeo_cola() -> dict:
    """Cola de generacion: aviso si esta LLENA (rechaza trabajo nuevo)."""
    try:
        snap = api_actividad.snapshot_cola()
    except Exception:  # noqa: BLE001 -- sonda defensiva: un blip de BD no tumba el doctor
        return _chequeo(
            "maquina:cola", "Cola de generación", "aviso",
            "No se pudo consultar la cola de generación.",
            admin=False,
            siguiente_paso="Comprueba que la base de datos responde y recarga el diagnóstico.",
        )
    if snap["cola_llena"]:
        return _chequeo(
            "maquina:cola", "Cola de generación", "aviso",
            f"Cola LLENA ({snap['activos']}/{snap['tope']}): se rechaza trabajo nuevo.",
            admin=False,
            siguiente_paso="Espera a que termine lo que está en vuelo o purga/prioriza la cola desde el Monitor.",
        )
    return _chequeo(
        "maquina:cola", "Cola de generación", "ok",
        f"Cola con hueco: {snap['activos']} de {snap['tope']} en uso.",
        admin=False,
    )


def _chequeos_presupuesto() -> list[dict]:
    """Presupuesto diario de tokens (dos escalones) + kill switch de generacion."""
    try:
        est = presupuesto_ia.estado()
    except Exception:  # noqa: BLE001 -- sonda defensiva
        return [
            _chequeo(
                "maquina:presupuesto", "Presupuesto de IA", "aviso",
                "No se pudo consultar el presupuesto de generación.",
                admin=False,
                siguiente_paso="Comprueba que la base de datos responde y recarga el diagnóstico.",
            )
        ]
    salida: list[dict] = []
    nivel = est.get("nivel")
    if nivel == presupuesto_ia.NIVEL_AGOTADO:
        salida.append(_chequeo(
            "maquina:presupuesto", "Presupuesto de IA", "error",
            "Presupuesto de tokens AGOTADO (margen incluido): corte total de la generación.",
            admin=False,
            siguiente_paso="Sube el presupuesto diario en el Monitor o espera al reinicio del día (UTC).",
        ))
    elif nivel == presupuesto_ia.NIVEL_SOLO_MANUAL:
        salida.append(_chequeo(
            "maquina:presupuesto", "Presupuesto de IA", "aviso",
            "Presupuesto de tokens al límite: solo siguen los lanzamientos manuales.",
            admin=False,
            siguiente_paso="Sube el presupuesto diario en el Monitor o deja que el fondo espere al día siguiente.",
        ))
    else:
        presupuesto = int(est.get("presupuesto_tokens_dia") or 0)
        pct = est.get("pct_usado")
        detalle = (
            f"Gasto de hoy: {pct}% del presupuesto diario."
            if presupuesto > 0 and pct is not None
            else "Sin presupuesto diario configurado (sin límite de tokens)."
        )
        salida.append(_chequeo(
            "maquina:presupuesto", "Presupuesto de IA", "ok", detalle, admin=False,
        ))
    if bool(est.get("pausada")):
        salida.append(_chequeo(
            "maquina:pausa", "Generación con IA", "aviso",
            "Generación PAUSADA por el kill switch: no se encola ni se ejecuta nada nuevo.",
            admin=False,
            siguiente_paso="Reactívala en el Monitor (ajuste «Generación con IA: pausada»).",
        ))
    else:
        salida.append(_chequeo(
            "maquina:pausa", "Generación con IA", "ok",
            "Generación activa (kill switch apagado).",
            admin=False,
        ))
    return salida


def _chequeo_daemons() -> dict:
    """Daemons de fondo: error si alguno no late; aviso si su ultimo barrido fallo."""
    try:
        sonda = api_sistema.sonda_daemons()
    except Exception:  # noqa: BLE001 -- sonda defensiva
        sonda = {"daemons": [], "error": "No se pudieron leer los latidos de los daemons."}
    if sonda.get("error"):
        return _chequeo(
            "maquina:daemons", "Daemons de fondo", "aviso",
            str(sonda["error"]),
            admin=False,
            siguiente_paso="Comprueba que la base de datos responde y recarga el diagnóstico.",
        )
    daemons = sonda.get("daemons") or []
    atrasados = [str(d.get("daemon", "?")) for d in daemons if d.get("estado") == "atrasado"]
    con_error = [str(d.get("daemon", "?")) for d in daemons if d.get("estado") == "error"]
    if atrasados:
        return _chequeo(
            "maquina:daemons", "Daemons de fondo", "error",
            f"Sin latido (hilo muerto o proceso caído): {', '.join(atrasados)}.",
            admin=False,
            siguiente_paso="Revisa el servicio `daemons` (docker compose logs daemons) y reinícialo si no late.",
        )
    if con_error:
        return _chequeo(
            "maquina:daemons", "Daemons de fondo", "aviso",
            f"Último barrido en error: {', '.join(con_error)}.",
            admin=False,
            siguiente_paso="Mira el detalle del barrido en el Monitor (sección Daemons).",
        )
    detalle = (
        f"{len(daemons)} daemon(s) latiendo con normalidad."
        if daemons
        else "Sin daemons registrados todavía (ninguno ha latido)."
    )
    return _chequeo("maquina:daemons", "Daemons de fondo", "ok", detalle, admin=False)


def _chequeos_maquina() -> list[dict]:
    """Chequeos de la maquina de contenido (cola, presupuesto, pausa, daemons)."""
    return [_chequeo_cola(), *_chequeos_presupuesto(), _chequeo_daemons()]


# --------------------------------------------------------------------------- #
# Chequeos de INFRAESTRUCTURA (admin=True: su remedio es de operador)          #
# --------------------------------------------------------------------------- #


def _chequeo_disco() -> dict:
    """Uso de disco de los volumenes relevantes (umbral compartido con el panel Sistema)."""
    try:
        discos = api_sistema._discos()
    except Exception:  # noqa: BLE001 -- sonda defensiva
        return _chequeo(
            "infra:disco", "Espacio en disco", "aviso",
            "No se pudo medir el uso de disco.",
            admin=True,
            siguiente_paso="Revisa el panel Sistema (recursos) y el estado de la máquina.",
        )
    llenos = [d for d in discos if d["porcentaje"] >= api_sistema.UMBRAL_DISCO_AVISO_PCT]
    criticos = [d for d in discos if d["porcentaje"] >= api_sistema.UMBRAL_DISCO_ERROR_PCT]
    if llenos:
        detalle = "; ".join(
            f"disco «{d['etiqueta']}» al {d['porcentaje']:.0f}%" for d in llenos
        )
        return _chequeo(
            "infra:disco", "Espacio en disco",
            "error" if criticos else "aviso",
            detalle[:1].upper() + detalle[1:] + ".",
            admin=True,
            siguiente_paso="Libera espacio en ese volumen (media vieja, backups, logs) o amplíalo.",
        )
    resumen = ", ".join(f"{d['etiqueta']} {d['porcentaje']:.0f}%" for d in discos)
    return _chequeo(
        "infra:disco", "Espacio en disco", "ok",
        f"Uso dentro del umbral ({resumen})." if resumen else "Sin volúmenes que medir.",
        admin=True,
    )


def _chequeo_backups() -> dict:
    """Backups locales del host: error si el ultimo fallo; aviso si >26h sin dump."""
    try:
        sonda = api_sistema.sonda_backups()
    except Exception:  # noqa: BLE001 -- sonda defensiva
        sonda = {"configurado": False, "estado": None, "atrasado": False}
    if not sonda.get("configurado"):
        return _chequeo(
            "infra:backups", "Backups locales", "ok",
            "Sin backups locales configurados en esta máquina (normal fuera de hosted).",
            admin=True,
        )
    paso = "Revisa el timer keni-backup del host (journalctl) y su estado.json, y relanza el backup."
    est = sonda.get("estado")
    if isinstance(est, dict) and not est.get("ok", True):
        return _chequeo(
            "infra:backups", "Backups locales", "error",
            f"El último backup FALLÓ en «{est.get('paso') or '?'}».",
            admin=True,
            siguiente_paso=paso,
        )
    if sonda.get("atrasado"):
        return _chequeo(
            "infra:backups", "Backups locales", "aviso",
            "Backup atrasado: más de 26 h sin un dump nuevo.",
            admin=True,
            siguiente_paso=paso,
        )
    return _chequeo(
        "infra:backups", "Backups locales", "ok",
        "Backups al día (hay dump de las últimas 26 h).",
        admin=True,
    )


def _chequeo_s3() -> dict:
    """Salud del object storage (S3/Garage): solo head_bucket, sin medir uso."""
    try:
        sonda = api_sistema.sonda_s3_salud()
    except Exception:  # noqa: BLE001 -- sonda defensiva
        sonda = {"configurado": True, "salud": "err", "error": None}
    if not sonda.get("configurado"):
        return _chequeo(
            "infra:s3", "Almacenamiento S3", "ok",
            "Sin object storage cableado: la media vive en disco local.",
            admin=True,
        )
    if sonda.get("salud") != "ok":
        return _chequeo(
            "infra:s3", "Almacenamiento S3", "error",
            sonda.get("error") or "El almacenamiento S3 no responde (error de salud).",
            admin=True,
            siguiente_paso="Prueba la conexión en Sistema → Almacenamiento y revisa endpoint/credenciales.",
        )
    return _chequeo(
        "infra:s3", "Almacenamiento S3", "ok",
        "El object storage (S3/Garage) responde.",
        admin=True,
    )


def _chequeos_infra() -> list[dict]:
    """Chequeos de infraestructura (disco, backups, S3)."""
    return [_chequeo_disco(), _chequeo_backups(), _chequeo_s3()]


# --------------------------------------------------------------------------- #
# Endpoint                                                                     #
# --------------------------------------------------------------------------- #


def _como_resultados(chequeos: list[dict]) -> list[doctor.Resultado]:
    """Resultados equivalentes del doctor para calcular resumen/cierre con sus frases."""
    return [
        doctor.Resultado(
            c["nombre"],
            _STR_A_ESTADO.get(c["estado"], doctor.Estado.AVISO),
            c["detalle"],
        )
        for c in chequeos
    ]


async def estado(request: Request) -> Response:
    try:
        resultados_doctor = [r for r in ejecutar_chequeos() if _es_dominio_consola(r)]
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse(
            {"error": "No se pudo ejecutar el autodiagnóstico. Vuelve a intentarlo en un momento."},
            status_code=500,
        )

    chequeos = [_chequeo_doctor(r) for r in resultados_doctor]
    chequeos += _chequeos_maquina()
    chequeos += _chequeos_infra()
    equivalentes = _como_resultados(chequeos)
    return JSONResponse(
        {
            "resultados": chequeos,
            "resumen": doctor.resumen_humano(equivalentes),
            "siguiente_paso": doctor.cierre_accionable(equivalentes),
        }
    )


RUTAS = [Route("/api/estado", estado)]
