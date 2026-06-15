"""API Galería de ARTES: cataloga objetos de media para reutilizarlos (durables).

Un ARTE es una imagen del almacen de media (subida, generada con IA o trabajada en el
Estudio) que el equipo decide CONSERVAR para reutilizar en publicaciones. Catalogarla:
  - la PROTEGE del GC de media suelta (`dominio/media_gc.py` ya cuenta los objetos
    catalogados como referencias vivas: un arte no se borra a las 24h), y
  - la hace SELECCIONABLE desde el editor de imagen de una pieza (galeria por marca).

Persistencia: tabla `catalogo_media` via `repos.*_media_catalogo`. El `objeto` es UNIQUE
(un objeto se cataloga una sola vez): re-catalogar el mismo objeto es IDEMPOTENTE (devuelve
el item ya existente, no duplica ni falla).

  - `GET    /api/artes`        lista artes catalogadas (filtros `?marca=&tipo=&q=`).
  - `POST   /api/artes`        cataloga un objeto de media ya existente.
  - `DELETE /api/artes/{id}`   descataloga (con `?purgar=1` borra tambien el binario).

SEGURIDAD: `objeto` debe EXISTIR en el almacen y `marca`, si llega, ser del catalogo unico
(`consola.marcas`). Errores en espanol, sin tracebacks. Multiusuario por middleware (el
tablero es compartido, como Etiquetas/Tareas). SQL parametrizado en `repos`/`db`.
"""

from __future__ import annotations

import json
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import almacen_media, libtexto, marcas, media, repos
from .._http_json import leer_json
from ..seguridad import autor_de_peticion
from .media import lanzar_generacion_imagen

_log = logging.getLogger("keni_consola.artes")

# Tope de imagenes ALTERNATIVAS por lanzamiento manual de arte: cada una cuesta dinero (una
# llamada al proveedor), asi que se acota para evitar ráfagas/abuso. 1..4 basta para
# comparar variaciones de un mismo prompt.
_MAX_ALTERNATIVAS = 4
# Prompt base del arte en la Biblioteca (mismo id que la directiva del generador): si el
# usuario no escribe nada, se usa el cuerpo efectivo de este prompt como tema a ilustrar.
_PROMPT_ARTE_ID = "prompt/ilustrar"
# Moneda del coste medio por imagen (el proveedor reporta el coste en USD).
_MONEDA_COSTE = "USD"
# Cuantas generaciones recientes de imagen promedia el coste medio por imagen.
_VENTANA_COSTE = 50

# Origen del arte (de donde salio): trabajado en el Estudio, subido por el usuario, generado
# con IA o la foto ORIGINAL de la nota (RSS de marca propia, auto-catalogada). Es informativo
# (la UI lo muestra/filtra como carpetas); no cambia el almacenamiento.
_TIPOS = ("estudio", "subida", "ia", "original")
_TIPO_DEFECTO = "estudio"

_MAX_TITULO = 120
_MAX_ETIQUETAS = 12
_MAX_ETIQUETA = 40


def _validar_marca(marca: object) -> tuple[str | None, str | None]:
    """'' (global) es valido; cualquier otra debe ser una marca del catalogo unico."""
    if marca in (None, ""):
        return "", None
    if not isinstance(marca, str) or not marcas.es_marca(marca):
        return None, "Marca no permitida."
    return marca, None


def _normalizar_etiquetas(valor: object) -> list[str]:
    """Lista de etiquetas normalizada (cadenas no vacias, recortadas, sin duplicados)."""
    if not isinstance(valor, list):
        return []
    vistas: list[str] = []
    for item in valor:
        if not isinstance(item, str):
            continue
        et = item.strip()[:_MAX_ETIQUETA]
        if et and et not in vistas:
            vistas.append(et)
        if len(vistas) >= _MAX_ETIQUETAS:
            break
    return vistas


def _arte_a_dict(item: dict) -> dict:
    """Serializa un item del catálogo como ARTE: etiquetas como lista, url y nombre de marca."""
    crudas = item.get("etiquetas") or "[]"
    try:
        tags = json.loads(crudas) if isinstance(crudas, str) else crudas
    except (ValueError, TypeError):
        tags = []
    if not isinstance(tags, list):
        tags = []
    return {
        **item,
        "etiquetas": [t for t in tags if isinstance(t, str)],
        "url": f"/api/media/{item['objeto']}",
        "marca_nombre": marcas.etiqueta_de(item["marca"]) if item.get("marca") else "",
    }


def _coincide_busqueda(arte: dict, q: str) -> bool:
    """Coincidencia simple (substring, sin acentos-fold) por titulo o etiquetas."""
    aguja = q.lower()
    if aguja in (arte.get("titulo") or "").lower():
        return True
    return any(aguja in t.lower() for t in arte.get("etiquetas", []))


