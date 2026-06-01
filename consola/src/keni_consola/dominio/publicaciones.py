"""Dominio PUBLICACIONES (app C · Operación): CONTRATO de C hacia el resto del catálogo.

Este módulo es el punto ÚNICO y explícito por el que otras apps tocan las piezas de C
(`publicaciones`). Expone tres clases de contrato, todos nombrados y propiedad de C:

  - SERIALIZACIÓN: `publicacion_a_dict` (forma pública de una pieza para API/UI).
  - LECTURA (solo lectura, ADR 0005 §Seams #2/#3): `listar_para_reciclaje` (universo que
    consume `reciclaje` de A) y `cola_de_aprobacion` / `proximas_programadas` (lo que
    agrega el `panel` del shell). Devuelven la forma pública de C; el consumidor NO arma
    su propia consulta contra el almacén ni conoce los estados internos de C.
  - HANDOFF A→C (ADR 0005 §Seams #1): `crear_borrador` (una generación de A deposita un
    borrador en C). Es la ÚNICA puerta de creación que A usa; A no llama a `repos`
    directamente ni decide el estado inicial de la pieza.

Por qué aquí: `publicacion_a_dict` ya vivía aquí (subido desde el handler de C tras H6/N7).
Convertir las lecturas/escrituras cruzadas en funciones-contrato de C —en vez de que A y
el shell repitan llamadas a `repos.listar_publicaciones`/`repos.crear_publicacion` y
re-serialicen a mano— hace explícito el seam: el cruce pasa por un símbolo PÚBLICO que C
posee, no por las tripas de C. La capa de datos (`repos`/`estados`) es infra compartida
(ADR 0005 §Seams #6): este módulo la usa por dentro; los consumidores ya no.

Solo depende de los catalogos `marcas`/`redes` (hoja), la fachada de datos `repos` y las
constantes neutras `estados` (infra compartida): no importa de `api/`.
"""

from __future__ import annotations

from typing import Any

from .. import marcas, redes, repos
from ..estados import ESTADO_EN_REVISION, ESTADO_PROGRAMADO


def publicacion_a_dict(pub: dict[str, Any]) -> dict[str, Any]:
    """Serializa una publicacion resolviendo nombres legibles de marca y red.

    Anade `imagen` (nombre de archivo en el dir de media, o "") y `imagen_url`
    (`/api/media/{imagen}` o "" si no hay imagen) para que la UI la pueda mostrar.
    """
    imagen = pub.get("imagen") or ""
    return {
        "id": pub["id"],
        # Id del `contenido` padre: la UI lo usa para colgar los comentarios del item
        # (que son del tema, no de la fila por red). "" en piezas legadas sin padre.
        "contenido_id": pub.get("contenido_id") or "",
        "titulo": pub["titulo"],
        "marca": pub["marca"],
        "marca_nombre": marcas.etiqueta_de(pub["marca"]),
        "red": pub["red"],
        "red_nombre": redes.nombre_por_id(pub["red"]),
        "contenido": pub["contenido"],
        # Texto que va DENTRO de la imagen (copy-in), distinto del `contenido` que acompana
        # a la publicacion. "" en piezas legadas o cuando la marca/red no lo genera.
        "copy_in": pub.get("copy_in") or "",
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
        # (preparada, NO publicada de verdad: el posteo real vía Metricool esta GATED por
        # `KENI_PUBLICAR_REAL`). ""
        # hasta que el programador la prepara al vencer su `fecha_programada`.
        "preparado_en": pub.get("preparado_en") or "",
        # Id del post en Metricool cuando KENI_PUBLICAR_REAL esta activo y la pieza
        # se envio al scheduler de Metricool. "" en dry-run y en piezas legadas.
        "id_post_metricool": pub.get("id_post_metricool") or "",
        "fecha_creacion": pub["fecha_creacion"],
        "fecha_actualizacion": pub["fecha_actualizacion"],
        "fecha_programada": pub["fecha_programada"],
        "origen": pub["origen"],
        "imagen": imagen,
        "imagen_url": f"/api/media/{imagen}" if imagen else "",
        "evergreen": bool(pub.get("evergreen")),
    }


# --------------------------------------------------------------------------- #
# CONTRATO DE LECTURA de C (ADR 0005 §Seams #2/#3): solo lectura, sin estado.   #
# Lo consumen `reciclaje` (A) y el `panel` (shell) en vez de consultar `repos`   #
# por su cuenta. C decide QUÉ universo expone y con qué forma; el consumidor no   #
# conoce los estados internos ni arma la query.                                 #
# --------------------------------------------------------------------------- #


def listar_para_reciclaje(
    marca: str | None = None, red: str | None = None
) -> list[dict[str, Any]]:
    """Universo de piezas que A·`reciclaje` necesita para proponer candidatas (LECTURA).

    Devuelve TODAS las piezas del (marca, red) filtrado, en cualquier estado y SIN
    serializar a la forma pública: la heurística de reciclaje trabaja sobre los campos
    crudos (titulo/contenido/estado/fechas/evergreen) y necesita ver borradores y
    programadas para no reproponer lo ya reciclado, y las publicadas para el cruce de
    temas. Es el contrato de lectura de C: A ya no llama a `repos.listar_publicaciones`.
    """
    return repos.listar_publicaciones(marca=marca, red=red)


