"""CRUD de piezas: alta (individual y lote), listado/paginacion, detalle, edicion,
borrado (individual y lote), cadenas batch, clonar y programar en Metricool.

El ciclo de vida editorial de cada pieza (borrador -> en_revision -> programado -> publicado),
con validacion de marca/red/estado y maquina de transiciones del PUT. Extraido
TAL CUAL del modulo `piezas.py` original (refactor de pura reubicacion, sin cambio de
comportamiento).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import marcas, permisos, redes, repos
from ..._http_json import (
    cursor_query,
    envoltura_paginacion,
    leer_json,
    paginacion_query,
    tope_listado,
)
from ...estados import (
    ESTADO_BORRADOR,
    ESTADO_EN_REVISION,
    ESTADO_PROGRAMADO,
    ESTADO_PUBLICADO,
)
from ...motor_db import IntegrityError
from ...seguridad import autor_de_peticion
from ...tiempo import iso_utc
from ._comun import (
    _CAMPOS_ESPEJO,
    _RESET_APROBACIONES,
    _inyectar_flags_falta,
    _limpiar_cadena,
    _pierde_aprobaciones,
    _publicacion_a_dict,
)
from .espejo import _propagar_espejo

# Nombres legibles de los estados (para poblar selects de la UI), en orden de flujo.
# `en_revision` (cola de aprobacion de equipo, #9) se intercala tras el borrador.
_ESTADO_NOMBRE: dict[str, str] = {
    "borrador": "Borrador",
    "en_revision": "En revisión",
    "programado": "Programado",
    "publicado": "Publicado",
}

# Marcas validas como destino de copy: TODAS las del catalogo unico. value
# interno = id canonico (slug-guion); etiqueta visible = nombre humano con acentos.
_MARCAS: tuple[tuple[str, str], ...] = tuple(marcas.opciones())
_MARCAS_IDS = {m[0] for m in _MARCAS}


_TRANSICIONES_PUT: dict[str, frozenset[str]] = {
    ESTADO_BORRADOR: frozenset({ESTADO_EN_REVISION, ESTADO_PROGRAMADO, ESTADO_PUBLICADO}),
    ESTADO_EN_REVISION: frozenset({ESTADO_BORRADOR, ESTADO_PROGRAMADO, ESTADO_PUBLICADO}),
    ESTADO_PROGRAMADO: frozenset({ESTADO_BORRADOR, ESTADO_PUBLICADO}),
    ESTADO_PUBLICADO: frozenset(),
}


def _normalizar_fecha_programada(valor: str) -> tuple[str | None, str | None]:
    """Valida y normaliza una `fecha_programada` al canon `YYYY-MM-DDTHH:MM` (minutos, UTC).

    Devuelve `(normalizada, None)` o `(None, error)`. El UNIQUE anti-doble-reserva de la
    parrilla (`idx_parrilla_slot_uniq`) compara el TEXT crudo: sin canon, "T18:00" y
    "T18:00:00" reservaban el mismo slot sin chocar. Reglas:
      - "" -> "" (sin programar; valido).
      - ISO naive -> se ASUME UTC (convencion del sistema) y se trunca a minutos.
      - ISO con zona (la UI manda el instante UTC con offset) -> se convierte a UTC y se
        despoja el offset.
      - No parseable -> error en espanol (400 en el handler).
    """
    if not valor:
        return "", None
    try:
        dt = datetime.fromisoformat(valor)
    except ValueError:
        return None, "La fecha programada no es válida (usa AAAA-MM-DDTHH:MM)."
    # `iso_utc` canoniza a segundos; el canon de parrilla es a MINUTOS (lo que generan
    # las franjas y el picker de la UI): truncamos el sufijo ":SS".
    return iso_utc(dt)[:16], None


def _validar_nueva(datos: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Valida el cuerpo de una pieza nueva.

    Devuelve `(entrada_normalizada, None)` si es valida, o `(None, mensaje)` con el
    error en espanol. No toca la base; solo valida tipos y allowlists.
    """
    marca = datos.get("marca")
    red = datos.get("red")
    if not isinstance(marca, str) or marca not in _MARCAS_IDS:
        return None, "Marca no permitida."
    if not isinstance(red, str) or not redes.es_red(red):
        return None, "Red no permitida."

    estado = datos.get("estado", "borrador")
    if estado is None or estado == "":
        estado = "borrador"
    if not isinstance(estado, str) or estado not in repos.ESTADOS_PIEZA:
        return None, "Estado no permitido."

    titulo = datos.get("titulo", "")
    contenido = datos.get("contenido", "")
    copy_in = datos.get("copy_in", "")
    revision = datos.get("revision", "")
    fecha_programada = datos.get("fecha_programada", "")
    origen = datos.get("origen", "")
    imagen = datos.get("imagen", "")
    for valor, etiqueta in (
        (titulo, "El título"),
        (contenido, "El contenido"),
        (copy_in, "El texto en imagen"),
        (revision, "El revision"),
        (fecha_programada, "La fecha programada"),
        (origen, "El origen"),
        (imagen, "La imagen"),
    ):
        if not isinstance(valor, str):
            return None, f"{etiqueta} debe ser texto."

    # Canon de `fecha_programada` (minutos, UTC sin offset): el UNIQUE de parrilla compara
    # el TEXT crudo, asi que el formato se normaliza ANTES de persistir.
    fecha_norm, err_fecha = _normalizar_fecha_programada(fecha_programada.strip())
    if err_fecha is not None:
        return None, err_fecha

    return (
        {
            "titulo": titulo.strip(),
            "marca": marca,
            "red": red,
            "contenido": contenido,
            "copy_in": copy_in,
            "estado": estado,
            "revision": revision,
            "fecha_programada": fecha_norm,
            "origen": origen.strip(),
            "imagen": imagen.strip(),
        },
        None,
    )


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def opciones(request: Request) -> Response:
    """Catalogos para los selects del SPA: redes, estados, marcas y lineas editoriales."""
    # Lineas editoriales = etiquetas de clase `vertical` (la LÍNEA de contenido). Pueblan el
    # selector de "Línea editorial" de las superficies Lista/Calendario/Feed. Se devuelven
    # TODAS las activas con su marca; el SPA acota por la marca activa del switch global.
    lineas = [
        {"id": e["id"], "nombre": e["nombre"], "marca": e.get("marca", "")}
        for e in repos.listar_etiquetas(clase="vertical", solo_activas=True)
    ]
    from ... import config

    return JSONResponse(
        {
            "redes": redes.opciones(),
            "estados": [{"id": e, "nombre": _ESTADO_NOMBRE[e]} for e in repos.ESTADOS_PIEZA],
            "marcas": [{"id": mid, "nombre": nombre} for mid, nombre in _MARCAS],
            "lineas": lineas,
            # Gate maestro de pieza real (KENI_PUBLICAR_REAL). OFF => las piezas
            # programadas NO salen solas (dry-run); el SPA avisa si hay programadas en cola.
            "publicar_real": config.publicar_real(),
        }
    )


