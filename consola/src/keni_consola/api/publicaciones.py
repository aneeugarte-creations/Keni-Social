"""API Publicaciones: CRUD de posts a gestionar (titulo, marca, red, estado, fechas).

El SPA gestiona el ciclo de vida de cada pieza: nace como borrador (a mano o desde
una generacion por red de Skills), se edita, se aprueba, se programa y se publica.
Persistencia en SQLite (`consola.db`, via `consola.db`). Nada se publica de verdad
aqui: solo se administra el estado editorial.

SEGURIDAD / VALIDACION (no duplica logica; reusa las fuentes de verdad):
  - `marca` SOLO puede ser una marca del catalogo unico (`consola.marcas`), por
    su `id` canonico (slug-guion), el mismo `value` que usa la generacion de copy.
  - `red` SOLO puede ser una red canonica (`consola.redes`).
  - `estado` SOLO puede ser uno de `repos.ESTADOS_PUBLICACION`.
  - SQL parametrizado en `consola.db`; los errores salen como JSON en espanol, sin
    tracebacks crudos.

`marca_nombre` y `red_nombre` se resuelven EN SERVIDOR (la UI solo muestra nombres).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, permisos, redes, repos
import os

from .._http_json import (
    cursor_query,
    envoltura_paginacion,
    leer_json,
    paginacion_query,
    tope_listado,
)
from ..dominio import cadencia as dom_cadencia
from ..dominio import colaboracion
from ..dominio.publicaciones import flags_falta_de_contenido, publicacion_a_dict
from ..estados import (
    ESTADO_APROBADO,
    ESTADO_BORRADOR,
    ESTADO_EN_REVISION,
    ESTADO_PROGRAMADO,
    ESTADO_PUBLICADO,
)
from ..motor_db import IntegrityError
from ..tiempo import iso_utc
from ..seguridad import autor_de_peticion
from . import franjas as api_franjas

# Nombres legibles de los estados (para poblar selects de la UI), en orden de flujo.
# `en_revision` (cola de aprobacion de equipo, #9) se intercala tras el borrador.
_ESTADO_NOMBRE: dict[str, str] = {
    "borrador": "Borrador",
    "en_revision": "En revisión",
    "aprobado": "Aprobado",
    "programado": "Programado",
    "publicado": "Publicado",
}

# Marcas validas como destino de copy: TODAS las del catalogo unico. value
# interno = id canonico (slug-guion); etiqueta visible = nombre humano con acentos.
_MARCAS: tuple[tuple[str, str], ...] = tuple(marcas.opciones())
_MARCAS_IDS = {m[0] for m in _MARCAS}


# Alias local para los handlers de este modulo. La serializacion vive en el dominio
# (`dominio.publicaciones.publicacion_a_dict`): asi `api/skills.py` la consume desde un
# sitio comun y publico, sin importar un simbolo privado de este handler (H6/N7).
_publicacion_a_dict = publicacion_a_dict


# MAQUINA DE ESTADOS del PUT generico (#estados): transiciones validas desde cada estado.
# Antes el PUT aceptaba CUALQUIER estado del catalogo sin mirar el actual, bypasseando los
# gates de los endpoints de flujo (enviar-a-revision/aprobar/encolar). Politica:
#   - AVANZAR en el flujo (borrador -> en_revision -> aprobado -> programado -> publicado)
#     se permite TAMBIEN a saltos: el operador puede marcar "ya lo publique a mano" sin
#     recorrer estados intermedios (es el uso real de la UI y del MCP).
#   - RETROCEDER solo a `borrador` (rechazo/reset de la pieza) o `programado -> aprobado`
#     (desprogramar). Otros retrocesos pasan por los endpoints de flujo.
#   - `publicado` es TERMINAL: una pieza ya publicada no se mueve por el PUT (evita
#     re-programar/duplicar un post que ya salio; el camino legitimo es duplicar/reciclar).
_TRANSICIONES_PUT: dict[str, frozenset[str]] = {
    ESTADO_BORRADOR: frozenset({ESTADO_EN_REVISION, ESTADO_APROBADO, ESTADO_PROGRAMADO, ESTADO_PUBLICADO}),
    ESTADO_EN_REVISION: frozenset({ESTADO_BORRADOR, ESTADO_APROBADO, ESTADO_PROGRAMADO, ESTADO_PUBLICADO}),
    ESTADO_APROBADO: frozenset({ESTADO_BORRADOR, ESTADO_PROGRAMADO, ESTADO_PUBLICADO}),
    ESTADO_PROGRAMADO: frozenset({ESTADO_BORRADOR, ESTADO_APROBADO, ESTADO_PUBLICADO}),
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
    # franjas/cadencias y el picker de la UI): truncamos el sufijo ":SS".
    return iso_utc(dt)[:16], None


def _validar_nueva(datos: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Valida el cuerpo de una publicacion nueva.

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
    if not isinstance(estado, str) or estado not in repos.ESTADOS_PUBLICACION:
        return None, "Estado no permitido."

    titulo = datos.get("titulo", "")
    contenido = datos.get("contenido", "")
    copy_in = datos.get("copy_in", "")
    veredicto = datos.get("veredicto", "")
    fecha_programada = datos.get("fecha_programada", "")
    origen = datos.get("origen", "")
    imagen = datos.get("imagen", "")
    for valor, etiqueta in (
        (titulo, "El título"),
        (contenido, "El contenido"),
        (copy_in, "El texto en imagen"),
        (veredicto, "El veredicto"),
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
            "veredicto": veredicto,
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
    from .. import config

    return JSONResponse(
        {
            "redes": redes.opciones(),
            "estados": [{"id": e, "nombre": _ESTADO_NOMBRE[e]} for e in repos.ESTADOS_PUBLICACION],
            "marcas": [{"id": mid, "nombre": nombre} for mid, nombre in _MARCAS],
            "lineas": lineas,
            # Gate maestro de publicacion real (KENI_PUBLICAR_REAL). OFF => las piezas
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
    """Listado de publicaciones con filtros `?marca=&red=&estado=&evergreen=` y paginacion.

    Envelope RETROCOMPATIBLE: mantiene la clave `publicaciones` (las paginas que solo
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
    pubs = repos.listar_publicaciones(
        marca=marca_efectiva, red=red, estado=estado, evergreen=evergreen, linea=linea,
        limite=limite, desplazamiento=desplazamiento, cursor=cursor,
    )
    total = repos.contar_publicaciones(
        marca=marca_efectiva, red=red, estado=estado, evergreen=evergreen, linea=linea
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
            "publicaciones": [_publicacion_a_dict(p) for p in pubs],
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
    pub = repos.crear_publicacion(
        entrada["marca"],
        entrada["red"],
        titulo=entrada["titulo"],
        contenido=entrada["contenido"],
        copy_in=entrada["copy_in"],
        estado=entrada["estado"],
        veredicto=entrada["veredicto"],
        fecha_programada=entrada["fecha_programada"],
        origen=entrada["origen"],
        imagen=entrada["imagen"],
        autor=autor_de_peticion(request),
    )
    return JSONResponse({"publicacion": _publicacion_a_dict(pub)})


async def crear_lote(request: Request) -> Response:
    """Crea varias publicaciones de una vez. Todo o nada: si una falla, 400 y no inserta."""
    datos = await leer_json(request)
    crudas = datos.get("publicaciones")
    if not isinstance(crudas, list) or not crudas:
        return JSONResponse(
            {"error": "Envía una lista de publicaciones a crear."}, status_code=400
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
    return JSONResponse({"publicaciones": [_publicacion_a_dict(p) for p in pubs]})


async def detalle(request: Request) -> Response:
    publicacion_id = request.path_params["publicacion_id"]
    pub = repos.obtener_publicacion(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"publicacion": _publicacion_a_dict(pub)})


# Campos de CONTENIDO que el espejo propaga entre redes hermanas (la "receta" completa de la
# pieza: copy + copy-in + foto/collage + plantilla). Estado, fechas y flags NO se espejan.
# También es la lista de campos cuyo cambio invalida aprobaciones (junto con `titulo`).
_CAMPOS_ESPEJO: tuple[str, ...] = (
    "contenido", "copy_in", "imagen", "foto", "fotos", "carrusel",
    "plantilla_diseno_id", "foto_encuadre", "placa_oculta",
)

# Campos cuyo cambio altera las flags de readiness DERIVADAS del contenido (copy/foto): si la
# edición toca alguno, hay que recalcular `falta_copy`/`falta_imagen`.
_CAMPOS_CONTENIDO_FALTA: tuple[str, ...] = ("contenido", "foto", "imagen")


def _inyectar_flags_falta(actual: dict[str, Any], campos: dict[str, Any]) -> None:
    """Si la edición toca el contenido (copy/foto/imagen), recalcula e INYECTA en `campos` las
    flags `falta_copy`/`falta_imagen` del estado RESULTANTE (fila + edición), para que la LISTA
    del feed (que lee las flags ALMACENADAS) refleje el cambio sin abrir cada pieza —incluidas
    las redes ESPEJO—. NO toca las flags de aprobación/publicación (eso no se espeja)."""
    if not any(k in campos for k in _CAMPOS_CONTENIDO_FALTA):
        return
    campos.update(flags_falta_de_contenido({**actual, **campos}))

# Reset al perder aprobaciones: la pieza vuelve a borrador con la revisión limpia (reentrará
# sola a revisión cuando se reenvíe, exigiendo OK nuevos).
_RESET_APROBACIONES: dict[str, Any] = {
    "estado": "borrador",
    "revisor_id": "",
    "revisor_nombre": "",
    "revisado_en": "",
    "enviado_a_revision_en": "",
    "fecha_programada": "",
}


def _pierde_aprobaciones(actual: dict[str, Any], campos: dict[str, Any]) -> bool:
    """True si aplicar `campos` a la pieza `actual` invalida aprobaciones YA dadas.

    Editar el CONTENIDO de una pieza que acumula aprobaciones las invalida (como reescribir
    un PR aprobado). Solo cuando hay aprobaciones REALES que perder (aprobada/programada, o
    en revisión con un OK humano). No aplica si la propia petición fija `estado` (el flujo
    la está moviendo a propósito).
    """
    cambia_contenido = any(
        clave in campos and campos[clave] != actual.get(clave)
        for clave in ("titulo", *_CAMPOS_ESPEJO)
    )
    if not cambia_contenido or "estado" in campos:
        return False
    estado_actual = actual.get("estado") or ""
    if estado_actual in (ESTADO_APROBADO, ESTADO_PROGRAMADO):
        return True
    if estado_actual == ESTADO_EN_REVISION:
        cadena = repos.listar_aprobaciones(actual["id"])
        return colaboracion.contar_aprobaciones_humanas(cadena) > 0
    return False


def _limpiar_cadena(publicacion_id: str) -> None:
    """Recrea la cadena de aprobación VACÍA de la pieza (las aprobaciones previas se pierden)."""
    plat = repos.obtener_contenido_plataforma(publicacion_id)
    repos.crear_cadena_aprobacion(
        plataforma_id=publicacion_id,
        contenido_id=(plat or {}).get("contenido_id", "") or "",
        etiquetas=[],
    )


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
    contenido_id = pub.get("contenido_id") or ""
    if not contenido_id:
        return
    for plat in repos.listar_contenido_plataforma(contenido_id):
        if plat["id"] == pub["id"]:
            continue
        hermana = repos.obtener_publicacion(plat["id"])
        if hermana is None or (hermana.get("estado") or "") == ESTADO_PUBLICADO:
            continue
        campos_h: dict[str, Any] = dict(espejo_campos)
        resetear = _pierde_aprobaciones(hermana, campos_h)
        if resetear:
            campos_h.update(_RESET_APROBACIONES)
        # El estado de readiness (falta copy/imagen) SÍ se actualiza en el espejo aunque la
        # aprobación no: la hermana hereda el contenido, así que sus flags reflejan lo heredado.
        _inyectar_flags_falta(hermana, campos_h)
        if repos.actualizar_publicacion(plat["id"], campos_h) is None:
            continue  # borrada en paralelo: nada que espejar
        if resetear:
            _limpiar_cadena(plat["id"])


async def actualizar(request: Request) -> Response:
    """Edicion PARCIAL: titulo/contenido/copy_in/estado/fecha_programada (404 si no existe)."""
    publicacion_id = request.path_params["publicacion_id"]
    # Existencia: 404 si la pieza ya no existe. Mas abajo se recarga `actual` para el reset de
    # aprobaciones. La marca NO acota nada: el equipo edita piezas de cualquier marca.
    pieza = repos.obtener_publicacion(publicacion_id)
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
        if not isinstance(estado, str) or estado not in repos.ESTADOS_PUBLICACION:
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
        # `null` = limpiar la fecha (la pieza deja de estar programada). El SPA manda null cuando
        # el estado no es "programado"; tratarlo como "" en vez de rechazarlo (antes daba 400 al
        # guardar cualquier pieza no programada).
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
    actual = repos.obtener_publicacion(publicacion_id)
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
        pub = repos.actualizar_publicacion(
            publicacion_id, campos, estado_esperado=estado_esperado
        )
    except IntegrityError:
        # Backstop de doble-reserva de parrilla (índice parcial `idx_parrilla_slot_uniq`): la
        # edición dejaría dos piezas programadas en el mismo (red, fecha). 409 accionable.
        return JSONResponse(
            {"error": "Ya hay una publicación programada en esa red y fecha; elige otra hora."},
            status_code=409,
        )
    if pub is None:
        if repos.obtener_publicacion(publicacion_id) is None:
            return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
        # Existe pero el CAS no aplico: otro flujo movio el estado entre lectura y escritura.
        return JSONResponse(
            {"error": "La publicación cambió de estado mientras editabas; recarga e intenta de nuevo."},
            status_code=409,
        )
    if resetear:
        # Limpia la cadena (borra todos los niveles): las aprobaciones previas dejan de existir.
        _limpiar_cadena(publicacion_id)
    # ESPEJO entre redes (default ON): los campos de contenido editados se replican a las
    # redes hermanas de la idea, con su mismo reset de aprobaciones si lo necesitan.
    _propagar_espejo(pub, campos)
    return JSONResponse({"publicacion": _publicacion_a_dict(pub)})


async def borrar(request: Request) -> Response:
    publicacion_id = request.path_params["publicacion_id"]
    pub = repos.obtener_publicacion(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    if not repos.borrar_publicacion(publicacion_id):
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Publicación borrada."})


# Tope de ids por peticion batch (cadenas / borrar-lote): defensivo, el SPA manda como
# mucho una pagina de feed o la seleccion visible de la lista.
_MAX_IDS_LOTE = 200


def _ids_de_lote(crudos: Any) -> list[str] | None:
    """Sanea una lista de ids (strings no vacios, sin duplicados, con tope). None si invalida."""
    if not isinstance(crudos, list):
        return None
    ids = list(dict.fromkeys(i.strip() for i in crudos if isinstance(i, str) and i.strip()))
    if not ids:
        return None
    return ids[:_MAX_IDS_LOTE]


async def borrar_lote(request: Request) -> Response:
    """Borra VARIAS publicaciones de una vez: `POST /api/publicaciones/borrar-lote {ids}`.

    Sustituye el patron del SPA de "N DELETEs en paralelo" (un solo round-trip). Itera la
    misma funcion de borrado individual (`repos.borrar_publicacion`); las ids inexistentes
    no abortan el resto: se reportan en `fallos`. -> `{borradas, fallos}` | 400.
    """
    datos = await leer_json(request)
    ids = _ids_de_lote(datos.get("ids"))
    if ids is None:
        return JSONResponse(
            {"error": "Envía la lista de ids de publicaciones a borrar."}, status_code=400
        )
    borradas = 0
    fallos: list[str] = []
    for publicacion_id in ids:
        if repos.borrar_publicacion(publicacion_id):
            borradas += 1
        else:
            fallos.append(publicacion_id)
    return JSONResponse({"borradas": borradas, "fallos": fallos})


async def cadenas_lote(request: Request) -> Response:
    """Cadenas de aprobacion de VARIAS piezas en una llamada (batch del feed).

    `GET /api/publicaciones/cadenas?ids=a,b,c` -> `{cadenas: {id: cadena}}`. Elimina el
    N+1 del feed (antes: un GET /aprobacion por pieza visible). SIEMPRE devuelve una
    entrada por id pedida: para una pieza inexistente la cadena sale vacia
    (`estado="sin_cadena"`), de modo que el cliente nunca reitere ids "que faltan".
    El endpoint individual (`GET /api/plataformas/{id}/aprobacion`) sigue intacto.
    """
    from . import colaboracion as api_colaboracion

    crudo = request.query_params.get("ids") or ""
    ids = _ids_de_lote(crudo.split(","))
    if ids is None:
        return JSONResponse(
            {"error": "Indica las ids de publicaciones (?ids=a,b,c)."}, status_code=400
        )
    cadenas = {pid: api_colaboracion.cadena_publica(pid) for pid in ids}
    return JSONResponse({"cadenas": cadenas})


def categoria_de_pieza(pub: dict[str, Any]) -> str:
    """Categoría del PLAN con la que programa una pieza. Best-effort ('' si no aplica).

    - 'evergreen' si su tema es de flujo evergreen (reciclaje),
    - la categoría de la HISTORIA de la que nació ('breaking' si lo era) en el resto,
    - '' para piezas manuales sin historia: usan las franjas genéricas.
    """
    try:
        plat = repos.obtener_contenido_plataforma(pub.get("id") or "") or {}
        cid = str(plat.get("contenido_id") or "")
        if not cid:
            return ""
        item = repos.obtener_contenido(cid) or {}
        # La categoría vive EN el contenido desde que se persiste al crear (promoción,
        # usar historia, reciclaje). Los fallbacks cubren filas anteriores a la columna.
        propia = str(item.get("categoria") or "").strip().lower()
        if propia:
            return propia
        if (item.get("flujo") or "") == "evergreen":
            return "evergreen"
        return repos.categoria_promovida_de_contenido(cid)
    except Exception:  # noqa: BLE001 -- la categoría es refinamiento; sin ella, genéricas
        return ""


# Margen (min) con el que se programa una pieza BREAKING: ya, pero con aire para el último
# vistazo humano en la parrilla. Búsqueda acotada de minuto libre por la unicidad de slot.
_BREAKING_MARGEN_MIN = 2
_BREAKING_BUSQUEDA_MIN = 240


def calcular_hueco_para(
    pub: dict[str, Any], ahora: datetime | None = None
) -> str | None:
    """Calcula el proximo hueco futuro para `pub` segun cadencias/franjas configuradas.

    Devuelve el datetime ISO ('YYYY-MM-DDTHH:MM') del hueco, o None si no hay NINGUNA
    cadencia/franja aplicable a la (marca, red) de la publicacion. `ahora` se puede inyectar
    para tests; por defecto es `datetime.now()`. Los huecos ya ocupados por OTRAS
    publicaciones `programado` de la MISMA (marca, red) se evitan — espejo del indice de
    unicidad de slot (`idx_parrilla_slot_uniq`, por marca+red+fecha): las piezas de un MISMO
    tema en redes distintas salen a la MISMA hora.

    CATEGORÍA del plan: una pieza BREAKING no espera franja (se programa a ahora+margen, en
    el primer minuto libre); el resto usa PRIMERO los horarios de SU línea (franjas con su
    categoría — ganan a cualquier cadencia), después la cadencia de la (marca, red) y por
    último las franjas genéricas.
    """
    if ahora is None:
        ahora = datetime.now()
    programadas = repos.listar_publicaciones(estado="programado")
    ocupados_mr = {
        otra["fecha_programada"]
        for otra in programadas
        if otra["id"] != pub["id"]
        and otra["fecha_programada"]
        and otra["marca"] == pub["marca"]
        and otra["red"] == pub["red"]
    }
    categoria = categoria_de_pieza(pub)
    # 0) BREAKING: la última hora no espera al siguiente hueco del plan — sale YA (con un
    # margen corto), en el primer minuto libre de su (marca, red).
    if categoria == "breaking":
        cand = (ahora + timedelta(minutes=_BREAKING_MARGEN_MIN)).replace(second=0, microsecond=0)
        for _ in range(_BREAKING_BUSQUEDA_MIN):
            clave = cand.strftime("%Y-%m-%dT%H:%M")
            if clave not in ocupados_mr:
                return clave
            cand += timedelta(minutes=1)
        return None  # parrilla patológicamente saturada
    # 1) HORARIOS DE LA LÍNEA (preferentes): si la pieza tiene categoría y su línea tiene
    # franjas propias, ESOS son sus horarios — una cadencia general no debe pisarlos (una
    # cadencia "todas las redes" creada a mano mandó una pieza nacional a las 3 a. m.).
    aplican = api_franjas.franjas_aplicables(
        repos.listar_franjas(), pub["marca"], pub["red"], categoria
    )
    de_linea = bool(categoria) and any(
        (f.get("categoria") or "") == categoria for f in aplican
    )
    if de_linea:
        return api_franjas.proximo_hueco(aplican, ahora, ocupados_mr)
    # 2) CADENCIA por margen: para piezas sin línea (o líneas sin horario propio).
    cad = dom_cadencia.cadencia_aplicable(repos.listar_cadencias(), pub["marca"], pub["red"])
    if cad is not None:
        return dom_cadencia.proximo_hueco_cadencia(cad, ahora, ocupados_mr)
    # 3) Franjas-caja genéricas.
    if not aplican:
        return None
    return api_franjas.proximo_hueco(aplican, ahora, ocupados_mr)


async def encolar(request: Request) -> Response:
    """Programa la publicacion en el proximo hueco futuro de sus franjas.

    `POST /api/publicaciones/{id}/encolar` -> `{publicacion}` (estado=programado y
    fecha_programada puesta al hueco). 404 si no existe; 400 si no hay franjas
    aplicables a su (marca, red).
    """
    publicacion_id = request.path_params["publicacion_id"]
    pub = repos.obtener_publicacion(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    actualizada, hubo_hueco = _encolar_en_hueco_libre(pub)
    if not hubo_hueco:
        return JSONResponse(
            {"error": "No hay cadencia ni franjas configuradas para esta marca/red."},
            status_code=400,
        )
    if actualizada is None:  # carrera: borrada entre el obtener y el actualizar
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"publicacion": _publicacion_a_dict(actualizada)})


# Tope de reintentos al programar en un hueco: cada choque significa que OTRA pieza tomo ese
# slot entre el calculo y la escritura; recalculamos el siguiente hueco libre y reintentamos.
_MAX_REINTENTOS_HUECO = 8


def _encolar_en_hueco_libre(
    pub: dict[str, Any], ahora: datetime | None = None
) -> tuple[dict[str, Any] | None, bool]:
    """Programa `pub` en el próximo hueco libre, con BACKSTOP de unicidad + reintento.

    Devuelve `(publicacion_actualizada | None, hubo_hueco)`. El índice único parcial
    `idx_parrilla_slot_uniq` impide que dos piezas queden programadas en el mismo (red, fecha):
    si entre el cálculo del hueco y la escritura otra pieza ya tomó ese slot, el UPDATE lanza
    una IntegrityError (carrera de doble-reserva); aquí RECALCULAMOS el siguiente hueco y
    reintentamos (bucle acotado). `hubo_hueco=False` => no hay cadencia/franja aplicable (None,
    sin tocar nada). `None` con `hubo_hueco=True` => la pieza se borró en la carrera.
    """
    for _ in range(_MAX_REINTENTOS_HUECO):
        hueco = calcular_hueco_para(pub, ahora)
        if hueco is None:
            return None, False
        try:
            # `preparado_en=""`: una pieza recién (re)programada aún no se preparó; resetearlo
            # evita que el programador la trate como ya preparada. Inocuo en el encolado manual.
            actualizada = repos.actualizar_publicacion(
                pub["id"],
                {"estado": "programado", "fecha_programada": hueco, "preparado_en": ""},
            )
        except IntegrityError:
            # Otra pieza reservó este slot antes que nosotros: recalcula y reintenta.
            continue
        return actualizada, True
    # Contención patológica: tras varios choques no se consiguió un slot libre estable.
    return None, True


async def duplicar(request: Request) -> Response:
    """Duplica una publicacion como borrador, con overrides opcionales.

    `POST /api/publicaciones/{id}/duplicar` con JSON opcional `{red?, marca?, titulo?}`.
    Copia contenido/copy_in/imagen/veredicto/hashtags; estado=borrador, fecha_programada=''.
    -> `{publicacion}` | 404.
    """
    publicacion_id = request.path_params["publicacion_id"]
    original = repos.obtener_publicacion(publicacion_id)
    if original is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    datos = await leer_json(request)
    marca = original["marca"]
    red = original["red"]
    titulo = original["titulo"]
    if "marca" in datos:
        nueva_marca = datos.get("marca")
        if not isinstance(nueva_marca, str) or nueva_marca not in _MARCAS_IDS:
            return JSONResponse({"error": "Marca no permitida."}, status_code=400)
        # Duplicar hacia CUALQUIER marca es legitimo: la marca es un foco, no un cerrojo.
        marca = nueva_marca
    if "red" in datos:
        nueva_red = datos.get("red")
        if not isinstance(nueva_red, str) or not redes.es_red(nueva_red):
            return JSONResponse({"error": "Red no permitida."}, status_code=400)
        red = nueva_red
    if "titulo" in datos:
        nuevo_titulo = datos.get("titulo")
        if not isinstance(nuevo_titulo, str):
            return JSONResponse({"error": "El título debe ser texto."}, status_code=400)
        titulo = nuevo_titulo.strip()

    copia = repos.crear_publicacion(
        marca,
        red,
        titulo=titulo,
        contenido=original["contenido"],
        copy_in=original.get("copy_in", ""),
        estado="borrador",
        veredicto=original["veredicto"],
        fecha_programada="",
        origen=original["origen"],
        imagen=original["imagen"],
        autor=autor_de_peticion(request),
    )
    return JSONResponse({"publicacion": _publicacion_a_dict(copia)})


async def clonar(request: Request) -> Response:
    """Clona el CONTENIDO de una pieza a OTRA RED de la misma idea (no crea otra idea).

    `POST /api/publicaciones/{id}/clonar` con `{red}`: copia copy/copy-in/foto/collage/
    plantilla (`_CAMPOS_ESPEJO`) a la pieza hermana de esa red —sobrescribiéndola, con el
    mismo reset de aprobaciones que una edición— o la CREA como borrador si la idea aún no
    salía en esa red. A diferencia de `duplicar` (que crea una idea nueva), aquí la pieza
    destino queda colgada del MISMO `contenido` padre. -> `{publicacion}` (la pieza destino)
    | 400 (red inválida / sin padre) | 404 | 409 (la hermana ya está publicada).
    """
    publicacion_id = request.path_params["publicacion_id"]
    original = repos.obtener_publicacion(publicacion_id)
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
    contenido_id = original.get("contenido_id") or ""
    if not contenido_id:
        return JSONResponse(
            {"error": "Esta pieza no tiene idea padre: no se puede clonar entre redes."},
            status_code=400,
        )

    campos: dict[str, Any] = {clave: original.get(clave) for clave in _CAMPOS_ESPEJO}
    hermanas = [
        p for p in repos.listar_contenido_plataforma(contenido_id) if (p.get("red") or "") == red
    ]
    if hermanas:
        destino = repos.obtener_publicacion(hermanas[0]["id"])
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
        pub = repos.actualizar_publicacion(destino["id"], campos)
        if pub is None:
            return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
        if resetear:
            _limpiar_cadena(destino["id"])
        return JSONResponse({"publicacion": _publicacion_a_dict(pub)})

    # La idea no salía en esa red: nace la pieza (borrador) con el contenido clonado. El
    # checklist (`falta_copy`/`falta_imagen`) se autodeduce del copy/imagen clonados.
    plat = repos.crear_contenido_plataforma(
        contenido_id=contenido_id,
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
    pub = repos.obtener_publicacion(plat["id"])
    if pub is None:
        return JSONResponse({"error": "No se pudo clonar la pieza."}, status_code=500)
    return JSONResponse({"publicacion": _publicacion_a_dict(pub)})


async def programar_metricool(request: Request) -> Response:
    """Programa/previsualiza la pieza en Metricool a demanda (botón de la UI).

    `POST /api/publicaciones/{id}/metricool`. Respeta el gate `KENI_PUBLICAR_REAL`:
    con el flag OFF (default) es DRY-RUN (previsualiza el cuerpo que se enviaría,
    NO publica ni persiste); con ON publica de verdad, persiste `id_post_metricool`
    y pasa la pieza a `publicado`. -> `{resultado, publicacion}` | 400 | 404.
    """
    # Import local: `programador` es infra (no es router de ninguna app); el camino
    # real solo se activa con el gate. Mantiene el módulo de API sin acoplarse a él.
    from .. import programador

    publicacion_id = request.path_params["publicacion_id"]
    pub = repos.obtener_publicacion(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    resultado = programador.programar_pieza_metricool(pub)
    if not resultado.get("ok"):
        return JSONResponse(
            {"error": resultado.get("motivo") or "No se pudo programar en Metricool."},
            status_code=400,
        )
    actualizada = repos.obtener_publicacion(publicacion_id)
    return JSONResponse(
        {
            "resultado": resultado,
            "publicacion": _publicacion_a_dict(actualizada) if actualizada else None,
        }
    )


async def integrar_foto(request: Request) -> Response:
    """Integra una FOTO subida dentro de la plantilla de marca de la publicación.

    `POST /api/publicaciones/{id}/integrar-foto {imagen}` (imagen = id de media de la foto).
    Si la pieza tiene marca (cualquiera del catálogo) RECOMPONE de forma determinista
    (síncrona, ~<1s) la foto detrás de la plantilla por SPEC usando el `copy_in` de la pieza
    como titular; sin marca devuelve la foto tal cual. NO persiste: devuelve la imagen
    resultante para que el SPA la fije y la guarde con el resto de la edición.
    -> `{imagen, imagen_url}` | 400 | 404.
    """
    from ..dominio import estudio_imagen

    publicacion_id = request.path_params["publicacion_id"]
    pub = repos.obtener_publicacion(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    datos = await leer_json(request)
    imagen = datos.get("imagen")
    if not isinstance(imagen, str) or not imagen.strip():
        return JSONResponse({"error": "Falta la foto a integrar."}, status_code=400)
    imagen = imagen.strip()
    # `copy_in` opcional: el SPA puede mandar el texto-en-imagen VIGENTE (aún sin guardar) para
    # que la placa use ese titular; si no viene, se usa el `copy_in` persistido de la pieza.
    copy_in = datos.get("copy_in")
    titular = copy_in if isinstance(copy_in, str) else (pub.get("copy_in") or "")

    marca = pub.get("marca") or ""
    final = imagen
    if estudio_imagen.marca_tiene_plantilla(marca):
        try:
            resultado = estudio_imagen.componer(
                imagen,
                marca=marca,
                formato=estudio_imagen.formato_por_red(pub.get("red") or ""),
                titular=titular,
                etiqueta=None,
                autor=autor_de_peticion(request),
            )
            final = resultado.get("id") or imagen
        except estudio_imagen.EstudioError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    return JSONResponse({"imagen": final, "imagen_url": f"/api/media/{final}"})


async def aplicar_plantilla(request: Request) -> Response:
    """Aplica una PLANTILLA del estudio a la publicación y RECOMPONE su imagen.

    `POST /api/publicaciones/{id}/aplicar-plantilla {plantilla_id}`: renderiza el documento de la
    plantilla (PlantillaDiseno) con la FOTO y el COPY-IN actuales de la pieza, fija la imagen
    resultante y recuerda la plantilla elegida (`plantilla_diseno_id`). Persiste. Así el equipo
    prueba distintas plantillas y compara el resultado real. -> `{publicacion}` | 400 | 404.
    """
    from ..dominio import estudio_imagen

    publicacion_id = request.path_params["publicacion_id"]
    pub = repos.obtener_publicacion(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    datos = await leer_json(request)
    plantilla_id = datos.get("plantilla_id")
    if not isinstance(plantilla_id, str) or not plantilla_id.strip():
        return JSONResponse({"error": "Falta la plantilla a aplicar."}, status_code=400)
    plantilla_id = plantilla_id.strip()
    plantilla = repos.obtener_plantilla_diseno(plantilla_id)
    if plantilla is None:
        return JSONResponse({"error": "Esa plantilla ya no existe."}, status_code=404)

    # `foto`/`copy_in`/`foto_encuadre` opcionales: el SPA manda los valores VIGENTES del editor
    # (aún sin guardar) para componer con ellos; si no vienen, se usan los persistidos de la pieza.
    foto_req = datos.get("foto")
    foto = foto_req if isinstance(foto_req, str) else (pub.get("foto") or "")
    copy_in_req = datos.get("copy_in")
    copy_in = copy_in_req if isinstance(copy_in_req, str) else (pub.get("copy_in") or "")
    enc_req = datos.get("foto_encuadre")
    foto_encuadre = enc_req if isinstance(enc_req, str) else (pub.get("foto_encuadre") or "")
    foco, zoom = estudio_imagen.parsear_encuadre(foto_encuadre)

    # Render de VALIDACIÓN (síncrono) a BYTES: confirma que la plantilla compone con esta
    # foto/copy_in antes de fijarla, SIN persistir nada (no genera huérfanos). La imagen se
    # renderiza on-demand y efímera desde la receta (`/compuesta`); no se hornea en `imagen`.
    try:
        estudio_imagen.componer_desde_plantilla_bytes(
            plantilla.get("documento") or "{}",
            copy_in=copy_in,
            foto=foto,
            foco=foco,
            zoom=zoom,
        )
    except estudio_imagen.EstudioError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    actualizada = repos.actualizar_publicacion(
        publicacion_id,
        {
            # `imagen` vacío: la composición se deriva de la receta y se sirve por `/compuesta`.
            "imagen": "",
            "plantilla_diseno_id": plantilla_id,
            "foto": foto,
            "foto_encuadre": foto_encuadre,
        },
    )
    if actualizada is None:  # carrera: borrada entre el obtener y el actualizar
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"publicacion": _publicacion_a_dict(actualizada)})


async def compuesta(request: Request) -> Response:
    """Sirve la imagen COMPUESTA de la pieza, renderizada ON-DEMAND y EFÍMERA (sin persistir).

    `GET /api/publicaciones/{id}/compuesta`: deriva la imagen publicable (placa de marca o
    plantilla del estudio aplicada a la foto + copy_in + encuadre) y devuelve los bytes SIN
    escribir nada en el almacén — el composite es función pura de la receta, no un objeto que
    almacenar. La caché vive en la capa HTTP: `ETag = hash(receta)` + `Cache-Control`; si el
    cliente reenvía `If-None-Match` y la receta no cambió, respondemos 304 SIN recomponer (el
    ETag se calcula de la receta, barato; no corre Node). Así no se generan huérfanos.

    404 si la pieza no existe o no tiene imagen servible; 422 si el render falla (motivo en
    español).
    """
    from ..dominio import estudio_imagen, render_pieza

    publicacion_id = request.path_params["publicacion_id"]
    pub = repos.obtener_publicacion(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    etag = f'"{render_pieza.firma_receta(pub)}"'
    cache = "private, max-age=300"
    # 304 sin renderizar si el cliente ya tiene esta versión de la receta.
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": cache})

    try:
        # Render es bloqueante (subprocess.run); ejecutar en threadpool para no bloquear el event loop.
        resultado = await run_in_threadpool(render_pieza.render_bytes, pub)
    except estudio_imagen.EstudioError as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    if resultado is None:
        return JSONResponse({"error": "La pieza aún no tiene imagen."}, status_code=404)
    datos, mime = resultado
    return Response(
        datos,
        media_type=mime,
        headers={"ETag": etag, "Cache-Control": cache},
    )


RUTAS = [
    Route("/api/publicaciones/opciones", opciones, methods=["GET"]),
    # Batch del feed: ANTES de "/{publicacion_id}" para que "cadenas" no matchee como id.
    Route("/api/publicaciones/cadenas", cadenas_lote, methods=["GET"]),
    Route("/api/publicaciones/borrar-lote", borrar_lote, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/compuesta", compuesta, methods=["GET"]),
    Route("/api/publicaciones", listar, methods=["GET"]),
    Route("/api/publicaciones", crear, methods=["POST"]),
    Route("/api/publicaciones/lote", crear_lote, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/encolar", encolar, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/duplicar", duplicar, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/clonar", clonar, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/metricool", programar_metricool, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/integrar-foto", integrar_foto, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/aplicar-plantilla", aplicar_plantilla, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}", detalle, methods=["GET"]),
    Route("/api/publicaciones/{publicacion_id}", actualizar, methods=["PUT"]),
    Route("/api/publicaciones/{publicacion_id}", borrar, methods=["DELETE"]),
]
