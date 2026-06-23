"""Dominio PIEZAS (app C · Operación): CONTRATO de C hacia el resto del catálogo.

Este módulo es el punto ÚNICO y explícito por el que otras apps tocan las piezas de C
(`piezas`). Expone tres clases de contrato, todos nombrados y propiedad de C:

  - SERIALIZACIÓN: `pieza_a_dict` (forma pública de una pieza para API/UI).
  - LECTURA (solo lectura, ADR 0005): `cola_de_aprobacion` /
    `proximas_programadas` (lo que agrega el `panel` del shell). Devuelven la forma
    pública de C; el consumidor NO arma su propia consulta contra el almacén ni conoce
    los estados internos de C.
  - HANDOFF A→C (ADR 0005): `crear_borrador` (una generación de A deposita un
    borrador en C). Es la ÚNICA puerta de creación que A usa; A no llama a `repos`
    directamente ni decide el estado inicial de la pieza.

Por qué aquí: `pieza_a_dict` ya vivía aquí (subido desde el handler de C).
Convertir las lecturas/escrituras cruzadas en funciones-contrato de C —en vez de que A y
el shell repitan llamadas a `repos.listar_piezas`/`repos.crear_pieza` y
re-serialicen a mano— hace explícito el seam: el cruce pasa por un símbolo PÚBLICO que C
posee, no por las tripas de C. La capa de datos (`repos`/`estados`) es infra compartida
(ADR 0005): este módulo la usa por dentro; los consumidores ya no.

Solo depende de los catalogos `marcas`/`redes` (hoja), la fachada de datos `repos` y las
constantes neutras `estados` (infra compartida): no importa de `api/`.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .. import marcas, pipeline_estado, redes, repos
from ..estados import ESTADO_EN_REVISION, ESTADO_PROGRAMADO

# Un hashtag en el caption: '#' + caracteres de palabra (acentos/dígitos bajo re.UNICODE).
# MISMO patrón que `campanias._PAT_HASHTAG` (que cruza piezas con campañas por el caption):
# aquí solo nos interesa SI hay alguno, para saber si falta ponerlos.
_PAT_HASHTAG = re.compile(r"#\w+", re.UNICODE)


def _cuerpos_hashtags(texto: str) -> set[str]:
    """Cuerpos (sin '#', en minúscula) de los hashtags presentes en un caption."""
    return {m.group(0).lstrip("#").lower() for m in _PAT_HASHTAG.finditer(str(texto or ""))}


def _falta_hashtags(pub: dict[str, Any]) -> bool:
    """True si al caption NO le lleva NINGÚN hashtag y por eso la pieza no puede avanzar.

    Los hashtags son clave para monitorizar campañas y líneas de contenido; el equipo los pone en
    la fase de revisión. El caso «tiene hashtags pero NO el de su LÍNEA editorial» es un gate
    DISTINTO (`_falta_hashtag_editorial`): así el feed puede pedir cada cosa en su propia etapa."""
    return not _cuerpos_hashtags(pub.get("contenido") or "")


def _falta_hashtag_editorial(pub: dict[str, Any]) -> bool:
    """True si el caption lleva hashtags pero NO el de su LÍNEA editorial (`linea_hashtags`).

    El de la sección es OBLIGATORIO (alimenta las métricas por línea), así que tener otros no basta.
    Solo aplica cuando YA hay algún hashtag (si no hay ninguno manda `_falta_hashtags`) y la línea
    declara hashtag; si el contenido no tiene línea, no falta nada por este concepto."""
    presentes = _cuerpos_hashtags(pub.get("contenido") or "")
    if not presentes:
        return False
    requeridos = [
        c for crudo in re.split(r"[,\s]+", str(pub.get("linea_hashtags") or ""))
        if (c := crudo.strip().lstrip("#").strip().lower())
    ]
    if not requeridos:
        return False
    # La línea puede declarar varios hashtags (sinónimos): basta con que el caption lleve UNO.
    return not any(req in presentes for req in requeridos)


def _hashtags_linea(pub: dict[str, Any]) -> list[str]:
    """Hashtag(s) de la LÍNEA editorial (lista CON '#'), de `linea_hashtags` (CSV). [] si no hay.

    Es la firma de la sección: el feed lo propone APARTE y en rojo (sin él las analíticas no
    desglosan bien por línea), y el gate `falta_hashtags` lo exige en el caption. Conserva la
    ortografía con que el equipo lo guardó (la comparación del gate es insensible a mayúsculas)."""
    return [
        f"#{c}" for crudo in re.split(r"[,\s]+", str(pub.get("linea_hashtags") or ""))
        if (c := crudo.strip().lstrip("#").strip())
    ]


def _hashtags_sugeridos(pub: dict[str, Any]) -> list[str]:
    """Lista de hashtags sugeridos (`pieza.hashtags_sugeridos`, JSON con '#'). [] si vacía/ilegible.

    La rellena la etapa `sugerir_hashtags` cuando una pieza recién redactada no lleva hashtags; el
    feed la muestra en gris para aceptar/rechazar. No es parte del copy hasta que un humano la acepta.
    """
    crudo = pub.get("hashtags_sugeridos")
    if isinstance(crudo, (list, tuple)):
        return [str(x) for x in crudo]
    if isinstance(crudo, str) and crudo.strip():
        try:
            datos = json.loads(crudo)
        except (ValueError, TypeError):
            return []
        if isinstance(datos, list):
            return [str(x) for x in datos]
    return []


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


def _hay_imagen_real(pub: dict[str, Any]) -> bool:
    """True si la pieza tiene una FOTO real (no la placa): subida (`foto`) o —en piezas SIN
    marca— la imagen bespoke (`imagen`). PURA.

    La imagen del ARTÍCULO de origen (`imagen_fuente`) NO cuenta: es solo una URL de
    referencia de la nota, no una foto inyectada en la pieza. Una pieza de marca sin `foto`
    real sigue necesitando foto (badge "Falta imagen") aunque traiga `imagen_fuente` —el
    equipo debe poner la foto propia—. En piezas de MARCA, `imagen` es solo la placa compuesta
    y tampoco cuenta como foto real.

    Una foto de STOCK sin autorizar (`imagen_origen='stock'`, `imagen_autorizada=False`) TAMPOCO
    cuenta como imagen real: es solo ayuda visual (atenuada + "SIN LICENCIA"), así la pieza sigue
    "Falta imagen" y no avanza/publica hasta sustituirla o autorizarla. Al autorizarla, su `foto`
    pasa a contar como real y la pieza se completa.
    """
    if (pub.get("imagen_origen") or "") == "stock" and not bool(pub.get("imagen_autorizada")):
        return False
    marca = str(pub.get("marca") or "").strip()
    return (
        bool(str(pub.get("foto") or "").strip())
        or (not marca and bool(str(pub.get("imagen") or "").strip()))
    )


def _carrusel_falta_foto(pub: dict[str, Any]) -> bool:
    """True si la pieza es variante CARRUSEL y algún SLIDE extra no tiene foto/medio real.

    El requisito de imagen se extiende a TODOS los slides, no solo a la portada: un carrusel de
    placas de SOLO TEXTO (lo que hornea la generación) no está listo —cada tarjeta necesita su
    FOTO real detrás (o ser un vídeo)—. La portada la cubre `_hay_imagen_real` (la `foto` de la
    pieza); aquí se valida el resto. Sin slides extra no añade falta (lo decide la portada).
    """
    if (str(pub.get("variante") or "foto")) != "carrusel":
        return False
    crudo = str(pub.get("carrusel") or "").strip()
    if not crudo:
        return False
    try:
        slides = json.loads(crudo)
    except (ValueError, TypeError):
        return False
    if not isinstance(slides, list):
        return False
    for s in slides:
        if not isinstance(s, dict):
            return True
        if (str(s.get("tipo") or "imagen")) == "video":
            # Un slide de vídeo está completo si trae su asset publicable.
            if not str(s.get("objeto") or "").strip():
                return True
            continue
        # Slide de imagen: completo si trae FOTO real de fondo (`foto` de procedencia) o si su
        # propio `objeto` es media CRUDA (una foto subida). NO basta una placa de SOLO TEXTO
        # horneada, que es un PNG generado en `artes/` sin foto detrás.
        objeto = str(s.get("objeto") or "").strip()
        es_placa_horneada = objeto.startswith("artes/")
        tiene_foto = bool(str(s.get("foto") or "").strip()) or (objeto != "" and not es_placa_horneada)
        if not tiene_foto:
            return True
    return False


def flags_falta_de_contenido(pub: dict[str, Any]) -> dict[str, bool]:
    """Flags `falta_*` DERIVADAS del CONTENIDO real de una pieza (copy + foto), no del flujo.

    FUENTE ÚNICA de "¿qué le falta de contenido?": la misma heurística que pinta la etapa en el
    feed. Devuelve solo las flags derivadas del contenido (`falta_copy`/`falta_imagen`); las de
    aprobación/publicación (`falta_revision`/`falta_publicar`) NO se tocan aquí.

    `falta_imagen` es SOLO la PORTADA (la `foto` de la pieza). Que a un carrusel le falten fotos
    en los SLIDES NO es «falta portada» (la portada puede estar): eso lo señala aparte la etapa
    `faltan_fotos` (ver `_carrusel_falta_foto` + `pipeline_estado.etapa_de_pieza`).

    La usan el editor y el ESPEJO para mantener en sync las flags ALMACENADAS en
    `pieza` cuando se edita/replica el contenido: sin esto, la LISTA del feed (que
    lee las flags almacenadas) seguía mostrando «falta imagen» en las redes espejo hasta abrir
    cada una (donde `pieza_a_dict` las recalculaba al vuelo). ADR 0011 / fix espejo.
    """
    return {
        "falta_copy": not str(pub.get("contenido") or "").strip(),
        "falta_imagen": not _hay_imagen_real(pub),
    }


def pieza_a_dict(pub: dict[str, Any]) -> dict[str, Any]:
    """Serializa una pieza resolviendo nombres legibles de marca y red.

    Anade `imagen` (nombre de archivo en el dir de media, o "") y `imagen_url` (URL servible:
    `/api/media/{imagen}` si está horneada, `/api/piezas/{id}/compuesta` si se deriva de
    la receta, la foto/fuente si solo hay eso, o "") para que la UI la pueda mostrar.
    """
    imagen = pub.get("imagen") or ""
    imagen_fuente = pub.get("imagen_fuente") or ""
    # ETAPA IA real de la pieza (Flujo C, follow-up #3): se DERIVA aquí, en la única
    # serialización pública de C, con la lógica PURA de `pipeline_estado.etapa_de_pieza`
    # (NO se duplica la heurística). El feed (Flujo D) PREFIERE este `etapa_ia`.
    #
    # IMPORTANTE: la etapa se deriva del CONTENIDO REAL, NO de los flags `falta_*` almacenados
    # (se DESINCRONIZAN: el pipeline rellena copy/imagen sin tocar siempre el flag).
    #
    # IMAGEN vs PLANTILLA: el campo `imagen` guarda la PLACA compuesta, que es solo la PLANTILLA
    # (parte del copy-in), NO una imagen real. Una pieza "lleva imagen" si tiene copy-in/placa o
    # está exenta; entonces necesita una FOTO real —subida (`foto`) o de fuente (`imagen_fuente`)—.
    # Las piezas de SOLO TEXTO (sin copy-in ni exención) NO necesitan imagen y están listas con
    # el copy. Por eso `imagen` (la placa) NO basta: lo que cuenta es la foto real.
    # TODO post necesita una FOTO REAL para estar LISTO (no se manda a revisión sin foto): la foto
    # cruda subida (`foto`), la imagen de la fuente (`imagen_fuente`) o —en piezas SIN marca/placa—
    # la imagen subida bespoke (`imagen`). En piezas de MARCA, `imagen` es solo la placa compuesta y
    # NO cuenta como foto.
    # CONTENIDO real, NO los flags `falta_*` almacenados (fuente única `flags_falta_de_contenido`).
    falta = flags_falta_de_contenido(pub)
    # El ASSET requerido depende del formato: vídeo -> `falta_video` (no `falta_imagen`).
    hay_video = (not bool(pub.get("falta_video", False))) or bool(str(pub.get("video") or "").strip())
    formato = redes.normalizar_formato(pub.get("formato"))
    etapa_ia = pipeline_estado.etapa_de_pieza(
        {
            "estado": pub.get("estado"),
            "formato": formato,
            "falta_copy": falta["falta_copy"],
            "falta_imagen": falta["falta_imagen"],
            "falta_video": not hay_video,
            # CARRUSEL: a sus SLIDES les falta foto real (placa de solo texto). Es distinto de
            # «falta portada» (la portada puede estar): etapa propia `faltan_fotos`.
            "falta_foto_slides": _carrusel_falta_foto(pub),
            # Placa (texto en la imagen) y hashtags: las dos acciones que el feed enseña como
            # «lo que falta» además de copy/foto (la etapa decide cuándo aplica cada una).
            "falta_copy_in": _falta_copy_in(pub, formato),
            "falta_hashtags": _falta_hashtags(pub),
            "falta_hashtag_editorial": _falta_hashtag_editorial(pub),
        }
    )
    return {
        "id": pub["id"],
        # Id del `contenido` padre: la UI lo usa para colgar los comentarios del item
        # (que son del tema, no de la fila por red). "" en piezas legadas sin padre.
        "publicacion_id": pub.get("publicacion_id") or "",
        # Enlace al RUN del pipeline (vista del proceso IA): el `publicacion_id` ES el id de la run
        # en `/api/pipelines/{id}`, pero SOLO si la pieza nació del pipeline (`origen='pipeline'`).
        # Las piezas manuales/radar/rss no tienen run que encontrar -> "" (la UI no ofrece "ver
        # proceso IA" y el usuario deja de buscar un pipeline inexistente).
        "pipeline_id": (
            (pub.get("publicacion_id") or "")
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
        # a la pieza. "" en piezas legadas o cuando la marca/red no lo genera.
        "copy_in": pub.get("copy_in") or "",
        "estado": pub["estado"],
        "revision": pub["revision"],
        # Atribucion por usuario: quien creo la pieza. "" en piezas
        # legadas/anonimas (la UI lo muestra como "desconocido").
        "autor_id": pub.get("autor_id") or "",
        "autor_nombre": pub.get("autor_nombre") or "",
        # REPARTO ("la lista", ClaroSports): quién tiene COGIDA la pieza. Vive en el
        # `contenido` PADRE (el reparto es del tema completo: todas las redes hermanas
        # comparten responsable). "" = libre, nadie la ha cogido. Se coge/suelta vía
        # `POST /api/publicaciones/{publicacion_id}/coger|soltar` (claim atómico).
        "responsable_id": pub.get("responsable_id") or "",
        "responsable_nombre": pub.get("responsable_nombre") or "",
        # Flujo de aprobacion de equipo (#9, Fase 3): quien la reviso/aprobo y cuando.
        # "" mientras la pieza no haya pasado por revision (incluidas las legadas).
        "enviado_a_revision_en": pub.get("enviado_a_revision_en") or "",
        "revisor_id": pub.get("revisor_id") or "",
        "revisor_nombre": pub.get("revisor_nombre") or "",
        "revisado_en": pub.get("revisado_en") or "",
        # Instante en que la pieza se publicó de verdad en redes (botón manual, gated por
        # `KENI_PUBLICAR_REAL`). "" mientras no se haya publicado.
        "preparado_en": pub.get("preparado_en") or "",
        # Id del post en Metricool cuando la pieza se publicó de verdad (KENI_PUBLICAR_REAL
        # activo). "" si solo se previsualizó (dry-run) o en piezas legadas.
        "id_post_metricool": pub.get("id_post_metricool") or "",
        # Origen de la imagen: 'ia'|'galeria'|'fuente'. Si es 'fuente', `imagen_fuente` trae
        # la URL original del artículo (p.ej. de un RSS de marca propia). El editor ofrece
        # "usar imagen original" tomando esa URL.
        "tipo_contenido": pub.get("tipo_contenido") or "ia",
        # FORMATO de la pieza (foto|video): decide a qué redes va (`redes.redes_de_formato`).
        # "" / desconocido -> "foto" (el formato del flujo automático). La UI muestra el badge.
        "formato": redes.normalizar_formato(pub.get("formato")),
        # VARIANTE ('foto'|'carrusel'): qué VERSIÓN de la idea es esta pieza. El feed agrupa por
        # variante para mostrar un MODO coherente por idea (todas foto o todas carrusel) con un
        # toggle, en vez de mezclar variantes por red.
        "variante": str(pub.get("variante") or "foto"),
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
        # PROCEDENCIA + AUTORIZACIÓN de la imagen adjunta (fotos de stock como ayuda visual).
        # `imagen_origen='stock'` => el front la pinta atenuada + "SIN LICENCIA" y bloquea publicar
        # hasta `imagen_autorizada=True`; el resto es crédito/licencia/atribución para el badge.
        "imagen_origen": pub.get("imagen_origen") or "",
        "imagen_proveedor": pub.get("imagen_proveedor") or "",
        "imagen_autor": pub.get("imagen_autor") or "",
        "imagen_licencia": pub.get("imagen_licencia") or "",
        "imagen_credito_url": pub.get("imagen_credito_url") or "",
        "imagen_autorizada": bool(pub.get("imagen_autorizada")),
        # Keyword de búsqueda de foto (sujeto visual) que propone la etapa Sugerir hashtags; es la
        # consulta por defecto del buscador de stock (en vez del titular largo que no encuentra nada).
        "imagen_clave": pub.get("imagen_clave") or "",
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
        # Etapa IA real del pipeline (Flujo C): generando_copy | generando_arte |
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
        # Categoría del PLAN ('breaking', 'mx', 'evergreen'…): el feed avisa con un rayo rojo
        # las de 'breaking' (al aprobarlas se programan de inmediato, sin esperar franja).
        "categoria": pub.get("categoria") or "",
        "imagen": imagen,
        # `imagen_url`: la URL SERVIBLE de la imagen de la pieza. Si hay `imagen` horneada
        # (editor pro / legacy) se sirve esa; si la imagen se DERIVA de la receta (placa de
        # marca o plantilla del estudio), apunta al render on-demand `/compuesta` en vez de a
        # un PNG horneado; si solo hay foto/fuente, esas. `render_pieza` decide sin componer.
        "imagen_url": _imagen_url_de(pub),
        "evergreen": bool(pub.get("evergreen")),
        # Sugerencia de hashtags (etapa `sugerir_hashtags`, tras Redactar): lista CON '#' que el
        # feed propone en gris para aceptar/rechazar de un clic. [] si no hay sugerencia o la pieza
        # ya lleva hashtags. La acepta un humano: solo entonces se inyecta en el copy.
        "hashtags_sugeridos": _hashtags_sugeridos(pub),
        # Hashtag(s) de la LÍNEA editorial: el feed los propone APARTE y en rojo (firma de la
        # sección, clave para el desglose de métricas por línea). [] si el contenido no tiene línea.
        "hashtags_linea": _hashtags_linea(pub),
        # ¿Al caption le falta CUALQUIER hashtag (ninguno)? Gate de la sugerencia en el feed.
        # Derivado del contenido real, no de un flag almacenado.
        "falta_hashtags": _falta_hashtags(pub),
        # ¿Lleva hashtags pero NO el de su LÍNEA editorial? Gate aparte (etapa propia): el de la
        # sección es obligatorio para el desglose de métricas por línea. Derivado del contenido.
        "falta_hashtag_editorial": _falta_hashtag_editorial(pub),
    }


# --------------------------------------------------------------------------- #
# CONTRATO DE LECTURA de C (ADR 0005): solo lectura, sin estado.                #
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
    return [pieza_a_dict(p) for p in repos.listar_piezas(estado=ESTADO_EN_REVISION)]


def proximas_programadas(limite: int) -> tuple[list[dict[str, Any]], int]:
    """Próximas piezas PROGRAMADAS de C, ordenadas por inminencia + total (LECTURA).

    Contrato de C para el `panel`: devuelve `(items, total)` donde `items` son las
    `limite` piezas en estado `programado` más inminentes (por `fecha_programada`
    ascendente; las sin fecha al final) en forma pública, y `total` el número total de
    programadas. El shell no conoce el literal `programado` ni el criterio de orden: los
    encapsula C.
    """
    programadas = repos.listar_piezas(estado=ESTADO_PROGRAMADO)
    programadas.sort(key=lambda p: p.get("fecha_programada") or "9999")
    items = [pieza_a_dict(p) for p in programadas[: max(0, limite)]]
    return items, len(programadas)


# --------------------------------------------------------------------------- #
# CONTRATO DE HANDOFF A→C (ADR 0005): A deposita un BORRADOR en C.               #
# Única puerta de creación cruzada: A no llama a `repos.crear_pieza` ni     #
# decide el estado inicial; C garantiza que el handoff nace siempre `borrador`.  #
# --------------------------------------------------------------------------- #


def crear_borrador(
    marca: str,
    red: str,
    *,
    titulo: str = "",
    contenido: str = "",
    copy_in: str = "",
    revision: str = "",
    origen: str = "",
    imagen: str = "",
    imagen_fuente: str = "",
    foto: str = "",
    tipo_contenido: str = "",
    evergreen: bool = False,
    autor: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Crea un BORRADOR en C a partir de una generación de A y lo devuelve serializado.

    Contrato de handoff A→C (ADR 0005): una generación de copy/imagen deposita
    su resultado como pieza editable en C. El estado inicial SIEMPRE es `borrador`
    (no se expone `estado`: A no puede crear nada ya aprobado/programado por esta vía);
    el resto del flujo (revisión, programación, publicación) es responsabilidad de C.

    `imagen_fuente` + `tipo_contenido='fuente'` permiten que un handoff desde un RSS de
    marca propia nazca con la imagen original del artículo lista para usarse. `foto` (foto
    cruda ya descargada a media, p. ej. la og:image original): la pieza nace con foto real
    (cuenta como imagen; la placa se compone sobre ella), sin "Falta imagen".
    """
    pub = repos.crear_pieza(
        marca,
        red,
        titulo=titulo,
        contenido=contenido,
        copy_in=copy_in,
        estado="borrador",
        revision=revision,
        origen=origen,
        imagen=imagen,
        imagen_fuente=imagen_fuente,
        foto=foto,
        tipo_contenido=tipo_contenido,
        evergreen=evergreen,
        autor=autor,
    )
    return pieza_a_dict(pub)