async def listar(request: Request) -> Response:
    """GET /api/artes: artes catalogadas (mas recientes primero).

    Filtros opcionales: `marca` (acota a esa marca, MÁS los artes globales compartidos),
    `tipo` (`estudio|subida|ia`) y `q` (busqueda por titulo/etiqueta, en memoria). Devuelve
    `{artes: [...]}`. Al acotar por marca se incluyen también los artes GLOBALES (marca='')
    para que un arte reutilizable (p.ej. una foto generada por IA) salga en cualquier marca.
    """
    q = request.query_params
    artes = [
        _arte_a_dict(item)
        for item in repos.listar_media_catalogo(
            marca=q.get("marca") or None,
            tipo=q.get("tipo") or None,
            incluir_globales=True,
        )
    ]
    busqueda = (q.get("q") or "").strip()
    if busqueda:
        artes = [a for a in artes if _coincide_busqueda(a, busqueda)]
    return JSONResponse({"artes": artes})


async def crear(request: Request) -> Response:
    """POST /api/artes: cataloga un objeto de media ya existente como arte reutilizable.

    Cuerpo: `objeto` (id de media, obligatorio), `marca` ('' = global), `tipo`
    (`estudio|subida|ia`), `titulo`, `etiquetas` (lista de cadenas). IDEMPOTENTE: si el
    objeto ya esta catalogado devuelve el item existente. -> `{arte}` | 400.
    """
    datos = await leer_json(request)

    objeto = datos.get("objeto")
    if not isinstance(objeto, str) or not objeto.strip():
        return JSONResponse({"error": "Falta la imagen a guardar."}, status_code=400)
    objeto = objeto.strip()
    if media.leer_media(objeto) is None:
        return JSONResponse({"error": "Esa imagen no existe en el almacén."}, status_code=400)
    # Catalogar = conservar para reutilizar: promovemos el objeto a la carpeta `artes/` ANTES
    # de la idempotencia/insert, de modo que el catálogo guarda la key ya en su carpeta protegida.
    objeto = almacen_media.promover_objeto(objeto, "artes")

    marca, err = _validar_marca(datos.get("marca"))
    if err:
        return JSONResponse({"error": err}, status_code=400)

    tipo = datos.get("tipo") or _TIPO_DEFECTO
    if tipo not in _TIPOS:
        return JSONResponse({"error": "Origen de arte no válido."}, status_code=400)

    # Idempotente: el `objeto` es UNIQUE en la tabla. Si ya esta catalogado, devolvemos el
    # item existente (no duplicamos ni dejamos que el INSERT falle por la restriccion).
    if repos.existe_media_objeto(objeto):
        for item in repos.listar_media_catalogo():
            if item.get("objeto") == objeto:
                return JSONResponse({"arte": _arte_a_dict(item)})

    titulo = (datos.get("titulo") or "").strip()[:_MAX_TITULO]
    etiquetas = _normalizar_etiquetas(datos.get("etiquetas"))

    arte = repos.crear_media_catalogo(
        objeto=objeto,
        tipo=tipo,
        marca=marca or "",
        titulo=titulo,
        etiquetas=json.dumps(etiquetas, ensure_ascii=False),
        autor=autor_de_peticion(request),
    )
    return JSONResponse({"arte": _arte_a_dict(arte)})


async def borrar(request: Request) -> Response:
    """DELETE /api/artes/{id}: descataloga un arte. Con `?purgar=1` borra el binario.

    Por defecto solo se quita del catalogo: el objeto queda en el almacen y el GC lo
    recogera si nadie lo referencia (umbral 24h). Con `purgar=1` se borra ademas el binario
    del almacen de inmediato (un fallo al purgar NO rompe el descatalogado).
    -> `{mensaje}` | 404.
    """
    arte_id = request.path_params["arte_id"]
    item = repos.borrar_media_catalogo(arte_id)
    if item is None:
        return JSONResponse({"error": "Ese arte ya no está en la galería."}, status_code=404)

    if request.query_params.get("purgar") == "1":
        try:
            almacen_media.borrar_objeto(item["objeto"])
        except Exception:  # noqa: BLE001 -- el descatalogado ya esta hecho; purgar es best-effort
            _log.exception("No se pudo purgar el binario del arte %r.", item.get("objeto"))

    return JSONResponse({"mensaje": "Arte quitado de la galería."})


def _prompt_arte_biblioteca() -> str:
    """Cuerpo efectivo del prompt de arte de la Biblioteca; "" si no hay (nunca lanza)."""
    try:
        return (libtexto.cuerpo_efectivo(_PROMPT_ARTE_ID) or "").strip()
    except Exception:  # noqa: BLE001 -- sin biblioteca no rompemos el lanzamiento
        _log.warning("No se pudo leer el prompt de arte de la biblioteca.", exc_info=True)
        return ""


