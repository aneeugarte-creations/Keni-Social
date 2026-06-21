"""Piezas — dominio/piezas.py (pieza_a_dict) + api.

Incluye la aprobacion de equipo (#9, Fase 3): la cola de revision.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

from ._base import Paginacion

__all__ = [
    "EstadoPieza",
    "EtapaIa",
    "Revision",
    "Pieza",
    "RespuestaPiezas",
    "RespuestaPieza",
    "RespuestaColaAprobacion",
]

# Vocabulario ÚNICO de estado de una pieza: el flujo de aprobación de equipo intercala
# `en_revision` entre el borrador y la salida; no hay estado de reposo `aprobado`
# (juntar los 2 likes auto-programa, no crea un estado intermedio).
EstadoPieza = Literal["borrador", "en_revision", "programado", "publicado"]
# Etapa REAL del flujo de IA de una pieza (Flujo C), derivada por
# `pipeline_estado.etapa_de_pieza`. La consume el Feed de ideación (Flujo D): es el
# estado-por-etapa "en vivo" de la pieza, más rico que `estado` (incluye el gate humano).
# Mantener en sincronía con `pipeline_estado.ETAPAS_PIEZA` y con `EtapaIa` del front.
EtapaIa = Literal[
    "generando_copy",
    "generando_arte",
    "falta_copy_in",
    "falta_hashtags",
    "lista_para_revisar",
    "programada",
    "publicada",
]
# Revision editorial de una pieza: TEXTO LIBRE. El auto-verificador (prompts de copy)
# escribe revisiones legibles y matizados ("ok — confirmar marcador con el equipo",
# "marcar claramente como rumor", "pendiente resultado real del partido"), no un enum
# cerrado. La UI deriva la insignia (Listo/Revisar/No publicar) de un prefijo normalizado
# (`meta.metaRevision`). "" = sin revision.
Revision = str


class Pieza(TypedDict):
    """Una pieza serializada (`dominio.piezas.pieza_a_dict`).

    `marca_nombre`/`red_nombre` se resuelven en servidor. `imagen` es el nombre de
    archivo ("" si no hay) e `imagen_url` su ruta servible ("" si no hay).
    `autor_id`/`autor_nombre` (atribucion por usuario, Fase 1) identifican a quien
    creo la pieza; "" en piezas legadas/anonimas (la UI las muestra como "desconocido").

    Flujo de aprobacion de equipo (#9, Fase 3): `enviado_a_revision_en`/`revisor_id`/
    `revisor_nombre`/`revisado_en` registran quien la envio/reviso y cuando; "" mientras
    no haya pasado por revision (incluidas las piezas legadas). `preparado_en` se estampa
    cuando la pieza se publica de verdad en redes (botón manual, gated por
    `KENI_PUBLICAR_REAL`); "" mientras no se haya publicado.
    """

    id: str
    # Id del `contenido` padre (tema). La UI lo usa para colgar los comentarios del item,
    # que son del tema y no de la fila por red. "" en piezas legadas sin padre.
    publicacion_id: str
    # Enlace al RUN del pipeline (vista del proceso IA): = `publicacion_id` SOLO si la pieza nació
    # del pipeline (`origen="pipeline"`); "" en piezas manuales/radar/rss (no hay run que hallar).
    # La UI ofrece "ver proceso IA" cuando no está vacío; evita posts en el feed sin pipeline.
    pipeline_id: str
    titulo: str
    marca: str
    marca_nombre: str
    red: str
    red_nombre: str
    contenido: str
    # Texto que va DENTRO de la imagen (copy-in: titular/claim sobre la placa), distinto del
    # `contenido` que acompana a la pieza. "" en piezas legadas o si no se genero.
    copy_in: str
    estado: EstadoPieza
    revision: Revision
    autor_id: str
    autor_nombre: str
    # REPARTO de trabajo ("la lista" de ClaroSports): quién tiene COGIDA la pieza. Vive en el
    # `contenido` PADRE (el reparto es del tema, no de cada red): todas las redes hermanas
    # comparten responsable. "" = libre (nadie la ha cogido). Se coge/suelta vía
    # `POST /api/publicaciones/{publicacion_id}/coger|soltar` y se filtra con `?responsable=`.
    responsable_id: str
    responsable_nombre: str
    enviado_a_revision_en: str
    revisor_id: str
    revisor_nombre: str
    revisado_en: str
    preparado_en: str
    id_post_metricool: str
    # Origen de la imagen: "ia"|"galeria"|"fuente". Si es "fuente", `imagen_fuente` trae la
    # URL original del articulo (p.ej. RSS de marca propia); el editor ofrece usarla.
    tipo_contenido: str
    # FORMATO de la pieza: "foto" (3 redes: IG/X/FB), "video" (las 5) o "carrusel" (IG/FB,
    # portada compuesta + slides extra en crudo). Lo hereda del `contenido` padre. Decide a qué
    # redes va (`redes.redes_de_formato`, fuente única). El flujo automático crea piezas "foto".
    # La UI lo muestra como badge ("Foto"/"Video"/"Carrusel").
    formato: str
    # ESPEJO entre redes (propiedad de la idea, default ON): editar el contenido de esta pieza
    # propaga copy/copy-in/foto/plantilla a sus redes hermanas (saltando las ya publicadas).
    # El editor lo togglea por pieza (PUT `{espejo}`); OFF = cada red se edita por separado.
    # Opcional (NotRequired): los productores legados no lo traen y la UI lo lee como True.
    espejo: NotRequired[bool]
    imagen_fuente: str
    # Asset de VIDEO (Ola VIDEO): clave del media (`videos/<sha256>.<ext>`), espejo de `imagen`.
    # "" si la pieza no es video o aún no tiene asset. Lo publica el programador como TipoMedia.video.
    video: str
    # Media id de la FOTO CRUDA de fondo (separada de `imagen`, la placa ya compuesta);
    # permite al editor inline recomponer la placa en vivo al reabrir la pieza.
    foto: str
    # Checklist de produccion por red (pendiente=True): Copy/Imagen/Revision/Publicar/Video. El
    # editor unificado los expone como checks marcables (PATCH a la fila por plataforma). `falta_video`
    # solo cuenta en piezas formato=video (espejo de `falta_imagen`); en piezas foto es False (N/A).
    falta_copy: bool
    falta_imagen: bool
    falta_revision: bool
    falta_publicar: bool
    falta_video: bool
    # Etapa REAL del flujo de IA (Flujo C), derivada de `estado`+checklist por
    # `pipeline_estado.etapa_de_pieza`. La prefiere el Feed (Flujo D) sobre su derivación.
    etapa_ia: EtapaIa
    fecha_creacion: str
    fecha_actualizacion: str
    fecha_programada: str
    # Fecha de la FUENTE de origen (pipeline automático): pubDate/updated del item de RSS/
    # noticia, normalizado a ISO UTC. La consola muestra "Fuente del …" junto a "Generado el
    # …" (`fecha_creacion`). "" si la pieza no nació de una fuente con fecha (alta manual).
    # Es la fecha de PUBLICACIÓN de la nota original (fallback: captura del Radar); la
    # cabecera de grupo del feed la muestra en hora CDMX junto a `fuente_original`.
    fecha_fuente: str
    # FUENTE ORIGINAL: nombre legible del medio del que salió la nota ("Récord"…), o el
    # dominio (sin www) de la URL de origen en piezas viejas. "" si la pieza no nació de
    # una nota (alta manual / creación propia): la UI omite fuente y fecha.
    fuente_original: str
    origen: str
    # Categoria del PLAN ('breaking', 'mx', 'evergreen'…), heredada del contenido padre. El feed
    # marca las 'breaking' con un rayo rojo: al aprobarlas se programan de inmediato (~5 min),
    # sin esperar a su franja. "" en piezas sin categoria (manuales / genericas).
    categoria: str
    imagen: str
    imagen_url: str
    evergreen: bool
    # Sugerencia de hashtags (etapa `sugerir_hashtags`, tras Redactar): lista CON '#' que el feed
    # propone en gris para aceptar/rechazar de un clic. [] si no hay sugerencia o la pieza ya lleva
    # hashtags. Solo se inyecta en el copy cuando un humano la acepta. Opcional: los productores
    # legados no lo traen y el feed lo lee como [].
    hashtags_sugeridos: NotRequired[list[str]]
    # ¿El caption NO lleva ningún hashtag? Gate de la sugerencia en el feed (solo se ofrece cuando
    # faltan). Derivado del contenido real (mismo criterio que `falta_hashtags` de la etapa IA).
    # Opcional: el front lo deriva igual del `contenido`, así que un payload legado sin él no rompe.
    falta_hashtags: NotRequired[bool]
    # Auto-avance: la pieza esta EXENTA de copy-in (imagen dramatica/autoexplicativa que no lo
    # necesita). Opcional: las piezas legadas no lo traen y el feed lo lee como False.
    copy_in_exento: NotRequired[bool]
    # "Quitar plantilla": publicar SOLO la foto, sin la placa de marca encima. Opcional: las
    # piezas legadas no lo traen y se lee como False (con plantilla).
    placa_oculta: NotRequired[bool]
    # Plantilla del estudio (PlantillaDiseno) elegida para esta pieza; "" = ninguna. Opcional.
    plantilla_diseno_id: NotRequired[str]
    # Reencuadre manual de la foto dentro del marco 4:5 (JSON `{"foco":[x,y],"zoom":z}`; "" = sin
    # reencuadre). Persiste la elección humana del recorte. Opcional (piezas legadas no lo traen).
    foto_encuadre: NotRequired[str]
    # COLLAGE multi-hueco: JSON array `[{objeto,foco,zoom}, …]`, una foto por hueco de la plantilla.
    # "" = sin collage (hueco único derivado de `foto`). Opcional. Frontera API->frontend.
    fotos: NotRequired[str]
    # CARRUSEL: slides EXTRA en crudo, JSON array `[{tipo:"imagen"|"video",objeto}, …]` en orden
    # de publicación (la portada es la imagen compuesta de siempre). "" = sin slides / otro
    # formato. Opcional. Frontera API->frontend.
    carrusel: NotRequired[str]


class RespuestaPiezas(TypedDict):
    """Listado de `GET /api/piezas` con el envelope de paginacion."""

    piezas: list[Pieza]
    paginacion: Paginacion


class RespuestaPieza(TypedDict):
    """Respuesta de los endpoints que devuelven UNA pieza (`{pieza}`)."""

    pieza: Pieza


class RespuestaColaAprobacion(TypedDict):
    """Cola de aprobacion (`GET /api/aprobacion/cola`): piezas en revision, FIFO.

    Cada item es una `Pieza` completa (incluye `autor_nombre`/
    `enviado_a_revision_en`: quien la envio y desde cuando espera). `total` = nº en cola.
    """

    cola: list[Pieza]
    total: int
