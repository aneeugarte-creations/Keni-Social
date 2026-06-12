"""GENERACIONES · ALMACÉN: localización del store, escritura atómica, CRUD, idempotencia,
poda de retención y reaper de zombis.

Submódulo interno del paquete `generaciones`. El registro YAML es la FUENTE DE VERDAD del
sondeo; aquí vive todo lo que LEE/ESCRIBE ese store (un `<id>.yaml` por generación) y las
políticas que lo acotan (poda #128, reaper de `ejecutando` colgadas). El `__init__.py`
re-exporta la superficie pública estable (`crear`, `actualizar`, `obtener`, `listar`,
`contar`, `crear_idempotente`, `podar_generaciones`, `reclamar_zombis`, `raiz`,
`clave_idempotencia`).

SEGURIDAD: escritura atomica (tmp + os.replace); el id de un registro se sanea contra
traversal al leer; sin shell. Errores en espanol, sin tracebacks.
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from keni_shared.esquema_yaml import migrar, sellar

from .. import config, rutas
from ..io_atomico import bloqueo_archivo, escribir_atomico
from ._comun import (
    _ES_ID,
    _ESTADOS_TERMINALES,
    _LISTADO_MAX,
    ESTADO_EJECUTANDO,
    ESTADO_ERROR,
    MOTIVO_INTERRUMPIDO,
    _log,
    ahora_iso,
    nuevo_id,
)

# Loader RÁPIDO (libyaml) cuando está disponible. Parsear los ~800 YAML de generaciones con el
# parser PURO de Python costaba ~3 s por petición (Actividad IA y el detalle de Pipelines lo
# hacían en cada carga → "tarda muchísimo"); `CSafeLoader` (libyaml) lo baja a ~130 ms (23×). Es
# API-compatible con `SafeLoader`; si no hay libyaml en la build, cae al loader puro.
_YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

__all__ = [
    "actualizar",
    "clave_idempotencia",
    "contar",
    "crear",
    "crear_idempotente",
    "listar",
    "obtener",
    "podar_generaciones",
    "raiz",
    "reclamar_zombis",
    "_RETENCION_DIAS_DEF",
    "_RETENCION_MAX_DEF",
    "_TIPO",
    "_cuerpo",
    "_entero_env",
    "_escribir_yaml_atomico",
    "_leer_idem",
    "_leer_yaml",
    "_publico",
    "_ruta",
    "_ruta_idem",
    "_todas_ordenadas",
]


# --------------------------------------------------------------------------- #
# Localizacion del almacen + escritura atomica                                #
# --------------------------------------------------------------------------- #


def raiz() -> Path:
    """Dir donde viven los registros de generacion.

    `KENI_CONSOLA_GENERACIONES` lo fija (override de maxima prioridad; tests). Si no,
    cuelga de la raiz de estado unica (`rutas.dir_config()`), igual que el resto de
    recursos de config: local `${XDG_CONFIG_HOME:-~/.config}/keni-social/generaciones`,
    o `<KENI_DATA_DIR>/keni-social/generaciones` en contenedor.

    XDG (#126): antes este recurso IGNORABA `XDG_CONFIG_HOME` (siempre `~/.config`); ahora
    lo respeta como los demas. Con XDG SIN fijar el default es IDENTICO al historico
    (`~/.config/keni-social/generaciones`), asi no se orfanan registros locales existentes.
    """
    if (p := config.override_ruta(config.ENV_GENERACIONES)) is not None:
        return p
    return rutas.dir_config() / "generaciones"


def _ruta(gen_id: str) -> Path:
    """Ruta `<raiz>/<id>.yaml` saneada (solo el nombre base; anti-traversal)."""
    base = raiz()
    seguro = Path(gen_id).name
    if not seguro or seguro != gen_id or seguro in (".", ".."):
        raise ValueError("Identificador de generación no válido.")
    destino = (base / f"{seguro}.yaml").resolve()
    if destino.parent != base.resolve():
        raise ValueError("Ruta de generación fuera del almacén.")
    return destino


# Tipo de esquema de este modulo (un solo tipo de fichero: el registro de generacion).
_TIPO = "generacion"


def _escribir_yaml_atomico(ruta_fichero: Path, datos: dict[str, Any]) -> None:
    """Escribe un dict como YAML de forma ATOMICA (tmp en el mismo dir + os.replace).

    `sellar` estampa la `version` de esquema antes de volcar (#125). Se aplica DESPUES
    de `_cuerpo` (que filtra claves vacias), asi la `version` int siempre sobrevive.
    """
    texto = yaml.safe_dump(
        sellar(_TIPO, datos),
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=4096,
    )
    escribir_atomico(ruta_fichero, texto, sufijo=".yaml")


def _leer_yaml(ruta_fichero: Path) -> dict[str, Any] | None:
    """Lee un YAML como dict, o None si no existe / esta corrupto / no es un mapa.

    `migrar` sube de version el dict legado en memoria (#125).
    """
    try:
        texto = ruta_fichero.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        datos = yaml.load(texto, Loader=_YAML_LOADER)  # noqa: S506 -- loader SAFE (libyaml o puro)
    except yaml.YAMLError:
        return None
    if not isinstance(datos, dict):
        return None
    return migrar(_TIPO, datos)


# --------------------------------------------------------------------------- #
# Normalizacion + CRUD del registro                                           #
# --------------------------------------------------------------------------- #


def _entero_o_cero(valor: Any) -> int:
    """Entero tolerante (0 si falta/ilegible): para campos numericos opcionales del registro."""
    try:
        return int(valor or 0)
    except (TypeError, ValueError):
        return 0


def _publico(datos: dict[str, Any], gen_id: str) -> dict[str, Any]:
    """Reconstruye el dict PUBLICO de una generacion (forma estable para la API/UI)."""
    metricas = datos.get("metricas")
    if not isinstance(metricas, dict) or not metricas:
        metricas = None
    resultado = datos.get("resultado")
    if not isinstance(resultado, dict) or not resultado:
        resultado = None

    def _str(clave: str) -> str:
        valor = datos.get(clave)
        return valor if isinstance(valor, str) else ""

    return {
        "id": gen_id,
        "tipo": _str("tipo"),
        "marca": _str("marca"),
        # Contenido correlacionado (opcional): las generaciones-marcador del pipeline
        # (`tipo='pipeline'`) lo sellan para que la vista Pipelines ate cada etapa a su run.
        # Ausente en registros legados/normales => "" (lo filtra `_cuerpo`, así no engorda).
        "contenido_id": _str("contenido_id"),
        # Generación correlacionada (opcional): un MARCADOR de etapa del pipeline (CD/QA)
        # apunta con `gen_id` a la generación REAL de `claude -p` de esa etapa, para que la
        # vista Pipelines pueda mostrar su STREAM (el proceso de pensamiento del agente).
        # Ausente en registros legados/normales => "" (lo filtra `_cuerpo`, así no engorda).
        "gen_id": _str("gen_id"),
        "etiqueta": _str("etiqueta"),
        # Proceso de la maquina (ADR 0011): "investigacion" | "produccion". Se SELLA al lanzar
        # (QA/Haiku del pool -> investigacion; copy/arte/manual -> produccion) para medir cada
        # loop por separado en el Monitor. Ausente en registros previos => "" (lo filtra
        # `_cuerpo`, no engorda; `generaciones.proceso_de` lo deduce de tipo/etiqueta al leer).
        "proceso": _str("proceso"),
        "estado": _str("estado"),
        # Fase de PROGRESO (en que etapa va; ausente en registros legados => "").
        "fase": _str("fase"),
        "motivo": _str("motivo"),
        "salida": _str("salida"),
        # Razonamiento (thinking) en vivo, cola acotada: feedback mientras el modelo piensa.
        # Como el prompt, se expone en el detalle y `_todas_ordenadas` lo quita del listado.
        "razonamiento": _str("razonamiento"),
        # Prompt EXACTO enviado a `claude -p` (visibilidad/control). Se persiste pero se
        # expone SOLO en el detalle (`obtener`); `_todas_ordenadas` lo quita del listado
        # para no engordar Actividad. Ausente en registros legados => "".
        "prompt": _str("prompt"),
        # Tamano del prompt (chars; economia de contexto). Lo sella el encolado y lo vuelca
        # el ledger `gasto_ia` al cerrar (deriva del contexto por dia). Legados => 0.
        "prompt_chars": _entero_o_cero(datos.get("prompt_chars")),
        "error": _str("error"),
        # Atribucion por usuario (#130 Fase 1). Ausente en registros legados/anonimos => "".
        "autor_id": _str("autor_id"),
        "autor_nombre": _str("autor_nombre"),
        "metricas": metricas,
        "resultado": resultado,
        "fecha_inicio": _str("fecha_inicio"),
        "fecha_fin": _str("fecha_fin"),
    }


def crear(datos: dict[str, Any]) -> dict[str, Any]:
    """Crea un registro de generacion y lo escribe (atomico). Devuelve el dict publico.

    `datos` debe traer al menos `tipo`, `marca`, `etiqueta`. Si no trae `id`/`estado`/
    `fecha_inicio`, se rellenan (`estado="ejecutando"`, fecha = ahora).
    """
    gen_id = datos.get("id") or nuevo_id()
    completo = {
        "estado": ESTADO_EJECUTANDO,
        "fecha_inicio": ahora_iso(),
        **datos,
        "id": gen_id,
    }
    pub = _publico(completo, gen_id)
    _escribir_yaml_atomico(_ruta(gen_id), _cuerpo(pub))
    return pub


def clave_idempotencia(*partes: Any) -> str:
    """Deriva una clave de idempotencia ESTABLE (hex de 32) de las partes del lanzamiento.

    Une las partes (autor, tipo, marca, contenido, prompt...) con un separador que no puede
    aparecer dentro de ellas y la hashea. Dos lanzamientos del MISMO trabajo logico producen la
    MISMA clave; un trabajo distinto (otro tema/tipo/redes -> otro prompt) produce otra. El
    resultado es un nombre de fichero seguro (solo hex), apto para el indice en disco.
    """
    crudo = "\x1f".join("" if p is None else str(p) for p in partes)
    return hashlib.blake2b(crudo.encode("utf-8"), digest_size=16).hexdigest()


def _ruta_idem(clave: str) -> Path:
    """Ruta `<raiz>/idem-<clave>.idx` saneada (solo hex; anti-traversal). El indice clave->gen_id."""
    base = raiz()
    seguro = re.sub(r"[^0-9a-f]", "", (clave or "").lower())
    if not seguro:
        raise ValueError("Clave de idempotencia no válida.")
    destino = (base / f"idem-{seguro}.idx").resolve()
    if destino.parent != base.resolve():
        raise ValueError("Ruta de idempotencia fuera del almacén.")
    return destino


def crear_idempotente(clave: str, datos: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Crea una generacion BAJO una clave de idempotencia. Devuelve `(gen, nueva)`.

    CONVERGENCIA ATOMICA: usa una creacion EXCLUSIVA de fichero (`O_CREAT|O_EXCL`) del indice
    `idem-<clave>.idx` como mutex en disco (el analogo a un indice UNICO): SOLO un llamante puede
    crearlo. El ganador acuña un `gen_id`, escribe el registro, sella el indice con ese id y
    devuelve `(gen, True)` (debe encolar). Un llamante CONCURRENTE que choca con el `O_EXCL` lee
    el `gen_id` del indice; si esa generacion EXISTE y NO es terminal, devuelve `(gen_existente,
    False)` (NO encola: comparte el run en vuelo). Si el indice apunta a una generacion ya
    TERMINAL o desaparecida (claim viejo de un run que ya acabo), el indice se RECLAMA para este
    lanzamiento nuevo (un re-lanzamiento legitimo tras completar debe poder correr).

    Asi dos POST casi-simultaneos del MISMO trabajo convergen a UNA generacion (un solo `claude
    -p`), y dos trabajos DISTINTOS (claves distintas) corren cada uno el suyo.
    """
    base = raiz()
    base.mkdir(parents=True, exist_ok=True)
    ruta_idx = _ruta_idem(clave)
    # Reintento acotado: cubre la carrera "el ganador aun no sello el id" y el reciclaje de un
    # claim terminal. En la practica converge en 1-2 vueltas; el tope evita un bucle infinito.
    for _ in range(50):
        try:
            fd = os.open(ruta_idx, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            gen_id_existente = _leer_idem(ruta_idx)
            if gen_id_existente:
                existente = obtener(gen_id_existente)
                if existente is not None and existente.get("estado") not in _ESTADOS_TERMINALES:
                    return existente, False  # run en vuelo: comparte, NO encoles otro
            # Claim viejo (terminal/ausente) o aun sin sellar: intenta reclamarlo borrandolo y
            # reintentando la creacion exclusiva. Si otro lo recrea entre medias, la siguiente
            # vuelta lo vera y compartira (o reciclara) segun su estado.
            try:
                os.unlink(ruta_idx)
            except FileNotFoundError:
                pass
            continue
        else:
            try:
                gen = crear(datos)
                os.write(fd, gen["id"].encode("ascii"))
            finally:
                os.close(fd)
            return gen, True
    # No deberia ocurrir (la carrera converge): degradamos a un lanzamiento NO idempotente
    # (crear + encolar) antes que bloquear al usuario. Mejor un posible duplicado que un cuelgue.
    _log.warning("idempotencia de generación: no convergió la clave %s; lanzo sin guardia", clave[:16])
    return crear(datos), True


def _leer_idem(ruta_idx: Path) -> str:
    """Lee el `gen_id` sellado en un indice de idempotencia ("" si vacio/ilegible)."""
    try:
        return ruta_idx.read_text(encoding="ascii").strip()
    except OSError:
        return ""


def borrar_registro(gen_id: str) -> bool:
    """Borra EN DURO el registro de una generacion que NUNCA llego a encolarse.

    Para el caso "el lanzamiento no ocurrio": el registro se crea ANTES de encolar
    (idempotencia) y, si la admision lo rechaza (cola llena / presupuesto / pausa), dejarlo
    en `error` llena la Actividad de cadaveres que no son fallos reales — el tick del
    pipeline reintenta cada pocos segundos y mintaria uno nuevo cada vez. Borrarlo deja la
    Actividad limpia; el indice de idempotencia que apunte a el se auto-recicla (un indice
    cuyo gen no existe se RECLAMA en `crear_idempotente`). Devuelve True si se borro.

    NO usar para registros que ya corrieron (su historial/gasto importa): solo el llamante
    que acaba de crearlo y vio fallar el encolado sabe que es seguro borrarlo.
    """
    if not isinstance(gen_id, str) or not gen_id.strip():
        return False
    try:
        ruta_fichero = _ruta(gen_id)
    except ValueError:
        return False
    try:
        ruta_fichero.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def actualizar(gen_id: str, cambios: dict[str, Any]) -> dict[str, Any]:
    """Mezcla `cambios` sobre el registro existente y lo reescribe (atomico).

    HOOK DE CIERRE (economia de tokens): cuando `cambios` lleva el registro a un estado
    TERMINAL, vuelca su gasto (tokens/coste de `metricas`) al ledger `gasto_ia` via
    `presupuesto_ia.registrar_cierre`. Este es el embudo UNICO por el que TODOS los caminos
    (claude, imagen, procesos, fakes de tests) fijan el terminal, asi que el ledger no
    depende de cada lanzador. Best-effort e idempotente (UPSERT por gen_id): un re-cierre
    (reintento/re-encolado tras deploy) actualiza la fila, no duplica gasto.
    """
    ruta_fichero = _ruta(gen_id)
    with bloqueo_archivo(ruta_fichero):
        actual = _leer_yaml(ruta_fichero) or {}
        fusion = {**actual, **cambios}
        pub = _publico(fusion, gen_id)
        _escribir_yaml_atomico(ruta_fichero, _cuerpo(pub))
    if cambios.get("estado") in _ESTADOS_TERMINALES:
        try:
            from .. import presupuesto_ia

            presupuesto_ia.registrar_cierre(pub)
        except Exception:  # noqa: BLE001 -- el ledger nunca debe romper la escritura del registro
            _log.warning("generacion %s: fallo el volcado al ledger de gasto", gen_id, exc_info=True)
    return pub


def _cuerpo(pub: dict[str, Any]) -> dict[str, Any]:
    """Cuerpo YAML de una generacion: el dict publico sin `id` y sin claves vacias."""
    return {
        k: v
        for k, v in pub.items()
        if k != "id" and v not in ("", None)
    }


def obtener(gen_id: str) -> dict[str, Any] | None:
    """Una generacion por id (None si no existe / id invalido / YAML corrupto)."""
    if not isinstance(gen_id, str) or not gen_id:
        return None
    try:
        ruta_fichero = _ruta(gen_id)
    except ValueError:
        return None
    if not ruta_fichero.is_file():
        return None
    datos = _leer_yaml(ruta_fichero)
    if datos is None:
        return None
    return _publico(datos, gen_id)


def _todas_ordenadas() -> list[dict[str, Any]]:
    """Todas las generaciones (publicas) ordenadas recientes primero (sin recortar).

    Las generaciones NO viven en el indice SQLite (son estado efimero de ejecucion en
    su propio almacen), asi que el orden/recorte se hace en memoria sobre el glob. El
    volumen lo ACOTA la poda de retencion (`podar_generaciones`, #128): sin ella el
    almacen y este escaneo crecian sin tope. Con la poda activa el conjunto queda en el
    orden de `KENI_GENERACIONES_RETENCION_MAX` (def 2000), un escaneo barato.

    SEGUIMIENTO (no en este cambio, bajo riesgo): este metodo parsea TODOS los .yaml en
    cada peticion solo para devolver una pagina. NO se cambia el orden aqui a mtime porque
    el orden CONTRACTUAL es por `fecha_inicio` (campo DENTRO del YAML), que difiere del
    mtime (el mtime cambia en cada `actualizar`); ordenar por mtime alteraria la semantica
    visible. La via correcta es un indice (un campo/columna `fecha_inicio` indexado) para
    paginar sin parsear todo; queda pendiente. De momento la poda basta para acotar el coste.
    """
    base = raiz()
    if not base.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for ruta_fichero in base.glob("*.yaml"):
        if ruta_fichero.name.startswith(".tmp-"):
            continue
        datos = _leer_yaml(ruta_fichero)
        if datos is None:
            continue
        pub = _publico(datos, ruta_fichero.stem)
        # Prompt y razonamiento pueden pesar (KB); solo se exponen en el detalle (`obtener`),
        # no en el listado de Actividad. Los quitamos aquí para que la lista quede liviana.
        pub.pop("prompt", None)
        pub.pop("razonamiento", None)
        items.append(pub)
    items.sort(key=lambda g: (g["fecha_inicio"], g["id"]), reverse=True)
    return items


def listar(
    limite: int | None = _LISTADO_MAX,
    desplazamiento: int = 0,
    *,
    marca: str | None = None,
) -> list[dict[str, Any]]:
    """Generaciones recientes primero (por `fecha_inicio` desc, luego id), paginadas.

    `limite=None` devuelve TODAS (sin recortar); por defecto recorta a `_LISTADO_MAX`
    (retrocompat con la UI de actividad). `desplazamiento` salta las N primeras.

    `marca` (opcional): si viene NO vacia, restringe a las generaciones de ESA marca
    (campo `marca` del registro). El default `None` (o "") NO filtra — todos los
    llamantes previos quedan inalterados. El filtro se aplica ANTES de paginar, asi el
    `limite`/`desplazamiento` operan sobre el subconjunto de la marca.
    """
    items = _todas_ordenadas()
    if marca:
        items = [g for g in items if g.get("marca") == marca]
    inicio = max(0, int(desplazamiento or 0))
    if limite is None:
        return items[inicio:]
    return items[inicio : inicio + max(0, int(limite))]


def contar() -> int:
    """Total de generaciones almacenadas (para el `total` del envelope de paginacion)."""
    return len(_todas_ordenadas())


# --------------------------------------------------------------------------- #
# Poda de retencion: acota el almacen de registros (disco + escaneo) #128       #
# --------------------------------------------------------------------------- #

# Defaults de la politica de retencion. Se leen INLINE de `os.environ` (no por
# `config.py`, propiedad de otro agente). Un registro se CONSERVA si es mas nuevo que
# `KENI_GENERACIONES_RETENCION_DIAS` (def 30 d) O si esta entre los `KENI_GENERACIONES_
# RETENCION_MAX` mas recientes (def 2000); solo se borra lo viejo que ademas cae fuera
# del piso de los N mas recientes. Asi el listado de Actividad (`_todas_ordenadas`,
# que parsea TODOS los .yaml en cada peticion) y el disco quedan acotados.
_RETENCION_DIAS_DEF = 30
_RETENCION_MAX_DEF = 2000


def _entero_env(nombre: str, defecto: int, *, minimo: int = 0) -> int:
    """Lee un entero >= `minimo` de `os.environ[nombre]`; cae a `defecto` si falta/inválido.

    Helper INLINE (no toca `config.py`, de otro agente): tolera valores ausentes, no
    numéricos o por debajo del mínimo sin romper la poda.
    """
    crudo = os.environ.get(nombre)
    if crudo is None:
        return defecto
    try:
        valor = int(str(crudo).strip())
    except (TypeError, ValueError):
        return defecto
    return valor if valor >= minimo else defecto


def podar_generaciones(
    *,
    dias: int | None = None,
    maximo: int | None = None,
    ahora: datetime | None = None,
) -> int:
    """Borra registros YAML de generacion fuera de la politica de retencion. Devuelve cuantos.

    POLITICA (conservadora, doble red de seguridad):
      - CONSERVA todo registro mas nuevo que `dias` (def `KENI_GENERACIONES_RETENCION_DIAS`,
        30 d), juzgado por el mtime del fichero (barato; sin parsear el YAML).
      - CONSERVA SIEMPRE los `maximo` registros mas recientes (def `KENI_GENERACIONES_
        RETENCION_MAX`, 2000), AUNQUE sean viejos: el piso de los N mas recientes NUNCA se
        borra. Solo es candidato a borrar lo que es viejo Y ademas cae por debajo del piso.

    SEGURIDAD: solo toca ficheros `<id>.yaml` del dir de generaciones cuyo nombre case con
    el patron de id (12 hex de `nuevo_id`) — nunca temporales `.tmp-*` ni nada ajeno. Tolera
    carreras (fichero ya borrado por otro): un `FileNotFoundError`/`OSError` al hacer stat o
    unlink se ignora por item, sin abortar el barrido. NO parsea los YAML (no depende de que
    sean validos), asi un fichero corrupto no rompe la poda. Loguea el total podado.

    `dias`/`maximo`/`ahora` se inyectan en tests; por defecto salen del entorno / del reloj.
    """
    dias_ret = dias if dias is not None else _entero_env(
        "KENI_GENERACIONES_RETENCION_DIAS", _RETENCION_DIAS_DEF, minimo=0
    )
    max_ret = maximo if maximo is not None else _entero_env(
        "KENI_GENERACIONES_RETENCION_MAX", _RETENCION_MAX_DEF, minimo=0
    )
    base = raiz()
    if not base.is_dir():
        return 0

    referencia = ahora if ahora is not None else datetime.now()
    corte = referencia.timestamp() - dias_ret * 86400.0

    # Recolecta (mtime, ruta) de los registros de generacion REALES (id de 12 hex), saltando
    # temporales y cualquier nombre ajeno. El stat es barato (no parsea el YAML).
    candidatos: list[tuple[float, Path]] = []
    for ruta_fichero in base.glob("*.yaml"):
        nombre = ruta_fichero.stem
        if not _ES_ID.fullmatch(nombre):
            continue  # no es un registro de generacion (`.tmp-*`, ajeno): no se toca
        try:
            mtime = ruta_fichero.stat().st_mtime
        except OSError:
            continue  # carrera (ya borrado) o ilegible: se omite
        candidatos.append((mtime, ruta_fichero))

    if len(candidatos) <= max_ret:
        return 0  # por debajo del piso: nada que podar

    # Mas reciente primero; el piso de los `max_ret` primeros queda SIEMPRE protegido.
    candidatos.sort(key=lambda par: par[0], reverse=True)
    podados = 0
    for mtime, ruta_fichero in candidatos[max_ret:]:
        if mtime >= corte:
            continue  # dentro de la ventana de dias: se conserva pese a estar fuera del piso
        try:
            ruta_fichero.unlink()
            podados += 1
        except FileNotFoundError:
            continue  # carrera: otro lo borro ya; cuenta como hecho sin sumar
        except OSError:
            _log.warning("Poda de generaciones: no se pudo borrar %s", ruta_fichero.name, exc_info=True)
            continue
    if podados:
        _log.info("Poda de generaciones: %d registro(s) viejo(s) borrado(s).", podados)
    return podados


def reclamar_zombis(max_edad_seg: float, *, ahora: datetime | None = None) -> int:
    """Marca como `error` (interrumpida) las generaciones colgadas en `ejecutando`.

    Una generacion nace `ejecutando` y solo pasa a terminal cuando corre su finalizador. Si
    el proceso que la ejecuta MUERE (reinicio/deploy, OOM, worker matado, `generar()` de
    imagen colgado), el finalizador nunca corre y el registro queda ZOMBI en `ejecutando`
    para siempre (el wall-timeout solo protege si el proceso sigue vivo). Este reaper barre
    las `ejecutando` cuyo `fecha_inicio` es mas viejo que `max_edad_seg` y las cierra como
    `error`/`interrumpido`. SEGURO: `max_edad_seg` debe ser MUY superior a cualquier job real
    (que termina en <= wall-timeout), asi nunca mata uno vivo. Devuelve cuantas reclamo.

    `ahora` se inyecta en tests; por defecto es la hora actual. Best-effort por item: un
    fallo al parsear/actualizar uno NO aborta el barrido.

    EXENTAS las generaciones cuyo job sigue PENDIENTE en la cola: no son zombis (nada llego
    a correr ni a morir), estan esperando turno — posiblemente retenidas MAS que el TTL por
    el corte de presupuesto o el kill switch (`presupuesto_ia`), o por una cola cargada.
    Segarlas las mataria en silencio: al reanudarse, la guardia anti-duplicado del reclamo
    veria el registro terminal y cerraria el job SIN ejecutarlo (trabajo perdido). Best-
    effort: si la cola no se puede leer, se asume vacia (comportamiento anti-zombi previo).
    """
    referencia = ahora if ahora is not None else datetime.now()
    try:
        from .. import repos

        en_cola = repos.gen_ids_jobs_pendientes()
    except Exception:  # noqa: BLE001 -- sin lectura de la cola, mejor reaper que zombis
        en_cola = set()
    reclamadas = 0
    for gen in _todas_ordenadas():
        if gen.get("estado") != ESTADO_EJECUTANDO:
            continue
        if gen.get("id") in en_cola:
            continue  # job aun pendiente: espera legitima (corte/pausa/cola), no zombi
        try:
            inicio = datetime.fromisoformat(gen.get("fecha_inicio", ""))
        except ValueError:
            continue  # sin fecha parseable: no podemos juzgar su edad, lo dejamos
        if (referencia - inicio).total_seconds() < max_edad_seg:
            continue  # aun dentro de ventana: podria estar viva de verdad
        try:
            actualizar(
                gen["id"],
                {
                    "estado": ESTADO_ERROR,
                    "motivo": MOTIVO_INTERRUMPIDO,
                    "error": "La generación se interrumpió (el proceso se reinició o se colgó).",
                    "fecha_fin": ahora_iso(),
                },
            )
            reclamadas += 1
        except Exception:  # noqa: BLE001 -- un fallo al reclamar uno no debe abortar el barrido
            continue
    return reclamadas
