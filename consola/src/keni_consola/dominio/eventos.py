"""Eventos internos del tablero + reparto a webhooks SALIENTES.

╔══════════════════════════════════════════════════════════════════════════╗
║  SEGURIDAD — ESTO PUEDE ENVIAR A LA RED. LEER ANTES DE TOCAR.             ║
║                                                                            ║
║  SAFE BY DEFAULT: si no hay NINGUN webhook activo, `emitir` no hace una    ║
║  sola peticion de red. El reparto ocurre SOLO hacia las URLs que un        ║
║  admin dio de alta (allowlist viva en la tabla `webhooks`). Misma          ║
║  disciplina que `keni_metricas.notificaciones` y `pieza/meta.py`:    ║
║  nada sale solo a destinos no configurados.                                ║
╚══════════════════════════════════════════════════════════════════════════╝

El tablero (`api/publicaciones`) llama a `emitir(...)` cuando pasa algo notificable (p. ej.
una pieza se aprueba). `emitir`:

  1. Registra el evento en la bitacora (`repos.registrar_evento_interno`). Se puede pasar una
     `clave_idempotencia` de modo que el mismo evento NO se re-emita: si la clave ya existe,
     se corta.
  2. Busca los webhooks ACTIVOS suscritos a ese tipo (`repos.listar_webhooks_para`) y les
     hace POST del payload, firmado con HMAC-SHA256 si el webhook tiene `secreto`.

El POST es best-effort: un webhook caido NO rompe la transicion del tablero ni el barrido
(se loguea y se estampa el `ultimo_estado` del webhook). El reparto corre en un HILO aparte
para no bloquear la respuesta HTTP del tablero.

TIPOS DE EVENTO (estables; el frontend y los webhooks se suscriben por nombre):
  - `pieza.aprobada`    la cadena de una pieza junta sus 2 OK (gate humano superado).
  - `pieza.publicada`   una fila por plataforma pasa a `publicado`.
  - `contenido.vencido` un contenido pasa su `fecha_entrega` sin estar cerrado.
  - `pieza.bajo_rendimiento`    una pieza publicada cae por debajo del umbral de engagement.
  - `revision.estancada`        N piezas de una marca llevan >X h en la cola de revisión.
  - `cuenta.credencial_expira`  la credencial de una cuenta de Claude caduca (o ya caducó).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
from typing import Any

from .. import repos
from ..tiempo import ahora_iso

log = logging.getLogger("keni_consola.eventos")

# Tipos de evento canonicos. La API de webhooks valida la suscripcion contra esta tupla;
# el frontend pinta las casillas a partir de ella (`/api/webhooks/catalogo`).
TIPOS_EVENTO: tuple[str, ...] = (
    "pieza.aprobada",
    "pieza.publicada",
    "contenido.vencido",
    # Fase 3 auto-operativa: alertas proactivas del barrido `alertas_rendimiento`.
    "pieza.bajo_rendimiento",
    # Cola de revisión ESTANCADA: N piezas de una marca llevan >X h en `en_revision` sin
    # decisión. AGREGADO por marca (un aviso al día); lo emite el mismo barrido de alertas.
    "revision.estancada",
    # CREDENCIAL de una cuenta de Claude a punto de caducar (o ya caducada). Sin credencial viva
    # NADA se genera, y una sin `refreshToken` no se renueva sola: exige `claude auth login`.
    # Lo emite el muestreo de cuentas (`cuenta_uso_daemon`), un aviso por estado y día.
    "cuenta.credencial_expira",
)

# Formatos de payload del POST saliente. `generico` = el evento crudo (`{tipo, datos, ...}`).
# `slack` = `{"text": <resumen humano>}` (un Incoming Webhook de Slack lo pinta directo).
FORMATOS_WEBHOOK: tuple[str, ...] = ("generico", "slack")

# Cabecera de la firma HMAC (mismo espiritu que `X-Signature` de Mixpost). El receptor
# recomputa HMAC-SHA256(secreto, cuerpo_crudo) y compara en tiempo constante.
CABECERA_FIRMA = "X-Keni-Signature"

# Timeout corto del POST: un webhook lento no debe atascar el hilo de reparto.
_TIMEOUT_POST = 10.0


def _resumen_humano(tipo: str, datos: dict[str, Any]) -> str:
    """Frase corta en espanol para el formato `slack` (y como `resumen` del payload)."""
    titulo = datos.get("titulo") or datos.get("contenido_titulo") or "(sin titulo)"
    marca = datos.get("marca_nombre") or datos.get("marca") or ""
    cola = f" · {marca}" if marca else ""
    if tipo == "pieza.aprobada":
        red = datos.get("red_nombre") or datos.get("red") or "una red"
        return f"✅ Pieza aprobada para {red}: «{titulo}»{cola}"
    if tipo == "pieza.publicada":
        red = datos.get("red_nombre") or datos.get("red") or "una red"
        return f"📣 Pieza publicada en {red}: «{titulo}»{cola}"
    if tipo == "contenido.vencido":
        fecha = datos.get("fecha_entrega") or ""
        venc = f" (entrega {fecha})" if fecha else ""
        return f"⏰ Contenido vencido: «{titulo}»{venc}{cola}"
    if tipo == "pieza.bajo_rendimiento":
        eng = datos.get("engagement_pct")
        cifra = f" ({eng:.1f}% engagement)" if isinstance(eng, (int, float)) else ""
        red = datos.get("red_nombre") or datos.get("red") or ""
        en_red = f" en {red}" if red else ""
        return f"📉 Bajo rendimiento{en_red}: «{titulo}»{cifra}{cola}"
    if tipo == "revision.estancada":
        n = datos.get("n")
        horas = datos.get("horas")
        cuantas = f"{n} pieza(s)" if isinstance(n, int) else "Hay piezas que"
        umbral = f" más de {horas} h" if isinstance(horas, (int, float)) else " demasiado"
        return f"⏳ {cuantas} llevan{umbral} esperando revisión{cola}"
    if tipo == "cuenta.credencial_expira":
        quien = str(datos.get("etiqueta") or "").strip()
        cual = f"cuenta {str(datos.get('cuenta') or '').upper()}".strip()
        de_quien = f"{cual} ({quien})" if quien else cual
        if datos.get("caducada"):
            return (
                f"🔑 La credencial de la {de_quien} CADUCÓ: no se genera nada con ella "
                f"hasta volver a autenticarla"
            )
        horas = datos.get("horas_restantes")
        plazo = f" en {horas:.0f} h" if isinstance(horas, (int, float)) else " pronto"
        return f"🔑 La credencial de la {de_quien} caduca{plazo}: vuelve a autenticarla"
    return f"{tipo}: «{titulo}»{cola}"


def construir_payload(tipo: str, datos: dict[str, Any]) -> dict[str, Any]:
    """Payload `generico` del evento (PURO, sin red). El `slack` se deriva de aqui al enviar."""

    return {
        "evento": tipo,
        "emitido_en": ahora_iso(),
        "resumen": _resumen_humano(tipo, datos),
        "datos": datos,
    }


def _cuerpo_para(formato: str, payload: dict[str, Any]) -> bytes:
    """Serializa el cuerpo del POST segun el formato del webhook."""
    if formato == "slack":
        cuerpo = {"text": payload.get("resumen", "")}
    else:
        cuerpo = payload
    return json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")


def _firmar(secreto: str, cuerpo: bytes) -> str:
    """HMAC-SHA256 hex del cuerpo crudo con el secreto del webhook."""
    return hmac.new(secreto.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()


def _enviar_a_webhook(webhook: dict[str, Any], payload: dict[str, Any]) -> tuple[bool, str]:
    """POST a UN webhook. Devuelve `(ok, estado)`. NUNCA lanza (best-effort).

    Importacion diferida de httpx (dependencia transitiva); los tests parchean
    `_enviar_a_webhook` o no dan de alta webhooks, asi que nunca llegan aqui.
    """
    url = (webhook.get("url") or "").strip()
    if not url:
        return False, "sin url"
    cuerpo = _cuerpo_para(webhook.get("formato") or "generico", payload)
    cabeceras = {"Content-Type": "application/json"}
    secreto = webhook.get("secreto") or ""
    if secreto:
        cabeceras[CABECERA_FIRMA] = _firmar(secreto, cuerpo)
    try:
        import httpx
    except ImportError:  # pragma: no cover -- httpx es dependencia transitiva
        return False, "httpx no disponible"
    try:
        resp = httpx.post(url, content=cuerpo, headers=cabeceras, timeout=_TIMEOUT_POST)
        ok = 200 <= resp.status_code < 300
        return ok, f"HTTP {resp.status_code}"
    except httpx.TimeoutException:
        return False, "timeout"
    except httpx.HTTPError as e:
        return False, f"error de red: {type(e).__name__}"


def probar_webhook(webhook: dict[str, Any]) -> tuple[bool, str]:
    """Envia un evento `pieza.aprobada` de PRUEBA a UN webhook (conectividad/firma).

    `webhook` necesita al menos `url`/`formato`/`secreto`. Devuelve `(ok, estado)`. NO toca
    la bitacora ni el tablero: es una prueba a demanda desde la pagina de webhooks.
    """
    payload = construir_payload(
        "pieza.aprobada",
        {"titulo": "Prueba de webhook", "marca_nombre": "", "red_nombre": "—"},
    )
    return _enviar_a_webhook(webhook, payload)


def _repartir(tipo: str, payload: dict[str, Any]) -> None:
    """Reparte el payload a todos los webhooks suscritos a `tipo` (best-effort, secuencial).

    SAFE BY DEFAULT: sin webhooks suscritos, no toca la red. Estampa `ultimo_estado`/
    `ultimo_en` de cada webhook para que la UI muestre si la ultima entrega fue OK.
    """

    try:
        webhooks = repos.listar_webhooks_para(tipo)
    except Exception:  # noqa: BLE001 -- un fallo de lectura no debe romper el reparto
        log.exception("No se pudieron listar los webhooks para %r.", tipo)
        return
    for wh in webhooks:
        ok, estado = _enviar_a_webhook(wh, payload)
        if not ok:
            log.warning("Webhook %r (%s): entrega fallida: %s", wh.get("id"), tipo, estado)
        try:
            repos.actualizar_webhook(
                wh["id"],
                {
                    "ultimo_estado": ("ok" if ok else "error") + f": {estado}",
                    "ultimo_en": ahora_iso(),
                },
            )
        except Exception:  # noqa: BLE001 -- estampar el estado es accesorio
            log.debug("No se pudo estampar el estado del webhook %r.", wh.get("id"))


def emitir(
    tipo: str,
    datos: dict[str, Any],
    *,
    publicacion_id: str = "",
    pieza_id: str = "",
    clave_idempotencia: str = "",
    en_hilo: bool = True,
) -> bool:
    """Emite un evento interno: lo bitacora y (si procede) lo reparte a los webhooks.

    Devuelve True si el evento se REGISTRO (y por tanto se reparte). False si una
    `clave_idempotencia` ya existia (vencimiento ya emitido): en ese caso NO se reparte,
    evitando spam en cada barrido.

    `en_hilo` (def): el reparto a la red corre en un hilo demonio para no bloquear la
    respuesta HTTP del tablero. Los tests lo ponen a False para un reparto sincrono (o,
    mejor, parchean `_repartir`/`_enviar_a_webhook` para no tocar la red).
    """
    if tipo not in TIPOS_EVENTO:
        log.debug("Evento %r desconocido; se ignora.", tipo)
        return False
    payload = construir_payload(tipo, datos)
    nuevo = repos.registrar_evento_interno(
        tipo=tipo,
        publicacion_id=publicacion_id,
        pieza_id=pieza_id,
        clave_idempotencia=clave_idempotencia,
        payload=payload,
    )
    if not nuevo:
        # Ya emitido antes (idempotencia): no se reparte de nuevo.
        return False
    # Notificaciones IN-APP (el "cajon"): cuando una pieza se PUBLICA, avisa a sus interesados.
    # Best-effort y local (solo BD, sin red); un fallo aqui no frena el evento ni los webhooks.
    if tipo == "pieza.publicada":
        try:
            from . import notificaciones as _notif

            _notif.tras_publicacion(
                publicacion_id=datos.get("publicacion_id", "") or publicacion_id,
                pieza_id=datos.get("pieza_id", "") or pieza_id,
                marca_id=datos.get("marca", "") or "",
                titulo=datos.get("titulo", "") or "",
                red_nombre=datos.get("red_nombre", "") or "",
            )
        except Exception:  # noqa: BLE001 -- notificar nunca rompe la emision del evento
            log.exception("Fallo creando notificaciones in-app para %s.", publicacion_id)
    if en_hilo:
        hilo = threading.Thread(
            target=_repartir, args=(tipo, payload), name=f"webhook-{tipo}", daemon=True
        )
        hilo.start()
    else:
        _repartir(tipo, payload)
    return True
