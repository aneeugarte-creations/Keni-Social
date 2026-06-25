"""API Galería de ARTES: cataloga objetos de media para reutilizarlos (durables).

Un ARTE es una imagen del almacen de media (subida, generada con IA o trabajada en el
Estudio) que el equipo decide CONSERVAR para reutilizar en piezas. Catalogarla:
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

import asyncio
import json
import logging
from typing import AsyncIterator

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from .. import (
    agencias_fotos,
    almacen_media,
    autogen_stock,
    fotos_tunel,
    libprompts,
    marcas,
    media,
    repos,
    stock_fotos,
)
from .._http_json import leer_json
from ..dominio import extraccion_url, licencia_imagen
from ..seguridad import autor_de_peticion
from .media import lanzar_generacion_imagen

_log = logging.getLogger("keni_consola.artes")

# Tope de imagenes ALTERNATIVAS por lanzamiento manual de arte: cada una cuesta dinero (una
# llamada al proveedor), asi que se acota para evitar ráfagas/abuso. 1..4 basta para
# comparar variaciones de un mismo prompt.
_MAX_ALTERNATIVAS = 4
# Prompt base del arte en la Prompts (mismo id que la directiva del generador): si el
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
    cuerpo = await run_in_threadpool(
        _listar, q.get("marca") or None, q.get("tipo") or None, (q.get("q") or "").strip()
    )
    return JSONResponse(cuerpo)


def _listar(marca: str | None, tipo: str | None, busqueda: str) -> dict:
    artes = [
        _arte_a_dict(item)
        for item in repos.listar_media_catalogo(
            marca=marca,
            tipo=tipo,
            incluir_globales=True,
        )
    ]
    if busqueda:
        artes = [a for a in artes if _coincide_busqueda(a, busqueda)]
    return {"artes": artes}


def _crear(
    *,
    objeto: str,
    marca_cruda: object,
    tipo_crudo: object,
    titulo_crudo: object,
    etiquetas_crudas: object,
    autor: dict | None,
) -> tuple[int, dict]:
    if media.leer_media(objeto) is None:
        return 400, {"error": "Esa imagen no existe en el almacén."}

    marca, err = _validar_marca(marca_cruda)
    if err:
        return 400, {"error": err}

    tipo = tipo_crudo or _TIPO_DEFECTO
    if tipo not in _TIPOS:
        return 400, {"error": "Origen de arte no válido."}

    # Catalogar = conservar para reutilizar: promovemos el objeto a su carpeta física ANTES de la
    # idempotencia/insert, de modo que el catálogo guarda la key ya en su carpeta. Las fotos SUBIDAS
    # a mano forman la carpeta `subidas/` de la biblioteca unificada; las demás vías (estudio/IA) van
    # a `artes/`. La carpeta física coincide así con la carpeta lógica de la biblioteca.
    categoria = "subidas" if tipo == "subida" else "artes"
    objeto = almacen_media.promover_objeto(objeto, categoria)

    # Idempotente: el `objeto` es UNIQUE en la tabla. Si ya esta catalogado, devolvemos el
    # item existente (no duplicamos ni dejamos que el INSERT falle por la restriccion).
    if repos.existe_media_objeto(objeto):
        for item in repos.listar_media_catalogo():
            if item.get("objeto") == objeto:
                return 200, {"arte": _arte_a_dict(item)}

    titulo = (titulo_crudo or "").strip()[:_MAX_TITULO]
    etiquetas = _normalizar_etiquetas(etiquetas_crudas)

    # Las fotos SUBIDAS a mano forman la carpeta `subidas` de la biblioteca unificada (las demás
    # vías —estudio/IA— no son una carpeta de origen navegable, quedan sin clasificar).
    fuente = "subidas" if tipo == "subida" else ""

    arte = repos.crear_media_catalogo(
        objeto=objeto,
        tipo=tipo,
        marca=marca or "",
        titulo=titulo,
        etiquetas=json.dumps(etiquetas, ensure_ascii=False),
        fuente=fuente,
        autor=autor,
    )
    return 200, {"arte": _arte_a_dict(arte)}


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

    status, cuerpo = await run_in_threadpool(
        _crear,
        objeto=objeto,
        marca_cruda=datos.get("marca"),
        tipo_crudo=datos.get("tipo"),
        titulo_crudo=datos.get("titulo"),
        etiquetas_crudas=datos.get("etiquetas"),
        autor=autor_de_peticion(request),
    )
    return JSONResponse(cuerpo, status_code=status)


def _borrar(arte_id: str, purgar: bool) -> tuple[int, dict]:
    item = repos.borrar_media_catalogo(arte_id)
    if item is None:
        return 404, {"error": "Ese arte ya no está en la galería."}

    if purgar:
        try:
            almacen_media.borrar_objeto(item["objeto"])
        except Exception:  # noqa: BLE001 -- el descatalogado ya esta hecho; purgar es best-effort
            _log.exception("No se pudo purgar el binario del arte %r.", item.get("objeto"))

    return 200, {"mensaje": "Arte quitado de la galería."}


async def borrar(request: Request) -> Response:
    """DELETE /api/artes/{id}: descataloga un arte. Con `?purgar=1` borra el binario.

    Por defecto solo se quita del catalogo: el objeto queda en el almacen y el GC lo
    recogera si nadie lo referencia (umbral 24h). Con `purgar=1` se borra ademas el binario
    del almacen de inmediato (un fallo al purgar NO rompe el descatalogado).
    -> `{mensaje}` | 404.
    """
    arte_id = request.path_params["arte_id"]
    purgar = request.query_params.get("purgar") == "1"
    status, cuerpo = await run_in_threadpool(_borrar, arte_id, purgar)
    return JSONResponse(cuerpo, status_code=status)


def _prompt_arte_almacen() -> str:
    """Cuerpo efectivo del prompt de arte de la Prompts; "" si no hay (nunca lanza)."""
    try:
        return (libprompts.cuerpo_efectivo(_PROMPT_ARTE_ID) or "").strip()
    except Exception:  # noqa: BLE001 -- sin prompts no rompemos el lanzamiento
        _log.warning("No se pudo leer el prompt de arte de la prompts.", exc_info=True)
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
                   Prompts (`prompt/ilustrar`).
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

    status, cuerpo = await run_in_threadpool(
        _generar_arte,
        marca=marca,
        modelo=modelo,
        n=n,
        prompt_dado=datos.get("prompt"),
        autor=autor_de_peticion(request) or {},
    )
    return JSONResponse(cuerpo, status_code=status)


def _generar_arte(
    *, marca: str, modelo: str, n: int, prompt_dado: object, autor: dict
) -> tuple[int, dict]:
    prompt = (
        prompt_dado.strip()
        if isinstance(prompt_dado, str) and prompt_dado.strip()
        else _prompt_arte_almacen()
    )
    if not prompt:
        return 400, {"error": "Falta el texto (prompt) para generar el arte."}

    if not media.proveedor_configurado():
        return 400, {
            "error": "La generación de imagen no está configurada. Añade una clave "
            "de proveedor de imagen para activarla."
        }

    generaciones = [
        lanzar_generacion_imagen(prompt=prompt, modelo=modelo, marca=marca, autor=autor)
        for _ in range(n)
    ]
    return 200, {
        "generaciones": generaciones,
        "modelo": modelo or media._modelo(),
        "n": n,
        "coste_medio": _coste_medio_payload(modelo),
    }


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
    cuerpo = await run_in_threadpool(_coste_medio_payload, modelo)
    return JSONResponse(cuerpo)


# --------------------------------------------------------------------------- #
# FOTOS DE STOCK (ayuda visual, NUNCA publicable sin autorizar)                 #
# --------------------------------------------------------------------------- #
# Buscar fotos en APIs gratuitas para PROPONERLAS como alternativa a galería/subir/IA.
# Al adjuntar una, la pieza queda marcada `imagen_origen='stock'` y `imagen_autorizada=0`:
# se ve como ayuda visual (atenuada + watermark "SIN LICENCIA" en el front), `falta_imagen`
# sigue activo y el bloqueo infranqueable impide publicarla hasta que un humano la autorice.

# Tope de candidatas por proveedor en una búsqueda manual (la UI muestra varias para elegir).
_STOCK_LIMITE_DEF = 4
_STOCK_LIMITE_MAX = 12


def _buscar_stock(query: str, proveedor: str, limite: int, marca: str) -> dict:
    """Busca candidatas en los proveedores usables de una marca. Degradación honesta.

    Las claves (Pexels/Pixabay) son GLOBALES; los toggles de qué fuentes usa la marca sí
    son POR MARCA: la lista `proveedores` y la búsqueda reflejan lo habilitado para `marca`
    (o todas las disponibles si '').
    """
    proveedores = [
        stock_fotos.estado_fuente(p, marca)
        for p in stock_fotos.proveedores_disponibles(marca)
    ]
    if not query.strip():
        return {"proveedores": proveedores, "candidatos": []}
    try:
        if proveedor:
            candidatos = stock_fotos.buscar(query, proveedor, limite=limite)
        else:
            candidatos = stock_fotos.buscar_todos(query, limite_por=limite, marca=marca)
    except Exception:  # noqa: BLE001 -- una API caída no rompe la búsqueda; devolvemos lo que haya
        _log.exception("Fallo buscando fotos de stock (q=%r proveedor=%r).", query, proveedor)
        candidatos = []
    return {"proveedores": proveedores, "candidatos": candidatos}


async def buscar_stock(request: Request) -> Response:
    """GET /api/artes/stock/buscar?q=&proveedor=&limite=&marca= -> {proveedores, candidatos}.

    `marca` ('' = global) acota claves y fuentes habilitadas a esa marca; si llega una
    marca desconocida se responde 400 (igual que el resto de endpoints de artes).
    """
    q = (request.query_params.get("q") or "").strip()
    proveedor = (request.query_params.get("proveedor") or "").strip().lower()
    marca, err = _validar_marca(request.query_params.get("marca"))
    if err is not None:
        return JSONResponse({"error": err}, status_code=400)
    try:
        limite = int(request.query_params.get("limite") or _STOCK_LIMITE_DEF)
    except ValueError:
        limite = _STOCK_LIMITE_DEF
    limite = max(1, min(_STOCK_LIMITE_MAX, limite))
    cuerpo = await run_in_threadpool(_buscar_stock, q, proveedor, limite, marca or "")
    return JSONResponse(cuerpo)


def _adjuntar_stock(pieza_id: str, datos: dict) -> tuple[int, dict]:
    """Descarga una foto de stock (o la original del RSS) y la adjunta como AYUDA VISUAL.

    `usar_fuente=True` baja la imagen original del artículo (`imagen_fuente` de la pieza);
    si no, baja la `url` de la candidata elegida. En ambos casos la pieza queda
    `imagen_origen='stock'`, `imagen_autorizada=0` y `falta_imagen=1`: visible pero no publicable.
    """
    plat = repos.obtener_pieza_fila(pieza_id)
    if plat is None:
        return 404, {"error": "Esa pieza ya no existe."}

    usar_fuente = bool(datos.get("usar_fuente"))
    if usar_fuente:
        url = (plat.get("imagen_fuente") or "").strip()
        proveedor = "rss"
        if not url:
            return 400, {"error": "La pieza no trae imagen original de la fuente."}
    else:
        url = (datos.get("url") or "").strip()
        proveedor = (datos.get("proveedor") or "").strip().lower() or "stock"
        if not url:
            return 400, {"error": "Falta la URL de la foto a adjuntar."}

    try:
        actualizada = autogen_stock.adjuntar_candidata(
            pieza_id,
            url=url,
            proveedor=proveedor,
            autor=(datos.get("autor") or "").strip(),
            licencia=(datos.get("licencia") or "").strip(),
            credito_url=(datos.get("credito_url") or "").strip() or (url if usar_fuente else ""),
        )
    except extraccion_url.ExtraccionError as e:
        return 400, {"error": str(e)}
    if actualizada is None:
        return 404, {"error": "Esa pieza ya no existe."}
    return 200, {"plataforma": _plataforma_stock_a_dict(actualizada)}


async def adjuntar_stock(request: Request) -> Response:
    """POST /api/artes/stock/adjuntar {pieza_id, url|usar_fuente, proveedor, autor, licencia, credito_url}."""
    datos = await leer_json(request)
    pieza_id = (datos.get("pieza_id") or "").strip()
    if not pieza_id:
        return JSONResponse({"error": "Falta la pieza."}, status_code=400)
    status, cuerpo = await run_in_threadpool(_adjuntar_stock, pieza_id, datos)
    return JSONResponse(cuerpo, status_code=status)


def _autorizar_stock(pieza_id: str, autorizar: bool) -> tuple[int, dict]:
    """Marca/desmarca una foto de stock como autorizada para publicar (decisión HUMANA de derechos)."""
    plat = repos.obtener_pieza_fila(pieza_id)
    if plat is None:
        return 404, {"error": "Esa pieza ya no existe."}
    if (plat.get("imagen_origen") or "") != licencia_imagen.ORIGEN_STOCK:
        return 400, {"error": "Esta pieza no tiene una imagen de stock que autorizar."}
    # Autorizar: la imagen pasa a contar como real (limpia `falta_imagen`). Revocar: vuelve a faltar.
    campos = {"imagen_autorizada": bool(autorizar), "falta_imagen": not autorizar}
    actualizada = repos.actualizar_pieza_fila(pieza_id, campos)
    if actualizada is None:
        return 404, {"error": "Esa pieza ya no existe."}
    # ESPEJO de la decisión: la MISMA foto en otras redes son los mismos derechos, así que
    # autorizar/revocar una vez se aplica a TODAS las hermanas del mismo tema que llevan esa foto
    # de stock (no se obliga a autorizar red por red, lo que dejaba unas redes OK y otras no).
    # "Misma foto" se identifica de forma robusta (la `foto` puede diferir entre redes aunque la
    # imagen sea la misma): por `foto` igual, o `imagen_credito_url` igual, o la terna
    # (proveedor, autor, licencia) igual. Solo toca stock; no pisa imágenes propias ni publicadas.
    pub_id = (actualizada.get("publicacion_id") or "").strip()
    foto = (actualizada.get("foto") or "").strip()
    credito_url = (actualizada.get("imagen_credito_url") or "").strip()
    firma = (
        (actualizada.get("imagen_proveedor") or "").strip(),
        (actualizada.get("imagen_autor") or "").strip(),
        (actualizada.get("imagen_licencia") or "").strip(),
    )
    if pub_id and (foto or credito_url or any(firma)):
        for hermana in repos.listar_piezas_fila(pub_id):
            if hermana.get("id") == pieza_id or (hermana.get("estado") or "") == "publicado":
                continue
            if _misma_foto_stock(hermana, foto, credito_url, firma):
                repos.actualizar_pieza_fila(hermana["id"], campos)
    return 200, {"plataforma": _plataforma_stock_a_dict(actualizada)}


def _misma_foto_stock(
    hermana: dict, foto: str, credito_url: str, firma: tuple[str, str, str]
) -> bool:
    """True si la hermana lleva la MISMA foto de stock (por `foto`, crédito o terna proveedor/autor/licencia)."""
    if (hermana.get("imagen_origen") or "") != licencia_imagen.ORIGEN_STOCK:
        return False
    if foto and (hermana.get("foto") or "").strip() == foto:
        return True
    if credito_url and (hermana.get("imagen_credito_url") or "").strip() == credito_url:
        return True
    h_firma = (
        (hermana.get("imagen_proveedor") or "").strip(),
        (hermana.get("imagen_autor") or "").strip(),
        (hermana.get("imagen_licencia") or "").strip(),
    )
    return bool(any(firma)) and h_firma == firma


async def autorizar_stock(request: Request) -> Response:
    """POST /api/artes/stock/autorizar {pieza_id, autorizar=true}: confirma derechos y desbloquea."""
    datos = await leer_json(request)
    pieza_id = (datos.get("pieza_id") or "").strip()
    if not pieza_id:
        return JSONResponse({"error": "Falta la pieza."}, status_code=400)
    autorizar = datos.get("autorizar", True)
    autor = autor_de_peticion(request)
    _log.info("Autorización de imagen de stock pieza=%s autorizar=%s por=%s", pieza_id, autorizar, autor)
    status, cuerpo = await run_in_threadpool(_autorizar_stock, pieza_id, bool(autorizar))
    return JSONResponse(cuerpo, status_code=status)


def _plataforma_stock_a_dict(plat: dict | None) -> dict:
    """Subconjunto de campos de stock de una fila por plataforma (lo que la UI refresca)."""
    plat = plat or {}
    return {
        "id": plat.get("id", ""),
        "imagen_url": plat.get("imagen_url", ""),
        "foto": plat.get("foto", ""),
        "falta_imagen": bool(plat.get("falta_imagen")),
        "imagen_origen": plat.get("imagen_origen", ""),
        "imagen_proveedor": plat.get("imagen_proveedor", ""),
        "imagen_autor": plat.get("imagen_autor", ""),
        "imagen_licencia": plat.get("imagen_licencia", ""),
        "imagen_credito_url": plat.get("imagen_credito_url", ""),
        "imagen_autorizada": bool(plat.get("imagen_autorizada")),
    }


# --------------------------------------------------------------------------- #
# FOTOS LICENCIADAS DE AGENCIA (AFP): imagen PUBLICABLE con crédito obligatorio  #
# --------------------------------------------------------------------------- #
# A diferencia del stock gratuito (ayuda visual bloqueada hasta autorizar), AFP da licencia
# editorial: la foto se adjunta como `imagen_origen='licenciada'`, `imagen_autorizada=1`,
# `falta_imagen=0` (publicable directamente), conservando autor/crédito (BYLINE obligatorio).
# AFP es una fuente GLOBAL (no por marca): una sola credencial OAuth2 para todas.


def _buscar_agencias(query: str, limite: int) -> dict:
    """Busca fotos licenciadas en AFP. Degradación honesta: nunca lanza al cliente."""
    proveedores = [agencias_fotos.estado_fuente()]
    if not query.strip():
        return {"proveedores": proveedores, "candidatos": []}
    try:
        candidatos = agencias_fotos.buscar(query, limite=limite)
    except Exception:  # noqa: BLE001 -- AFP caída no rompe la búsqueda; devolvemos lo que haya
        _log.exception("Fallo buscando fotos de agencia (q=%r).", query)
        candidatos = []
    return {"proveedores": proveedores, "candidatos": candidatos}


async def buscar_agencias(request: Request) -> Response:
    """GET /api/artes/agencias/buscar?q=&limite= -> {proveedores:[estado_afp], candidatos:[...]}.

    Sin marca: AFP es global. `proveedores` lleva el estado de la fuente (disponible o pendiente
    por credencial). Cada candidato tiene la forma de stock: `{proveedor,url,thumb,autor,
    licencia,credito_url,titulo}`.
    """
    q = (request.query_params.get("q") or "").strip()
    try:
        limite = int(request.query_params.get("limite") or _STOCK_LIMITE_DEF)
    except ValueError:
        limite = _STOCK_LIMITE_DEF
    limite = max(1, min(_STOCK_LIMITE_MAX, limite))
    cuerpo = await run_in_threadpool(_buscar_agencias, q, limite)
    return JSONResponse(cuerpo)


def _adjuntar_agencias(pieza_id: str, datos: dict) -> tuple[int, dict]:
    """Descarga una foto de AFP y la adjunta como imagen LICENCIADA (publicable, con crédito)."""
    plat = repos.obtener_pieza_fila(pieza_id)
    if plat is None:
        return 404, {"error": "Esa pieza ya no existe."}

    url = (datos.get("url") or "").strip()
    if not url:
        return 400, {"error": "Falta la URL de la foto a adjuntar."}
    proveedor = (datos.get("proveedor") or "").strip().lower() or "afp"

    try:
        actualizada = autogen_stock.adjuntar_candidata(
            pieza_id,
            url=url,
            proveedor=proveedor,
            autor=(datos.get("autor") or "").strip(),
            licencia=(datos.get("licencia") or "").strip(),
            credito_url=(datos.get("credito_url") or "").strip(),
            origen=licencia_imagen.ORIGEN_LICENCIADA,
            autorizada=True,
            falta_imagen=False,
        )
    except extraccion_url.ExtraccionError as e:
        return 400, {"error": str(e)}
    if actualizada is None:
        return 404, {"error": "Esa pieza ya no existe."}
    return 200, {"plataforma": _plataforma_stock_a_dict(actualizada)}


async def adjuntar_agencias(request: Request) -> Response:
    """POST /api/artes/agencias/adjuntar {pieza_id, url, proveedor, autor, licencia, credito_url}.

    Adjunta la foto como `imagen_origen='licenciada'` (publicable, sin bloqueo de derechos) y la
    reparte a las redes hermanas en gris con su crédito.
    """
    datos = await leer_json(request)
    pieza_id = (datos.get("pieza_id") or "").strip()
    if not pieza_id:
        return JSONResponse({"error": "Falta la pieza."}, status_code=400)
    status, cuerpo = await run_in_threadpool(_adjuntar_agencias, pieza_id, datos)
    return JSONResponse(cuerpo, status_code=status)


# --------------------------------------------------------------------------- #
# GALERÍA LOCAL «PROPIO» (túnel keni-fotos): foto PROPIA del equipo, publicable  #
# --------------------------------------------------------------------------- #
# Fuente paralela a stock/agencias, pero las fotos NO viven en la nube: están en el equipo de
# la persona, expuestas por la app de escritorio keni-fotos sobre un WebSocket saliente
# (`fotos_tunel`). El registro es POR MARCA (cruza usuarios): cada dispositivo declara a qué marcas
# comparte su galería. El backend hace fan-out de la búsqueda a las apps que comparten la marca de
# la pieza y, al adjuntar, pide el ORIGINAL por el túnel, lo sube a keni-media y lo liga como foto
# propia (`imagen_origen='propia'`, publicable). Opera para CUALQUIER marca con ≥1 dispositivo
# compartiendo a ella; sin dispositivos, la fuente sale `disponible=False` y sin candidatos.

# Origen de imagen de la galería local: foto PROPIA del equipo (no stock ni licenciada -> publicable).
_ORIGEN_PROPIO = "propia"


def _proveedor_propio(*, disponible: bool, dispositivos: int, motivo: str = "") -> dict:
    """Estado de la fuente «Propio» (misma forma que `estado_fuente` de stock + `dispositivos`)."""
    return {
        "proveedor": "propio",
        "nombre": "Galería local",
        "requiere_clave": False,
        "disponible": disponible,
        "activa": True,
        "motivo": motivo if motivo else ("" if disponible else "Sin dispositivos conectados"),
        "dispositivos": dispositivos,
    }


def _candidato_propio(crudo: dict) -> dict:
    """Convierte un candidato del túnel (forma del contrato §1) a la forma de candidato de stock §2."""
    thumb = crudo.get("thumb_b64") or ""
    partes = [
        p
        for p in (crudo.get("nombre"), crudo.get("fase"), crudo.get("en_foco"))
        if isinstance(p, str) and p.strip()
    ]
    return {
        "proveedor": "propio",
        "url": thumb,
        "thumb": thumb,
        "autor": "Galería local",
        "licencia": "Propio",
        "credito_url": "",
        "titulo": " · ".join(partes),
        "galeria_id": crudo.get("galeria_id") or "",
        "archivo": crudo.get("archivo") or "",
        "dispositivo": crudo.get("dispositivo") or "",
    }


async def _buscar_propio(q: str, limite: int, marca: str) -> dict:
    """Búsqueda «Propio»: fan-out a las apps que comparten `marca` (cualquier dueño)."""
    marca = (marca or "").strip()
    conns = await run_in_threadpool(fotos_tunel.conexiones_de_marca, marca) if marca else []
    n = len(conns)
    disponible = n > 0
    proveedor = _proveedor_propio(disponible=disponible, dispositivos=n)
    if not disponible or not q.strip():
        return {"proveedores": [proveedor], "candidatos": []}
    crudos = await fotos_tunel.buscar(marca, q, limite)
    return {"proveedores": [proveedor], "candidatos": [_candidato_propio(c) for c in crudos]}


async def buscar_propio(request: Request) -> Response:
    """GET /api/artes/propio/buscar?q=&limite=&marca= -> {proveedores, candidatos}.

    Opera para cualquier `marca`: `disponible` refleja si hay ≥1 dispositivo compartiendo a esa
    marca (de cualquier dueño); los candidatos se agregan de esas apps y se trocean a `limite`.
    """
    q = (request.query_params.get("q") or "").strip()
    marca = (request.query_params.get("marca") or "").strip()
    try:
        limite = int(request.query_params.get("limite") or _STOCK_LIMITE_DEF)
    except ValueError:
        limite = _STOCK_LIMITE_DEF
    limite = max(1, min(_STOCK_LIMITE_MAX, limite))
    cuerpo = await _buscar_propio(q, limite, marca)
    return JSONResponse(cuerpo)


# Listar una galería entera (carpeta de partido) trae muchos más keepers que una búsqueda puntual.
_GALERIA_LIMITE_DEF = 120
_GALERIA_LIMITE_MAX = 400


async def _galeria_propio(galeria_id: str, dispositivo: str, limite: int, marca: str) -> dict:
    """Lista los keepers de una galería conectada como candidatos (forma de candidato de stock)."""
    marca = (marca or "").strip()
    if not marca or not galeria_id:
        return {"candidatos": []}
    crudos = await fotos_tunel.galeria(marca, galeria_id, dispositivo, limite)
    return {"candidatos": [_candidato_propio(c) for c in crudos]}


async def galeria_propio(request: Request) -> Response:
    """GET /api/artes/propio/galeria?galeria_id=&marca=&dispositivo=&limite= -> {candidatos}.

    Lista los KEEPERS de una galería (partido) conectada por el túnel keni-fotos, para navegarla como
    una carpeta. Misma forma de candidato que `propio/buscar` (con `galeria_id`/`archivo`/`dispositivo`
    para luego guardar el original). Degrada a `{candidatos:[]}` si no hay dispositivo de la marca o la
    app no responde.
    """
    q = request.query_params
    galeria_id = (q.get("galeria_id") or "").strip()
    marca = (q.get("marca") or "").strip()
    dispositivo = (q.get("dispositivo") or "").strip()
    try:
        limite = int(q.get("limite") or _GALERIA_LIMITE_DEF)
    except ValueError:
        limite = _GALERIA_LIMITE_DEF
    limite = max(1, min(_GALERIA_LIMITE_MAX, limite))
    cuerpo = await _galeria_propio(galeria_id, dispositivo, limite, marca)
    return JSONResponse(cuerpo)


def _subir_propio(pieza_id: str, datos: bytes) -> dict | None:
    """Sube los bytes del original a keni-media y los liga a la pieza como foto PROPIA (publicable)."""
    return autogen_stock.adjuntar_bytes(
        pieza_id,
        datos,
        proveedor="propio",
        origen=_ORIGEN_PROPIO,
        autorizada=True,
        falta_imagen=False,
    )


async def _adjuntar_propio(
    pieza_id: str, galeria_id: str, archivo: str, dispositivo: str, marca: str
) -> tuple[int, dict]:
    """Pide el original (a un dispositivo que comparte `marca`), lo sube a keni-media y lo adjunta a la pieza."""
    marca = (marca or "").strip()
    if not marca:
        return 400, {"error": "Falta la marca."}
    plat = await run_in_threadpool(repos.obtener_pieza_fila, pieza_id)
    if plat is None:
        return 404, {"error": "Esa pieza ya no existe."}
    try:
        datos, _mime = await fotos_tunel.pedir_original(marca, galeria_id, archivo, dispositivo)
    except fotos_tunel.TunelError as e:
        return 400, {"error": str(e)}
    try:
        actualizada = await run_in_threadpool(_subir_propio, pieza_id, datos)
    except extraccion_url.ExtraccionError as e:
        return 400, {"error": str(e)}
    if actualizada is None:
        return 404, {"error": "Esa pieza ya no existe."}
    return 200, {"plataforma": _plataforma_stock_a_dict(actualizada)}


async def adjuntar_propio(request: Request) -> Response:
    """POST /api/artes/propio/adjuntar {pieza_id, galeria_id, archivo, marca, dispositivo?}."""
    datos = await leer_json(request)
    pieza_id = (datos.get("pieza_id") or "").strip()
    galeria_id = (datos.get("galeria_id") or "").strip()
    archivo = (datos.get("archivo") or "").strip()
    dispositivo = (datos.get("dispositivo") or "").strip()
    marca = (datos.get("marca") or "").strip()
    if not pieza_id:
        return JSONResponse({"error": "Falta la pieza."}, status_code=400)
    if not galeria_id or not archivo:
        return JSONResponse({"error": "Falta la foto a adjuntar."}, status_code=400)
    status, cuerpo = await _adjuntar_propio(pieza_id, galeria_id, archivo, dispositivo, marca)
    return JSONResponse(cuerpo, status_code=status)


async def rafaga_propio(request: Request) -> Response:
    """GET /api/artes/propio/rafaga?galeria_id=&archivo=&marca=&dispositivo= -> {fotos:[{archivo,thumb}]}.

    Fotos del MISMO burst (ráfaga) del keeper que `archivo`, por el túnel keni-fotos, para navegarlas
    como thumbs antes de elegir cuál guardar. Degrada a `{fotos:[]}` si no hay dispositivo de la marca
    o la app no soporta/responde la ráfaga.
    """
    q = request.query_params
    marca = (q.get("marca") or "").strip()
    galeria_id = (q.get("galeria_id") or "").strip()
    archivo = (q.get("archivo") or "").strip()
    dispositivo = (q.get("dispositivo") or "").strip()
    if not marca or not galeria_id or not archivo:
        return JSONResponse({"fotos": []})
    fotos = await fotos_tunel.rafaga(marca, galeria_id, archivo, dispositivo)
    return JSONResponse({"fotos": fotos})


async def dispositivos_propio(request: Request) -> Response:
    """GET /api/artes/propio/dispositivos -> {dispositivos:[{usuario, online, dispositivo?, marcas?, galerias?}]}.

    Usuarios REGISTRADOS en keni-fotos (token de escritorio) con flag `online`. NO se filtra por
    marca: el listado es de quién está dado de alta y conectado; la marca filtra la BÚSQUEDA."""
    dispositivos = await run_in_threadpool(fotos_tunel.dispositivos_registrados)
    return JSONResponse({"dispositivos": dispositivos})


# Keepalive del SSE de dispositivos: un comentario `: ping` cada 20 s mantiene viva la conexión
# inactiva para que el proxy (Traefik) no la corte. Menor que su idle timeout.
_SSE_KEEPALIVE = 20.0


async def _frame_dispositivos() -> str:
    """Frame SSE (`data: <json>\\n\\n`) con el snapshot de dispositivos registrados (online/offline)."""
    dispositivos = await run_in_threadpool(fotos_tunel.dispositivos_registrados)
    cuerpo = json.dumps({"dispositivos": dispositivos}, ensure_ascii=False)
    return f"data: {cuerpo}\n\n"


async def _eventos_dispositivos() -> AsyncIterator[str]:
    """Stream SSE: snapshot inicial + un snapshot nuevo por cada cambio del registro del túnel.

    Se suscribe al pub/sub LOCAL de `fotos_tunel` (que un NOTIFY `tunel_cambio` de cualquier worker
    dispara): ante cada aviso (alta/baja/cambio de marcas) reenvía el snapshot vigente. Sin cambios,
    emite un comentario keepalive cada `_SSE_KEEPALIVE` s. Se da de baja al cerrarse el generador.
    """
    cola = fotos_tunel.suscribir()
    try:
        yield await _frame_dispositivos()
        while True:
            try:
                await asyncio.wait_for(cola.get(), _SSE_KEEPALIVE)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            yield await _frame_dispositivos()
    finally:
        fotos_tunel.desuscribir(cola)


async def eventos_propio(request: Request) -> Response:
    """GET /api/artes/propio/eventos -> stream SSE de dispositivos registrados (push en vivo).

    Sustituye al sondeo: manda un snapshot inicial (`{dispositivos:[...]}`, misma forma que
    `GET /api/artes/propio/dispositivos`) y reenvía el snapshot cada vez que un dispositivo
    conecta/desconecta o cambia las marcas que comparte. Autenticado por la sesión del SPA (cookie).
    """
    return StreamingResponse(
        _eventos_dispositivos(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


RUTAS = [
    Route("/api/artes", listar, methods=["GET"]),
    Route("/api/artes", crear, methods=["POST"]),
    Route("/api/artes/generar", generar_arte, methods=["POST"]),
    Route("/api/artes/coste-medio", coste_medio, methods=["GET"]),
    Route("/api/artes/stock/buscar", buscar_stock, methods=["GET"]),
    Route("/api/artes/stock/adjuntar", adjuntar_stock, methods=["POST"]),
    Route("/api/artes/stock/autorizar", autorizar_stock, methods=["POST"]),
    Route("/api/artes/agencias/buscar", buscar_agencias, methods=["GET"]),
    Route("/api/artes/agencias/adjuntar", adjuntar_agencias, methods=["POST"]),
    Route("/api/artes/propio/buscar", buscar_propio, methods=["GET"]),
    Route("/api/artes/propio/adjuntar", adjuntar_propio, methods=["POST"]),
    Route("/api/artes/propio/rafaga", rafaga_propio, methods=["GET"]),
    Route("/api/artes/propio/galeria", galeria_propio, methods=["GET"]),
    Route("/api/artes/propio/dispositivos", dispositivos_propio, methods=["GET"]),
    Route("/api/artes/propio/eventos", eventos_propio, methods=["GET"]),
    Route("/api/artes/{arte_id}", borrar, methods=["DELETE"]),
]
