"""API Comercial: seguimiento de UNA publicacion por su link + reporte.

Apartado SEPARADO de Metricas (rendimiento diario). Aqui se registra una pieza ya
publicada por su enlace, se le da seguimiento (interacciones/alcance en el tiempo) con
captura programada, y al llegar el KPI se arma su reporte (de la pieza o de la
campania de un cliente). La logica de muestra/captura/reporte vive en `consola.comercial`;
la persistencia (SQLite) en `consola.db`. Este modulo solo es la frontera HTTP.

SEGURIDAD / VALIDACION (reusa las fuentes de verdad, no las duplica):
  - `marca` (si se da) SOLO del catalogo unico (`consola.marcas`), por su id canonico.
  - `red` (si se da) SOLO una red canonica (`consola.redes`).
  - `estado` SOLO de `repos.ESTADOS_COMERCIAL`; `metrica_objetivo` de `repos.METRICAS_COMERCIAL`.
  - `url` debe ser un enlace http(s). SQL parametrizado en `db`; errores como JSON ES.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import campanias, comercial, marcas, redes, repos
from .._http_json import leer_json

# Nombres legibles de los estados del seguimiento (para los selects del SPA).
_ESTADO_NOMBRE: dict[str, str] = {
    "activa": "Activa",
    "pausada": "Pausada",
    "cerrada": "Cerrada",
}
# Nombres legibles de la metrica del objetivo.
_METRICA_NOMBRE: dict[str, str] = {
    "interacciones": "Interacciones",
    "visualizaciones": "Visualizaciones",
    "alcance": "Alcance",
}
_MARCAS_IDS = {mid for mid, _ in marcas.opciones()}


# --------------------------------------------------------------------------- #
# Serializacion                                                                #
# --------------------------------------------------------------------------- #


def _a_dict(pub: dict[str, Any], *, con_serie: bool = False) -> dict[str, Any]:
    """Serializa una pieza con nombres resueltos + valor actual + progreso/aviso.

    `con_serie=True` adjunta la serie temporal completa (para el detalle); en el
    listado se omite por peso.
    """
    actual = comercial.resumen_actual(pub)
    objetivo = int(pub.get("objetivo") or 0)
    progreso = comercial.progreso_pct(pub, actual)
    d: dict[str, Any] = {
        "id": pub["id"],
        "url": pub.get("url") or "",
        "id_post_metricool": pub.get("id_post_metricool") or "",
        "titulo": pub.get("titulo") or "",
        "marca": pub.get("marca") or "",
        "marca_nombre": marcas.etiqueta_de(pub["marca"]) if pub.get("marca") else "",
        "cliente": pub.get("cliente") or "",
        "campania": pub.get("campania") or "",
        "red": pub.get("red") or "",
        "red_nombre": redes.nombre_por_id(pub["red"]) if pub.get("red") else "",
        # Formato ESTATICO de la pieza (reel/foto/carrusel/...); se resuelve desde la fuente
        # en la primera captura real. Vacio hasta entonces (o en modo muestra).
        "formato": pub.get("formato") or "",
        "metrica_objetivo": pub.get("metrica_objetivo") or "interacciones",
        "objetivo": objetivo,
        "estado": pub.get("estado") or "activa",
        "publicado": pub.get("publicado") or "",
        "notas": pub.get("notas") or "",
        "aviso_en": pub.get("aviso_en") or "",
        "fecha_creacion": pub.get("fecha_creacion") or "",
        "fecha_actualizacion": pub.get("fecha_actualizacion") or "",
        "actual": actual,
        "progreso_pct": progreso,
        "alcanzado": bool(pub.get("aviso_en")) or (objetivo > 0 and progreso >= 100),
        # Procedencia de las cifras: de muestra (sinteticas) mientras no haya APIs
        # reales conectadas. Que el frontend nunca las confunda con datos reales.
        "fuente": comercial.fuente_actual(),
        "es_muestra": comercial.es_muestra(),
    }
    if con_serie:
        d["serie"] = comercial.serie(pub["id"])
    return d


# --------------------------------------------------------------------------- #
# Validacion                                                                   #
# --------------------------------------------------------------------------- #


def _validar_url(valor: Any) -> tuple[str | None, str | None]:
    if not isinstance(valor, str) or not valor.strip():
        return None, "Falta el enlace de la publicación."
    url = valor.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return None, "El enlace debe empezar por http:// o https://."
    return url, None


def _validar_objetivo(valor: Any) -> tuple[int | None, str | None]:
    """Objetivo entero >= 0 (acepta numero o string numerico); '' o None -> 0."""
    if valor in (None, ""):
        return 0, None
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return None, "El objetivo debe ser un número entero."
    if n < 0:
        return None, "El objetivo no puede ser negativo."
    return n, None


def _validar_publicado(valor: Any) -> tuple[str | None, str | None]:
    """Fecha de publicacion ISO (YYYY-MM-DD); vacio -> hoy. None si invalida."""
    if valor in (None, ""):
        return date.today().isoformat(), None
    if not isinstance(valor, str):
        return None, "La fecha de publicación debe ser texto (YYYY-MM-DD)."
    try:
        date.fromisoformat(valor[:10])
    except ValueError:
        return None, "La fecha de publicación no es válida (usa YYYY-MM-DD)."
    return valor[:10], None


def _validar_campos(datos: dict[str, Any], *, claves: tuple[str, ...]) -> tuple[dict[str, Any] | None, str | None]:
    """Valida y normaliza SOLO las `claves` presentes en `datos` (allowlists).

    Sirve tanto para el alta (todas las claves) como para la edicion parcial (solo
    las que vengan). Devuelve `(cambios, None)` o `(None, mensaje)`.
    """
    cambios: dict[str, Any] = {}
    for clave in claves:
        if clave not in datos:
            continue
        valor = datos[clave]
        if clave == "marca":
            if valor and (not isinstance(valor, str) or valor not in _MARCAS_IDS):
                return None, "Marca no permitida."
            cambios["marca"] = valor or ""
        elif clave == "red":
            if valor and (not isinstance(valor, str) or not redes.es_red(valor)):
                return None, "Red no permitida."
            cambios["red"] = valor or ""
        elif clave == "estado":
            if not isinstance(valor, str) or valor not in repos.ESTADOS_COMERCIAL:
                return None, "Estado no permitido."
            cambios["estado"] = valor
        elif clave == "metrica_objetivo":
            if not isinstance(valor, str) or valor not in repos.METRICAS_COMERCIAL:
                return None, "Métrica de objetivo no permitida."
            cambios["metrica_objetivo"] = valor
        elif clave == "objetivo":
            n, error = _validar_objetivo(valor)
            if error is not None:
                return None, error
            cambios["objetivo"] = n
        elif clave == "publicado":
            iso, error = _validar_publicado(valor)
            if error is not None:
                return None, error
            cambios["publicado"] = iso
        else:  # titulo, cliente, campania, notas: texto libre
            if not isinstance(valor, str):
                return None, f"El campo «{clave}» debe ser texto."
            cambios[clave] = valor.strip()
    return cambios, None


# Claves que admite el alta (url se valida aparte) y la edicion parcial.
_CLAVES = (
    "titulo",
    "marca",
    "cliente",
    "campania",
    "red",
    "metrica_objetivo",
    "objetivo",
    "estado",
    "publicado",
    "notas",
)


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def opciones(request: Request) -> Response:
    """Catalogos para los selects del SPA: marcas, redes, estados y metricas."""
    return JSONResponse(
        {
            "marcas": [{"id": mid, "nombre": nombre} for mid, nombre in marcas.opciones()],
            "redes": redes.opciones(),
            "estados": [{"id": e, "nombre": _ESTADO_NOMBRE.get(e, e)} for e in repos.ESTADOS_COMERCIAL],
            "metricas": [
                {"id": m, "nombre": _METRICA_NOMBRE.get(m, m)} for m in repos.METRICAS_COMERCIAL
            ],
        }
    )


async def listar(request: Request) -> Response:
    """Listado de piezas monitoreadas con filtros `?estado=&cliente=&campania=`."""
    qp = request.query_params
    estado = qp.get("estado") or None
    if estado is not None and estado not in repos.ESTADOS_COMERCIAL:
        estado = None
    cliente = qp.get("cliente") or None
    campania = qp.get("campania") or None
    pubs = repos.listar_publicaciones_comerciales(estado=estado, cliente=cliente, campania=campania)
    return JSONResponse(
        {
            "publicaciones": [_a_dict(p) for p in pubs],
            # Procedencia comun a todas: de muestra mientras no haya APIs reales.
            "fuente": comercial.fuente_actual(),
            "es_muestra": comercial.es_muestra(),
        }
    )


async def crear(request: Request) -> Response:
    """Da de alta una pieza a monitorear, arranca su serie y evalua el aviso.

    Forma preferida (sin enlaces a mano): se selecciona un post real de Metricool, asi
    que llega `id_post_metricool` + `marca` + `red` (la `url` es derivada/opcional). Se
    mantiene el alta por `url` (sin `id_post_metricool`) para la demo y la compatibilidad.
    """
    datos = await leer_json(request)
    cambios, error = _validar_campos(datos, claves=_CLAVES)
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)

    id_post = datos.get("id_post_metricool")
    if id_post:
        if not isinstance(id_post, str) or not id_post.strip():
            return JSONResponse({"error": "El id del post no es válido."}, status_code=400)
        if not cambios.get("marca"):
            return JSONResponse({"error": "Falta la marca del post."}, status_code=400)
        if not cambios.get("red"):
            return JSONResponse({"error": "Falta la red del post."}, status_code=400)
        url = str(datos.get("url") or "").strip()  # derivada del post; no se exige
        pub = comercial.registrar(url, id_post_metricool=id_post.strip(), **cambios)
    else:
        url, error = _validar_url(datos.get("url"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        pub = comercial.registrar(url, **cambios)
    return JSONResponse({"publicacion": _a_dict(pub, con_serie=True)}, status_code=201)


async def posts(request: Request) -> Response:
    """Posts reales seleccionables para monitorizar: `?marca=&red=&rango=`.

    Lista en vivo de la fuente activa (Metricool en prod; piezas de muestra en demo) para
    que el alta elija una pieza por su `id_post_metricool` sin pegar enlaces. `marca`/`red`
    se validan contra sus allowlists (vacios = sin filtro); `rango` cae al valor por defecto.
    """
    qp = request.query_params
    marca = qp.get("marca") or ""
    if marca and marca not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    red = qp.get("red") or ""
    if red and not redes.es_red(red):
        return JSONResponse({"error": "Red no permitida."}, status_code=400)
    rango = qp.get("rango") or comercial.RANGO_LISTADO_DEF
    lista = comercial.listar_posts_seleccionables(marca, red, rango)
    return JSONResponse(
        {
            "posts": lista,
            "fuente": comercial.fuente_actual(),
            "es_muestra": comercial.es_muestra(),
        }
    )


async def detalle(request: Request) -> Response:
    publicacion_id = request.path_params["publicacion_id"]
    pub = repos.obtener_publicacion_comercial(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"publicacion": _a_dict(pub, con_serie=True)})


async def actualizar(request: Request) -> Response:
    """Edicion PARCIAL (titulo/cliente/campania/objetivo/estado/...); 404 si no existe.

    Tras editar, reevalua el aviso (p. ej. si se bajo el objetivo, puede pasar a
    alcanzado) para que el estado quede coherente sin esperar a la siguiente captura.
    """
    publicacion_id = request.path_params["publicacion_id"]
    datos = await leer_json(request)
    cambios, error = _validar_campos(datos, claves=_CLAVES)
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    pub = repos.actualizar_publicacion_comercial(publicacion_id, cambios)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    comercial.evaluar_aviso(pub)
    pub = repos.obtener_publicacion_comercial(publicacion_id) or pub
    return JSONResponse({"publicacion": _a_dict(pub, con_serie=True)})


async def eliminar(request: Request) -> Response:
    publicacion_id = request.path_params["publicacion_id"]
    if not repos.borrar_publicacion_comercial(publicacion_id):
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Publicación eliminada del seguimiento."})


async def refrescar(request: Request) -> Response:
    """Toma un snapshot AHORA de UNA pieza (refresco manual); 404 si no existe."""
    publicacion_id = request.path_params["publicacion_id"]
    pub = repos.obtener_publicacion_comercial(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    comercial.capturar(pub)
    pub = repos.obtener_publicacion_comercial(publicacion_id) or pub
    return JSONResponse({"publicacion": _a_dict(pub, con_serie=True)})


async def refrescar_todas(request: Request) -> Response:
    """Toma un snapshot AHORA de todas las piezas activas (refresco manual global)."""
    n = comercial.capturar_pendientes()
    return JSONResponse({"actualizadas": n})


def _descarga(texto: str, nombre: str, media_type: str) -> Response:
    cabecera = f'attachment; filename="{nombre}"'
    return Response(texto, media_type=media_type, headers={"Content-Disposition": cabecera})


async def reporte(request: Request) -> Response:
    """Reporte de UNA pieza (`?publicacion=`) o de una campania/cliente.

    `?formato=md` descarga Markdown; por defecto devuelve JSON (para verlo en la UI).
    """
    qp = request.query_params
    formato = (qp.get("formato") or "json").lower()
    publicacion_id = qp.get("publicacion") or None
    campania = qp.get("campania") or None
    cliente = qp.get("cliente") or None

    if publicacion_id:
        pub = repos.obtener_publicacion_comercial(publicacion_id)
        if pub is None:
            return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
        rep = comercial.reporte_publicacion(pub)
        nombre = f"reporte-comercial-{publicacion_id}"
    elif campania or cliente:
        pubs = repos.listar_publicaciones_comerciales(cliente=cliente, campania=campania)
        if not pubs:
            return JSONResponse(
                {"error": "No hay publicaciones para esa campaña o cliente."}, status_code=404
            )
        rep = comercial.reporte_campania(pubs, campania=campania or "", cliente=cliente or "")
        nombre = "reporte-comercial-" + (campania or cliente or "campania")
    else:
        return JSONResponse(
            {"error": "Indica una publicación, una campaña o un cliente."}, status_code=400
        )

    if formato == "md":
        texto = comercial.render_markdown_reporte(rep)
        return _descarga(texto, f"{nombre}.md", "text/markdown; charset=utf-8")
    return JSONResponse({"reporte": rep})


# --------------------------------------------------------------------------- #
# Campañas (agrupan piezas por hashtag; analítica al vuelo)                     #
# --------------------------------------------------------------------------- #


def _leer_hashtags(valor: Any) -> tuple[list[str] | None, str | None]:
    """Acepta lista de strings o un string con hashtags separados por espacios/comas."""
    if isinstance(valor, str):
        valor = [t for t in valor.replace(",", " ").split() if t]
    if not isinstance(valor, list) or not all(isinstance(t, str) for t in valor):
        return None, "Los hashtags deben ser una lista de texto."
    return valor, None


async def listar_campanias(request: Request) -> Response:
    """Campañas, opcionalmente filtradas por `?marca=`."""
    marca = request.query_params.get("marca") or None
    if marca and marca not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    return JSONResponse(
        {
            "campanias": campanias.listar_campanias(marca=marca),
            "fuente": comercial.fuente_actual(),
            "es_muestra": comercial.es_muestra(),
        }
    )


def _leer_marcas(valor: Any) -> tuple[list[str] | None, str | None]:
    """Acepta una lista de ids de marca (o un string único, retrocompat). Valida allowlist."""
    if isinstance(valor, str):
        valor = [valor] if valor else []
    if not isinstance(valor, list) or not all(isinstance(m, str) for m in valor):
        return None, "Las marcas deben ser una lista de ids."
    if not valor:
        return None, "Elige al menos una marca."
    if any(m not in _MARCAS_IDS for m in valor):
        return None, "Marca no permitida."
    return valor, None


async def crear_campania(request: Request) -> Response:
    """Crea una campaña (multimarca): `{marcas: [...], nombre, hashtags: [...]}`."""
    datos = await leer_json(request)
    # `marcas` (lista) es la forma actual; se acepta `marca` (string) por retrocompat.
    marcas_ids, error = _leer_marcas(datos.get("marcas", datos.get("marca")))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    nombre = datos.get("nombre")
    if not isinstance(nombre, str):
        return JSONResponse({"error": "El nombre debe ser texto."}, status_code=400)
    tags, error = _leer_hashtags(datos.get("hashtags"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    try:
        cam = campanias.crear_campania(marcas_ids=marcas_ids, nombre=nombre, hashtags=tags)
    except campanias.CampaniaInvalida as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"campania": cam}, status_code=201)


async def detalle_campania(request: Request) -> Response:
    cam = campanias.obtener_campania(request.path_params["campania_id"])
    if cam is None:
        return JSONResponse({"error": "Esa campaña ya no existe."}, status_code=404)
    return JSONResponse({"campania": cam})


async def actualizar_campania(request: Request) -> Response:
    """Edición parcial: `{nombre?, marcas?, hashtags?, activa?}`; 404 si no existe."""
    campania_id = request.path_params["campania_id"]
    datos = await leer_json(request)
    campos: dict[str, Any] = {}
    if "nombre" in datos:
        if not isinstance(datos["nombre"], str):
            return JSONResponse({"error": "El nombre debe ser texto."}, status_code=400)
        campos["nombre"] = datos["nombre"]
    if "marcas" in datos:
        marcas_ids, error = _leer_marcas(datos.get("marcas"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["marcas"] = marcas_ids
    if "hashtags" in datos:
        tags, error = _leer_hashtags(datos.get("hashtags"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["hashtags"] = tags
    if "activa" in datos:
        campos["activa"] = bool(datos["activa"])
    try:
        cam = campanias.actualizar_campania(campania_id, campos)
    except campanias.CampaniaInvalida as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if cam is None:
        return JSONResponse({"error": "Esa campaña ya no existe."}, status_code=404)
    return JSONResponse({"campania": cam})


async def eliminar_campania(request: Request) -> Response:
    if not campanias.borrar_campania(request.path_params["campania_id"]):
        return JSONResponse({"error": "Esa campaña ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Campaña eliminada."})


async def analitica_campania(request: Request) -> Response:
    """Analítica de una campaña en un periodo: `?rango=` (def `mes`). 404 si no existe."""
    campania_id = request.path_params["campania_id"]
    rango = request.query_params.get("rango") or campanias.RANGO_DEF
    try:
        datos = campanias.analitica_campania(campania_id, rango)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if datos is None:
        return JSONResponse({"error": "Esa campaña ya no existe."}, status_code=404)
    return JSONResponse(datos)


RUTAS = [
    Route("/api/comercial/opciones", opciones, methods=["GET"]),
    Route("/api/comercial/campanias", listar_campanias, methods=["GET"]),
    Route("/api/comercial/campanias", crear_campania, methods=["POST"]),
    Route("/api/comercial/campanias/{campania_id}", detalle_campania, methods=["GET"]),
    Route("/api/comercial/campanias/{campania_id}", actualizar_campania, methods=["PUT"]),
    Route("/api/comercial/campanias/{campania_id}", eliminar_campania, methods=["DELETE"]),
    Route(
        "/api/comercial/campanias/{campania_id}/analitica",
        analitica_campania,
        methods=["GET"],
    ),
    Route("/api/comercial/posts", posts, methods=["GET"]),
    Route("/api/comercial/reporte", reporte, methods=["GET"]),
    Route("/api/comercial/refrescar", refrescar_todas, methods=["POST"]),
    Route("/api/comercial/publicaciones", listar, methods=["GET"]),
    Route("/api/comercial/publicaciones", crear, methods=["POST"]),
    Route("/api/comercial/publicaciones/{publicacion_id}", detalle, methods=["GET"]),
    Route("/api/comercial/publicaciones/{publicacion_id}", actualizar, methods=["PUT"]),
    Route("/api/comercial/publicaciones/{publicacion_id}", eliminar, methods=["DELETE"]),
    Route(
        "/api/comercial/publicaciones/{publicacion_id}/refrescar",
        refrescar,
        methods=["POST"],
    ),
]