def crear_borrador_en(
    publicacion_id: str,
    marca: str,
    red: str,
    *,
    titulo: str = "",
    contenido: str = "",
    copy_in: str = "",
    revision: str = "",
    imagen: str = "",
    imagen_fuente: str = "",
    foto: str = "",
    carrusel: str = "",
    evergreen: bool = False,
) -> dict[str, Any] | None:
    """Adjunta un BORRADOR a un `contenido` (tema) EXISTENTE y lo devuelve serializado.

    `carrusel` (pipeline, output carrusel): JSON de slides EXTRA en crudo
    (`[{tipo:"imagen",objeto}, …]`, mismo contrato que el cajón presidencia). La portada
    sigue siendo `imagen`/`imagen_fuente`. "" = pieza de foto normal (no se pisa la media
    que un placeholder ya traiga). `foto` (foto cruda ya descargada, p. ej. la og:image
    original de marca propia): cuenta como imagen real → la pieza nace LISTA (sin "Falta
    imagen") y la placa de marca se compone sobre ella on-demand.

    Variante de `crear_borrador` que NIDA la pieza bajo un tema del tablero en vez de crear
    su propio padre (peticion de un content manager: el borrador auto-generado cuelga del tema origen).
    Crea una fila `pieza` con `es_publicacion=1`, estado `pendiente`
    (== `borrador` editorial) y `falta_copy` DERIVADO del copy real (no hardcodeado): con copy
    es `False`, y si llega vacío (copy aún por generar) es `True`, para que el flag NO mienta
    (era la causa de piezas "copy listo" sin copy → label y auto-avance erróneos). De modo que:

      - aparece en `/api/piezas` y en `cola_de_aprobacion` (ambos filtran
        `es_publicacion=1`), igual que cualquier borrador, y
      - se muestra en la tarjeta del tema (es una fila por plataforma de ESE `contenido`).

    RELLENA antes de crear: si el tema YA tiene una fila VACÍA de esa red (placeholder sin
    copy, pre-creada al promover el tema —usar noticia, cajón presidencia—), el borrador se
    DEPOSITA en ella (conservando su media adjunta: foto/carrusel/imagen_fuente) en vez de
    crear una fila hermana duplicada de la misma red.

    Sigue siendo el contrato de C: la pieza nace `borrador` (estado `pendiente` de
    plataforma); el resto del flujo (revision/programacion/pieza) es de C. Devuelve la
    forma publica de la pieza, o `None` si el tema no existe (no nidamos en el vacio:
    el caller decide si cae al borrador suelto). NO se pasa `autor`: la atribucion del tema
    es la del `contenido` padre (que ya existe); el copy no reescribe su autor.
    """
    if not publicacion_id or repos.obtener_publicacion(publicacion_id) is None:
        return None
    falta_copy = not (contenido or "").strip()
    # Fila VACÍA pre-existente de la misma red (sin copy ni video, en borrador): se rellena.
    hueco = next(
        (
            p
            for p in repos.listar_piezas_fila(publicacion_id)
            if (p.get("red") or "") == red
            and (p.get("estado") or "borrador") == "borrador"
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
            "revision": revision,
            "evergreen": evergreen,
        }
        # La media del placeholder (foto/carrusel adjuntos al promover) se CONSERVA; la del
        # copy solo se escribe si trae algo (no pisar con "").
        if imagen:
            campos["imagen"] = imagen
        # Foto cruda real (og:image descargada): cuenta como imagen → la pieza queda LISTA.
        if foto:
            campos["foto"] = foto
            campos["falta_imagen"] = False
        if imagen_fuente:
            campos["imagen_fuente"] = imagen_fuente
            # `imagen_fuente` a secas es la URL del artículo (referencia), NO la foto de la pieza:
            # no limpia "Falta imagen". Solo `foto` (descargada arriba) cuenta y ya lo hizo.
        if carrusel:
            campos["carrusel"] = carrusel
        plat = repos.actualizar_pieza_fila(hueco["id"], campos) or hueco
    else:
        plat = repos.crear_pieza_fila(
            publicacion_id=publicacion_id,
            red=red,
            estado="borrador",
            # DERIVADO del copy real (no `False` fijo): un copy vacío => falta_copy=True. Evita el
            # drift "copy listo" sin copy que mentía en el label del feed y el gate de auto-avance.
            falta_copy=falta_copy,
            # Solo la foto real (og:image descargada) cuenta como imagen; `imagen_fuente` a secas
            # es la URL del artículo (referencia) y NO limpia "Falta imagen".
            falta_imagen=False if foto else None,
            copy=contenido,
            copy_in=copy_in,
            imagen=imagen,
            imagen_fuente=imagen_fuente,
            foto=foto,
            carrusel=carrusel,
            revision=revision,
            evergreen=evergreen,
            es_publicacion=True,
        )
    pub = repos.obtener_pieza(plat["id"])
    return pieza_a_dict(pub) if pub is not None else None