def _parsear_bool_query(valor: str | None) -> bool | None:
    """Interpreta un parametro de query como bool: '1'/'true' -> True, '0'/'false' -> False.

    Devuelve None si el parametro no viene (sin filtrar). Cualquier otro valor se trata
    como no presente para no filtrar de forma sorpresiva.
    """
    if valor is None:
        return None
    bajo = valor.strip().lower()
    if bajo in ("1", "true", "si", "sí"):
        return True
    if bajo in ("0", "false", "no"):
        return False
    return None


# Tamaño de página por defecto del FEED (scroll infinito) cuando se pagina por keyset
# (`?cursor=`) sin `?limite=` explícito. Pequeño para que la primera carga sea instantánea
# y se vayan pidiendo más al hacer scroll. Configurable por entorno (sin tocar config.py).
_FEED_PAGINA_DEFECTO = 20


def _feed_pagina_defecto() -> int:
    """Tamaño de página por defecto del keyset (env `KENI_FEED_PAGINA`, fallback 20)."""
    try:
        n = int(os.environ.get("KENI_FEED_PAGINA", "") or _FEED_PAGINA_DEFECTO)
    except (TypeError, ValueError):
        return _FEED_PAGINA_DEFECTO
    return n if n >= 1 else _FEED_PAGINA_DEFECTO


