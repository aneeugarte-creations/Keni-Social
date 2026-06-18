"""Sugerencias: kanban del motor de auto-desarrollo.

Capa de DOMINIO sobre `db_sugerencias` (persistencia Postgres). Aquí viven el catálogo
de categorías/estados y la MÁQUINA DE ESTADOS del kanban; la persistencia pura está en
`db_sugerencias.py` (mismo patrón que `idear`/`db_idear`).

Máquina de estados:
    nueva → discovery → en_cola → building → revisión → hecha
    building → fallida
    fallida → en_cola            (reintento)
    revisión → en_cola/building  (checkpoint "cambios")
    descartada → nueva           (revivir)
    cualquiera → descartada      (descartar)
Atajo: una sugerencia `simple` salta el discovery (nueva → en_cola directo). La decisión
de tomar el atajo la hace el motor (`dominio.desarrollo`); aquí la transición es válida.
"""

from __future__ import annotations

from typing import Any

from . import db_sugerencias

# Categorías de ADMISIÓN (la UI las pinta con etiquetas legibles).
CATEGORIAS: tuple[str, ...] = ("idea", "producto", "mejora", "bug")
CATEGORIA_DEFECTO = "idea"

# Estados del kanban (orden de columnas izquierda→derecha; `fallida`/`descartada` aparte).
ESTADOS: tuple[str, ...] = (
    "nueva",
    "discovery",
    "en_cola",
    "building",
    "revision",
    "hecha",
    "fallida",
    "descartada",
)
ESTADO_DEFECTO = "nueva"

# Complejidad estimada (decide los checkpoints del pipeline; la fija el discovery).
COMPLEJIDADES: tuple[str, ...] = ("", "simple", "standard", "complex")

# Transiciones permitidas por estado. `descartada` se permite SIEMPRE (se añade abajo).
_TRANSICIONES: dict[str, frozenset[str]] = {
    "nueva": frozenset({"discovery", "en_cola"}),
    "discovery": frozenset({"en_cola"}),
    "en_cola": frozenset({"building"}),
    "building": frozenset({"revision", "fallida"}),
    "revision": frozenset({"hecha", "en_cola", "building"}),
    "hecha": frozenset(),
    "fallida": frozenset({"en_cola"}),
    "descartada": frozenset({"nueva"}),
}

# Topes defensivos de longitud (el front también limita).
_MAX_TITULO = 200
_MAX_DETALLE = 8000
_MAX_AUTOR = 120


class TransicionInvalida(ValueError):
    """Una transición de estado no permitida por la máquina (origen → destino)."""


def categoria_valida(categoria: str) -> bool:
    """True si `categoria` está en el catálogo de admisión."""
    return categoria in CATEGORIAS


def transicion_valida(origen: str, destino: str) -> bool:
    """True si se puede pasar de `origen` a `destino`.

    `descartada` es destino válido desde CUALQUIER estado; el resto sale del mapa. Una
    transición a sí mismo (idempotente) también se acepta.
    """
    if destino not in ESTADOS:
        return False
    if destino == "descartada":
        return True
    if destino == origen:
        return True
    return destino in _TRANSICIONES.get(origen, frozenset())


# --------------------------------------------------------------------------- #
# Lectura / creación                                                           #
# --------------------------------------------------------------------------- #


def listar() -> list[dict[str, Any]]:
    """Todas las sugerencias, recientes primero."""
    return db_sugerencias.listar_sugerencias()


def obtener(sugerencia_id: str) -> dict[str, Any] | None:
    """Una sugerencia por id (None si no existe)."""
    return db_sugerencias.obtener_sugerencia(sugerencia_id)


def crear(
    titulo: str,
    detalle: str = "",
    categoria: str = CATEGORIA_DEFECTO,
    autor: str = "",
) -> dict[str, Any]:
    """Crea una sugerencia en estado `nueva` y la persiste.

    Lanza `ValueError` si el título está vacío. Categoría inválida → defecto.
    """
    titulo = (titulo or "").strip()[:_MAX_TITULO]
    if not titulo:
        raise ValueError("titulo")
    return db_sugerencias.crear_sugerencia(
        titulo=titulo,
        detalle=(detalle or "").strip()[:_MAX_DETALLE],
        categoria=categoria if categoria in CATEGORIAS else CATEGORIA_DEFECTO,
        autor=(autor or "").strip()[:_MAX_AUTOR],
        estado=ESTADO_DEFECTO,
    )


# --------------------------------------------------------------------------- #
# Edición de texto / borrado                                                   #
# --------------------------------------------------------------------------- #


