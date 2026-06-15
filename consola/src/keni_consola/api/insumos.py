"""API de Insumos del día (cajones) — bandejas de material diario.

Los cajones reciben el material que el equipo de redes recibe cada día:
  - portal        : lista numerada Portal/SMS                (UnoTV)
  - corresponsales: el "así vamos" por estado                (UnoTV)
  - reporteros    : PDF de agenda de coberturas              (UnoTV)
  - eventos_claro : Excel/CSV de programación TV Claro Sports (Claro Sports)
  - notas         : volcado de notas/links/tweets/PDFs        (Claro Sports)
  - contexto      : indicaciones/correcciones — GUÍA EDITORIAL, nunca se publica (Claro Sports)

Contrato completo: docs/maquina-contenido/01-insumos-del-dia.md

Endpoints:
  GET  /api/insumos                  -> {fecha, cajones:[{cajon,lotes,items},...]}
  GET  /api/insumos/dias             -> {dias:[{fecha,total,por_cajon},...]}}
  POST /api/insumos/aportar          -> {lote, items}  (multipart/form-data o JSON)
  GET  /api/insumos/lote/{id}        -> {lote, items}
  PATCH /api/insumos/item/{id}       -> {item}
  DELETE /api/insumos/item/{id}      -> {ok: true}  (descarta un ítem NO usado)
  POST /api/insumos/item/{id}/usar   -> {item, contenido_id}
  POST /api/insumos/item/{id}/crear-evento -> {item, evento}
  DELETE /api/insumos/lote/{id}      -> {ok: true}
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import autogen_redactar, config, generaciones, marcas, redes, repos, rutas
from .._http_json import leer_json
from ..dominio import indicaciones, ingesta, recibir_parse, jobspec
from ..dominio.frescura import estado_frescura, resolver_linea
from ..seguridad import autor_de_peticion
from ..tiempo import hoy_utc

_log = logging.getLogger("keni_consola.api.insumos")

# Cajones en el orden del contrato (siempre todos, incluso vacíos). Los 4 primeros son de
# UnoTV; "notas" y "contexto" son de Claro Sports. "contexto" es guía editorial: sus ítems
# NUNCA entran al pool ni al tablero (ver `noticia_item_de_insumo` y los backstops de abajo).
_CAJONES: tuple[str, ...] = (
    "portal", "corresponsales", "reporteros", "eventos_claro", "notas", "contexto",
)
_MARCAS_IDS = {m[0] for m in marcas.opciones()}

# Límites de texto de entrada.
_MAX_TEXTO = 256_000  # ~256 KB para texto pegado
_MAX_ARCHIVO = 10 * 1024 * 1024  # 10 MB para archivos

# Campos editables de un ítem (PATCH).
_CAMPOS_PATCH_ITEM = frozenset(
    {"titulo", "resumen", "marca", "linea", "hora", "lugar", "estado_material", "tipo"}
)


# --------------------------------------------------------------------------- #
# Helpers de serialización                                                     #
# --------------------------------------------------------------------------- #


def _lote_a_dict(lote: dict[str, Any]) -> dict[str, Any]:
    """Serializa un lote añadiendo marca_nombre."""
    return {
        **lote,
        "marca_nombre": marcas.etiqueta_de(lote["marca"]) if lote.get("marca") else "",
    }


def _item_a_dict(item: dict[str, Any], hoy: str | None = None) -> dict[str, Any]:
    """Serializa un ítem añadiendo marca_nombre y frescura.

    `hoy` (ISO YYYY-MM-DD) se usa para calcular la frescura. Si es None usa la
    fecha del día en el servidor. La frescura se resuelve por la línea+marca del ítem.
    """
    _hoy = hoy or hoy_utc().isoformat()
    ttl_dias, es_evergreen = resolver_linea(
        item.get("linea") or "",
        item.get("marca") or "",
    )
    frescura = estado_frescura(
        item.get("fecha") or "",
        ttl_dias,
        es_evergreen,
        hoy=_hoy,
    )
    salida = {
        **item,
        "marca_nombre": marcas.etiqueta_de(item["marca"]) if item.get("marca") else "",
        "frescura": frescura,
    }
    # Vigencia de las INDICACIONES (cajón `contexto`): caducan a los `VENTANA_DIAS` días
    # (dominio/indicaciones.py) pero esa vigencia era INVISIBLE. La exponemos SOLO para los
    # ítems de guía editorial (`tipo=="contexto"`) para que el front pinte "Guía hasta DD/MM" /
    # "Caducada"; el resto de cajones no llevan el campo (no aplica). Mismo criterio de fecha
    # que `indicaciones.indicaciones_vigentes` (quien de verdad inyecta las vigentes en el copy),
    # para no divergir.
    if str(item.get("tipo") or "") == "contexto":
        salida["indicacion_vigente"] = _indicacion_vigente(item.get("fecha") or "", _hoy)
    return salida


def _indicacion_vigente(fecha_item: str, hoy_iso: str) -> bool:
    """¿La indicación (cajón `contexto`) sigue VIGENTE hoy?

    True si la fecha del ítem cae dentro de la ventana de `indicaciones.VENTANA_DIAS` días
    hasta `hoy_iso` (mismo corte que `indicaciones.indicaciones_vigentes`: vigente ⇔
    `fecha >= hoy - VENTANA_DIAS`). Sin fecha parseable no hay vigencia que evaluar: caducada.
    """
    try:
        fecha = date.fromisoformat((fecha_item or "").strip())
        hoy = date.fromisoformat((hoy_iso or "").strip())
    except ValueError:
        return False
    return fecha >= hoy - timedelta(days=indicaciones.VENTANA_DIAS)


def _noticia_pool_de_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """Fila GEMELA del pool de noticias creada al parsear el ítem; None si no hay.

    El parseo vuelca cada nota de cajón al pool (`noticias_items`) con identidad
    `fuente_id="cajon-{cajon}"` + `clave` = hash del TÍTULO normalizado
    (`ingesta.noticia_item_de_insumo`). Recalculamos esa identidad con el título
    ACTUAL del ítem: si el equipo lo editó después de parsear, el enlace se pierde
    y devolvemos None (mejor esfuerzo honesto, sin heurísticas frágiles).
    """
    fila = ingesta.noticia_item_de_insumo(item)
    if fila is None:
        return None
    return repos.noticia_item_por_clave(fila["fuente_id"], fila["clave"])


def _descartar_gemela_pool(item: dict[str, Any]) -> None:
    """Aparta del pool la fila GEMELA de un ítem de cajón (descarte fino y en bloque comparten esto).

    Marca `descartado` la fila de `noticias_items` que el parseo volcó (enlace por
    `fuente_id`+`clave`) para que el auto-feed NO la convierta en pieza; si su historia quedó
    SOLO con esa fuente (`n_fuentes<=1`, sin corroboración externa), también la apaga. Una
    historia corroborada por otras fuentes sigue viva (existe sin el cajón). Solo toca gemelas
    `nuevo` SIN `contenido_id` (una ya usada/recogida por el auto-feed conserva su rastro).

    Best-effort por diseño: NUNCA lanza. Un fallo aquí no debe impedir el borrado/descarte del
    ítem que lo invoca (`descartar_item`, `borrar_lote`) — el dedup por título del pipeline es la
    segunda red.
    """
    try:
        gemela = _noticia_pool_de_item(item)
        if gemela is None or gemela.get("estado") != "nuevo" or gemela.get("contenido_id"):
            return
        repos.actualizar_noticia_item(gemela["id"], estado="descartado")
        cid = str(gemela.get("cluster_id") or "")
        if not cid:
            return
        cluster = repos.obtener_noticia_cluster(cid)
        if (
            cluster is not None
            and cluster.get("estado") == "nuevo"
            and not cluster.get("contenido_id")
            and int(cluster.get("n_fuentes") or 0) <= 1
        ):
            repos.actualizar_noticia_cluster(cid, estado="descartado")
    except Exception:  # noqa: BLE001 -- el descarte del pool es aditivo; nunca frena al llamante
        _log.warning(
            "insumos: no se pudo descartar la gemela del pool (%s)",
            item.get("id", ""), exc_info=True,
        )


def _reenlazar_gemela_pool(item_previo: dict[str, Any], campos: dict[str, Any]) -> None:
    """Mantiene VIVO el enlace ítem↔gemela-del-pool cuando se EDITA el título.

    El enlace ítem↔gemela se deriva del hash del título (`_noticia_pool_de_item`): si el equipo
    reescribe el título, la gemela queda SUELTA (Descartar deja viva la vieja y el 409
    anti-doble-pieza de "Empujar ya" no dispara). No hay enlace ESTABLE persistido en
    `insumos_item` (haría falta una columna nueva + migración, y el punto que crea AMBAS filas
    vive en el worker, fuera de este router), así que RE-CALCULAMOS aquí, en el mismo PATCH:
    apartamos la gemela vieja (por el título anterior) y volcamos una gemela fresca con el título
    nuevo, de modo que el lookup por título vuelva a encontrarla. Best-effort: nunca rompe la
    edición. Solo re-enlaza una gemela aún SIN consumir (una usada/recogida conserva su rastro).
    """
    try:
        gemela = _noticia_pool_de_item(item_previo)
        if gemela is None or gemela.get("estado") != "nuevo" or gemela.get("contenido_id"):
            return
        nueva_fila = ingesta.noticia_item_de_insumo({**item_previo, **campos})
        # Si el título normalizado no cambió de hash, el enlace sigue vivo: nada que hacer.
        if (nueva_fila or {}).get("clave") == gemela.get("clave"):
            return
        # Aparta la gemela vieja (por el título anterior) y vuelca la nueva (idempotente por
        # UNIQUE(fuente_id, clave)). Si tras editar el ítem dejó de entrar al pool (re-tipado a
        # evento/contexto o sin título útil), `nueva_fila` es None: solo apartamos la vieja.
        _descartar_gemela_pool(item_previo)
        if nueva_fila is not None:
            repos.crear_noticias_items([nueva_fila])
    except Exception:  # noqa: BLE001 -- el re-enlace es dedup; nunca rompe la edición del ítem
        _log.warning(
            "insumos: no se pudo re-enlazar la gemela del pool al editar el título (%s)",
            item_previo.get("id", ""), exc_info=True,
        )


def _redes_iniciales(crudo: Any) -> list[str]:
    """Filtra una lista de ids de red contra las canónicas."""
    if not isinstance(crudo, list):
        return []
    vistas: list[str] = []
    for r in crudo:
        if isinstance(r, str) and redes.es_red(r) and r not in vistas:
            vistas.append(r)
    return vistas


# --------------------------------------------------------------------------- #
# GET /api/insumos                                                             #
# --------------------------------------------------------------------------- #


async def listar(request: Request) -> Response:
    """`GET /api/insumos?fecha=YYYY-MM-DD&cajon=&marca=&solo_frescos=1`

    Devuelve todos los cajones para la fecha pedida (def hoy), cada uno con sus lotes e ítems.

    Parámetros opcionales:
    - `solo_frescos=1`: filtra (oculta, no borra) los ítems caducados según la TTL de su línea.
      Útil para UnoTV donde publicar noticias de ayer es perjudicial.
    """
    fecha = (request.query_params.get("fecha") or "").strip()
    if not fecha:
        fecha = hoy_utc().isoformat()
    cajon_filtro = (request.query_params.get("cajon") or "").strip() or None
    marca_filtro = (request.query_params.get("marca") or "").strip() or None
    solo_frescos = request.query_params.get("solo_frescos") == "1"

    if cajon_filtro and cajon_filtro not in _CAJONES:
        return JSONResponse({"error": "Cajón no válido."}, status_code=400)
    if marca_filtro and marca_filtro not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no válida."}, status_code=400)

    hoy = hoy_utc().isoformat()
    cajones_resultado: list[dict[str, Any]] = []
    for cajon in _CAJONES:
        if cajon_filtro and cajon != cajon_filtro:
            cajones_resultado.append({"cajon": cajon, "lotes": [], "items": []})
            continue
        lotes = repos.listar_lotes(fecha=fecha, cajon=cajon)
        items = repos.listar_insumo_items(fecha=fecha, cajon=cajon, marca=marca_filtro)
        items_serializados = [_item_a_dict(i, hoy=hoy) for i in items]
        if solo_frescos:
            items_serializados = [i for i in items_serializados if i.get("frescura") != "caduco"]
        # Badge HONESTO de cara al feed (mismo patrón que las historias del pool): un ítem
        # `usado` significa "pieza creada", NO "en el feed" — la pieza sale real solo cuando
        # tiene copy. Derivamos `pieza_estado` (en_cola/generando/en_feed) en batch para los
        # usados NO-evento (en eventos `contenido_id` guarda el id del EVENTO de la rota, no
        # una pieza). Best-effort: si falla la lectura, el campo no viaja y la UI cae al texto
        # de siempre.
        try:
            ids_pieza = [
                str(i.get("contenido_id") or "")
                for i in items_serializados
                if i.get("usado") and i.get("contenido_id")
                and cajon != "eventos_claro" and str(i.get("tipo") or "") != "evento"
            ]
            if ids_pieza:
                resumen_pieza = repos.estado_pieza_por_contenido(ids_pieza)
                for i in items_serializados:
                    cid = str(i.get("contenido_id") or "")
                    if not (i.get("usado") and cid):
                        continue
                    if cajon == "eventos_claro" or str(i.get("tipo") or "") == "evento":
                        continue
                    pieza = resumen_pieza.get(cid)
                    i["pieza_estado"] = (
                        "en_feed" if pieza == "lista"
                        else "generando" if pieza == "generando"
                        else "en_cola"
                    )
        except Exception:  # noqa: BLE001 -- el badge es informativo; nunca rompe el listado
            pass
        cajones_resultado.append({
            "cajon": cajon,
            "lotes": [_lote_a_dict(lt) for lt in lotes],
            "items": items_serializados,
        })

    return JSONResponse({"fecha": fecha, "cajones": cajones_resultado})


# --------------------------------------------------------------------------- #
# GET /api/insumos/dias                                                        #
# --------------------------------------------------------------------------- #


async def dias(request: Request) -> Response:
    """`GET /api/insumos/dias` -> historial de días con insumos."""
    resultado = repos.dias_con_insumos()
    return JSONResponse({"dias": resultado})


# --------------------------------------------------------------------------- #
# POST /api/insumos/aportar                                                    #
# --------------------------------------------------------------------------- #


def _dir_temporal_insumos() -> Path:
    """Vuelca un temporal de subida BAJO el dir de datos compartido (back y worker lo ven).

    El parseo de cajones corre en el WORKER (#desacoplo: el back no tiene `claude`). back,
    worker y daemons montan el MISMO volumen `keni-data:/data`, así que un archivo que el back
    escribe bajo `<data>/keni-social/insumos-tmp` lo lee el worker via `--add-dir`. El propio
    `lanzar_job_claude` borra el `dir_temporal` al terminar el job.
    """
    base = rutas.dir_config() / "insumos-tmp"
    base.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="lote-", dir=str(base)))


async def aportar(request: Request) -> Response:
    """`POST /api/insumos/aportar` (multipart/form-data O JSON body).

    Campos obligatorios: `cajon`.
    Opcionales: `fecha` (def hoy), `marca`, `texto` O `archivo`.
    ASÍNCRONO: crea el lote en estado `parseando` y ENCOLA un job de generación (Haiku) que
    el WORKER ejecuta (el back no tiene `claude`); su post-procesado parsea la salida, inserta
    los ítems y deja el lote `listo`/`error`. Devuelve `{lote, generacion}` para que el SPA
    sondee. Mismo patrón que la generación de copy y la subida de archivos de la Texto.
    """
    content_type = request.headers.get("content-type", "")
    archivo_bytes: bytes = b""
    archivo_nombre: str = ""
    texto: str = ""
    cajon: str = ""
    fecha: str = ""
    marca: str = ""

    if "multipart/form-data" in content_type:
        form = await request.form()
        cajon = str(form.get("cajon") or "").strip()
        fecha = str(form.get("fecha") or "").strip()
        marca = str(form.get("marca") or "").strip()
        texto = str(form.get("texto") or "").strip()
        archivo_field = form.get("archivo")
        if isinstance(archivo_field, UploadFile):
            archivo_nombre = archivo_field.filename or "insumo.bin"
            archivo_bytes = await archivo_field.read(_MAX_ARCHIVO + 1)
            if len(archivo_bytes) > _MAX_ARCHIVO:
                return JSONResponse(
                    {"error": "El archivo supera el límite de 10 MB."}, status_code=400
                )
    else:
        datos = await leer_json(request)
        cajon = str(datos.get("cajon") or "").strip()
        fecha = str(datos.get("fecha") or "").strip()
        marca = str(datos.get("marca") or "").strip()
        texto = str(datos.get("texto") or "").strip()

    # Validaciones básicas.
    if cajon not in _CAJONES:
        return JSONResponse(
            {"error": f"El cajón es obligatorio y debe ser uno de: {', '.join(_CAJONES)}."},
            status_code=400,
        )
    if marca and marca not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no válida."}, status_code=400)
    if not fecha:
        fecha = hoy_utc().isoformat()
    if not texto and not archivo_bytes:
        return JSONResponse(
            {"error": "Debes aportar texto o un archivo."}, status_code=400
        )

    # Autor de la petición.
    autor = autor_de_peticion(request)
    creado_por = (autor or {}).get("usuario") or (autor or {}).get("id") or ""

    # Crea el lote en estado "parseando": el WORKER lo dejará en "listo"/"error" al terminar.
    archivo_nombre_lote = archivo_nombre if archivo_bytes else ""
    lote = repos.crear_insumo_lote(
        fecha=fecha,
        cajon=cajon,
        marca=marca,
        origen_texto=texto[:10000] if not archivo_bytes else "",
        origen_archivo=archivo_nombre_lote,
        estado="parseando",
        creado_por=creado_por,
    )
    lote_id = lote["id"]

    # Compone el prompt y, si hay archivo, lo vuelca a un temporal del dir COMPARTIDO (back y
    # worker montan el mismo `/data`), para que el worker lo lea via `--add-dir`/`dir_temporal`.
    dir_temporal: Path | None = None
    if archivo_bytes:
        dir_temporal = _dir_temporal_insumos()
        nombre_seguro = Path(archivo_nombre or "").name or "insumo.bin"
        ruta = dir_temporal / nombre_seguro
        try:
            ruta.write_bytes(archivo_bytes)
        except OSError:
            shutil.rmtree(dir_temporal, ignore_errors=True)
            repos.actualizar_insumo_lote(
                lote_id, {"estado": "error", "error": "No se pudo preparar el archivo."}
            )
            lote = repos.obtener_insumo_lote(lote_id) or lote
            return JSONResponse({"lote": _lote_a_dict(lote), "generacion": None}, status_code=500)
        prompt = recibir_parse.construir_prompt_archivo(cajon, str(ruta))
    else:
        prompt = recibir_parse.construir_prompt_texto(cajon, texto)

    # Spec del post-procesado: parsea la salida de Haiku e inserta los ítems (en el worker).
    procesar_spec = jobspec.construir_insumos(
        lote_id=lote_id, cajon=cajon, fecha=fecha, marca_defecto=marca
    )
    spec = jobspec.construir(
        prompt=prompt,
        procesar=procesar_spec,
        dir_temporal=str(dir_temporal) if dir_temporal is not None else None,
        # Haiku (config.insumos_modelo()): parseo mecánico de JSON, no necesita un modelo grande.
        endurecer={"modelo": config.insumos_modelo()},
    )

    # Registro de generación (para sondeo del SPA) y encolado. El back NO ejecuta `claude`.
    gen = generaciones.crear({
        "tipo": "insumos",
        "marca": marca,
        "etiqueta": f"Cajón {cajon} · {fecha}",
        "autor_id": (autor or {}).get("id", "") or "",
        "autor_nombre": (autor or {}).get("usuario", "") or "",
    })
    try:
        generaciones.encolar_job_claude(
            gen["id"],
            prompt=prompt,
            cwd=jobspec.cwd_generacion(),
            procesar=jobspec.reconstruir_procesar({"procesar": procesar_spec}),
            dir_temporal=dir_temporal,
            spec=spec,
        )
    except generaciones.ColaLlenaError:
        if dir_temporal is not None:
            shutil.rmtree(dir_temporal, ignore_errors=True)
        repos.actualizar_insumo_lote(
            lote_id,
            {"estado": "error", "error": "Hay demasiados trabajos en curso; inténtalo en unos segundos."},
        )
        generaciones.actualizar(gen["id"], {
            "estado": generaciones.ESTADO_ERROR, "motivo": generaciones.MOTIVO_COLA_LLENA,
            "error": "Hay demasiados trabajos en curso; inténtalo en unos segundos.",
            "fecha_fin": generaciones.ahora_iso(),
        })
        lote = repos.obtener_insumo_lote(lote_id) or lote
        return JSONResponse(
            {"lote": _lote_a_dict(lote), "generacion": generaciones.obtener(gen["id"])},
            status_code=429,
        )
    except Exception:  # noqa: BLE001 -- reflejamos el fallo en el lote/generación, sin traceback al cliente
        _log.exception("no se pudo encolar el parseo del lote %s", lote_id)
        if dir_temporal is not None:
            shutil.rmtree(dir_temporal, ignore_errors=True)
        repos.actualizar_insumo_lote(
            lote_id, {"estado": "error", "error": "No se pudo iniciar el parseo."}
        )
        generaciones.actualizar(gen["id"], {
            "estado": generaciones.ESTADO_ERROR, "error": "No se pudo iniciar el parseo.",
            "fecha_fin": generaciones.ahora_iso(),
        })
        lote = repos.obtener_insumo_lote(lote_id) or lote
        return JSONResponse(
            {"lote": _lote_a_dict(lote), "generacion": generaciones.obtener(gen["id"])},
            status_code=500,
        )

    lote = repos.obtener_insumo_lote(lote_id) or lote
    return JSONResponse({
        "lote": _lote_a_dict(lote),
        "generacion": generaciones.obtener(gen["id"]) or gen,
    })


# --------------------------------------------------------------------------- #
# GET /api/insumos/lote/{id}                                                   #
# --------------------------------------------------------------------------- #


async def detalle_lote(request: Request) -> Response:
    """`GET /api/insumos/lote/{lote_id}` -> {lote, items}."""
    lote_id = request.path_params["lote_id"]
    lote = repos.obtener_insumo_lote(lote_id)
    if lote is None:
        return JSONResponse({"error": "Ese lote no existe."}, status_code=404)
    items = repos.listar_insumo_items(lote_id=lote_id)
    _hoy = hoy_utc().isoformat()
    return JSONResponse({
        "lote": _lote_a_dict(lote),
        "items": [_item_a_dict(i, hoy=_hoy) for i in items],
    })


# --------------------------------------------------------------------------- #
# PATCH /api/insumos/item/{id}                                                 #
# --------------------------------------------------------------------------- #


async def editar_item(request: Request) -> Response:
    """`PATCH /api/insumos/item/{item_id}` -> {item}.

    Campos editables: titulo, resumen, marca, linea, hora, lugar, estado_material, tipo.
    """
    item_id = request.path_params["item_id"]
    item_previo = repos.obtener_insumo_item(item_id)
    if item_previo is None:
        return JSONResponse({"error": "Ese ítem no existe."}, status_code=404)
    datos = await leer_json(request)
    campos: dict[str, Any] = {}
    for campo in _CAMPOS_PATCH_ITEM:
        if campo in datos:
            campos[campo] = datos[campo]
    if "marca" in campos:
        m = campos["marca"]
        if m and m not in _MARCAS_IDS:
            return JSONResponse({"error": "Marca no válida."}, status_code=400)
    if "tipo" in campos and campos["tipo"] not in {"nota", "cobertura", "evento", "contexto"}:
        return JSONResponse({"error": "Tipo no válido."}, status_code=400)
    if "estado_material" in campos and campos["estado_material"] not in {"tengo", "espero", ""}:
        return JSONResponse({"error": "estado_material no válido."}, status_code=400)
    # Si cambia el TÍTULO, re-enlaza la gemela del pool (su identidad es el hash del título): sin
    # esto el enlace ítem↔gemela se pierde y Descartar / el 409 anti-doble-pieza dejan de operar.
    if "titulo" in campos and str(campos["titulo"] or "").strip() != str(
        item_previo.get("titulo") or ""
    ).strip():
        _reenlazar_gemela_pool(item_previo, campos)
    item = repos.actualizar_insumo_item(item_id, campos)
    if item is None:
        return JSONResponse({"error": "Ese ítem no existe."}, status_code=404)
    return JSONResponse({"item": _item_a_dict(item, hoy=hoy_utc().isoformat())})


# --------------------------------------------------------------------------- #
# POST /api/insumos/item/{id}/usar                                             #
# --------------------------------------------------------------------------- #


async def usar_item(request: Request) -> Response:
    """`POST /api/insumos/item/{item_id}/usar` -> {item, contenido_id}.

    Lleva el ítem al tablero (`repos.crear_contenido`, origen="insumo",
    flujo="importante"), opcionalmente lanza copy en segundo plano y marca el ítem
    como usado con el `contenido_id` resultante.

    Guardas: 400 si el ítem no tiene marca (la pieza nacería invisible y sin copy);
    409 si su historia gemela del pool ya tiene pieza (el auto-feed la recogió).

    Cuerpo JSON (todo opcional):
      {redes: ["x", ...], generar: bool}
    """
    item_id = request.path_params["item_id"]
    item = repos.obtener_insumo_item(item_id)
    if item is None:
        return JSONResponse({"error": "Ese ítem no existe."}, status_code=404)
    # Backstop: las indicaciones (cajón contexto) son guía editorial, NUNCA piezas. Aunque
    # alguien archive una nota en el cajón equivocado, el `tipo=contexto` la frena aquí.
    if str(item.get("tipo") or "") == "contexto":
        return JSONResponse(
            {"error": "Las indicaciones son guía editorial; no se llevan al tablero."},
            status_code=400,
        )
    if item.get("usado"):
        # Ya fue llevado al tablero; devuelve el estado actual.
        return JSONResponse({"item": _item_a_dict(item), "contenido_id": item.get("contenido_id", "")})
    # Sin marca NO se empuja: la pieza nacería sin marca (invisible en los feeds por marca)
    # y el copy ni arrancaría (la generación se gatea por marca) — el toast "Copy en marcha"
    # sería mentira. Que el equipo asigne marca (editar ítem) y reintente.
    if not str(item.get("marca") or "").strip():
        return JSONResponse(
            {"error": "Asigna marca al ítem antes de empujarlo."}, status_code=400
        )
    # Dedup contra el AUTO-FEED: si la historia gemela del pool (la fila de noticias creada
    # al parsear) ya tiene pieza (el auto-feed la recogió y la marcó usada con su
    # `contenido_id`), empujar crearía una SEGUNDA pieza del mismo tema. 409 honesto.
    gemela = _noticia_pool_de_item(item)
    if gemela is not None and (gemela.get("estado") == "usado" or gemela.get("contenido_id")):
        return JSONResponse(
            {"error": "Ya está en el feed: el auto-feed la recogió."}, status_code=409
        )

    datos = await leer_json(request)
    redes_iniciales = _redes_iniciales(datos.get("redes"))
    generar = datos.get("generar", True)
    autor = autor_de_peticion(request)

    contenido = repos.crear_contenido(
        clase="contenido",
        flujo="importante",
        titulo=item["titulo"],
        descripcion=item.get("resumen", ""),
        marca=item.get("marca", ""),
        prioridad="media",
        fecha_objetivo=item.get("fecha", hoy_utc().isoformat()),
        autor=autor,
        origen="insumo",
        tipo_contenido="fuente",
        notas=f"Cajón: {item.get('cajon', '')} | Línea: {item.get('linea', '')}",
    )
    for red in redes_iniciales:
        repos.crear_contenido_plataforma(
            contenido_id=contenido["id"], red=red, falta_copy=True, falta_imagen=True
        )

    # Copy en segundo plano (best-effort), gateado por marca y por generar.
    genero = False
    if item.get("marca") and generar:
        try:
            genero = autogen_redactar.lanzar_para_topic(contenido) is not None
        except Exception:  # noqa: BLE001 -- la generación es opcional
            genero = False

    # Marca el ítem como usado.
    item_actualizado = repos.marcar_insumo_item_usado(item_id, contenido_id=contenido["id"])
    if item_actualizado is None:
        item_actualizado = item

    # Y la gemela del pool (y su historia, si la tiene) también: así el auto-feed no vuelve
    # a promover el mismo tema después del empujón manual. Best-effort: el dedup por título
    # del pipeline es la segunda red; un fallo aquí no rompe el empujón.
    try:
        if gemela is not None:
            repos.actualizar_noticia_item(
                gemela["id"], estado="usado", contenido_id=contenido["id"]
            )
            cid = str(gemela.get("cluster_id") or "")
            if cid:
                cluster = repos.obtener_noticia_cluster(cid)
                if cluster is not None and cluster.get("estado") == "nuevo":
                    repos.actualizar_noticia_cluster(
                        cid, estado="usado", contenido_id=contenido["id"]
                    )
    except Exception:  # noqa: BLE001 -- el marcado del pool es dedup, nunca rompe el empujón
        _log.warning("insumos: no se pudo marcar la gemela del pool usada (%s)", item_id, exc_info=True)

    return JSONResponse({
        "item": _item_a_dict(item_actualizado, hoy=hoy_utc().isoformat()),
        "contenido_id": contenido["id"],
        "copy_en_proceso": genero,
    })


# --------------------------------------------------------------------------- #
# POST /api/insumos/item/{id}/crear-evento                                     #
# --------------------------------------------------------------------------- #


async def crear_evento_item(request: Request) -> Response:
    """`POST /api/insumos/item/{item_id}/crear-evento` -> {item, evento}.

    Crea un evento de la rota (`rota_eventos`) a partir de un ítem del cajón
    `eventos_claro` (Excel/CSV de programación de Claro Sports): mapea
    titulo→titulo, fecha→fecha, hora→hora, resumen→nota, y marca el ítem como
    usado guardando el id del evento creado en `contenido_id` (reutilizamos el
    campo existente, sin añadir columnas). Así el recorrido Excel → cajón →
    evento queda visible de punta a punta en Fuentes.

    Idempotente: si el ítem ya está usado, devuelve su estado actual sin crear
    un evento nuevo (mismo patrón que `usar_item`).

    Cuerpo JSON (todo opcional):
      {tipo_cobertura: str, prioridad: str}
    """
    item_id = request.path_params["item_id"]
    item = repos.obtener_insumo_item(item_id)
    if item is None:
        return JSONResponse({"error": "Ese ítem no existe."}, status_code=404)
    if str(item.get("tipo") or "") == "contexto":
        return JSONResponse(
            {"error": "Las indicaciones son guía editorial; no generan eventos."},
            status_code=400,
        )
    if item.get("usado"):
        # Ya fue convertido en evento (o llevado al tablero); devuelve el estado actual.
        return JSONResponse(
            {"item": _item_a_dict(item), "evento_id": item.get("contenido_id", "")}
        )
    if not (item.get("titulo") or "").strip():
        return JSONResponse({"error": "El ítem necesita un título."}, status_code=400)
    if not (item.get("fecha") or "").strip():
        return JSONResponse({"error": "El ítem necesita una fecha."}, status_code=400)

    datos = await leer_json(request)
    tipo_cobertura = str(datos.get("tipo_cobertura", "transmision")).strip() or "transmision"
    prioridad = str(datos.get("prioridad", "media")).strip() or "media"

    # Crea el evento de la rota (la validación de tipo_cobertura/prioridad la hace
    # `crear_evento_rota`, que cae al valor por defecto si no es válido).
    # Propaga la `marca` del ítem para que el evento quede en la marca correcta (p.ej.
    # los eventos de Claro Sports del Excel cajón -> claro-sports).
    evento = repos.crear_evento_rota(
        item["titulo"].strip(),
        fecha=(item.get("fecha") or "").strip(),
        hora=(item.get("hora") or "").strip(),
        nota=(item.get("resumen") or "").strip(),
        tipo_cobertura=tipo_cobertura,
        prioridad=prioridad,
        marca=(item.get("marca") or ""),
    )

    # Marca el ítem como usado, guardando el id del evento en `contenido_id`.
    item_actualizado = repos.marcar_insumo_item_usado(item_id, contenido_id=evento["id"])
    if item_actualizado is None:
        item_actualizado = item

    return JSONResponse(
        {
            "item": _item_a_dict(item_actualizado, hoy=hoy_utc().isoformat()),
            "evento": evento,
            "evento_id": evento["id"],
        }
    )


# --------------------------------------------------------------------------- #
# DELETE /api/insumos/item/{id}                                                #
# --------------------------------------------------------------------------- #


async def descartar_item(request: Request) -> Response:
    """`DELETE /api/insumos/item/{item_id}` -> {ok: true}. Descarta un ítem NO usado.

    El descarte fino que promete el explainer del SPA ("Descarta insumos o empuja
    historias ya"): borra la fila de `insumos_item` y, si existe la gemela del pool
    de noticias (creada al parsear; enlace por `fuente_id`+`clave`), la marca
    `descartado` para que el auto-feed no la convierta en pieza. Si su historia del
    pool quedó SOLO con esa fuente (sin corroboración externa), también se descarta;
    una historia corroborada por otras fuentes sigue viva (existe sin el cajón).

    Un ítem ya usado NO se descarta (400): su pieza/evento vive en el tablero/rota
    (borrarlo aquí mentiría sobre lo ya producido).
    """
    item_id = request.path_params["item_id"]
    item = repos.obtener_insumo_item(item_id)
    if item is None:
        return JSONResponse({"error": "Ese ítem no existe."}, status_code=404)
    if item.get("usado"):
        return JSONResponse(
            {"error": "El ítem ya se usó; no se puede descartar."}, status_code=400
        )
    # Gemela del pool: descartarla evita que el auto-feed la promueva después. Best-effort:
    # si el equipo editó el título tras parsear, el PATCH ya re-enlazó la gemela
    # (`_reenlazar_gemela_pool`), así que el lookup por título actual sigue encontrándola.
    _descartar_gemela_pool(item)
    if not repos.borrar_insumo_item(item_id):
        return JSONResponse({"error": "Ese ítem no existe."}, status_code=404)
    return JSONResponse({"ok": True})


# --------------------------------------------------------------------------- #
# DELETE /api/insumos/lote/{id}                                                #
# --------------------------------------------------------------------------- #


async def borrar_lote(request: Request) -> Response:
    """`DELETE /api/insumos/lote/{lote_id}` -> {ok: true}. Borra lote + sus ítems.

    Antes de borrar, aparta del pool las gemelas de los ítems NO usados del lote (igual que el
    descarte fino de `descartar_item`): sin esto, material borrado EN BLOQUE reaparecía como
    piezas del auto-feed (la gemela seguía `nuevo` en `noticias_items`). Los ítems ya usados
    conservan su rastro: su pieza/evento vive en el tablero/rota y su gemela quedó `usado`.
    """
    lote_id = request.path_params["lote_id"]
    for item in repos.listar_insumo_items(lote_id=lote_id):
        if not item.get("usado"):
            _descartar_gemela_pool(item)
    if not repos.borrar_insumo_lote(lote_id):
        return JSONResponse({"error": "Ese lote no existe."}, status_code=404)
    return JSONResponse({"ok": True})


# --------------------------------------------------------------------------- #
# Rutas                                                                        #
# --------------------------------------------------------------------------- #

RUTAS = [
    Route("/api/insumos", listar, methods=["GET"]),
    Route("/api/insumos/dias", dias, methods=["GET"]),
    Route("/api/insumos/aportar", aportar, methods=["POST"]),
    Route("/api/insumos/lote/{lote_id}", detalle_lote, methods=["GET"]),
    Route("/api/insumos/lote/{lote_id}", borrar_lote, methods=["DELETE"]),
    Route("/api/insumos/item/{item_id}", editar_item, methods=["PATCH"]),
    Route("/api/insumos/item/{item_id}", descartar_item, methods=["DELETE"]),
    Route("/api/insumos/item/{item_id}/usar", usar_item, methods=["POST"]),
    Route("/api/insumos/item/{item_id}/crear-evento", crear_evento_item, methods=["POST"]),
]