async def listar(request: Request) -> Response:
    """Listado de piezas con filtros `?marca=&red=&estado=&evergreen=&origen=&excluir_origen=` y paginacion.

    Envelope RETROCOMPATIBLE: mantiene la clave `piezas` (las paginas que solo
    desestructuran esa clave siguen funcionando) y AÑADE `paginacion:{total, limite,
    desplazamiento}`. Tres modos de lectura:
      - COMPLETO (sin `?limite=` ni `?cursor=`): conjunto completo, con `total` exacto.
        Lo usan el calendario y la lista (esperan todas las filas).
      - OFFSET (`?limite=&desplazamiento=`): ventana clásica en el índice.
      - KEYSET/FEED (`?cursor=`): scroll infinito por `(creado, id)` en orden `creado DESC`.
        Inmune a inserciones nuevas (no desplaza páginas). Tamaño de página = `?limite=` o
        `KENI_FEED_PAGINA` (def 20). Devuelve `paginacion.cursor_siguiente` (clave de la
        siguiente página) mientras haya más; se OMITE en la última página.
    """
    qp = request.query_params
    marca = qp.get("marca") or None
    red = qp.get("red") or None
    estado = qp.get("estado") or None
    # `linea` = id de una etiqueta editorial de clase `vertical` (la LÍNEA de contenido):
    # filtra las piezas cuyo `contenido` padre la tiene asignada (ver `opciones`).
    linea = qp.get("linea") or None
    # REPARTO ("la lista" de ClaroSports): `?responsable=<id>` = piezas COGIDAS por ese
    # usuario; `?responsable=sin` = piezas LIBRES (por coger). El responsable vive en el
    # `contenido` PADRE (el reparto es del tema); el filtro junta hijo->padre en SQL.
    responsable_q = qp.get("responsable") or None
    responsable: str | None = None
    if responsable_q is not None:
        responsable = "" if responsable_q == "sin" else responsable_q
    # RANGO de `fecha_programada` (ISO `YYYY-MM-DD`): el CALENDARIO pide solo la ventana
    # visible (mes ± margen) en vez del conjunto completo, que el cap de 1000 truncaba en
    # silencio. Sin `desde`/`hasta` el comportamiento es el de hoy (retrocompatible). Las
    # piezas SIN fecha quedan fuera del rango (ver `_filtros_publicacion`).
    desde = qp.get("desde") or None
    hasta = qp.get("hasta") or None
    # ORIGEN del contenido padre: el clon «Portal» del feed pide `?origen=portal` (los
    # auto-producidos de fuente propia, cross-marca). Transversal al estado.
    origen = qp.get("origen") or None
    # EXCLUSIÓN por origen (lo inverso de `origen`): el FEED normal pide `?excluir_origen=portal`
    # para mantenerse independiente del canal Portal —que tiene su propia superficie—. La Lista
    # no lo pide (ve todos los orígenes, incluido portal).
    excluir_origen = qp.get("excluir_origen") or None
    # LIMPIEZA del feed: filtros sobre el `contenido` padre para barrer/conservar por lotes.
    #  - `categoria` (plan: breaking/mx/evergreen…), `tipo` (ia|galeria|fuente), `fuente` (medio).
    #  - `fase`: incompleto (en producción, candidato a borrar) | producido | programado | publicado.
    #  - `antiguedad_h`: solo lo creado hace MÁS de N horas (presets >24h/>48h/>1sem…). El corte se
    #    calcula con la hora del SERVIDOR (UTC) para no depender del reloj del cliente.
    categoria = qp.get("categoria") or None
    tipo_contenido = qp.get("tipo") or None
    fuente = qp.get("fuente") or None
    fase = qp.get("fase") or None
    creado_antes: str | None = None
    antiguedad_h = qp.get("antiguedad_h")
    if antiguedad_h:
        try:
            horas = int(antiguedad_h)
        except ValueError:
            horas = 0
        if horas > 0:
            creado_antes = iso_utc(datetime.now(UTC) - timedelta(hours=horas))
    evergreen = _parsear_bool_query(qp.get("evergreen"))
    limite, desplazamiento = paginacion_query(request)
    cursor = cursor_query(request)
    # MODO FEED (keyset/scroll infinito): se activa con `?feed=1` o en cuanto llega un `?cursor=`
    # (páginas 2+). La PRIMERA página del feed llega sin cursor (desde el inicio) pero igualmente
    # debe acotarse y devolver `cursor_siguiente`; sin esta marca caería al modo COMPLETO y traería
    # todo de golpe. Si no se pidió `?limite=`, usa el tamaño de página por defecto del feed.
    modo_feed = cursor is not None or _parsear_bool_query(qp.get("feed")) is True
    if modo_feed and limite is None:
        limite = _feed_pagina_defecto()
    # FOCO POR DEFECTO (no es restriccion): si la sesion tiene marcas preferentes y NO se pidio
    # marca explicita, el feed se ENFOCA en SUS marcas para reducir la mezcla de contexto. Es
    # siempre sobreescribible: con `?marca=` (cualquiera) se ve esa marca. El foco multi-marca
    # se empuja al SQL (`marca IN (...)`): el post-filtro en memoria previo ROMPIA el keyset
    # (paginas cortas + cursor que saltaba filas) y mentia en el `total`. Sin preferencia
    # (admin/token/sin marcas): sin cambios, ve todas las marcas.
    preferentes = permisos.marcas_preferentes(request)
    marca_efectiva: str | list[str] | None = marca
    if marca is None and preferentes is not None:
        marca_efectiva = sorted(preferentes)  # 1 o N marcas: siempre via SQL (total exacto)
    # CAP DE SERVIDOR (`KENI_LISTADO_MAX`, def 1000): ningun GET devuelve un conjunto sin
    # tope. Sin `?limite=` el modo "completo" queda acotado al cap (solo se nota con
    # universos enormes); un `?limite=` explicito mayor que el cap se recorta.
    tope = tope_listado()
    sin_limite = limite is None
    limite = tope if limite is None else min(limite, tope)
    pubs = repos.listar_piezas(
        marca=marca_efectiva, red=red, estado=estado, evergreen=evergreen, linea=linea,
        responsable=responsable, desde=desde, hasta=hasta, origen=origen,
        categoria=categoria, tipo_contenido=tipo_contenido, fuente=fuente, fase=fase,
        creado_antes=creado_antes, excluir_origen=excluir_origen,
        limite=limite, desplazamiento=desplazamiento, cursor=cursor,
    )
    total = repos.contar_piezas(
        marca=marca_efectiva, red=red, estado=estado, evergreen=evergreen, linea=linea,
        responsable=responsable, desde=desde, hasta=hasta, origen=origen,
        categoria=categoria, tipo_contenido=tipo_contenido, fuente=fuente, fase=fase,
        creado_antes=creado_antes, excluir_origen=excluir_origen,
    )
    # SEÑAL DE SIGUIENTE PÁGINA (solo modo feed/keyset, incluida la 1ª página): si la página vino
    # LLENA (tantas filas como `limite`), asumimos que puede haber más y emitimos el cursor de la
    # última fila vista (`<creado>|<id>`). Si vino corta (o vacía), es la última página y omitimos
    # el cursor. El modo OFFSET puro (sin `?feed=`/`?cursor=`) NO emite cursor (usa `total`).
    cursor_siguiente: str | None = None
    if modo_feed and limite is not None and len(pubs) >= limite and pubs:
        ultima = pubs[-1]
        cursor_siguiente = f"{ultima.get('fecha_creacion', '')}|{ultima.get('id', '')}"
    # Envelope retrocompatible: sin `?limite=` y sin truncado por el cap, se reporta como
    # antes (`limite = total`); si el cap recorto de verdad, se reporta el cap (honesto).
    limite_reportado = None if (sin_limite and not modo_feed and total <= limite) else limite
    return JSONResponse(
        {
            "piezas": [_publicacion_a_dict(p) for p in pubs],
            "paginacion": envoltura_paginacion(
                total, limite_reportado, desplazamiento, cursor_siguiente=cursor_siguiente
            ),
        }
    )


