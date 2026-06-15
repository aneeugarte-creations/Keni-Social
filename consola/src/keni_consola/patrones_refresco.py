"""Re-derivación PERIÓDICA de los perfiles de patrones por marca (daemon, OFF por defecto).

Cierra el ciclo de `patrones_marca`/`patrones_derivar`: los patrones editoriales se
derivaron de datos UNA vez, pero las audiencias cambian; este daemon los RE-DERIVA de
Metricool cada N días y aplica el resultado al runtime (perfil JSON + doc editorial
`patrones` del store), de modo que el copy nuevo y el verificador de voz siempre
comparan contra la foto reciente, sin tocar git ni esperar un deploy.

SAFE BY DEFAULT: gateado por `KENI_PATRONES_AUTO` (ausente = OFF). Solo LEE de la API
de Metricool y escribe los artefactos de patrones; jamás toca Voz/Reglas (criterio
humano) ni publica nada. El gate se lee EN VIVO via `config.patrones_auto_activo`
(`bucle_gateado`, precedencia store > env > defecto): el toggle del catálogo de ajustes
enciende/apaga sin reiniciar, igual que el resto de daemons del Monitor.

Frescura SIN estado extra: el campo `generado` del propio perfil runtime es el marcador.
Al arrancar (y en cada comprobación) se re-deriva solo si el perfil más viejo supera
`KENI_PATRONES_REFRESCO_DIAS` (o si aún no hay perfil runtime, p. ej. primer arranque
con el daemon activo). Reinicios/redeploys frecuentes NO provocan re-derivaciones.

Env:
  - KENI_PATRONES_AUTO            "1"/"true" activa el daemon (def OFF; editable en UI).
  - KENI_PATRONES_REFRESCO_DIAS   edad máxima del perfil antes de re-derivar (def 30).
  - KENI_PATRONES_MESES           ventana de extracción hacia atrás (def 6 meses).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone

from . import config, daemon_util

_log = logging.getLogger("keni_consola.patrones_refresco")

# Cadencia de COMPROBACIÓN (no de re-derivación): barata (lee un campo de un JSON local).
_COMPROBAR_CADA_S = 6 * 3600.0

_DIAS_DEFECTO = 30
_MESES_DEFECTO = 6


def _dias_refresco() -> int:
    try:
        return max(1, int(os.environ.get("KENI_PATRONES_REFRESCO_DIAS", _DIAS_DEFECTO)))
    except ValueError:
        return _DIAS_DEFECTO


def _meses_ventana() -> int:
    try:
        return max(1, int(os.environ.get("KENI_PATRONES_MESES", _MESES_DEFECTO)))
    except ValueError:
        return _MESES_DEFECTO


def _edad_dias(generado: str, ahora: datetime) -> float | None:
    """Edad en días de un timestamp ISO del perfil; None si no es parseable."""
    try:
        ts = datetime.fromisoformat(generado)
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (ahora - ts).total_seconds() / 86400.0


def _perfil_mas_viejo_dias(marcas_keni: list[str], ahora: datetime) -> float | None:
    """Edad del perfil RUNTIME más viejo entre `marcas_keni`; None si falta alguno.

    None = "hay una marca sin perfil runtime aún" -> toca derivar (primer arranque).
    Solo mira el runtime (`dir_perfiles_data`): la base del paquete es la foto del
    último commit, no del último refresco.
    """
    from . import patrones_marca

    base = patrones_marca.dir_perfiles_data()
    peor: float | None = 0.0
    for marca in marcas_keni:
        ruta = base / f"{marca}.json"
        if not ruta.is_file():
            return None
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            edad = _edad_dias(str(datos.get("generado") or ""), ahora)
        except (OSError, json.JSONDecodeError, ValueError):
            return None
        if edad is None:
            return None
        peor = max(peor or 0.0, edad)
    return peor


def refrescar_patrones(*, forzar: bool = False) -> int:
    """Re-deriva y APLICA los perfiles de las marcas del catálogo si toca (o `forzar`).

    Devuelve cuántas marcas se aplicaron (0 si no tocaba o no hubo datos). Las marcas
    sin credenciales de Metricool o sin piezas suficientes se omiten con WARN (el
    perfil anterior se conserva: nunca se degrada un perfil bueno con una extracción
    vacía). Pensado para el daemon y para una invocación manual de operación.
    """
    from keni_shared import marcas as cat_marcas

    from . import patrones_derivar, patrones_marca

    ahora = datetime.now(timezone.utc)
    ids_keni = [m for m, _ in cat_marcas.opciones()]
    if not forzar:
        edad = _perfil_mas_viejo_dias(ids_keni, ahora)
        if edad is not None and edad < _dias_refresco():
            return 0
    a_metricas = {cat_marcas.id_metricas_de(m): m for m in ids_keni}
    por_marca = patrones_derivar.extraer_piezas_metricool(
        list(a_metricas), meses=_meses_ventana()
    )
    aplicadas = 0
    ahora_iso = ahora.isoformat(timespec="seconds")
    for id_metricas, marca_keni in a_metricas.items():
        piezas = por_marca.get(id_metricas) or []
        if not piezas:
            continue
        fechas = sorted(str(p.get("publicado") or "") for p in piezas if p.get("publicado"))
        perfil = patrones_marca.derivar_perfil(
            piezas, marca_keni,
            desde=fechas[0] if fechas else "", hasta=fechas[-1] if fechas else "",
            generado=ahora_iso,
        )
        if not perfil["redes"]:
            _log.warning("patrones: %s sin muestra suficiente; se conserva el perfil previo", marca_keni)
            continue
        try:
            patrones_derivar.aplicar_store(perfil, marca_keni, ahora=ahora_iso)
            aplicadas += 1
        except Exception:  # noqa: BLE001 -- una marca no debe tumbar el barrido de las demás
            _log.exception("patrones: no se pudo aplicar el perfil de %s", marca_keni)
    if aplicadas:
        _log.info("patrones: %d perfil(es) re-derivados y aplicados.", aplicadas)
    return aplicadas


def _resumen_barrido(n: int) -> str:
    """Resumen corto del barrido de patrones para el historial (perfiles re-derivados)."""
    return f"{n} marca(s) re-derivada(s)" if n else "sin novedad"


def iniciar_refresco_patrones() -> threading.Thread:
    """Arranca el hilo demonio de re-derivación de patrones (GATEADO EN VIVO).

    Espejo de `media_gc_daemon`: el hilo arranca SIEMPRE y comprueba `KENI_PATRONES_AUTO`
    en cada ciclo (`bucle_gateado`), así el toggle del catálogo aplica sin reiniciar
    (apagar en <= ~1 min; encender tras estar apagado dispara una comprobación de
    inmediato — que solo re-deriva si el perfil está viejo, ver `refrescar_patrones`).
    Antes el flag se leía UNA vez al arrancar (solo-env): encenderlo en runtime no hacía
    nada hasta el siguiente deploy.
    """

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.patrones_auto_activo,
            intervalo_seg_fn=lambda: _COMPROBAR_CADA_S,
            sweep_fn=refrescar_patrones,
            log=_log,
            resumen_fn=_resumen_barrido,
        )

    hilo = threading.Thread(target=bucle, name="patrones-refresco-daemon", daemon=True)
    hilo.start()
    estado = "ACTIVA" if config.patrones_auto_activo() else "EN ESPERA (KENI_PATRONES_AUTO off)"
    _log.info(
        "Re-derivación de patrones %s, comprobación cada %.0f h.",
        estado, _COMPROBAR_CADA_S / 3600.0,
    )
    return hilo