def _coste_medio_payload(modelo: str) -> dict:
    """Coste medio por imagen para `modelo` (fallback a la media GLOBAL si no hay muestras).

    Forma estable para el front ("~$X por imagen × N"): `{por_imagen, moneda, unidad,
    muestras, modelo, global}`. `por_imagen` es None si no hay ninguna muestra ni global.
    `global=True` indica que el dato es la media global de imagen (no la del modelo pedido).
    """
    dato = repos.coste_medio_imagen(modelo=modelo, limite=_VENTANA_COSTE)
    es_global = False
    if dato["muestras"] == 0 and modelo:
        # Sin historico del modelo: cae a la media global de imagen (cualquier modelo).
        dato = repos.coste_medio_imagen(modelo="", limite=_VENTANA_COSTE)
        es_global = True
    return {
        "por_imagen": dato["por_imagen"],
        "moneda": _MONEDA_COSTE,
        "unidad": "por_imagen",
        "muestras": dato["muestras"],
        "modelo": modelo or media._modelo(),
        "global": es_global or not modelo,
    }


async def generar_arte(request: Request) -> Response:
    """POST /api/artes/generar: lanza N imágenes de ARTE a mano para una marca -> generaciones.

    Cuerpo JSON:
      - `marca`   (obligatoria): marca del catálogo único.
      - `prompt`  (opcional): tema a ilustrar; si falta, se usa el prompt de arte de la
                   Biblioteca (`prompt/ilustrar`).
      - `modelo`  (opcional): id de un modelo de `GET /api/conexiones/imagen` (`modelos`);
                   si falta, el modelo configurado por defecto.
      - `n`       (opcional, def 1): nº de alternativas, 1..`_MAX_ALTERNATIVAS` (4).

    Reutiliza el camino de imagen (`lanzar_generacion_imagen`): crea N generaciones tipo
    `imagen` y las ejecuta en 2.º plano. Devuelve `{generaciones:[...], modelo, n, coste_medio}`
    para que el front sondee cada `GET /api/generaciones/{id}` y, al completarse, lea
    `resultado={id,url,modelo,coste_usd}` (la imagen se sirve en `/api/media/{id}`).
    400 si la marca/modelo/n son inválidos, falta prompt utilizable o no hay proveedor.
    """
    datos = await leer_json(request)

    marca = datos.get("marca")
    if not isinstance(marca, str) or not marca.strip() or not marcas.es_marca(marca.strip()):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    marca = marca.strip()

    modelo = datos.get("modelo")
    if modelo in (None, ""):
        modelo = ""
    elif not isinstance(modelo, str) or not media.modelo_valido(modelo):
        return JSONResponse({"error": "Modelo de imagen no reconocido."}, status_code=400)

    n_crudo = datos.get("n", 1)
    try:
        n = int(n_crudo)
    except (TypeError, ValueError):
        return JSONResponse({"error": "El número de imágenes no es válido."}, status_code=400)
    if n < 1 or n > _MAX_ALTERNATIVAS:
        return JSONResponse(
            {"error": f"El número de imágenes debe estar entre 1 y {_MAX_ALTERNATIVAS}."},
            status_code=400,
        )

    prompt = datos.get("prompt")
    prompt = prompt.strip() if isinstance(prompt, str) and prompt.strip() else _prompt_arte_biblioteca()
    if not prompt:
        return JSONResponse(
            {"error": "Falta el texto (prompt) para generar el arte."}, status_code=400
        )

    if not media.proveedor_configurado():
        return JSONResponse(
            {
                "error": "La generación de imagen no está configurada. Añade una clave "
                "de proveedor de imagen para activarla."
            },
            status_code=400,
        )

    autor = autor_de_peticion(request) or {}
    generaciones = [
        lanzar_generacion_imagen(prompt=prompt, modelo=modelo, marca=marca, autor=autor)
        for _ in range(n)
    ]
    return JSONResponse(
        {
            "generaciones": generaciones,
            "modelo": modelo or media._modelo(),
            "n": n,
            "coste_medio": _coste_medio_payload(modelo),
        }
    )


async def coste_medio(request: Request) -> Response:
    """GET /api/artes/coste-medio?modelo=: coste medio por imagen (USD) para estimar el gasto.

    Calcula la media de `coste_usd` de las últimas `_VENTANA_COSTE` (50) generaciones de
    imagen (ledger `gasto_ia`) del `modelo` pedido (o el configurado por defecto), con
    fallback a la media global si no hay historial del modelo. -> `{por_imagen, moneda,
    unidad, muestras, modelo, global}`; `por_imagen` None si aún no hay datos. El front lo
    multiplica por N.
    """
    modelo = request.query_params.get("modelo") or ""
    if modelo and not media.modelo_valido(modelo):
        return JSONResponse({"error": "Modelo de imagen no reconocido."}, status_code=400)
    return JSONResponse(_coste_medio_payload(modelo))


RUTAS = [
    Route("/api/artes", listar, methods=["GET"]),
    Route("/api/artes", crear, methods=["POST"]),
    Route("/api/artes/generar", generar_arte, methods=["POST"]),
    Route("/api/artes/coste-medio", coste_medio, methods=["GET"]),
    Route("/api/artes/{arte_id}", borrar, methods=["DELETE"]),
]