async def crear(request: Request) -> Response:
    datos = await leer_json(request)
    entrada, error = _validar_nueva(datos)
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    pub = repos.crear_pieza(
        entrada["marca"],
        entrada["red"],
        titulo=entrada["titulo"],
        contenido=entrada["contenido"],
        copy_in=entrada["copy_in"],
        estado=entrada["estado"],
        revision=entrada["revision"],
        fecha_programada=entrada["fecha_programada"],
        origen=entrada["origen"],
        imagen=entrada["imagen"],
        autor=autor_de_peticion(request),
    )
    return JSONResponse({"pieza": _publicacion_a_dict(pub)})


async def crear_lote(request: Request) -> Response:
    """Crea varias piezas de una vez. Todo o nada: si una falla, 400 y no inserta."""
    datos = await leer_json(request)
    crudas = datos.get("piezas")
    if not isinstance(crudas, list) or not crudas:
        return JSONResponse(
            {"error": "Envía una lista de piezas a crear."}, status_code=400
        )
    autor = autor_de_peticion(request) or {}
    entradas: list[dict[str, Any]] = []
    for i, cruda in enumerate(crudas, start=1):
        if not isinstance(cruda, dict):
            return JSONResponse(
                {"error": f"La publicación {i} no es válida."}, status_code=400
            )
        entrada, error = _validar_nueva(cruda)
        if error is not None:
            return JSONResponse({"error": f"Publicación {i}: {error}"}, status_code=400)
        # Atribucion por usuario (#130 Fase 1): el lote lo crea el usuario de la peticion.
        entrada["autor_id"] = autor.get("id", "")
        entrada["autor_nombre"] = autor.get("usuario", "")
        entradas.append(entrada)
    pubs = repos.crear_publicaciones(entradas)
    return JSONResponse({"piezas": [_publicacion_a_dict(p) for p in pubs]})


