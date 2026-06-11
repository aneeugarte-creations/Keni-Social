"""Dominio PUBLICACIONES (app C · Operación): CONTRATO de C hacia el resto del catálogo.

Este módulo es el punto ÚNICO y explícito por el que otras apps tocan las piezas de C
(`publicaciones`). Expone tres clases de contrato, todos nombrados y propiedad de C:

  - SERIALIZACIÓN: `publicacion_a_dict` (forma pública de una pieza para API/UI).
  - LECTURA (solo lectura, ADR 0005 §Seams #2/#3): `cola_de_aprobacion` /
    `proximas_programadas` (lo que agrega el `panel` del shell). Devuelven la forma
    pública de C; el consumidor NO arma su propia consulta contra el almacén ni conoce
    los estados internos de C.
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

import re
from typing import Any

from .. import marcas, pipeline_estado, redes, repos
from ..estados import ESTADO_EN_REVISION, ESTADO_PROGRAMADO

# Un hashtag en el caption: '#' + caracteres de palabra (acentos/dígitos bajo re.UNICODE).
# MISMO patrón que `campanias._PAT_HASHTAG` (que cruza piezas con campañas por el caption):
# aquí solo nos interesa SI hay alguno, para saber si falta ponerlos.
_PAT_HASHTAG = re.compile(r"#\w+", re.UNICODE)


def _falta_hashtags(pub: dict[str, Any]) -> bool:
    """True si el copy (caption) NO lleva ningún hashtag. Los hashtags son clave para
    monitorizar campañas y líneas de contenido; el equipo los pone en la fase de revisión."""
    return not _PAT_HASHTAG.search(str(pub.get("contenido") or ""))


def _falta_copy_in(pub: dict[str, Any], formato: str) -> bool:
    """True si la pieza necesita el TEXTO sobre la imagen (placa, `copy_in`) y no lo tiene.

    Solo aplica a piezas de MARCA con placa (foto/carrusel): la placa con su titular es de marca.
    No aplica a piezas SIN marca (imagen bespoke, sin plantilla) ni a vídeo. Tampoco falta cuando
    la pieza está EXENTA de copy-in (imagen autoexplicativa, `copy_in_exento`) o se publica sin
    placa (`placa_oculta`, foto cruda). Es producción (la genera el pipeline con el copy)."""
    if not str(pub.get("marca") or "").strip():
        return False
    if redes.normalizar_formato(formato) not in ("foto", "carrusel"):
        return False
    if pub.get("copy_in_exento") or pub.get("placa_oculta"):
        return False
    return not str(pub.get("copy_in") or "").strip()


def _fuente_original_de(pub: dict[str, Any]) -> str:
    """Nombre LEGIBLE del medio del que salió la nota original de la pieza ("Récord"…).

    Prefiere `fuente_nombre` (copiado al `contenido` en la promoción CI, para sobrevivir
    al GC de noticias). Para piezas viejas (anteriores a esa columna) deriva el dominio
    de `url_fuente`, que se guarda CANÓNICA (sin esquema ni `www.`); defensivo por si
    llegara una URL completa. "" si la pieza no nació de una nota (alta manual /
    creación propia): la UI omite entonces fuente y fecha en la cabecera del grupo.
    """
    nombre = str(pub.get("fuente_nombre") or "").strip()
    if nombre:
        return nombre
    url = str(pub.get("url_fuente") or "").strip()
    if not url:
        return ""
    sin_esquema = url.split("://", 1)[-1]
    dominio = sin_esquema.split("/", 1)[0].split("?", 1)[0].strip().lower()
    return dominio.removeprefix("www.")


def _imagen_url_de(pub: dict[str, Any]) -> str:
    """URL servible de la imagen de la pieza (delega en `render_pieza`, sin componer).

    Import DIFERIDO: `render_pieza` importa el Estudio (motores), que no debe cargarse al
    importar el contrato de C. La decisión es barata (no llama a Node): solo elige la URL.
    """
    from . import render_pieza

    return render_pieza.imagen_url_de(pub)


def publicacion_a_dict(pub: dict[str, Any]) -> dict[str, Any]:
    """Serializa una publicacion resolviendo nombres legibles de marca y red.

    Anade `imagen` (nombre de archivo en el dir de media, o "") y `imagen_url` (URL servible:
    `/api/media/{imagen}` si está horneada, `/api/publicaciones/{id}/compuesta` si se deriva de
    la receta, la foto/fuente si solo hay eso, o "") para que la UI la pueda mostrar.
    """
    imagen = pub.get("imagen") or ""
    imagen_fuente = pub.get("imagen_fuente") or ""
    # ETAPA IA real de la pieza (Flujo C, follow-up #3): se DERIVA aquí, en la única
    # serialización pública de C, con la lógica PURA de `pipeline_estado.etapa_de_pieza`
    # (NO se duplica la heurística). El feed (Flujo D) PREFIERE este `etapa_ia`.
    #
    # IMPORTANTE: la etapa se deriva del CONTENIDO REAL, NO de los flags `falta_*` almacenados
    # (se DESINCRONIZAN: la tubería rellena copy/imagen sin tocar siempre el flag).
    #
    # IMAGEN vs PLANTILLA: el campo `imagen` guarda la PLACA compuesta, que es solo la PLANTILLA
    # (parte del copy-in), NO una imagen real. Una pieza "lleva imagen" si tiene copy-in/placa o
    # está exenta; entonces necesita una FOTO real —subida (`foto`) o de fuente (`imagen_fuente`)—.
    # Las piezas de SOLO TEXTO (sin copy-in ni exención) NO necesitan imagen y están listas con
    # el copy. Por eso `imagen` (la placa) NO basta: lo que cuenta es la foto real.
    # TODO post necesita una FOTO REAL para estar LISTO (no se manda a revisión sin foto): la foto
    # cruda subida (`foto`), la imagen de la fuente (`imagen_fuente`) o —en piezas SIN marca/placa—
    # la imagen subida bespoke (`imagen`). En piezas de MARCA, `imagen` es solo la placa compuesta y
    # NO cuenta como foto. (Antes una pieza sin copy-in se daba por lista SIN foto; ya no.)
    marca = str(pub.get("marca") or "").strip()
    hay_imagen_real = (
        bool(str(pub.get("foto") or "").strip())
        or bool(imagen_fuente)
        or (not marca and bool(str(pub.get("imagen") or "").strip()))
    )
    # El ASSET requerido depende del formato: vídeo -> `falta_video` (no `falta_imagen`).
    hay_video = (not bool(pub.get("falta_video", False))) or bool(str(pub.get("video") or "").strip())
    formato = redes.normalizar_formato(pub.get("formato"))
    etapa_ia = pipeline_estado.etapa_de_pieza(
        {
            "estado": pub.get("estado"),
            "formato": formato,
            "falta_copy": not str(pub.get("contenido") or "").strip(),
            "falta_imagen": not hay_imagen_real,
            "falta_video": not hay_video,
            # Placa (texto en la imagen) y hashtags: las dos acciones que el feed enseña como
            # «lo que falta» además de copy/foto (la etapa decide cuándo aplica cada una).
            "falta_copy_in": _falta_copy_in(pub, formato),
            "falta_hashtags": _falta_hashtags(pub),
        }
    )
    return {
        "id": pub["id"],
        # Id del `contenido` padre: la UI lo usa para colgar los comentarios del item
        # (que son del tema, no de la fila por red). "" en piezas legadas sin padre.
        "contenido_id": pub.get("contenido_id") or "",
        # Enlace al RUN del pipeline (vista del proceso IA): el `contenido_id` ES el id de la run
        # en `/api/pipelines/{id}`, pero SOLO si la pieza nació del pipeline (`origen='pipeline'`).
        # Las piezas manuales/radar/rss no tienen run que encontrar -> "" (la UI no ofrece "ver
        # proceso IA" y el usuario deja de buscar un pipeline inexistente).
        "pipeline_id": (
            (pub.get("contenido_id") or "")
            if str(pub.get("origen") or "").strip() == "pipeline"
            else ""
        ),
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
        # Origen de la imagen: 'ia'|'galeria'|'fuente'. Si es 'fuente', `imagen_fuente` trae
        # la URL original del artículo (p.ej. de un RSS de marca propia). El editor ofrece
        # "usar imagen original" tomando esa URL.
        "tipo_contenido": pub.get("tipo_contenido") or "ia",
        # FORMATO de la pieza (foto|video): decide a qué redes va (`redes.redes_de_formato`).
        # "" / desconocido -> "foto" (el formato del flujo automático). La UI muestra el badge.
        "formato": redes.normalizar_formato(pub.get("formato")),
        # ESPEJO entre redes (propiedad de la idea, default ON): editar el contenido de una
        # pieza propaga los mismos campos a sus redes hermanas. El editor lo togglea.
        "espejo": bool(pub.get("espejo", True)),
        "imagen_fuente": imagen_fuente,
        # Asset de VIDEO (Ola VIDEO): clave del media (`videos/<sha256>.<ext>`) y su checklist,
        # espejo de `imagen`/`falta_imagen`. "" si la pieza no es video o no tiene asset aún.
        "video": pub.get("video") or "",
        "falta_video": bool(pub.get("falta_video", False)),
        # Media id de la FOTO CRUDA de fondo (separada de `imagen`, la placa ya compuesta);
        # permite al editor inline recomponer la placa en vivo al reabrir la pieza.
        "foto": pub.get("foto") or "",
        # Checklist de producción por red (Copy/Imagen/Revisión/Publicar pendientes). El
        # editor unificado lo muestra como checks marcables; default True (pendiente).
        "falta_copy": bool(pub.get("falta_copy", True)),
        "falta_imagen": bool(pub.get("falta_imagen", True)),
        "falta_revision": bool(pub.get("falta_revision", True)),
        "falta_publicar": bool(pub.get("falta_publicar", True)),
        # Auto-avance: la pieza está exenta de copy-in (imagen dramática/autoexplicativa que
        # no lo necesita). El editor lo marca; el gate de auto-avance lo respeta.
        "copy_in_exento": bool(pub.get("copy_in_exento", False)),
        # "Quitar plantilla": publicar solo la foto, sin la placa de marca encima. Persiste la
        # elección del editor entre reaperturas.
        "placa_oculta": bool(pub.get("placa_oculta", False)),
        # Plantilla del estudio (PlantillaDiseno) elegida para esta pieza. "" = ninguna (placa de
        # marca por defecto). La imagen ya compuesta con ella vive en `imagen`.
        "plantilla_diseno_id": pub.get("plantilla_diseno_id") or "",
        # Reencuadre manual de la foto dentro del marco 4:5 (JSON `{"foco":[x,y],"zoom":z}`;
        # "" = sin reencuadre). El editor lo edita; persiste la elección humana del recorte.
        "foto_encuadre": pub.get("foto_encuadre") or "",
        # COLLAGE multi-hueco: JSON array `[{objeto,foco,zoom}, …]`, una foto por hueco de la
        # plantilla (en orden de `capas`). "" = sin collage (hueco único derivado de `foto`).
        "fotos": pub.get("fotos") or "",
        # CARRUSEL: slides EXTRA en crudo (JSON `[{tipo:"imagen"|"video",objeto}, …]`, en orden
        # de publicación). La PORTADA del carrusel es la imagen compuesta de siempre (slide 1);
        # estos van detrás tal cual en el post multi-media. "" = sin slides / otro formato.
        "carrusel": pub.get("carrusel") or "",
        # Etapa IA real de la tubería (Flujo C): generando_copy | generando_arte |
        # lista_para_revisar | aprobada | programada | publicada. La consume el Feed.
        "etapa_ia": etapa_ia,
        "fecha_creacion": pub["fecha_creacion"],
        "fecha_actualizacion": pub["fecha_actualizacion"],
        "fecha_programada": pub["fecha_programada"],
        # Fecha de la FUENTE de origen (pipeline automático): pubDate normalizado a ISO UTC.
        # La UI la muestra junto a `fecha_creacion` ("Generado el …" + "Fuente del …"). "" si
        # la pieza no nació de una fuente con fecha (alta manual, fuente sin pubDate).
        # NOTA: este campo ES el "publicado_original" de la nota (en clusters cae al
        # `primer_visto` del Radar si el medio no traía fecha); no se duplica con otro nombre.
        "fecha_fuente": pub.get("fecha_fuente") or "",
        # FUENTE ORIGINAL: nombre legible del medio del que salió la nota ("Récord"…), o el
        # dominio de `url_fuente` para piezas viejas sin `fuente_nombre`. "" si la pieza no
        # nació de una nota. La cabecera de grupo del feed lo muestra junto a `fecha_fuente`.
        "fuente_original": _fuente_original_de(pub),
        "origen": pub["origen"],
        "imagen": imagen,
        # `imagen_url`: la URL SERVIBLE de la imagen de la pieza. Si hay `imagen` horneada
        # (editor pro / legacy) se sirve esa; si la imagen se DERIVA de la receta (placa de
        # marca o plantilla del estudio), apunta al render on-demand `/compuesta` en vez de a
        # un PNG horneado; si solo hay foto/fuente, esas. `render_pieza` decide sin componer.
        "imagen_url": _imagen_url_de(pub),
        "evergreen": bool(pub.get("evergreen")),
    }


# --------------------------------------------------------------------------- #
# CONTRATO DE LECTURA de C (ADR 0005 §Seams #2/#3): solo lectura, sin estado.   #
# Lo consumen `reciclaje` (A) y el `panel` (shell) en vez de consultar `repos`   #
# por su cuenta. C decide QUÉ universo expone y con qué forma; el consumidor no   #
# conoce los estados internos ni arma la query.                                 #
# --------------------------------------------------------------------------- #



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
    imagen_fuente: str = "",
    tipo_contenido: str = "",
    evergreen: bool = False,
    autor: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Crea un BORRADOR en C a partir de una generación de A y lo devuelve serializado.

    Contrato de handoff A→C (ADR 0005 §Seams #1): una generación de copy/imagen deposita
    su resultado como pieza editable en C. El estado inicial SIEMPRE es `borrador`
    (no se expone `estado`: A no puede crear nada ya aprobado/programado por esta vía);
    el resto del flujo (revisión, programación, publicación) es responsabilidad de C.

    `imagen_fuente` + `tipo_contenido='fuente'` permiten que un handoff desde un RSS de
    marca propia nazca con la imagen original del artículo lista para usarse.
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
        imagen_fuente=imagen_fuente,
        tipo_contenido=tipo_contenido,
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
    imagen_fuente: str = "",
    evergreen: bool = False,
) -> dict[str, Any] | None:
    """Adjunta un BORRADOR a un `contenido` (tema) EXISTENTE y lo devuelve serializado.

    Variante de `crear_borrador` que NIDA la pieza bajo un tema del tablero en vez de crear
    su propio padre (peticion de Angel: el borrador auto-generado cuelga del tema origen).
    Crea una fila `contenido_plataforma` con `es_publicacion=1`, estado `pendiente`
    (== `borrador` editorial) y `falta_copy` DERIVADO del copy real (no hardcodeado): con copy
    es `False`, y si llega vacío (copy aún por generar) es `True`, para que el flag NO mienta
    (era la causa de piezas "copy listo" sin copy → label y auto-avance erróneos). De modo que:

      - aparece en `/api/publicaciones` y en `cola_de_aprobacion` (ambos filtran
        `es_publicacion=1`), igual que cualquier borrador, y
      - se muestra en la tarjeta del tema (es una fila por plataforma de ESE `contenido`).

    RELLENA antes de crear: si el tema YA tiene una fila VACÍA de esa red (placeholder sin
    copy, pre-creada al promover el tema —usar noticia, cajón presidencia—), el borrador se
    DEPOSITA en ella (conservando su media adjunta: foto/carrusel/imagen_fuente) en vez de
    crear una fila hermana duplicada de la misma red.

    Sigue siendo el contrato de C: la pieza nace `borrador` (estado `pendiente` de
    plataforma); el resto del flujo (revision/programacion/publicacion) es de C. Devuelve la
    forma publica de la publicacion, o `None` si el tema no existe (no nidamos en el vacio:
    el caller decide si cae al borrador suelto). NO se pasa `autor`: la atribucion del tema
    es la del `contenido` padre (que ya existe); el copy no reescribe su autor.
    """
    if not contenido_id or repos.obtener_contenido(contenido_id) is None:
        return None
    falta_copy = not (contenido or "").strip()
    # Fila VACÍA pre-existente de la misma red (sin copy ni video, en borrador): se rellena.
    hueco = next(
        (
            p
            for p in repos.listar_contenido_plataforma(contenido_id)
            if (p.get("red") or "") == red
            and (p.get("estado") or "pendiente") == "pendiente"
            and not str(p.get("copy") or "").strip()
            and not str(p.get("video") or "").strip()
        ),
        None,
    )
    if hueco is not None:
        campos: dict[str, Any] = {
            "falta_copy": falta_copy,
            "copy": contenido,
            "copy_in": copy_in,
            "veredicto": veredicto,
            "evergreen": evergreen,
        }
        # La media del placeholder (foto/carrusel adjuntos al promover) se CONSERVA; la del
        # copy solo se escribe si trae algo (no pisar con "").
        if imagen:
            campos["imagen"] = imagen
        if imagen_fuente:
            campos["imagen_fuente"] = imagen_fuente
            campos["falta_imagen"] = False
        plat = repos.actualizar_contenido_plataforma(hueco["id"], campos) or hueco
    else:
        plat = repos.crear_contenido_plataforma(
            contenido_id=contenido_id,
            red=red,
            estado="pendiente",
            # DERIVADO del copy real (no `False` fijo): un copy vacío => falta_copy=True. Evita el
            # drift "copy listo" sin copy que mentía en el label del feed y el gate de auto-avance.
            falta_copy=falta_copy,
            # Con imagen de fuente (URL del artículo) la pieza YA tiene imagen.
            falta_imagen=False if imagen_fuente else None,
            copy=contenido,
            copy_in=copy_in,
            imagen=imagen,
            imagen_fuente=imagen_fuente,
            veredicto=veredicto,
            evergreen=evergreen,
            es_publicacion=True,
        )
    pub = repos.obtener_publicacion(plat["id"])
    return publicacion_a_dict(pub) if pub is not None else None
