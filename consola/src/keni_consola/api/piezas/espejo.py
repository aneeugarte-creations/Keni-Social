"""Propagacion de ESPEJO entre redes hermanas de una misma idea.

Cuando se edita el CONTENIDO de una pieza, los campos de la "receta" (`_CAMPOS_ESPEJO`) se
replican a las piezas hermanas (otras redes del mismo `contenido` padre) salvo a las ya
publicadas. Extraido TAL CUAL del modulo `piezas.py` original (refactor de pura
reubicacion, sin cambio de comportamiento).
"""

from __future__ import annotations

import logging
from typing import Any

from ... import repos
from ...dominio.piezas import pieza_a_dict
from ...estados import ESTADO_BORRADOR, ESTADO_PUBLICADO
from ._comun import (
    _CAMPOS_ESPEJO,
    _RESET_APROBACIONES,
    _inyectar_flags_falta,
    _limpiar_cadena,
    _pierde_aprobaciones,
)

_log = logging.getLogger("keni_consola.api.piezas")


def _propagar_espejo(pub: dict[str, Any], campos: dict[str, Any]) -> None:
    """ESPEJO entre redes: replica los campos de CONTENIDO editados a las redes hermanas.

    Las piezas de una idea normalmente van parejas en todas sus redes, así que el espejo
    nace ACTIVADO (`contenido.espejo`, toggle por pieza en el editor). `pub` es la pieza ya
    actualizada (con su `espejo` vigente); solo se propagan los campos de `_CAMPOS_ESPEJO`
    presentes en la edición. Las hermanas YA PUBLICADAS no se tocan (lo que salió a la red
    no cambia desde aquí); una hermana con aprobaciones sufre el MISMO reset que la pieza
    editada (su contenido cambió: exige OK nuevos).
    """
    espejo_campos = {k: campos[k] for k in _CAMPOS_ESPEJO if k in campos}
    if not espejo_campos or not pub.get("espejo", True):
        return
    publicacion_id = pub.get("publicacion_id") or ""
    if not publicacion_id:
        return
    variante = pub.get("variante") or "foto"
    for plat in repos.listar_piezas_fila(publicacion_id):
        if plat["id"] == pub["id"]:
            continue
        # El espejo NO cruza variantes: una pieza foto y su hermana carrusel son generaciones
        # independientes del mismo contenido. Editar el copy de la foto no debe pisar el del
        # carrusel (ni al revés). Solo se replica entre piezas de la MISMA variante.
        if (plat.get("variante") or "foto") != variante:
            continue
        hermana = repos.obtener_pieza(plat["id"])
        if hermana is None or (hermana.get("estado") or "") == ESTADO_PUBLICADO:
            continue
        campos_h: dict[str, Any] = dict(espejo_campos)
        resetear = _pierde_aprobaciones(hermana, campos_h)
        if resetear:
            campos_h.update(_RESET_APROBACIONES)
        # El estado de readiness (falta copy/imagen) SÍ se actualiza en el espejo aunque la
        # aprobación no: la hermana hereda el contenido, así que sus flags reflejan lo heredado.
        _inyectar_flags_falta(hermana, campos_h)
        actualizada = repos.actualizar_pieza(plat["id"], campos_h)
        if actualizada is None:
            continue  # borrada en paralelo: nada que espejar
        if resetear:
            _limpiar_cadena(plat["id"])
        _promover_si_completa(actualizada)


def _promover_si_completa(hermana: dict[str, Any]) -> None:
    """Envía la hermana a revisión si quedó completa en `borrador`, igual que el daemon de avance.

    Tras heredar el contenido por el espejo, una hermana ya LISTA (copy + asset del formato, la
    misma derivación del feed: `etapa_ia == "lista_para_revisar"`) entra sola a la cola de
    revisión con su cadena, sin esperar a que un humano abra y cierre su editor. Reúsa la
    transición CAS + montaje de cadena del avance (fuente de verdad). Best-effort: un fallo de
    la promoción no rompe la edición que disparó el espejo.
    """
    if (hermana.get("estado") or "") != ESTADO_BORRADOR:
        return
    if pieza_a_dict(hermana).get("etapa_ia") != "lista_para_revisar":
        return
    # Import tardío: la fuente de verdad del avance vive en el pipeline; se carga al promover.
    from ...pipeline_contenido._avance import enviar_a_revision

    try:
        enviar_a_revision(hermana)
    except Exception:  # noqa: BLE001 -- la promoción es best-effort; nunca rompe la edición
        _log.warning(
            "espejo: no se pudo promover la hermana %s a revisión",
            hermana.get("id", ""),
            exc_info=True,
        )