async def detalle(request: Request) -> Response:
    pieza_id = request.path_params["pieza_id"]
    pub = repos.obtener_pieza(pieza_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"pieza": _publicacion_a_dict(pub)})


async def actualizar(request: Request) -> Response:
    """Edicion PARCIAL: titulo/contenido/copy_in/estado/fecha_programada (404 si no existe)."""
    pieza_id = request.path_params["pieza_id"]
    # Existencia: 404 si la pieza ya no existe. Mas abajo se recarga `actual` para el reset de
    # aprobaciones. La marca NO acota nada: el equipo edita piezas de cualquier marca.
    pieza = repos.obtener_pieza(pieza_id)
    if pieza is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    datos = await leer_json(request)

    campos: dict[str, Any] = {}
    if "titulo" in datos:
        titulo = datos.get("titulo")
        if not isinstance(titulo, str):
            return JSONResponse({"error": "El título debe ser texto."}, status_code=400)
        campos["titulo"] = titulo.strip()
    if "contenido" in datos:
        contenido = datos.get("contenido")
        if not isinstance(contenido, str):
            return JSONResponse({"error": "El contenido debe ser texto."}, status_code=400)
        campos["contenido"] = contenido
    if "copy_in" in datos:
        copy_in = datos.get("copy_in")
        if not isinstance(copy_in, str):
            return JSONResponse(
                {"error": "El texto en imagen debe ser texto."}, status_code=400
            )
        campos["copy_in"] = copy_in
    if "estado" in datos:
        estado = datos.get("estado")
        if not isinstance(estado, str) or estado not in repos.ESTADOS_PIEZA:
            return JSONResponse({"error": "Estado no permitido."}, status_code=400)
        # MAQUINA DE ESTADOS: la transicion debe ser valida DESDE el estado actual (tabla
        # `_TRANSICIONES_PUT`). Mismo estado = no-op permitido (PUT idempotente).
        estado_desde = pieza.get("estado") or ESTADO_BORRADOR
        if estado != estado_desde and estado not in _TRANSICIONES_PUT.get(
            estado_desde, frozenset()
        ):
            return JSONResponse(
                {
                    "error": (
                        f"Transición de estado no permitida: de '{estado_desde}' "
                        f"a '{estado}'."
                    )
                },
                status_code=400,
            )
        campos["estado"] = estado
    if "fecha_programada" in datos:
        fecha = datos.get("fecha_programada")
        if fecha is None:
            campos["fecha_programada"] = ""
        elif isinstance(fecha, str):
            # Canon de parrilla (minutos, UTC sin offset): el UNIQUE anti-doble-reserva
            # compara el TEXT crudo; sin canon "T18:00" y "T18:00:00" no chocaban.
            fecha_norm, err_fecha = _normalizar_fecha_programada(fecha.strip())
            if err_fecha is not None:
                return JSONResponse({"error": err_fecha}, status_code=400)
            campos["fecha_programada"] = fecha_norm
        else:
            return JSONResponse(
                {"error": "La fecha programada debe ser texto o nula."}, status_code=400
            )
        # REPROGRAMAR (mover la fecha a una DISTINTA) resetea el claim de preparación, igual que
        # `_encolar_en_hueco_libre`: hay que limpiar `preparado_en` para que el barrido NO trate la
        # pieza como "ya preparada" y la (re)publique a la NUEVA hora —con KENI_PUBLICAR_REAL on, un
        # arrastre del calendario sin esto perdería el post en silencio—. Solo en el CAMBIO real (el
        # no-op de misma fecha conserva el claim). Una pieza PUBLICADA con cambio de fecha se rechaza
        # con 409 más abajo (terminalidad), antes de tocar nada: este reset no la alcanza.
        if campos["fecha_programada"] != (pieza.get("fecha_programada") or ""):
            campos["preparado_en"] = ""
    if "imagen" in datos:
        imagen = datos.get("imagen")
        if not isinstance(imagen, str):
            return JSONResponse({"error": "La imagen debe ser texto."}, status_code=400)
        campos["imagen"] = imagen.strip()
    if "foto" in datos:
        foto = datos.get("foto")
        if not isinstance(foto, str):
            return JSONResponse({"error": "La foto debe ser texto."}, status_code=400)
        campos["foto"] = foto.strip()
    if "evergreen" in datos:
        evergreen = datos.get("evergreen")
        if not isinstance(evergreen, bool):
            return JSONResponse({"error": "El campo evergreen debe ser verdadero o falso."}, status_code=400)
        campos["evergreen"] = evergreen
    if "placa_oculta" in datos:
        placa_oculta = datos.get("placa_oculta")
        if not isinstance(placa_oculta, bool):
            return JSONResponse(
                {"error": "El campo placa_oculta debe ser verdadero o falso."}, status_code=400
            )
        campos["placa_oculta"] = placa_oculta
    if "plantilla_diseno_id" in datos:
        plantilla_diseno_id = datos.get("plantilla_diseno_id")
        if not isinstance(plantilla_diseno_id, str):
            return JSONResponse({"error": "La plantilla debe ser texto."}, status_code=400)
        campos["plantilla_diseno_id"] = plantilla_diseno_id.strip()
    if "foto_encuadre" in datos:
        foto_encuadre = datos.get("foto_encuadre")
        if not isinstance(foto_encuadre, str):
            return JSONResponse(
                {"error": "El reencuadre de la foto debe ser texto."}, status_code=400
            )
        campos["foto_encuadre"] = foto_encuadre.strip()
    if "fotos" in datos:
        # COLLAGE: JSON array `[{objeto,foco,zoom}, …]` (una por hueco), serializado por el editor.
        fotos = datos.get("fotos")
        if not isinstance(fotos, str):
            return JSONResponse(
                {"error": "Las fotos del collage deben ser texto (JSON)."}, status_code=400
            )
        campos["fotos"] = fotos.strip()
    if "carrusel" in datos:
        # CARRUSEL: slides extra en crudo, JSON `[{tipo:"imagen"|"video",objeto}, …]` serializado
        # por el editor (mismo trato que `fotos`: el backend lo persiste como texto).
        carrusel = datos.get("carrusel")
        if not isinstance(carrusel, str):
            return JSONResponse(
                {"error": "Los slides del carrusel deben ser texto (JSON)."}, status_code=400
            )
        campos["carrusel"] = carrusel.strip()
    if "espejo" in datos:
        # ESPEJO entre redes (vive en el padre: es de la idea). El editor lo togglea desde
        # cualquier pieza hermana; OFF = cada red se edita por separado.
        espejo = datos.get("espejo")
        if not isinstance(espejo, bool):
            return JSONResponse(
                {"error": "El campo espejo debe ser verdadero o falso."}, status_code=400
            )
        campos["espejo"] = espejo

    # PUBLICADO ES TERMINAL para la fecha: el post de una pieza publicada ya salió en su
    # momento; mover su `fecha_programada` reubicaría su píldora verde y MENTIRÍA sobre cuándo
    # salió. La máquina de estados (`_TRANSICIONES_PUT`) ya congela el `estado`, pero NO la
    # fecha; esto cierra ese hueco. Se permite el NO-OP (misma fecha ya normalizada) para no
    # romper guardados inocuos; cualquier CAMBIO real se rechaza ANTES de tocar nada (sin
    # disparar el reset de aprobaciones ni el espejo, que vienen después).
    if (
        (pieza.get("estado") or "") == ESTADO_PUBLICADO
        and "fecha_programada" in campos
        and campos["fecha_programada"] != (pieza.get("fecha_programada") or "")
    ):
        return JSONResponse(
            {"error": "Una pieza ya publicada es terminal: su fecha no se cambia."},
            status_code=409,
        )

    if not campos:
        return JSONResponse(
            {
                "error": (
                    "No hay nada que actualizar (título, contenido, texto en imagen, "
                    "estado, fecha, imagen o evergreen)."
                )
            },
            status_code=400,
        )

    # RESET DE APROBACIONES AL EDITAR: editar el CONTENIDO de una pieza que ya acumula
    # aprobaciones las invalida (como reescribir un PR aprobado). La pieza vuelve a `borrador` con
    # la cadena LIMPIA; reentrará sola a revisión cuando el editor la reenvíe, exigiendo OK nuevos.
    # El front avisa con un popup antes de tocar nada. Solo cuando hay aprobaciones REALES que
    # perder (aprobada/programada, o en revisión con un OK humano), para no churnar lo demás. No
    # aplica si la propia petición fija `estado` (el flujo lo está moviendo a propósito).
    actual = repos.obtener_pieza(pieza_id)
    if actual is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    estado_actual = actual.get("estado") or ""
    resetear = _pierde_aprobaciones(actual, campos)
    if resetear:
        campos.update(_RESET_APROBACIONES)
    # Mantén en sync las flags de readiness (falta copy/imagen) con el contenido editado, para
    # que la lista del feed no quede stale tras añadir la foto/copy (el espejo hace lo mismo).
    _inyectar_flags_falta(actual, campos)

    # CAS de estado: si la peticion mueve el estado (o el reset lo fuerza), la escritura solo
    # aplica si la pieza SIGUE en el estado desde el que se valido la transicion. Cierra el
    # TOCTOU del PUT (otro flujo —aprobacion, programador— pudo moverla entre lectura y
    # escritura, y la transicion validada dejaria de ser valida).
    estado_esperado: str | None = None
    if "estado" in campos:
        estado_esperado = estado_actual if resetear else (pieza.get("estado") or ESTADO_BORRADOR)
    try:
        pub = repos.actualizar_pieza(
            pieza_id, campos, estado_esperado=estado_esperado
        )
    except IntegrityError:
        # Backstop de doble-reserva de parrilla (índice parcial `idx_parrilla_slot_uniq`): la
        # edición dejaría dos piezas programadas en el mismo (red, fecha). 409 accionable.
        return JSONResponse(
            {"error": "Ya hay una publicación programada en esa red y fecha; elige otra hora."},
            status_code=409,
        )
    if pub is None:
        if repos.obtener_pieza(pieza_id) is None:
            return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
        # Existe pero el CAS no aplico: otro flujo movio el estado entre lectura y escritura.
        return JSONResponse(
            {"error": "La publicación cambió de estado mientras editabas; recarga e intenta de nuevo."},
            status_code=409,
        )
    if resetear:
        # Limpia la cadena (borra todos los niveles): las aprobaciones previas dejan de existir.
        _limpiar_cadena(pieza_id)
    # ESPEJO entre redes (default ON): los campos de contenido editados se replican a las
    # redes hermanas de la idea, con su mismo reset de aprobaciones si lo necesitan.
    _propagar_espejo(pub, campos)
    return JSONResponse({"pieza": _publicacion_a_dict(pub)})


