"""API Dashboard "Marcas" (`GET /api/marcas`, SOLO ADMIN): una vista única por marca.

Marcas es de POSTPROXY (las métricas de Metricool viven en Analíticas, no aquí). Una
sola lista: por cada marca, una fila de sumatorio y, debajo, una fila por red con sus
números (seguidores / posts / posts-día) y su estado de conexión, para conectarla o
desconectarla. Los números salen de los snapshots de Postproxy de cada cuenta CONECTADA;
las redes sin conectar aparecen con números a null y un botón de conectar.

PRINCIPIO RECTOR: el endpoint NUNCA debe cascar. Si Postproxy falla (config incompleta,
red caída), esa parte DEGRADA a null/desconectado y NUNCA inventa ceros (ADR 0005). Los
secretos NUNCA salen (solo estado/pista, ya filtrados por los helpers de `api.conexiones`).

Las redes son las del catálogo Postproxy; se EXCLUYE `google_business` por no ser una red
de publicación de contenido editorial en el alcance del piloto (añadirla = a `_REDES_DASHBOARD`).
"""

from __future__ import annotations

from datetime import UTC, datetime

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from keni_metricas.fuentes import postproxy as _pp_cliente
from keni_shared import marcas as _km
from keni_shared.cliente import normalizar_etiqueta_investigacion, normalizar_tipo
from keni_shared.io_atomico import escribir_atomico

from .. import permisos
from .._http_json import leer_json
from . import conexiones as _conexiones

# Mensaje de rechazo (mismo que conexiones: vista de estado de conexiones globales).
_MSG_SOLO_ADMIN = "Solo un administrador puede ver el panel de marcas (estado de conexiones)."

# Redes que pinta el dashboard: catálogo Postproxy SIN google_business (ver módulo).
_REDES_DASHBOARD: tuple[str, ...] = tuple(
    p for p in _pp_cliente.PLATAFORMAS if p != "google_business"
)


def _stats_perfil(api_key: str, perfil_id: str) -> dict:
    """Números de un perfil desde Postproxy ({seguidores, posts_totales, posts_dia}); defensivo."""
    try:
        _ok, _m, st = _pp_cliente.stats_perfil(api_key, perfil_id)
    except Exception:  # noqa: BLE001 -- el endpoint nunca debe cascar
        return {"seguidores": None, "posts_totales": None, "posts_dia": None}
    return st


def _fila_marca(mid: str, id_canonico: str, etiqueta: str, api_key: str, pp_marca: dict) -> dict:
    """Una marca: sus redes (estado + números) y el sumatorio. Todo desde Postproxy.

    `mid` es el `id_metricas` (clave de Postproxy/canal); `id_canonico` es el `id` del
    catálogo (clave del CRUD). Se exponen ambos: las acciones de red/canal usan `marca`
    (=id_metricas) y las de editar/borrar la marca usan `id` (=canónico).
    """
    grupo = pp_marca.get("profile_group_id")
    canal = pp_marca.get("canal") or "metricool"

    # Perfiles conectados, indexados por plataforma (primer perfil gana).
    perfiles: dict[str, dict] = {}
    if api_key and grupo:
        try:
            ok, _msg, lista = _pp_cliente.listar_perfiles(api_key, grupo)
        except Exception:  # noqa: BLE001 -- defensivo
            ok, lista = False, []
        if ok:
            for p in lista:
                plat = p.get("platform")
                if isinstance(plat, str) and plat not in perfiles:
                    perfiles[plat] = p

    redes: list[dict] = []
    tot_seg = tot_posts = 0
    suma_dia = 0.0
    hay_seg = hay_posts = hay_dia = False

    for plataforma in _REDES_DASHBOARD:
        perfil = perfiles.get(plataforma)
        if perfil is None:
            redes.append(
                {
                    "plataforma": plataforma,
                    "conectado": False,
                    "estado": None,
                    "perfil_id": None,
                    "nombre_cuenta": None,
                    "seguidores": None,
                    "posts_totales": None,
                    "posts_dia": None,
                }
            )
            continue

        pid = perfil.get("id")
        st = _stats_perfil(api_key, pid) if isinstance(pid, str) else {}
        seg = st.get("seguidores")
        posts = st.get("posts_totales")
        if posts is None:
            posts = perfil.get("post_count")  # respaldo: posts gestionados por Postproxy
        dia = st.get("posts_dia")

        if isinstance(seg, int):
            tot_seg += seg
            hay_seg = True
        if isinstance(posts, int):
            tot_posts += posts
            hay_posts = True
        if isinstance(dia, (int, float)):
            suma_dia += dia
            hay_dia = True

        redes.append(
            {
                "plataforma": plataforma,
                "conectado": True,
                "estado": perfil.get("status"),
                "perfil_id": pid,
                "nombre_cuenta": perfil.get("name"),
                "seguidores": seg if isinstance(seg, int) else None,
                "posts_totales": posts if isinstance(posts, int) else None,
                "posts_dia": dia if isinstance(dia, (int, float)) else None,
            }
        )

    marca_cat = _km.marca_de(id_canonico)
    return {
        "marca": mid,
        "id": id_canonico,
        "etiqueta": etiqueta,
        # 'noticias' (pasa por investigación) o 'propio' (contenido propio): editable en el form.
        "tipo": marca_cat.tipo if marca_cat is not None else "noticias",
        # Nombre del panel de investigación de esta marca (p.ej. "Curiosidades"); "Noticias" por defecto.
        "etiqueta_investigacion": (
            marca_cat.etiqueta_investigacion if marca_cat is not None else "Noticias"
        ),
        "canal_publicacion": canal,
        "postproxy": {"conectado": bool(grupo), "profile_group_id": grupo},
        "redes": redes,
        "total": {
            "seguidores": tot_seg if hay_seg else None,
            "posts_totales": tot_posts if hay_posts else None,
            "posts_dia": (round(suma_dia, 1) if hay_dia else None),
        },
    }


