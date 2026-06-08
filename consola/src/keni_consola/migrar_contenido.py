"""Migración de datos legados al tablero de CONTENIDO unificado.

Lleva las PIEZAS de la rota (`rota_piezas`) al modelo nuevo `contenido`
(+ `contenido_plataforma`), para que el tablero del community manager muestre
lo que el equipo ya tenía. NO destruye los orígenes (las tablas legadas quedan intactas);
es IDEMPOTENTE: cada item migrado marca su `origen` (`pieza:<id>`) y un
segundo paso no lo duplica.

Las PUBLICACIONES ya viven en Postgres (ADR 0004); su backfill YAML→PG se retiró tras
migrar el piloto, así que aquí solo queda la migración de piezas de la rota.

Uso:  python -m keni_consola.migrar_contenido        (requiere DATABASE_URL, ADR 0004)
"""

from __future__ import annotations

import logging

from . import repos

_logger = logging.getLogger(__name__)

# Tokens libres de `rota_piezas.red_social` ("FB, IG, X" / "IG, TK (REEL)" / "WEB") -> red
# canónica. Lo que no mapea (HISTORIA, REEL, NOTA...) NO es una red: se vuelca a `notas`.
_TOKENS_RED: dict[str, str] = {
    "FB": "facebook",
    "FACEBOOK": "facebook",
    "IG": "instagram",
    "INSTAGRAM": "instagram",
    "X": "x",
    "TW": "x",
    "TWITTER": "x",
    "TK": "tiktok",
    "TIKTOK": "tiktok",
    "YT": "youtube",
    "YOUTUBE": "youtube",
    "WEB": "web",
}

# Estado de una PIEZA (pendiente/en_curso/listo/publicado) -> estado de una fila por
# plataforma del tablero. `listo` mapea a `aprobado` (lista para publicar).
_ESTADO_PIEZA_A_PLATAFORMA: dict[str, str] = {
    "pendiente": "pendiente",
    "en_curso": "en_curso",
    "listo": "aprobado",
    "publicado": "publicado",
}


def _parsear_redes(red_social: str) -> tuple[list[str], list[str]]:
    """Separa el texto libre de redes en (redes canónicas, tokens no reconocidos).

    Conserva el orden y sin duplicados. Los tokens no reconocidos se devuelven para
    registrarlos en `notas` (no se inventan redes).
    """
    redes: list[str] = []
    sobrantes: list[str] = []
    actual = ""
    for ch in red_social.upper():
        if ch.isalpha():
            actual += ch
        else:
            actual = _consumir_token(actual, redes, sobrantes)
    _consumir_token(actual, redes, sobrantes)
    return redes, sobrantes


def _consumir_token(token: str, redes: list[str], sobrantes: list[str]) -> str:
    if not token:
        return ""
    red = _TOKENS_RED.get(token)
    if red is not None:
        if red not in redes:
            redes.append(red)
    elif token not in sobrantes:
        sobrantes.append(token)
    return ""


def _origenes_existentes(prefijo: str) -> set[str]:
    """Ids de origen ya migrados (para idempotencia): de `origen` == f"{prefijo}:{id}"."""
    return {
        c["origen"].split(":", 1)[1]
        for c in repos.listar_contenido()
        if c.get("origen", "").startswith(f"{prefijo}:")
    }


def _id_etiqueta(nombre: str) -> str:
    """Id de la etiqueta `nombre` (la crea si no existe). Best-effort idempotente.

    Mismo patrón que `importador_calendario._id_etiqueta`: normaliza a minúsculas y reutiliza
    la etiqueta existente con ese nombre antes de crear una nueva. Devuelve "" si no se pudo.
    """
    norm = nombre.strip().lower()
    if not norm:
        return ""
    for et in repos.listar_etiquetas():
        if (et.get("nombre", "") or "").strip().lower() == norm:
            return et.get("id", "")
    return repos.crear_etiqueta(nombre=norm).get("id", "")


def migrar_piezas() -> int:
    """Migra `rota_piezas` -> `contenido` (clase='contenido') + filas por plataforma."""
    ya = _origenes_existentes("pieza")
    # Cache nombre_normalizado -> etiqueta_id para no releer/crear la misma etiqueta por fila.
    etiquetas_cache: dict[str, str] = {}
    creadas = 0
    for p in repos.listar_piezas_rota():
        if p["id"] in ya:
            continue
        redes, sobrantes = _parsear_redes(p.get("red_social", "") or "")
        flujo = "evento" if p.get("evento_id") else ("evergreen" if p.get("always_on") else "")
        notas = "\n".join(
            x for x in (p.get("notas", ""), p.get("comentarios", "")) if x
        )
        if sobrantes:
            notas = (notas + "\n" if notas else "") + "Formatos: " + ", ".join(sobrantes)
        item = repos.crear_contenido(
            clase="contenido",
            flujo=flujo,
            titulo=p.get("contenido_sugerido") or p.get("programa") or "Pieza",
            descripcion=p.get("contenido_sugerido", "") or "",
            programa=p.get("programa", "") or "",
            evento_id=p.get("evento_id", "") or "",
            fecha_objetivo=p.get("dia", "") or "",
            hora_objetivo=p.get("hora_post", "") or "",
            fecha_entrega=p.get("fecha_entrega_material", "") or "",
            responsable=(
                {"id": p["responsable_id"], "usuario": p.get("responsable_nombre", "")}
                if p.get("responsable_id")
                else None
            ),
            notas=notas,
            origen=f"pieza:{p['id']}",
        )
        # `tipo_pieza` (texto libre: HISTORIA / REEL / IMAGEN...) se preserva como ETIQUETA
        # del tablero (no como flujo): se asegura/reutiliza la etiqueta con ese nombre
        # normalizado y se asigna. Idempotente: `asignar_etiqueta` ignora duplicados.
        tipo = (p.get("tipo_pieza", "") or "").strip().lower()
        if tipo:
            etiqueta_id = etiquetas_cache.get(tipo)
            if etiqueta_id is None:
                etiqueta_id = _id_etiqueta(tipo)
                etiquetas_cache[tipo] = etiqueta_id
            if etiqueta_id:
                repos.asignar_etiqueta(item["id"], etiqueta_id)
        estado_plat = _ESTADO_PIEZA_A_PLATAFORMA.get(p.get("estado", ""), "pendiente")
        for red in redes:
            repos.crear_contenido_plataforma(
                contenido_id=item["id"],
                red=red,
                estado=estado_plat,
                falta_copy=not p.get("contenido_entregado"),
                falta_imagen=not p.get("material_entregado"),
                falta_revision=p.get("estado") in ("pendiente", "en_curso"),
                falta_publicar=not p.get("publicado"),
                enlace=p.get("enlace", "") or "",
                hora_post=p.get("hora_post", "") or "",
            )
        creadas += 1
    return creadas


def migrar() -> dict[str, int]:
    """Ejecuta toda la migración (idempotente). Devuelve recuentos por origen."""
    resultado = {
        "piezas": migrar_piezas(),
    }
    _logger.info("Migración a contenido: %s", resultado)
    return resultado


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    repos.arrancar_persistencia()
    resultado = migrar()
    print(f"Migrado al tablero de contenido: {resultado}")  # noqa: T201 -- CLI


if __name__ == "__main__":
    main()
