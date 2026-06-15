"""PIPELINES · `GET /api/pipelines/problemas`: temas BLOQUEADOS del pipeline (solo lectura)."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import marcas, repos
from ..._http_json import _entero_query
from ...pipeline_contenido import ORIGEN_PIPELINE, VERDICTO_PROBLEMA, intentos_de
from ._comun import _LIMITE_DEF, _LIMITE_MAX, _marca_nombre, _qa_fuente_de


def _problema_de(item: dict) -> dict:
    """Forma pública de un tema BLOQUEADO (veredicto `problema`): qué falló, dónde y cuántas veces.

    `etapa`/`error` salen del ÚLTIMO hallazgo: los fallos repetidos de etapa
    (`marcar_fallo_etapa`) dejan un hallazgo `tipo='sistema'` con la etapa en `fragmento`;
    un 🔴 de la propia criba (sin hallazgo de sistema) es un problema de "Verificar".
    `intentos` lee los contadores de reintento de `copy_pendiente` (qa/cd).
    """
    qa = _qa_fuente_de(item)
    ultimo = qa["hallazgos"][-1] if qa["hallazgos"] else {}
    es_sistema = (ultimo.get("tipo") or "") == "sistema"
    marca = item.get("marca", "") or ""
    return {
        "id": item.get("id", "") or "",
        "titulo": item.get("titulo", "") or "",
        "marca": marca,
        "marca_nombre": _marca_nombre(marca),
        "etapa": (ultimo.get("fragmento") or "") if es_sistema else "Verificar",
        "intentos": {
            "qa": intentos_de(item, "verificar_intentos"),
            "cd": intentos_de(item, "redactar_intentos"),
        },
        "error": str(ultimo.get("explicacion") or "") or qa["resumen"],
        "resumen": qa["resumen"],
        "hallazgos": qa["hallazgos"],
        "creado": item.get("creado", "") or "",
        "actualizado": item.get("actualizado", "") or "",
    }


async def problemas(request: Request) -> Response:
    """GET /api/pipelines/problemas?marca=&limite=50: temas BLOQUEADOS del pipeline (solo lectura).

    Tras agotar sus reintentos (o una criba 🔴 de peso), un tema queda con veredicto `problema`
    y SALE del flujo (no se reintenta ni cuenta en el cupo en curso): esta lista lo hace VISIBLE
    para que un humano decida (relanzar a mano / descartar). Recientes (por `actualizado`)
    primero. Aún sin UI propia: lo consume quien monitorea (curl / consola / vista futura).
    """
    qp = request.query_params
    marca = (qp.get("marca") or "").strip()
    if marca and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    limite = _entero_query(qp.get("limite"), minimo=1)
    if limite is None:
        limite = _LIMITE_DEF
    limite = min(limite, _LIMITE_MAX)

    bloqueados = [
        it
        for it in repos.listar_contenido(marca=marca or None)
        if (it.get("origen") or "") == ORIGEN_PIPELINE
        and (it.get("verificar_veredicto") or "").strip() == VERDICTO_PROBLEMA
    ]
    bloqueados.sort(
        key=lambda it: (it.get("actualizado") or it.get("creado") or "", it.get("id", "")),
        reverse=True,
    )
    total = len(bloqueados)
    return JSONResponse({
        "problemas": [_problema_de(it) for it in bloqueados[:limite]],
        "total": total,
    })