def _construir_dashboard() -> dict:
    """Arma la vista de Marcas: por marca, sus redes (estado + números) y el sumatorio.

    Una llamada a Postproxy por cuenta conectada (el handler lo corre en threadpool). Cada
    proveedor degrada por separado a null/desconectado si falla; nunca casca."""
    from keni_shared import marcas as _marcas_catalogo

    estado_pp = _conexiones.estado_postproxy()
    pp_por_marca = {m["marca"]: m for m in estado_pp.get("marcas", [])}
    api_key = _conexiones._postproxy_api_key(_conexiones._config_existente())

    filas: list[dict] = []
    tot_seg = tot_posts = 0
    suma_dia = 0.0
    hay_seg = hay_posts = hay_dia = False

    for mid, etiqueta in _marcas_catalogo.opciones_metricas():
        m_obj = _marcas_catalogo.marca_por_id_metricas(mid)
        id_canonico = m_obj.id if m_obj is not None else mid
        fila = _fila_marca(mid, id_canonico, etiqueta, api_key, pp_por_marca.get(mid, {}))
        filas.append(fila)
        t = fila["total"]
        if isinstance(t["seguidores"], int):
            tot_seg += t["seguidores"]
            hay_seg = True
        if isinstance(t["posts_totales"], int):
            tot_posts += t["posts_totales"]
            hay_posts = True
        if isinstance(t["posts_dia"], (int, float)):
            suma_dia += t["posts_dia"]
            hay_dia = True

    return {
        "generado_en": datetime.now(UTC).isoformat(timespec="seconds"),
        "totales": {
            "seguidores": tot_seg if hay_seg else None,
            "posts_totales": tot_posts if hay_posts else None,
            "posts_dia": (round(suma_dia, 1) if hay_dia else None),
        },
        "marcas": filas,
    }