async def borrar(request: Request) -> Response:
    pieza_id = request.path_params["pieza_id"]
    pub = repos.obtener_pieza(pieza_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    if not repos.borrar_pieza(pieza_id):
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Publicación borrada."})


# Tope de ids por peticion batch (cadenas / borrar-lote): defensivo, el SPA manda como
# mucho una pagina de feed o la seleccion visible de la lista.
_MAX_IDS_LOTE = 200


def _ids_de_lote(crudos: Any) -> list[str] | None:
    """Repara una lista de ids (strings no vacios, sin duplicados, con tope). None si invalida."""
    if not isinstance(crudos, list):
        return None
    ids = list(dict.fromkeys(i.strip() for i in crudos if isinstance(i, str) and i.strip()))
    if not ids:
        return None
    return ids[:_MAX_IDS_LOTE]


async def borrar_lote(request: Request) -> Response:
    """Borra VARIAS piezas de una vez: `POST /api/piezas/borrar-lote {ids}`.

    Sustituye el patron del SPA de "N DELETEs en paralelo" (un solo round-trip). Itera la
    misma funcion de borrado individual (`repos.borrar_pieza`); las ids inexistentes
    no abortan el resto: se reportan en `fallos`. -> `{borradas, fallos}` | 400.
    """
    datos = await leer_json(request)
    ids = _ids_de_lote(datos.get("ids"))
    if ids is None:
        return JSONResponse(
            {"error": "Envía la lista de ids de piezas a borrar."}, status_code=400
        )
    borradas = 0
    fallos: list[str] = []
    for pieza_id in ids:
        if repos.borrar_pieza(pieza_id):
            borradas += 1
        else:
            fallos.append(pieza_id)
    return JSONResponse({"borradas": borradas, "fallos": fallos})


async def cadenas_lote(request: Request) -> Response:
    """Cadenas de aprobacion de VARIAS piezas en una llamada (batch del feed).

    `GET /api/piezas/cadenas?ids=a,b,c` -> `{cadenas: {id: cadena}}`. Elimina el
    N+1 del feed (antes: un GET /aprobacion por pieza visible). SIEMPRE devuelve una
    entrada por id pedida: para una pieza inexistente la cadena sale vacia
    (`estado="sin_cadena"`), de modo que el cliente nunca reitere ids "que faltan".
    El endpoint individual (`GET /api/plataformas/{id}/aprobacion`) sigue intacto.
    """
    from .. import colaboracion as api_colaboracion

    crudo = request.query_params.get("ids") or ""
    ids = _ids_de_lote(crudo.split(","))
    if ids is None:
        return JSONResponse(
            {"error": "Indica las ids de piezas (?ids=a,b,c)."}, status_code=400
        )
    cadenas = {pid: api_colaboracion.cadena_publica(pid) for pid in ids}
    return JSONResponse({"cadenas": cadenas})


async def clonar(request: Request) -> Response:
    """Clona el CONTENIDO de una pieza a OTRA RED de la misma idea (no crea otra idea).

    `POST /api/piezas/{id}/clonar` con `{red}`: copia copy/copy-in/foto/collage/
    plantilla (`_CAMPOS_ESPEJO`) a la pieza hermana de esa red —sobrescribiéndola, con el
    mismo reset de aprobaciones que una edición— o la CREA como borrador si la idea aún no
    salía en esa red. La pieza destino queda colgada del MISMO `contenido` padre (no crea otra
    idea). -> `{pieza}` (la pieza destino)
    | 400 (red inválida / sin padre) | 404 | 409 (la hermana ya está publicada).
    """
    pieza_id = request.path_params["pieza_id"]
    original = repos.obtener_pieza(pieza_id)
    if original is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    datos = await leer_json(request)
    red = datos.get("red")
    if not isinstance(red, str) or not redes.es_red(red):
        return JSONResponse({"error": "Red no permitida."}, status_code=400)
    if red == original["red"]:
        return JSONResponse(
            {"error": "La pieza ya está en esa red; elige otra red destino."}, status_code=400
        )
    publicacion_id = original.get("publicacion_id") or ""
    if not publicacion_id:
        return JSONResponse(
            {"error": "Esta pieza no tiene idea padre: no se puede clonar entre redes."},
            status_code=400,
        )

    campos: dict[str, Any] = {clave: original.get(clave) for clave in _CAMPOS_ESPEJO}
    hermanas = [
        p for p in repos.listar_piezas_fila(publicacion_id) if (p.get("red") or "") == red
    ]
    if hermanas:
        destino = repos.obtener_pieza(hermanas[0]["id"])
        if destino is None:
            return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
        if (destino.get("estado") or "") == ESTADO_PUBLICADO:
            return JSONResponse(
                {"error": "La pieza de esa red ya está publicada; no se sobrescribe."},
                status_code=409,
            )
        resetear = _pierde_aprobaciones(destino, campos)
        if resetear:
            campos.update(_RESET_APROBACIONES)
        pub = repos.actualizar_pieza(destino["id"], campos)
        if pub is None:
            return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
        if resetear:
            _limpiar_cadena(destino["id"])
        return JSONResponse({"pieza": _publicacion_a_dict(pub)})

    # La idea no salía en esa red: nace la pieza (borrador) con el contenido clonado. El
    # checklist (`falta_copy`/`falta_imagen`) se autodeduce del copy/imagen clonados.
    plat = repos.crear_pieza_fila(
        publicacion_id=publicacion_id,
        red=red,
        marca=original.get("marca") or None,
        copy=original.get("contenido") or "",
        copy_in=original.get("copy_in") or "",
        imagen=original.get("imagen") or "",
        imagen_fuente=original.get("imagen_fuente") or "",
        foto=original.get("foto") or "",
        fotos=original.get("fotos") or "",
        carrusel=original.get("carrusel") or "",
        plantilla_diseno_id=original.get("plantilla_diseno_id") or "",
        foto_encuadre=original.get("foto_encuadre") or "",
        placa_oculta=bool(original.get("placa_oculta")),
    )
    pub = repos.obtener_pieza(plat["id"])
    if pub is None:
        return JSONResponse({"error": "No se pudo clonar la pieza."}, status_code=500)
    return JSONResponse({"pieza": _publicacion_a_dict(pub)})


async def programar_metricool(request: Request) -> Response:
    """Programa/previsualiza la pieza en Metricool a demanda (botón de la UI).

    `POST /api/piezas/{id}/metricool`. Respeta el gate `KENI_PUBLICAR_REAL`:
    con el flag OFF (default) es DRY-RUN (previsualiza el cuerpo que se enviaría,
    NO publica ni persiste); con ON publica de verdad, persiste `id_post_metricool`
    y pasa la pieza a `publicado`. -> `{resultado, pieza}` | 400 | 404.
    """
    # Import local: `programador` es infra (no es router de ninguna app); el camino
    # real solo se activa con el gate. Mantiene el módulo de API sin acoplarse a él.
    from ... import programador

    pieza_id = request.path_params["pieza_id"]
    pub = repos.obtener_pieza(pieza_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    resultado = programador.programar_pieza_metricool(pub)
    if not resultado.get("ok"):
        return JSONResponse(
            {"error": resultado.get("motivo") or "No se pudo programar en Metricool."},
            status_code=400,
        )
    actualizada = repos.obtener_pieza(pieza_id)
    return JSONResponse(
        {
            "resultado": resultado,
            "pieza": _publicacion_a_dict(actualizada) if actualizada else None,
        }
    )
