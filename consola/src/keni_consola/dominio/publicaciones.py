"""Dominio PUBLICACIONES: serializacion de una publicacion a su forma publica (API/UI).

`publicacion_a_dict` resuelve los nombres legibles de marca y red y la URL de la imagen.
Antes era un helper PRIVADO de `api/publicaciones.py` (`_publicacion_a_dict`) que
`api/skills.py` importaba por su nombre con guion bajo (hallazgo H6/N7): un handler HTTP
tomando un simbolo privado de otro handler. Se sube aqui, al dominio, para que ambos
handlers lo consuman desde un sitio comun y publico, sin acoplarse entre si.

Solo depende de los catalogos `marcas` y `redes` (modulos hoja): no importa de `api/`.
"""

from __future__ import annotations

from typing import Any

from .. import marcas, redes


def publicacion_a_dict(pub: dict[str, Any]) -> dict[str, Any]:
    """Serializa una publicacion resolviendo nombres legibles de marca y red.

    Anade `imagen` (nombre de archivo en el dir de media, o "") y `imagen_url`
    (`/api/media/{imagen}` o "" si no hay imagen) para que la UI la pueda mostrar.
    """
    imagen = pub.get("imagen") or ""
    return {
        "id": pub["id"],
        "titulo": pub["titulo"],
        "marca": pub["marca"],
        "marca_nombre": marcas.etiqueta_de(pub["marca"]),
        "red": pub["red"],
        "red_nombre": redes.nombre_por_id(pub["red"]),
        "contenido": pub["contenido"],
        "estado": pub["estado"],
        "veredicto": pub["veredicto"],
        # Atribucion por usuario (#130 Fase 1): quien creo la pieza. "" en piezas
        # legadas/anonimas (la UI lo muestra como "desconocido").
        "autor_id": pub.get("autor_id") or "",
        "autor_nombre": pub.get("autor_nombre") or "",
        # Flujo de aprobacion de equipo (#9, Fase 3): quien la reviso/aprobo y cuando.
        # "" mientras la pieza no haya pasado por revision (incluidas las legadas).
        "enviado_a_revision_en": pub.get("enviado_a_revision_en") or "",
        "revisor_id": pub.get("revisor_id") or "",
        "revisor_nombre": pub.get("revisor_nombre") or "",
        "revisado_en": pub.get("revisado_en") or "",
        # Marca dry-run del programador (#9): instante en que quedo "lista para publicar"
        # (preparada, NO publicada de verdad: el posteo real esta GATED por #5/#8). ""
        # hasta que el programador la prepara al vencer su `fecha_programada`.
        "preparado_en": pub.get("preparado_en") or "",
        "fecha_creacion": pub["fecha_creacion"],
        "fecha_actualizacion": pub["fecha_actualizacion"],
        "fecha_programada": pub["fecha_programada"],
        "origen": pub["origen"],
        "imagen": imagen,
        "imagen_url": f"/api/media/{imagen}" if imagen else "",
        "evergreen": bool(pub.get("evergreen")),
    }