async def dashboard(request: Request) -> Response:
    """GET /api/marcas: vista única de marcas × redes (estado + números). SOLO ADMIN (#153).

    Nunca casca: lo que falte va a null/desconectado. En threadpool: las llamadas a
    Postproxy son síncronas y no deben bloquear el event loop.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    try:
        cuerpo = await run_in_threadpool(_construir_dashboard)
    except Exception:  # noqa: BLE001 -- última red de seguridad: nunca un 500 crudo
        return JSONResponse(
            {"error": "No se pudo construir el panel de marcas."}, status_code=500
        )
    return JSONResponse(cuerpo)


# --------------------------------------------------------------------------- #
# CRUD del CATÁLOGO de marcas (fuente única editable). SOLO ADMIN (#153).      #
#                                                                             #
# La fuente única vive en un fichero editable bajo /data (`keni_shared.marcas`,
# `ruta_editable()`). El CRUD lo reescribe ENTERO de forma atómica y recarga el
# catálogo en caliente (`marcas.recargar()`); el resto de procesos lo ven por su
# `mtime`. Crear una marca NO crea sus credenciales (eso se conecta luego en el
# panel); borrarla NO toca sus credenciales (quedan inertes).
# --------------------------------------------------------------------------- #

import re as _re

_MSG_CRUD_ADMIN = "Solo un administrador puede gestionar las marcas."
_RE_ID = _re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_RE_ID_METRICAS = _re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")
# Sin acentos en los ids: traducción mínima para auto-derivar el slug desde la etiqueta.
_ACENTOS = str.maketrans("áàäâãéèëêíìïîóòöôõúùüûñç", "aaaaaeeeeiiiiooooouuuunc")


def _slug(texto: str, sep: str) -> str:
    """Normaliza a slug (`a-z0-9` + `sep`): minúsculas, sin acentos, separadores colapsados."""
    base = texto.strip().lower().translate(_ACENTOS)
    base = _re.sub(r"[^a-z0-9]+", sep, base)
    return base.strip(sep)


def _catalogo_actual() -> list[dict]:
    """Catálogo vigente como lista de dicts {id, etiqueta, id_metricas, tipo, etiqueta_investigacion}."""
    return [
        {
            "id": m.id,
            "etiqueta": m.etiqueta,
            "id_metricas": m.id_metricas,
            "tipo": m.tipo,
            "etiqueta_investigacion": m.etiqueta_investigacion,
        }
        for m in _km.catalogo()
    ]


def _serializar_marcas(marcas: list[dict]) -> str:
    """Serializa el catálogo a TOML (`[[marca]]`). Escapa comillas/backslash en los valores."""
    def esc(v: str) -> str:
        return v.replace("\\", "\\\\").replace('"', '\\"')

    cabecera = (
        "# Catálogo de marcas de Keni — fuente única, editable desde la consola.\n"
        "# Generado automáticamente; edítalo desde la página de Marcas, no a mano.\n"
    )
    bloques = []
    for m in marcas:
        bloques.append(
            "[[marca]]\n"
            f'id = "{esc(m["id"])}"\n'
            f'etiqueta = "{esc(m["etiqueta"])}"\n'
            f'id_metricas = "{esc(m["id_metricas"])}"\n'
            f'tipo = "{esc(normalizar_tipo(m.get("tipo")))}"\n'
            f'etiqueta_investigacion = '
            f'"{esc(normalizar_etiqueta_investigacion(m.get("etiqueta_investigacion")))}"\n'
        )
    return cabecera + "\n" + "\n".join(bloques)


def _persistir(marcas: list[dict]) -> Response | None:
    """Escribe el catálogo entero de forma atómica y recarga en caliente. None si OK."""
    ruta = _km.ruta_editable()
    if ruta is None:
        return JSONResponse(
            {"error": "El almacenamiento de marcas no está configurado (falta KENI_DATA_DIR)."},
            status_code=503,
        )
    try:
        escribir_atomico(ruta, _serializar_marcas(marcas), prefijo=".marcas-", sufijo=".toml.tmp")
    except OSError:
        return JSONResponse({"error": "No se pudo guardar el catálogo de marcas."}, status_code=500)
    _km.recargar()
    return None


async def catalogo_listar(request: Request) -> Response:
    """GET /api/marcas/catalogo: el catálogo editable (id, etiqueta, id_metricas). SOLO ADMIN."""
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_CRUD_ADMIN)
    return JSONResponse({"marcas": _catalogo_actual()})


async def catalogo_crear(request: Request) -> Response:
    """POST /api/marcas/catalogo: crea una marca `{etiqueta, id?, id_metricas?}`. SOLO ADMIN.

    `id` se auto-deriva de la etiqueta (slug-guion) si no viene; `id_metricas` del id
    (guion_bajo) si no viene. Valida formato y unicidad de `id` e `id_metricas`.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_CRUD_ADMIN)
    datos = await leer_json(request)
    etiqueta = datos.get("etiqueta")
    if not isinstance(etiqueta, str) or not etiqueta.strip():
        return JSONResponse({"error": "Falta el nombre (etiqueta) de la marca."}, status_code=400)
    etiqueta = etiqueta.strip()
    bruto_id = datos.get("id")
    mid = _slug(bruto_id, "-") if isinstance(bruto_id, str) and bruto_id.strip() else _slug(etiqueta, "-")
    bruto_im = datos.get("id_metricas")
    id_metricas = (
        _slug(bruto_im, "_") if isinstance(bruto_im, str) and bruto_im.strip() else mid.replace("-", "_")
    )
    if not _RE_ID.match(mid):
        return JSONResponse({"error": "El id de la marca no es válido (usa minúsculas y guiones)."}, status_code=400)
    if not _RE_ID_METRICAS.match(id_metricas):
        return JSONResponse({"error": "El id_metricas no es válido (usa minúsculas y guiones_bajos)."}, status_code=400)

    catalogo = _catalogo_actual()
    if any(m["id"] == mid for m in catalogo):
        return JSONResponse({"error": f"Ya existe una marca con id {mid!r}."}, status_code=409)
    if any(m["id_metricas"] == id_metricas for m in catalogo):
        return JSONResponse({"error": f"Ya existe una marca con id_metricas {id_metricas!r}."}, status_code=409)

    nueva = {
        "id": mid,
        "etiqueta": etiqueta,
        "id_metricas": id_metricas,
        "tipo": normalizar_tipo(datos.get("tipo")),
        "etiqueta_investigacion": normalizar_etiqueta_investigacion(datos.get("etiqueta_investigacion")),
    }
    if (err := _persistir([*catalogo, nueva])) is not None:
        return err
    return JSONResponse({"marca": nueva, "mensaje": f"Marca {etiqueta!r} creada."}, status_code=201)


