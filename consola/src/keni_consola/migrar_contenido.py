"""Migración de datos legados al tablero de CONTENIDO unificado.

Lleva las PIEZAS de la rota (`rota_piezas`) al modelo nuevo `contenido`
(+ `contenido_plataforma`), para que el tablero del community manager muestre
lo que el equipo ya tenía. NO destruye los orígenes (las tablas legadas quedan intactas);
es IDEMPOTENTE: cada item migrado marca su `origen` (`pieza:<id>`) y un
segundo paso no lo duplica.

Las PUBLICACIONES (hoy en YAML) NO se migran aquí: se incorporan al fusionar su
persistencia sobre Postgres (paso 3 del plan), para no duplicar mientras siguen viviendo
en disco y editándose por su propia página.

Uso:  python -m keni_consola.migrar_contenido        (requiere DATABASE_URL, ADR 0004)
"""

from __future__ import annotations

import logging

from . import ficheros, repos

_logger = logging.getLogger(__name__)

# Campos editoriales de una publicacion que no entran en `crear_publicacion` y se aplican
# con un `actualizar_publicacion` posterior al migrar (preservan el flujo de aprobación).
_CAMPOS_PUB_EXTRA = (
    "enviado_a_revision_en",
    "revisor_id",
    "revisor_nombre",
    "revisado_en",
    "preparado_en",
    "id_post_metricool",
)

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


def migrar_piezas() -> int:
    """Migra `rota_piezas` -> `contenido` (clase='contenido') + filas por plataforma."""
    ya = _origenes_existentes("pieza")
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


def migrar_publicaciones() -> int:
    """Migra las publicaciones YAML legadas (`ficheros`) a Postgres (modelo `contenido`).

    Idempotente: si el id ya existe en Postgres, se salta (el id de la publicación se
    preserva). Lee la fuente legada DIRECTO de `ficheros` (YAML); las nuevas ya nacen en
    Postgres vía `repos`/`db`.
    """
    creadas = 0
    for pub in ficheros.listar_publicaciones():
        if repos.obtener_publicacion(pub["id"]) is not None:
            continue
        repos.crear_publicacion(
            pub.get("marca", "") or "",
            pub.get("red", "") or "",
            titulo=pub.get("titulo", "") or "",
            contenido=pub.get("contenido", "") or "",
            estado=pub.get("estado", "borrador") or "borrador",
            veredicto=pub.get("veredicto", "") or "",
            fecha_programada=pub.get("fecha_programada", "") or "",
            origen=pub.get("origen", "") or "",
            imagen=pub.get("imagen", "") or "",
            evergreen=bool(pub.get("evergreen")),
            autor=(
                {"id": pub["autor_id"], "usuario": pub.get("autor_nombre", "")}
                if pub.get("autor_id")
                else None
            ),
            id=pub["id"],
            fecha_creacion=pub.get("fecha_creacion", "") or "",
        )
        extra = {k: pub[k] for k in _CAMPOS_PUB_EXTRA if pub.get(k)}
        if extra:
            repos.actualizar_publicacion(pub["id"], extra)
        creadas += 1
    return creadas


def migrar_plantillas_plano() -> int:
    """Migra las plantillas de copy PLANO (YAML legado) al catálogo unificado en Postgres.

    El catálogo unificado vive en `plantilla_contenido` (`repos.crear_plantilla_contenido`):
    las plantillas planas entran con `modo='plano'` y su texto en `contenido`. Idempotente:
    se preserva el id YAML y, si ya existe en Postgres, se salta. La fuente legada (YAML) NO
    se destruye; las nuevas planas ya nacen en Postgres por la API unificada.
    """
    creadas = 0
    for p in ficheros.listar_plantillas():
        if repos.obtener_plantilla_contenido(p["id"]) is not None:
            continue
        repos.crear_plantilla_contenido(
            nombre=p.get("nombre", "") or "",
            modo="plano",
            marca=p.get("marca", "") or "",
            red=p.get("red", "") or "",
            contenido=p.get("contenido", "") or "",
            id=p["id"],
        )
        creadas += 1
    return creadas


def migrar() -> dict[str, int]:
    """Ejecuta toda la migración (idempotente). Devuelve recuentos por origen."""
    resultado = {
        "piezas": migrar_piezas(),
        "publicaciones": migrar_publicaciones(),
        "plantillas_plano": migrar_plantillas_plano(),
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
