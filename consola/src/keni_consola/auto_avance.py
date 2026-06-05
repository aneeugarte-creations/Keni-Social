"""Auto-avance "dale el OK" (Flujo D): lleva SOLO a `en_revision` las piezas ya listas.

El equipo no debería tener que pulsar "pedir OK del equipo": una pieza entra sola en el estado
de revisión (que abre los OK del equipo) en cuanto está LISTA. "Lista" = tiene todo lo que la
hace publicable:

  1. copy out (`contenido`) — el texto que acompaña a la publicación.
  2. copy in — el texto dentro de la imagen, SALVO que la pieza esté marcada exenta
     (`copy_in_exento`: imágenes dramáticas/autoexplicativas a las que el copy-in solo estorba).
  3. imagen con FORMATO correcto — hay imagen y su aspecto encaja en un lienzo de la red
     (`dominio.formato_imagen` sobre la matriz `formatos_red`).
  4. QA pasado — el QA editorial por pieza dio 🟢 "listo" o 🟡 "revisar" (🔴 "no_publicar" y
     "sin veredicto" NO avanzan: 🔴 hay que corregir, sin veredicto se lanza la QA y se espera).

Así la "aprobación de IA" es la PUERTA de entrada al estado de OK (solo entra lo que el QA no
bloquea), y los dos OK humanos (Edición + Coordinación) son la cadena que la deja lista para
publicar. Avanzar NO salta el gate humano: solo lo ABRE.

Para que el veredicto exista, este barrido LANZA la QA editorial por pieza de las que están
listas en lo demás pero aún no tienen veredicto (acotado por `KENI_AUTO_AVANCE_MAX` por barrido,
porque cada una es un `claude -p`). `qa_auto_hash` guarda el hash del copy con QA ya lanzada para
no relanzarla en cada barrido (se relanza solo si el copy cambió).

Demonio GATEADO EN VIVO por `KENI_AUTO_AVANCE` (def OFF). Sin el flag, mandar a revisión sigue
siendo manual; el código queda inerte. No crea esquema nuevo salvo las dos columnas del avance.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from io import BytesIO
from typing import Any

from . import config, daemon_util, media, repos
from .api.colaboracion import montar_cadena_aprobacion
from .biblioteca import cuerpo_efectivo, editoriales_de_marca
from .dominio import colaboracion, formato_imagen
from .dominio import generar as gen_dom
from .dominio import jobspec
from .dominio import qa_editorial as dom_qa
from .estados import ESTADO_EN_REVISION

_log = logging.getLogger("keni_consola.auto_avance")

# Prompt de QA editorial en la Biblioteca (mismo que usa `api/qa_editorial`).
PROMPT_QA_ID = "prompt/qa-editorial"

# Veredictos de QA que DEJAN avanzar (la "aprobación de IA"). 🔴 "no_publicar" no avanza.
_QA_AVANZA = frozenset({"listo", "revisar"})


def _dimensiones(imagen_nombre: str) -> tuple[int, int] | None:
    """`(ancho, alto)` de la imagen del almacén; None si no se puede leer/abrir.

    Best-effort: cualquier fallo (objeto ausente, bytes corruptos, Pillow no la entiende) se
    trata como "no verificable" -> None, y la pieza no avanza por formato (conservador).
    """
    datos = media.leer_media(imagen_nombre)
    if not datos:
        return None
    try:
        from PIL import Image  # import perezoso: solo cuando hay que medir una imagen

        with Image.open(BytesIO(datos)) as img:
            return int(img.width), int(img.height)
    except Exception:  # noqa: BLE001 -- imagen ilegible: no verificable, no avanza
        return None


def _copy_listo(pub: dict[str, Any]) -> bool:
    """Copy out presente (no falta y no vacío)."""
    return not pub.get("falta_copy", True) and bool((pub.get("contenido") or "").strip())


def _copy_in_listo(pub: dict[str, Any]) -> bool:
    """Copy in presente, o la pieza está EXENTA (imagen autoexplicativa)."""
    return bool((pub.get("copy_in") or "").strip()) or bool(pub.get("copy_in_exento", False))


def _imagen_lista(pub: dict[str, Any]) -> bool:
    """Hay imagen y su formato encaja con el de la red (lee dimensiones con Pillow)."""
    if pub.get("falta_imagen", True):
        return False
    imagen = (pub.get("imagen") or "").strip()
    if not imagen:
        return False
    dims = _dimensiones(imagen)
    if dims is None:
        return False
    return formato_imagen.formato_correcto(pub.get("red") or "", dims[0], dims[1])


def base_lista(pub: dict[str, Any]) -> bool:
    """Todo lo NO-QA: copy out + copy in (o exención) + imagen con formato correcto."""
    return _copy_listo(pub) and _copy_in_listo(pub) and _imagen_lista(pub)


def _lanzar_qa(pub: dict[str, Any]) -> bool:
    """Lanza la QA editorial por pieza (claude -p) y sella `qa_auto_hash`. True si la lanzó.

    Mirror sin-HTTP de `api/qa_editorial.revisar`: compone el prompt (criterios de QA +
    editorial de marca + el copy) y encola el trabajo atado a la pieza (`plataforma_id`/
    `contenido_id` + `copy_hash`) para que el veredicto quede ligado y se invalide si el copy
    cambia. Best-effort: si falta el prompt, no hace nada.
    """
    cuerpo = cuerpo_efectivo(PROMPT_QA_ID)
    if not cuerpo:
        return False
    marca = pub.get("marca") or ""
    texto = (pub.get("contenido") or "").strip()
    plataforma_id = pub["id"]
    contenido_id = pub.get("contenido_id") or ""
    copy_hash = dom_qa.hash_copy(texto)
    titulo = f"QA editorial (auto) · {marca}"
    prompt = gen_dom.componer(
        cuerpo, editoriales_de_marca(marca), f"Red: {pub.get('red') or ''}\n\n{texto}"
    )
    gen_dom.lanzar(
        tipo="qa-editorial",
        titulo=titulo,
        marca=marca,
        prompt=prompt,
        procesar=dom_qa.construir_procesar_qa(
            marca, titulo, None,
            plataforma_id=plataforma_id, contenido_id=contenido_id, copy_hash=copy_hash,
        ),
        procesar_spec=jobspec.construir_qa(
            marca=marca, titulo=titulo, autor=None,
            plataforma_id=plataforma_id, contenido_id=contenido_id, copy_hash=copy_hash,
        ),
        autor=None,
        # QA (auto) = VERIFICACIÓN con SALIDA ESTRUCTURADA (informe parseado; el usuario no ve la
        # salida cruda). Verificar un dato puede requerir LEER la fuente: NO se le veta la web.
        # Queda la veta global `Bash Write Edit`.
    )
    # Sella el hash del copy con QA lanzada: no se relanza en el próximo barrido salvo que el
    # copy cambie (entonces `hash_copy` difiere y vuelve a tocar QA). `qa_auto_hash` es un campo
    # interno de la fila por plataforma (no del dict público), así que se escribe directo.
    repos.actualizar_contenido_plataforma(plataforma_id, {"qa_auto_hash": copy_hash})
    return True


def _avanzar(pub: dict[str, Any], verdicto: str) -> None:
    """Lleva la pieza a `en_revision`: monta los dos OK y guarda el veredicto de IA.

    Mismo efecto que `enviar_a_revision` (montar cadena + estado en_revision + sello), pero
    disparado por el sistema. Guarda el `veredicto` en la pieza para que el feed pinte el
    semáforo de IA. La cadena son los dos OK (Edición + Coordinación); el gate humano queda
    ABIERTO, no saltado.
    """
    plataforma_id = pub["id"]
    plat = repos.obtener_contenido_plataforma(plataforma_id)
    montar_cadena_aprobacion(
        plataforma_id, plat or {}, colaboracion.cadena_simple(), con_cargos=False
    )
    repos.actualizar_publicacion(
        plataforma_id,
        {
            "estado": ESTADO_EN_REVISION,
            "enviado_a_revision_en": datetime.now().isoformat(timespec="seconds"),
            "veredicto": verdicto,
            "revisor_id": "",
            "revisor_nombre": "",
            "revisado_en": "",
        },
    )


def ejecutar_barrido() -> dict[str, int]:
    """Un barrido: avanza las piezas listas y lanza la QA de las que aún no la tienen.

    Devuelve `{avanzadas, qa_lanzadas, bloqueadas}` para el log. `bloqueadas` cuenta las
    base-listas con veredicto 🔴 (no avanzan: hay que corregir el copy).
    """
    avanzadas = qa_lanzadas = bloqueadas = 0
    cap = config.auto_avance_max()
    for pub in repos.listar_publicaciones(estado="borrador"):
        # Exclusión por marca: si el auto-avance de esta marca se apagó a mano, no se toca su
        # pieza (ni avanza ni se le lanza QA). Sin override, sigue al daemon (global).
        if config.marca_apagada(config.ENV_AUTO_AVANCE, pub.get("marca") or ""):
            continue
        if not base_lista(pub):
            continue  # aún en producción (le falta copy/copy-in/imagen-formato)
        # ¿Hay veredicto de QA FRESCO para este copy? (None si no hay o si el copy cambió.)
        veredicto = repos.ultimo_veredicto_qa(pub["id"], pub.get("contenido_id") or "")
        if veredicto is not None:
            v = (veredicto.get("verdicto") or "").strip().lower()
            if v in _QA_AVANZA:
                _avanzar(pub, v)
                avanzadas += 1
            else:
                bloqueadas += 1  # 🔴 no_publicar: se queda en borrador para corregir
            continue
        # Sin veredicto fresco: lanza la QA (una sola vez por versión de copy), hasta el cap.
        if pub.get("qa_auto_hash") == dom_qa.hash_copy((pub.get("contenido") or "").strip()):
            continue  # QA ya lanzada para este copy: esperando el veredicto
        if qa_lanzadas >= cap:
            continue
        try:
            if _lanzar_qa(pub):
                qa_lanzadas += 1
        except Exception:  # noqa: BLE001 -- un fallo por pieza no debe matar el barrido
            _log.exception("auto-avance: falló lanzar la QA de la pieza %s", pub.get("id"))
    if avanzadas or qa_lanzadas or bloqueadas:
        _log.info(
            "auto-avance: %d a revisión, %d QA lanzadas, %d bloqueadas por QA.",
            avanzadas, qa_lanzadas, bloqueadas,
        )
    return {"avanzadas": avanzadas, "qa_lanzadas": qa_lanzadas, "bloqueadas": bloqueadas}


def _intervalo_segundos() -> float:
    return config.auto_avance_intervalo_horas() * 3600.0


def iniciar_auto_avance(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca el hilo demonio de auto-avance (GATEADO EN VIVO por `KENI_AUTO_AVANCE`).

    Igual que el resto de daemons: el hilo arranca SIEMPRE y comprueba el flag en cada ciclo
    (encender/apagar en runtime aplica sin reiniciar). Daemon; un fallo de barrido se loguea y
    no lo mata. NO se arranca en `crear_app` (los tests no lo levantan).
    """
    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.gate_maquina(config.auto_avance_activo),
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=ejecutar_barrido,
            log=_log,
        )

    hilo = threading.Thread(target=bucle, name="auto-avance-daemon", daemon=True)
    hilo.start()
    estado = "ACTIVO" if config.auto_avance_activo() else "EN ESPERA (KENI_AUTO_AVANCE off)"
    _log.info(
        "Auto-avance %s, cada %.0f h (QA máx/barrido=%d).",
        estado, intervalo / 3600.0, config.auto_avance_max(),
    )
    return hilo
