"""Tools del MCP de tablero. Se registran contra un `ClienteConsola`.

Cada tool es una accion del community manager sobre el tablero, expresada en lenguaje
natural y mapeada a la API de la Consola. ESCRITURA real (a diferencia de keni-metricas):
el humano sigue al mando (es el quien le pide a Claude que cree/mueva), pero el sistema
puede mutar el tablero. Toda salida es un dict JSON-serializable; los errores salen como
`{"error": "..."}` en espanol (nunca un traceback).

Estados de una fila por plataforma (el "carril" del tablero):
    pendiente -> en_curso -> en_revision -> aprobado -> programado -> publicado
"mover" una pieza = cambiar el estado de su fila por plataforma. Cruzar a `aprobado`/
`publicado` dispara los eventos internos/webhooks de la Consola (no hay que hacer nada extra).
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .cliente import ClienteConsola, ErrorConsola

# Estados validos de una fila por plataforma (espejo de `estados.ESTADOS_CONTENIDO_PLATAFORMA`
# de la Consola). Se valida aqui para dar un error claro ANTES de tocar la red.
ESTADOS_PLATAFORMA = (
    "pendiente",
    "en_curso",
    "en_revision",
    "aprobado",
    "programado",
    "publicado",
)
ESTADOS_CONTENIDO = ("pendiente", "en_curso", "hecha")
FLUJOS = ("importante", "evergreen", "evento")
CLASES = ("contenido", "tarea")


def _resumen_item(item: dict[str, Any]) -> dict[str, Any]:
    """Vista compacta de un item del tablero (lo justo para que el modelo razone/encadene)."""
    return {
        "id": item.get("id"),
        "titulo": item.get("titulo"),
        "clase": item.get("clase"),
        "flujo": item.get("flujo"),
        "marca": item.get("marca"),
        "marca_nombre": item.get("marca_nombre"),
        "prioridad": item.get("prioridad"),
        "estado": item.get("estado"),
        "fecha_objetivo": item.get("fecha_objetivo"),
        "fecha_entrega": item.get("fecha_entrega"),
        "responsable_nombre": item.get("responsable_nombre"),
        "vencido": item.get("vencido"),
        "plataformas": [
            {
                "id": p.get("id"),
                "red": p.get("red"),
                "red_nombre": p.get("red_nombre"),
                "estado": p.get("estado"),
            }
            for p in item.get("plataformas", [])
        ],
    }


def registrar(mcp: FastMCP, cliente: ClienteConsola) -> None:
    @mcp.tool()
    def listar_tablero(
        flujo: str = "",
        marca: str = "",
        estado: str = "",
        clase: str = "",
        desde: str = "",
        hasta: str = "",
    ) -> dict:
        """Lista los items del tablero de contenido (con sus filas por plataforma) y los
        catalogos (marcas, redes, estados validos). Filtros opcionales: `flujo`
        (importante|evergreen|evento), `marca` (id), `estado` (del padre), `clase`
        (contenido|tarea), `desde`/`hasta` (fecha objetivo ISO). Usala PRIMERO para saber
        que ids existen antes de mover o editar."""
        params = {
            "flujo": flujo,
            "marca": marca,
            "estado": estado,
            "clase": clase,
            "desde": desde,
            "hasta": hasta,
        }
        try:
            datos = cliente.listar_contenido(params)
        except ErrorConsola as e:
            return {"error": str(e)}
        contenidos = datos.get("contenidos", [])
        catalogos = datos.get("catalogos", {})
        return {
            "total": len(contenidos),
            "items": [_resumen_item(c) for c in contenidos],
            "catalogos": {
                "marcas": catalogos.get("marcas", []),
                "redes": [
                    {"id": r.get("id"), "nombre": r.get("nombre")}
                    for r in catalogos.get("redes", [])
                ],
                "flujos": catalogos.get("flujos", list(FLUJOS)),
                "estados_plataforma": catalogos.get("estados_plataforma", list(ESTADOS_PLATAFORMA)),
            },
        }

    @mcp.tool()
    def crear_contenido(
        titulo: str,
        flujo: str = "importante",
        marca: str = "",
        prioridad: str = "media",
        descripcion: str = "",
        fecha_objetivo: str = "",
        fecha_entrega: str = "",
        redes: list[str] | None = None,
        clase: str = "contenido",
    ) -> dict:
        """Crea un item en el tablero (lo importante del dia, evergreen, cobertura de evento,
        o una tarea libre del equipo). `titulo` es obligatorio. `redes` es la lista de ids de
        red (p.ej. ["instagram","x"]) para crear de una vez una fila por plataforma por cada
        una. `marca` debe ser un id del catalogo (mira `listar_tablero`). Devuelve el item
        creado con sus plataformas e ids (para luego moverlo)."""
        if not titulo.strip():
            return {"error": "El contenido necesita un titulo."}
        if flujo and flujo not in FLUJOS:
            return {"error": f"Flujo invalido. Usa uno de: {', '.join(FLUJOS)}."}
        if clase not in CLASES:
            return {"error": f"Clase invalida. Usa una de: {', '.join(CLASES)}."}
        cuerpo: dict[str, Any] = {
            "titulo": titulo.strip(),
            "clase": clase,
            "flujo": flujo,
            "prioridad": prioridad,
            "descripcion": descripcion,
            "fecha_objetivo": fecha_objetivo,
            "fecha_entrega": fecha_entrega,
            "redes": [r for r in (redes or []) if isinstance(r, str)],
        }
        if marca:
            cuerpo["marca"] = marca
        try:
            datos = cliente.crear_contenido(cuerpo)
        except ErrorConsola as e:
            return {"error": str(e)}
        return {"contenido": _resumen_item(datos.get("contenido", {}))}

    @mcp.tool()
    def mover_pieza(contenido_id: str, plataforma_id: str, estado: str) -> dict:
        """Mueve una pieza (una fila por plataforma) a otro estado del carril:
        pendiente|en_curso|en_revision|aprobado|programado|publicado. Es el equivalente a
        arrastrar la tarjeta en el tablero. Pasar a `aprobado` o `publicado` dispara los
        eventos internos/webhooks de la Consola. Usa `listar_tablero` para conocer
        `contenido_id` y `plataforma_id`."""
        if estado not in ESTADOS_PLATAFORMA:
            return {"error": f"Estado invalido. Usa uno de: {', '.join(ESTADOS_PLATAFORMA)}."}
        try:
            datos = cliente.actualizar_plataforma(contenido_id, plataforma_id, {"estado": estado})
        except ErrorConsola as e:
            return {"error": str(e)}
        plat = datos.get("plataforma", {})
        return {
            "plataforma": {
                "id": plat.get("id"),
                "red": plat.get("red"),
                "red_nombre": plat.get("red_nombre"),
                "estado": plat.get("estado"),
            }
        }

    @mcp.tool()
    def actualizar_contenido(
        contenido_id: str,
        estado: str = "",
        prioridad: str = "",
        responsable_id: str = "",
        fecha_objetivo: str = "",
        fecha_entrega: str = "",
        notas: str = "",
    ) -> dict:
        """Edita el item PADRE del tablero (no una pieza concreta): su estado
        (pendiente|en_curso|hecha), prioridad (alta|media|baja), responsable, fechas o notas.
        Solo manda los campos que quieras cambiar (el resto se deja como esta)."""
        cuerpo: dict[str, Any] = {}
        if estado:
            if estado not in ESTADOS_CONTENIDO:
                return {"error": f"Estado invalido. Usa uno de: {', '.join(ESTADOS_CONTENIDO)}."}
            cuerpo["estado"] = estado
        if prioridad:
            cuerpo["prioridad"] = prioridad
        if responsable_id:
            cuerpo["responsable_id"] = responsable_id
        if fecha_objetivo:
            cuerpo["fecha_objetivo"] = fecha_objetivo
        if fecha_entrega:
            cuerpo["fecha_entrega"] = fecha_entrega
        if notas:
            cuerpo["notas"] = notas
        if not cuerpo:
            return {"error": "Indica algun campo a actualizar."}
        try:
            datos = cliente.actualizar_contenido(contenido_id, cuerpo)
        except ErrorConsola as e:
            return {"error": str(e)}
        return {"contenido": _resumen_item(datos.get("contenido", {}))}

    @mcp.tool()
    def agregar_plataforma(contenido_id: str, red: str) -> dict:
        """Anade una fila por plataforma (una red) a un contenido ya creado, p.ej. cuando
        decides publicar tambien en TikTok una pieza que solo tenia Instagram. `red` es un id
        del catalogo (mira `listar_tablero`) o "web"."""
        try:
            datos = cliente.agregar_plataforma(contenido_id, red)
        except ErrorConsola as e:
            return {"error": str(e)}
        plat = datos.get("plataforma", {})
        return {
            "plataforma": {
                "id": plat.get("id"),
                "red": plat.get("red"),
                "red_nombre": plat.get("red_nombre"),
                "estado": plat.get("estado"),
            }
        }