def cola_de_aprobacion() -> list[dict[str, Any]]:
    """Piezas en la COLA DE APROBACIÓN de C (estado `en_revision`), forma pública (LECTURA).

    Contrato de C para el `panel` del shell: el panel solo necesita el conteo, pero C
    expone la lista (forma pública) y deja que el shell la agregue. El shell no conoce el
    literal del estado `en_revision`; lo encapsula C.
    """
    return [publicacion_a_dict(p) for p in repos.listar_publicaciones(estado=ESTADO_EN_REVISION)]


def proximas_programadas(limite: int) -> tuple[list[dict[str, Any]], int]:
    """Próximas piezas PROGRAMADAS de C, ordenadas por inminencia + total (LECTURA).

    Contrato de C para el `panel`: devuelve `(items, total)` donde `items` son las
    `limite` piezas en estado `programado` más inminentes (por `fecha_programada`
    ascendente; las sin fecha al final) en forma pública, y `total` el número total de
    programadas. El shell no conoce el literal `programado` ni el criterio de orden: los
    encapsula C.
    """
    programadas = repos.listar_publicaciones(estado=ESTADO_PROGRAMADO)
    programadas.sort(key=lambda p: p.get("fecha_programada") or "9999")
    items = [publicacion_a_dict(p) for p in programadas[: max(0, limite)]]
    return items, len(programadas)


# --------------------------------------------------------------------------- #
# CONTRATO DE HANDOFF A→C (ADR 0005 §Seams #1): A deposita un BORRADOR en C.     #
# Única puerta de creación cruzada: A no llama a `repos.crear_publicacion` ni     #
# decide el estado inicial; C garantiza que el handoff nace siempre `borrador`.  #
# --------------------------------------------------------------------------- #


def crear_borrador(
    marca: str,
    red: str,
    *,
    titulo: str = "",
    contenido: str = "",
    copy_in: str = "",
    veredicto: str = "",
    origen: str = "",
    imagen: str = "",
    evergreen: bool = False,
    autor: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Crea un BORRADOR en C a partir de una generación de A y lo devuelve serializado.

    Contrato de handoff A→C (ADR 0005 §Seams #1): una generación de copy/imagen deposita
    su resultado como pieza editable en C. El estado inicial SIEMPRE es `borrador`
    (no se expone `estado`: A no puede crear nada ya aprobado/programado por esta vía);
    el resto del flujo (revisión, programación, publicación) es responsabilidad de C.
    """
    pub = repos.crear_publicacion(
        marca,
        red,
        titulo=titulo,
        contenido=contenido,
        copy_in=copy_in,
        estado="borrador",
        veredicto=veredicto,
        origen=origen,
        imagen=imagen,
        evergreen=evergreen,
        autor=autor,
    )
    return publicacion_a_dict(pub)


def crear_borrador_en(
    contenido_id: str,
    marca: str,
    red: str,
    *,
    titulo: str = "",
    contenido: str = "",
    copy_in: str = "",
    veredicto: str = "",
    imagen: str = "",
    evergreen: bool = False,
) -> dict[str, Any] | None:
    """Adjunta un BORRADOR a un `contenido` (tema) EXISTENTE y lo devuelve serializado.

    Variante de `crear_borrador` que NIDA la pieza bajo un tema del tablero en vez de crear
    su propio padre (peticion de Angel: el borrador auto-generado cuelga del tema origen).
    Crea una fila `contenido_plataforma` con `es_publicacion=1`, estado `pendiente`
    (== `borrador` editorial) y `falta_copy=False` (la pieza YA trae copy), de modo que:

      - aparece en `/api/publicaciones` y en `cola_de_aprobacion` (ambos filtran
        `es_publicacion=1`), igual que cualquier borrador, y
      - se muestra en la tarjeta del tema (es una fila por plataforma de ESE `contenido`).

    Sigue siendo el contrato de C: la pieza nace `borrador` (estado `pendiente` de
    plataforma); el resto del flujo (revision/programacion/publicacion) es de C. Devuelve la
    forma publica de la publicacion, o `None` si el tema no existe (no nidamos en el vacio:
    el caller decide si cae al borrador suelto). NO se pasa `autor`: la atribucion del tema
    es la del `contenido` padre (que ya existe); el copy no reescribe su autor.
    """
    if not contenido_id or repos.obtener_contenido(contenido_id) is None:
        return None
    plat = repos.crear_contenido_plataforma(
        contenido_id=contenido_id,
        red=red,
        estado="pendiente",
        falta_copy=False,
        copy=contenido,
        copy_in=copy_in,
        imagen=imagen,
        veredicto=veredicto,
        evergreen=evergreen,
        es_publicacion=True,
    )
    pub = repos.obtener_publicacion(plat["id"])
    return publicacion_a_dict(pub) if pub is not None else None