def editar(sugerencia_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita el texto de una sugerencia (titulo/detalle/categoria). None si no existe.

    Lanza `ValueError` si el título dado queda vacío. Categoría inválida → defecto.
    """
    cambios: dict[str, Any] = {}
    if "titulo" in campos:
        titulo = str(campos["titulo"] or "").strip()[:_MAX_TITULO]
        if not titulo:
            raise ValueError("titulo")
        cambios["titulo"] = titulo
    if "detalle" in campos:
        cambios["detalle"] = str(campos["detalle"] or "").strip()[:_MAX_DETALLE]
    if "categoria" in campos:
        cat = campos["categoria"]
        cambios["categoria"] = cat if cat in CATEGORIAS else CATEGORIA_DEFECTO
    if not cambios:
        return obtener(sugerencia_id)
    return db_sugerencias.actualizar_sugerencia(sugerencia_id, cambios)


def borrar(sugerencia_id: str) -> bool:
    """Borra una sugerencia por id. True si existía."""
    return db_sugerencias.borrar_sugerencia(sugerencia_id)


# --------------------------------------------------------------------------- #
# Máquina de estados / avance del motor                                        #
# --------------------------------------------------------------------------- #


def cambiar_estado(
    sugerencia_id: str, destino: str, *, campos: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Mueve una sugerencia a `destino` validando la transición. None si no existe.

    Lanza `TransicionInvalida` si el destino no es alcanzable desde el estado actual.
    `campos` (opcional) son campos del motor (fase/spec/plan/rama/...) que se escriben en
    el MISMO update que el estado (atómico).
    """
    if destino not in ESTADOS:
        raise TransicionInvalida(f"estado desconocido: {destino!r}")
    actual = obtener(sugerencia_id)
    if actual is None:
        return None
    if not transicion_valida(actual["estado"], destino):
        raise TransicionInvalida(f"{actual['estado']} → {destino}")
    cambios: dict[str, Any] = dict(campos or {})
    cambios["estado"] = destino
    return db_sugerencias.actualizar_sugerencia(sugerencia_id, cambios)


def actualizar_avance(sugerencia_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Escribe campos del motor SIN cambiar de estado (fase/spec/plan/rama/diff/coste/gen_id).

    Lo usa el post-procesado de los jobs de desarrollo para ir registrando el progreso del
    pipeline (la transición de estado, si la hay, va por `cambiar_estado`).
    """
    cambios = {k: v for k, v in campos.items() if k != "estado"}
    if not cambios:
        return obtener(sugerencia_id)
    return db_sugerencias.actualizar_sugerencia(sugerencia_id, cambios)


# --------------------------------------------------------------------------- #
# Post-procesado de los jobs de desarrollo (lo reconstruye `dominio.jobspec`)  #
# --------------------------------------------------------------------------- #


def construir_procesar_dev_discovery(*, sugerencia_id: str):  # noqa: ANN201
    """Callback `procesar(salida, metricas) -> dict` del DISCOVERY (lo corre el worker).

    Parsea la salida (SPEC + complejidad) y deja la sugerencia en `en_cola`, lista para
    construir. Devuelve un resumen para el registro de la generación.
    """
    from .dominio import desarrollo

    def procesar(salida: str, _metricas: object) -> dict[str, Any]:
        datos = desarrollo.parsear_discovery(salida or "")
        actualizar_avance(
            sugerencia_id,
            {"spec": datos["spec"], "complejidad": datos["complejidad"]},
        )
        try:
            cambiar_estado(sugerencia_id, "en_cola")
        except TransicionInvalida:
            pass  # ya avanzó / se descartó por otra vía: el SPEC quedó guardado igual
        return {"complejidad": datos["complejidad"], "spec_chars": len(datos["spec"])}

    return procesar


def construir_procesar_dev_fase(*, sugerencia_id: str, fase: str):  # noqa: ANN201
    """Callback `procesar(salida, metricas) -> dict` de UNA fase del pipeline (lo corre el worker).

    Parsea la salida de la fase (plan / resumen de diff), la persiste y mueve la sugerencia a
    `revision` si la fase es un checkpoint, o la deja en `building` si el pipeline sigue. El
    ENCADENADO a la siguiente fase lo decide `worker_dev` leyendo la fila ya actualizada.
    """
    from .dominio import desarrollo

    def procesar(salida: str, _metricas: object) -> dict[str, Any]:
        datos = desarrollo.parsear_fase(salida or "", fase)
        actualizar_avance(sugerencia_id, {"fase": fase, **datos})
        sug = obtener(sugerencia_id)
        complejidad = (sug or {}).get("complejidad", "") or ""
        destino = desarrollo.estado_tras_fase(complejidad, fase)
        try:
            cambiar_estado(sugerencia_id, destino)
        except TransicionInvalida:
            pass
        return {"fase": fase, "estado": destino}

    return procesar


# --------------------------------------------------------------------------- #
# Lanzamiento de jobs de desarrollo (carril `dev`)                             #
# --------------------------------------------------------------------------- #
#
# Crea el registro de generación, arma el spec (carril=dev) y lo ENCOLA; un `worker_dev` lo
# reclama, crea el worktree y corre `claude -p` sin sandbox. Lo usan tanto la API (discovery/
# construir) como `worker_dev` (encadenado de fases). Heavy imports en perezoso.

# Cuerpos de respaldo si la biblioteca de prompts (clase `desarrollo`) aún no trae el doc:
# instrucciones mínimas para que el motor funcione sin depender del seed editorial.
_BASE_FALLBACK_GENERICO = (
    "Eres un agente de desarrollo del repositorio keni-social. Trabaja con criterio de "
    "ingeniería: cambios mínimos y correctos, tests en el mismo commit, comentarios limpios "
    "(qué hace el código hoy, no el historial). Sigue el flujo worktree → promover-main."
)
_BASE_FALLBACK: dict[str, str] = {
    "discovery": (
        "Analiza la sugerencia y produce un SPEC en markdown: problema, alcance, archivos a "
        "tocar y plan de pruebas. Termina con una línea exactamente así: "
        "`complejidad: simple|standard|complex` según el tamaño del cambio."
    ),
    "analyze": "Analiza el problema y el área del repo afectada. No escribas código todavía.",
    "plan": "Diseña el cambio: qué archivos tocar, qué tests añadir/actualizar, en qué orden.",
    "build": "Implementa el cambio en el worktree siguiendo el plan. Añade/actualiza los tests.",
    "review": "Revisa el diff y los tests. Señala riesgos antes del checkpoint humano.",
}


def _cargar_base(nombre: str) -> str:
    """Cuerpo base del prompt de `nombre` (fase o 'discovery'). Best-effort + respaldo.

    Busca en la biblioteca de prompts un doc de la clase `desarrollo` cuyo id/título case con
    `nombre`; si no hay (o la biblioteca falla), usa el respaldo built-in para no bloquear el
    motor por un seed editorial ausente.
    """
    try:
        from . import libprompts
        from .dominio import desarrollo

        for d in libprompts.listar(clase=desarrollo.CLASE_EDITORIAL):
            if nombre in d.id or nombre in (d.titulo or "").lower():
                cuerpo = libprompts.cuerpo_efectivo(d.id)
                if cuerpo:
                    return cuerpo
    except Exception:  # noqa: BLE001 -- el respaldo cubre cualquier fallo de la biblioteca
        pass
    return _BASE_FALLBACK.get(nombre, _BASE_FALLBACK_GENERICO)


def _lanzar(*, tipo: str, etiqueta: str, prompt: str,
            procesar_spec: dict[str, Any], modelo: str = ""):
    """Crea el registro de generación, encola el spec (carril dev) y devuelve el registro."""
    from . import cola, generaciones
    from .dominio import jobspec

    gen = generaciones.crear({"tipo": tipo, "marca": "", "etiqueta": etiqueta})
    spec = jobspec.construir(
        prompt=prompt,
        procesar=procesar_spec,
        carril=jobspec.CARRIL_DEV,
        endurecer={"modelo": modelo} if modelo else None,
        prioridad=jobspec.PRIORIDAD_MANUAL,
    )
    cola.encolar(gen["id"], spec)
    return gen


def lanzar_discovery(sugerencia_id: str) -> dict[str, Any] | None:
    """Encola el job de DISCOVERY y mueve la sugerencia a `discovery`. None si no existe."""
    sug = obtener(sugerencia_id)
    if sug is None:
        return None
    from .dominio import desarrollo, jobspec

    prompt = desarrollo.componer_prompt(_cargar_base("discovery"), sug, "discovery")
    gen = _lanzar(
        tipo="dev-discovery",
        etiqueta=f"Discovery · {sug['titulo']}",
        prompt=prompt,
        procesar_spec=jobspec.construir_dev_discovery(sugerencia_id=sugerencia_id),
    )
    try:
        cambiar_estado(sugerencia_id, "discovery", campos={"gen_id": gen["id"], "fase": ""})
    except TransicionInvalida:
        actualizar_avance(sugerencia_id, {"gen_id": gen["id"]})
    return gen


def lanzar_fase(sugerencia_id: str, fase: str, *, modelo: str = "") -> dict[str, Any] | None:
    """Encola el job de una FASE del pipeline y deja la sugerencia en `building`. None si no existe."""
    sug = obtener(sugerencia_id)
    if sug is None:
        return None
    from .dominio import desarrollo, jobspec

    modelo = modelo or desarrollo.modelo_de(fase)
    prompt = desarrollo.componer_prompt(_cargar_base(fase), sug, fase)
    gen = _lanzar(
        tipo="dev-fase",
        etiqueta=f"{fase} · {sug['titulo']}",
        prompt=prompt,
        procesar_spec=jobspec.construir_dev_fase(
            sugerencia_id=sugerencia_id, fase=fase, modelo=modelo
        ),
        modelo=modelo,
    )
    try:
        cambiar_estado(sugerencia_id, "building", campos={"gen_id": gen["id"], "fase": fase})
    except TransicionInvalida:
        actualizar_avance(sugerencia_id, {"gen_id": gen["id"], "fase": fase})
    return gen


def lanzar_construir(
    sugerencia_id: str, *, complejidad: str = ""
) -> dict[str, Any] | None:
    """Mueve a `en_cola` (fijando complejidad) y encola la PRIMERA fase del pipeline.

    None si no existe. La complejidad efectiva sale del parámetro, de la fila o del defecto.
    """
    sug = obtener(sugerencia_id)
    if sug is None:
        return None
    from .dominio import desarrollo

    comp = complejidad or sug.get("complejidad") or desarrollo.COMPLEJIDAD_DEFECTO
    if comp not in desarrollo.COMPLEJIDADES:
        comp = desarrollo.COMPLEJIDAD_DEFECTO
    try:
        cambiar_estado(sugerencia_id, "en_cola", campos={"complejidad": comp})
    except TransicionInvalida:
        actualizar_avance(sugerencia_id, {"complejidad": comp})
    return lanzar_fase(sugerencia_id, desarrollo.primera_fase(comp))


# --------------------------------------------------------------------------- #
# Checkpoint humano / promoción                                                #
# --------------------------------------------------------------------------- #


def aplicar_checkpoint(
    sugerencia_id: str, accion: str, *, comentario: str = ""
) -> dict[str, Any] | None:
    """Aplica la decisión humana de un checkpoint. None si la sugerencia no existe.

    - cancelar: descarta la sugerencia (válido desde cualquier estado).
    - continuar: sigue el pipeline (lanza la siguiente fase; si no hay, queda en `revision`
      lista para promover). Solo desde `revision`.
    - cambios: re-ejecuta la construcción con `comentario` como feedback. Solo desde `revision`.
    Lanza `TransicionInvalida` si la acción no aplica al estado actual.
    """
    sug = obtener(sugerencia_id)
    if sug is None:
        return None
    if accion == "cancelar":
        return cambiar_estado(sugerencia_id, "descartada")
    if sug["estado"] != "revision":
        raise TransicionInvalida(f"checkpoint {accion} desde {sug['estado']}")
    if accion == "continuar":
        from .dominio import desarrollo

        siguiente = desarrollo.siguiente_fase(sug.get("complejidad", ""), sug.get("fase", ""))
        if siguiente is None:
            return sug  # pipeline terminado: queda en revisión, lista para /promover
        lanzar_fase(sugerencia_id, siguiente)
        return obtener(sugerencia_id)
    if accion == "cambios":
        from .dominio import desarrollo

        if comentario.strip():
            nota = f"\n\n## Feedback de checkpoint\n{comentario.strip()}"
            detalle = (str(sug.get("detalle", "")) + nota)[:_MAX_DETALLE]
            actualizar_avance(sugerencia_id, {"detalle": detalle})
        lanzar_fase(sugerencia_id, desarrollo.FASE_BUILD)
        return obtener(sugerencia_id)
    raise TransicionInvalida(f"acción de checkpoint desconocida: {accion!r}")


def promover(sugerencia_id: str) -> dict[str, Any] | None:
    """Promueve a `main` (checkpoint humano final): marca `hecha`. None si no existe.

    La ejecución REAL del git push la hace `worker_dev` sobre la rama de la sugerencia; aquí
    se registra la decisión humana y se mueve el kanban. Lanza `TransicionInvalida` si la
    sugerencia no está en `revision`.
    """
    sug = obtener(sugerencia_id)
    if sug is None:
        return None
    actualizada = cambiar_estado(sugerencia_id, "hecha")
    rama = (actualizada or sug).get("rama", "")
    detalle = (
        f"Promoción solicitada para la rama «{rama}»."
        if rama
        else "Promoción solicitada."
    )
    return {"ok": True, "detalle": detalle, "sugerencia": actualizada}