async def catalogo_editar(request: Request) -> Response:
    """PUT /api/marcas/catalogo/{id}: edita `etiqueta` y/o `id_metricas` de una marca. SOLO ADMIN.

    El `id` canónico NO se cambia (es la clave estable que referencia el contenido).
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_CRUD_ADMIN)
    mid = request.path_params["id"]
    catalogo = _catalogo_actual()
    actual = next((m for m in catalogo if m["id"] == mid), None)
    if actual is None:
        return JSONResponse({"error": "Marca desconocida."}, status_code=404)
    datos = await leer_json(request)

    etiqueta = actual["etiqueta"]
    if "etiqueta" in datos:
        if not isinstance(datos["etiqueta"], str) or not datos["etiqueta"].strip():
            return JSONResponse({"error": "El nombre (etiqueta) no puede quedar vacío."}, status_code=400)
        etiqueta = datos["etiqueta"].strip()

    id_metricas = actual["id_metricas"]
    if "id_metricas" in datos:
        cand = _slug(str(datos["id_metricas"] or ""), "_")
        if not _RE_ID_METRICAS.match(cand):
            return JSONResponse({"error": "El id_metricas no es válido."}, status_code=400)
        if any(m["id_metricas"] == cand and m["id"] != mid for m in catalogo):
            return JSONResponse({"error": f"Ya existe una marca con id_metricas {cand!r}."}, status_code=409)
        id_metricas = cand

    tipo = normalizar_tipo(datos["tipo"]) if "tipo" in datos else actual.get("tipo", "noticias")
    etiqueta_investigacion = (
        normalizar_etiqueta_investigacion(datos["etiqueta_investigacion"])
        if "etiqueta_investigacion" in datos
        else actual.get("etiqueta_investigacion", "Noticias")
    )
    actualizado = {
        "id": mid,
        "etiqueta": etiqueta,
        "id_metricas": id_metricas,
        "tipo": tipo,
        "etiqueta_investigacion": etiqueta_investigacion,
    }
    nuevo = [actualizado if m["id"] == mid else m for m in catalogo]
    if (err := _persistir(nuevo)) is not None:
        return err
    return JSONResponse({"marca": actualizado, "mensaje": "Marca actualizada."})


async def catalogo_borrar(request: Request) -> Response:
    """DELETE /api/marcas/catalogo/{id}: elimina una marca del catálogo. SOLO ADMIN.

    No se permite borrar la ÚLTIMA marca (el catálogo no puede quedar vacío). No toca las
    credenciales de la marca (quedan inertes en el config; conéctala de nuevo si la recreas).
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_CRUD_ADMIN)
    mid = request.path_params["id"]
    catalogo = _catalogo_actual()
    if not any(m["id"] == mid for m in catalogo):
        return JSONResponse({"error": "Marca desconocida."}, status_code=404)
    if len(catalogo) <= 1:
        return JSONResponse({"error": "No puedes borrar la última marca."}, status_code=400)
    nuevo = [m for m in catalogo if m["id"] != mid]
    if (err := _persistir(nuevo)) is not None:
        return err
    return JSONResponse({"mensaje": "Marca eliminada."})


RUTAS = [
    Route("/api/marcas", dashboard, methods=["GET"]),
    Route("/api/marcas/catalogo", catalogo_listar, methods=["GET"]),
    Route("/api/marcas/catalogo", catalogo_crear, methods=["POST"]),
    Route("/api/marcas/catalogo/{id}", catalogo_editar, methods=["PUT"]),
    Route("/api/marcas/catalogo/{id}", catalogo_borrar, methods=["DELETE"]),
]
