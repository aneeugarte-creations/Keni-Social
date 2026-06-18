"""Gestor de N procesos `claude` PERSISTENTES (sesiones Ralph multi-turno, conversacion en vivo).

POR QUE EXISTE: keni-social ejecuta `claude -p` en modo ONE-SHOT (un job, una respuesta; ver
`generaciones`/`worker`). Los agentes Ralph necesitan CONVERSACION VIVA: un proceso `claude`
que se queda abierto y al que el humano va mandando turnos. El equivalente servidor del tmux de
Nolan v1. Cada Ralph es un proceso `claude` interactivo con stdin ABIERTO en modo stream-json:

    claude -p --input-format stream-json --output-format stream-json --include-partial-messages
           --verbose --model <modelo> --dangerously-skip-permissions

El stdin abierto permite el multi-turno: cada turno del humano se escribe como UNA linea JSON
(`{"type":"user","message":{"role":"user","content":[{"type":"text","text":...}]}}`) y `claude`
responde token a token por stdout (mismos eventos NDJSON que parsea `dominio/stream/invocacion`).
Cada Ralph trabaja sobre su PROPIO git worktree+rama del repo (`KENI_DEV_REPO`), SIN sandbox
(Bash/Write/Edit permitidos): es desarrollo de verdad, no generacion de copy.

DONDE CORRE: SOLO en la imagen del worker (con Node + `claude`), arrancado por
`worker_ralph` (instancia unica). El `back` no tiene `claude`: lo alcanza por el listener de
control de worker-ralph y lo proxea (admin-gated) en `api/ralph.py`.

SEPARACION testeable: las partes PURAS (pool de nombres, parser de stream-json, maquina de
estado) viven arriba y se testean sin subprocess; el gestor de procesos (`GestorRalph`) toca el
sistema (Popen, git worktree, hilos) y no se testea con un `claude` real.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field

_log = logging.getLogger("keni_consola.ralph_sesiones")

_CLAUDE = "claude"

# --------------------------------------------------------------------------- #
# Estados de un Ralph (maquina simple, contrato con el frontend).             #
# --------------------------------------------------------------------------- #
# idle      -> recien creado, aun no ha empezado a trabajar en un turno.
# activo    -> generando (un turno en curso: llega texto/razonamiento o arranco).
# esperando -> termino el turno (llego el `result`), a la espera del siguiente mensaje.
# error     -> el proceso murio/fallo el lanzamiento o un `result` vino con error.
ESTADO_IDLE = "idle"
ESTADO_ACTIVO = "activo"
ESTADO_ESPERANDO = "esperando"
ESTADO_ERROR = "error"
ESTADOS = (ESTADO_IDLE, ESTADO_ACTIVO, ESTADO_ESPERANDO, ESTADO_ERROR)

# Modelos ofrecidos por la burbuja Ralph (alias que `claude --model` entiende). opus por def.
MODELOS = ("opus", "sonnet", "haiku")
MODELO_DEF = "opus"


# --------------------------------------------------------------------------- #
# Pool de nombres estilo Nolan v1 (ziggy, nova, echo, ...).                    #
# --------------------------------------------------------------------------- #

POOL_NOMBRES: tuple[str, ...] = (
    "ziggy",
    "nova",
    "echo",
    "pixel",
    "comet",
    "atlas",
    "lumen",
    "vega",
    "orbit",
    "quartz",
    "sable",
    "indigo",
)


def siguiente_nombre(usados) -> str:
    """Primer nombre del pool no presente en `usados`; si todos estan tomados, uno sufijado.

    PURO: no toca estado global. `usados` es cualquier iterable de nombres en uso. El fallback
    sufijado (`ziggy-2`, ...) garantiza un nombre unico aunque haya mas Ralphs que nombres en el
    pool (el tope real lo aplica el gestor con `KENI_MAX_RALPH`)."""
    tomados = set(usados)
    for nombre in POOL_NOMBRES:
        if nombre not in tomados:
            return nombre
    # Pool agotado: sufija el primero con el menor entero libre.
    base = POOL_NOMBRES[0]
    i = 2
    while f"{base}-{i}" in tomados:
        i += 1
    return f"{base}-{i}"


# --------------------------------------------------------------------------- #
# stream-json: linea de ENTRADA (turno del humano) + parser de la SALIDA.      #
# --------------------------------------------------------------------------- #


def linea_mensaje_usuario(texto: str) -> str:
    """Serializa un turno del humano como UNA linea stream-json para el stdin de `claude`.

    Forma que espera `--input-format stream-json`: un objeto `user` con el contenido como
    bloque de texto. Termina en `\\n` (cada mensaje es una linea NDJSON). PURO."""
    obj = {
        "type": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": texto}]},
    }
    return json.dumps(obj, ensure_ascii=False) + "\n"


def estado_para_evento(evento: dict, estado_actual: str) -> str:
    """Maquina de estado PURA: nuevo estado de un Ralph tras consumir un evento stream-json.

    Transiciones:
      - `system`/`init`, `stream_event`, `assistant` -> `activo` (esta trabajando).
      - `result` con error -> `error`.
      - `result` ok        -> `esperando` (turno cerrado, a la espera del siguiente mensaje).
    Cualquier otra cosa conserva el estado. No transiciona desde `error` (terminal)."""
    if estado_actual == ESTADO_ERROR:
        return ESTADO_ERROR
    tipo = evento.get("type")
    if tipo == "result":
        subtype = evento.get("subtype")
        if bool(evento.get("is_error")) or (subtype not in (None, "success")):
            return ESTADO_ERROR
        return ESTADO_ESPERANDO
    if tipo in ("system", "stream_event", "assistant"):
        return ESTADO_ACTIVO
    return estado_actual


@dataclass
class ParserRalph:
    """Consume la SALIDA stream-json de un `claude` interactivo y emite eventos semanticos.

    `procesar_linea(linea)` devuelve una lista de eventos (dicts) a difundir a los suscriptores;
    sus claves son YA las del contrato SSE del frontend (el `tipo` es solo el discriminador, que
    el worker usa como nombre de evento `mensaje`/`estado` y NO viaja en el `data`):
      - `{"tipo": "mensaje", "delta": <fragmento>}` por cada `text_delta` del asistente (en vivo).
      - `{"tipo": "mensaje", "delta": "", "fin": True}` al cerrar el turno (corta el mensaje en
        curso del front; imprescindible para que el multi-turno no funda varios turnos en una
        burbuja al reproducir el buffer).
      - `{"tipo": "estado", "estado": <nuevo>}` cuando cambia el estado del Ralph.
    PURO respecto a I/O: el hilo lector lo alimenta linea a linea. Tolerante: lineas vacias o
    no-JSON se ignoran (degradacion robusta). El `thinking` NO se difunde (irrelevante para el
    chat); solo mueve el estado a `activo`.
    """

    estado: str = ESTADO_IDLE
    # Texto acumulado del turno en curso (para depurar/snapshot); se reinicia en cada turno.
    texto: str = ""

    def procesar_linea(self, linea: str) -> list[dict]:
        crudo = (linea or "").strip()
        if not crudo:
            return []
        try:
            evento = json.loads(crudo)
        except (json.JSONDecodeError, ValueError):
            return []
        if not isinstance(evento, dict):
            return []

        eventos: list[dict] = []
        # Texto en vivo del asistente (modo `--include-partial-messages`).
        if evento.get("type") == "stream_event":
            evt = evento.get("event")
            if isinstance(evt, dict) and evt.get("type") == "content_block_delta":
                delta = evt.get("delta")
                if isinstance(delta, dict) and delta.get("type") == "text_delta":
                    t = delta.get("text")
                    if isinstance(t, str) and t:
                        self.texto += t
                        eventos.append({"tipo": "mensaje", "delta": t})

        nuevo = estado_para_evento(evento, self.estado)
        if nuevo != self.estado:
            anterior = self.estado
            self.estado = nuevo
            if anterior == ESTADO_ACTIVO and nuevo in (ESTADO_ESPERANDO, ESTADO_ERROR):
                # Cierra el turno: si hubo texto, corta el mensaje en curso del front (un `fin`
                # por turno con texto, para que cada turno sea su propia burbuja al reproducir el
                # buffer) y limpia el acumulador para el siguiente turno.
                if self.texto:
                    eventos.append({"tipo": "mensaje", "delta": "", "fin": True})
                self.texto = ""
            eventos.append({"tipo": "estado", "estado": nuevo})
        return eventos


def construir_argv(modelo: str) -> list[str]:
    """argv de un `claude` interactivo multi-turno (stream-json IN/OUT) SIN sandbox.

    `--input-format stream-json` mantiene stdin abierto (multi-turno); `--output-format
    stream-json --include-partial-messages --verbose` da los deltas en vivo; `-p` corre headless;
    `--dangerously-skip-permissions` permite las tools (Bash/Write/Edit) sin aprobacion
    interactiva (carril dev, sin sandbox). PURO (solo compone la lista)."""
    return [
        _CLAUDE,
        "-p",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--include-partial-messages",
        "--verbose",
        "--model",
        modelo or MODELO_DEF,
        "--dangerously-skip-permissions",
    ]


# --------------------------------------------------------------------------- #
# Gestor de procesos (IMPURO: Popen + git worktree + hilos). Instancia unica.  #
# --------------------------------------------------------------------------- #
#
# Cada turno del lector empuja eventos a `eventos` y despierta a los suscriptores via `cond`.
# `leer_stream` reproduce el buffer entero al suscribirse y luego sigue en vivo (asi el SSE del
# back reconecta sin perderse nada). El proceso worker-ralph es de INSTANCIA UNICA, asi que el
# registro en memoria es seguro.

# Cadencia con que `leer_stream` despierta sin eventos nuevos para emitir un heartbeat (mantiene
# viva la conexion SSE a traves de Traefik) y reevaluar el cierre.
_HEARTBEAT_SEG = 15.0
_ESPERA_KILL_SEG = 5


@dataclass
class SesionRalph:
    id: str
    nombre: str
    modelo: str
    creado: float
    proc: subprocess.Popen | None = None
    worktree: str = ""
    rama: str = ""
    estado: str = ESTADO_IDLE
    detalle: str = ""  # mensaje de error legible cuando estado == error
    parser: ParserRalph = field(default_factory=ParserRalph)
    eventos: list[dict] = field(default_factory=list)
    cerrado: bool = False
    cond: threading.Condition = field(default_factory=threading.Condition)
    escritura: threading.Lock = field(default_factory=threading.Lock)

    def info(self) -> dict:
        """Vista serializable (contrato `Ralph` del frontend)."""
        return {
            "id": self.id,
            "nombre": self.nombre,
            "modelo": self.modelo,
            "estado": self.estado,
            "creado": self.creado,
        }


class GestorRalph:
    """Registro de Ralphs vivos. spawn / enviar / leer_stream / kill / listar."""

    def __init__(self) -> None:
        self._sesiones: dict[str, SesionRalph] = {}
        self._lock = threading.Lock()

    # -- consulta ---------------------------------------------------------- #

    def listar(self) -> list[dict]:
        with self._lock:
            return [s.info() for s in self._sesiones.values()]

    def obtener(self, ralph_id: str) -> SesionRalph | None:
        with self._lock:
            return self._sesiones.get(ralph_id)

    # -- ciclo de vida ----------------------------------------------------- #

    def spawn(self, prompt: str, modelo: str | None = None) -> dict:
        """Crea un Ralph: worktree+rama, lanza `claude` interactivo y envia el `prompt` inicial.

        Devuelve la info del Ralph. Si se alcanza el tope (`KENI_MAX_RALPH`) lanza
        `RuntimeError`. Si el worktree o el lanzamiento fallan, el Ralph queda en estado `error`
        con `detalle` (nunca casca el listener)."""
        from . import config

        modelo = modelo if modelo in MODELOS else MODELO_DEF
        with self._lock:
            if len(self._sesiones) >= config.ralph_max():
                raise RuntimeError("limite de Ralphs alcanzado")
            nombre = siguiente_nombre(s.nombre for s in self._sesiones.values())
            ralph_id = uuid.uuid4().hex
            sesion = SesionRalph(
                id=ralph_id, nombre=nombre, modelo=modelo, creado=time.time()
            )
            self._sesiones[ralph_id] = sesion

        try:
            sesion.worktree, sesion.rama = _crear_worktree(config.dev_repo(), nombre)
        except Exception as e:  # noqa: BLE001 -- sin repo git utilizable: arranca en dir plano
            # /repo aún no clonado (p.ej. GitHub sin conectar) o git no disponible: el Ralph
            # arranca igual en un directorio de trabajo plano y escribible para poder CONVERSAR;
            # sin contexto del repo hasta que /repo exista. NO bloquea el chat.
            _log.warning("Ralph %s: sin worktree (%s); arranca en directorio plano", nombre, e)
            sesion.worktree, sesion.rama = _dir_trabajo_plano(nombre), ""

        try:
            sesion.proc = subprocess.Popen(  # noqa: S603 -- argv lista, sin shell
                construir_argv(modelo),
                cwd=sesion.worktree,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,  # line-buffered: el lector ve cada linea NDJSON al instante
                start_new_session=True,  # grupo propio: matar_arbol en kill
            )
        except FileNotFoundError:
            self._marcar_error(sesion, "claude no disponible en este servidor")
            return sesion.info()
        except OSError as e:
            self._marcar_error(sesion, f"no se pudo lanzar claude: {e}")
            return sesion.info()

        hilo = threading.Thread(
            target=self._bucle_lector, args=(sesion,), name=f"ralph-{nombre}", daemon=True
        )
        hilo.start()

        if prompt and prompt.strip():
            self.enviar(ralph_id, prompt)
        return sesion.info()

    def enviar(self, ralph_id: str, texto: str) -> dict:
        """Escribe un turno del humano en el stdin del Ralph. {ok, error?}."""
        sesion = self.obtener(ralph_id)
        if sesion is None:
            return {"ok": False, "error": "Ralph desconocido"}
        if sesion.proc is None or sesion.proc.stdin is None or sesion.cerrado:
            return {"ok": False, "error": "Ralph no esta activo"}
        with sesion.escritura:
            try:
                sesion.proc.stdin.write(linea_mensaje_usuario(texto))
                sesion.proc.stdin.flush()
            except (OSError, ValueError):
                return {"ok": False, "error": "no se pudo enviar (proceso cerrado)"}
        # El humano acaba de pedir algo: el Ralph pasa a activo (el `result` lo volvera a
        # esperando). Emitimos el estado ya, sin aguardar al primer evento del modelo.
        self._fijar_estado(sesion, ESTADO_ACTIVO)
        return {"ok": True}

    def kill(self, ralph_id: str) -> dict:
        """Mata el Ralph (arbol de proceso) y limpia su worktree. Idempotente. {ok}."""
        with self._lock:
            sesion = self._sesiones.pop(ralph_id, None)
        if sesion is None:
            return {"ok": True}
        _matar_proceso(sesion.proc)
        _borrar_worktree(sesion.worktree)
        with sesion.cond:
            sesion.cerrado = True
            sesion.cond.notify_all()
        return {"ok": True}

    # -- stream ------------------------------------------------------------ #

    def leer_stream(self, ralph_id: str):
        """Generador BLOQUEANTE de eventos de un Ralph: reproduce el buffer y sigue en vivo.

        Reproduce desde el inicio (para que el SSE del back reconecte sin huecos) y luego cede
        cada evento nuevo segun llega. Emite `{"tipo": "ping"}` cada `_HEARTBEAT_SEG` sin
        novedades (heartbeat) y termina cuando el Ralph se cierra (kill o EOF del proceso)."""
        sesion = self.obtener(ralph_id)
        if sesion is None:
            return
        idx = 0
        while True:
            with sesion.cond:
                while idx >= len(sesion.eventos) and not sesion.cerrado:
                    if not sesion.cond.wait(timeout=_HEARTBEAT_SEG):
                        # Sin novedades en la ventana: heartbeat (fuera del lock).
                        break
                nuevos = sesion.eventos[idx:]
                idx = len(sesion.eventos)
                cerrado = sesion.cerrado
            if nuevos:
                for ev in nuevos:
                    yield ev
            else:
                yield {"tipo": "ping"}
            if cerrado and idx >= len(sesion.eventos):
                return

    # -- interno ----------------------------------------------------------- #

    def _bucle_lector(self, sesion: SesionRalph) -> None:
        """Lee el stdout del `claude` linea a linea, parsea y difunde los eventos."""
        proc = sesion.proc
        if proc is None or proc.stdout is None:
            return
        try:
            for linea in proc.stdout:
                for ev in sesion.parser.procesar_linea(linea):
                    if ev.get("tipo") == "estado":
                        self._fijar_estado(sesion, ev["estado"])
                    else:
                        self._emitir(sesion, ev)
        except (OSError, ValueError):
            pass
        finally:
            # El proceso cerro su stdout: turno/sesion terminados. Si no esta ya en error y no
            # cerro limpio en `esperando`, lo dejamos como esperando salvo que muriese con rc!=0.
            rc = proc.poll()
            if sesion.estado != ESTADO_ERROR and rc not in (0, None):
                self._marcar_error(sesion, f"el proceso termino con codigo {rc}")
            with sesion.cond:
                sesion.cerrado = True
                sesion.cond.notify_all()

    def _emitir(self, sesion: SesionRalph, evento: dict) -> None:
        with sesion.cond:
            sesion.eventos.append(evento)
            sesion.cond.notify_all()

    def _fijar_estado(self, sesion: SesionRalph, estado: str) -> None:
        if sesion.estado == estado:
            return
        sesion.estado = estado
        self._emitir(sesion, {"tipo": "estado", "estado": estado})

    def _marcar_error(self, sesion: SesionRalph, detalle: str) -> None:
        sesion.detalle = detalle
        sesion.parser.estado = ESTADO_ERROR
        sesion.estado = ESTADO_ERROR
        with sesion.cond:
            sesion.eventos.append({"tipo": "estado", "estado": ESTADO_ERROR, "detalle": detalle})
            sesion.cerrado = True
            sesion.cond.notify_all()


# --------------------------------------------------------------------------- #
# Git worktree por Ralph + limpieza de procesos (best-effort).                 #
# --------------------------------------------------------------------------- #


def _base_escribible(sub: str, repo: str) -> str:
    """Directorio base ESCRIBIBLE para worktrees/cwd. `$KENI_DATA_DIR/<sub>` en el servidor
    (el padre de `/repo` es la raíz, no escribible por el uid no-root); junto al repo si no hay
    `KENI_DATA_DIR` (tests/local)."""
    raiz = os.environ.get("KENI_DATA_DIR")
    base = (
        os.path.join(raiz, sub)
        if raiz
        else os.path.join(os.path.dirname(os.path.abspath(repo)), sub)
    )
    os.makedirs(base, exist_ok=True)
    return base


def _dir_trabajo_plano(nombre: str) -> str:
    """Directorio de trabajo plano y escribible para un Ralph sin repo git (fallback).

    Permite CONVERSAR con el Ralph aunque `/repo` no esté clonado todavía (GitHub sin conectar)."""
    destino = os.path.join(
        _base_escribible("ralph-cwd", ""), f"{nombre}-{uuid.uuid4().hex[:8]}"
    )
    os.makedirs(destino, exist_ok=True)
    return destino


def _crear_worktree(repo: str, nombre: str) -> tuple[str, str]:
    """Crea un worktree+rama del `repo` para un Ralph. Devuelve (ruta_worktree, rama).

    Rama `ralph/<nombre>`; worktree en `$KENI_DATA_DIR/ralph-worktrees/<nombre>-<sufijo>`.
    Sube la excepcion si git falla (el llamante cae al directorio plano)."""
    rama = f"ralph/{nombre}"
    sufijo = uuid.uuid4().hex[:8]
    base = _base_escribible("ralph-worktrees", repo)
    destino = os.path.join(base, f"{nombre}-{sufijo}")
    subprocess.run(  # noqa: S603 -- argv lista, sin shell
        ["git", "-C", repo, "worktree", "add", "-b", rama, destino],
        check=True,
        capture_output=True,
        text=True,
    )
    return destino, rama


def _borrar_worktree(worktree: str) -> None:
    """Elimina el worktree de un Ralph (best-effort; nunca propaga).

    `git worktree remove` desde el propio worktree desregistra la entrada en el repo padre; el
    `rmtree` final cubre el caso de un worktree ya huerfano o un `git` ausente."""
    if not worktree:
        return
    try:
        subprocess.run(  # noqa: S603 -- argv lista, sin shell
            ["git", "-C", worktree, "worktree", "remove", "--force", worktree],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        pass
    shutil.rmtree(worktree, ignore_errors=True)


def _matar_proceso(proc: subprocess.Popen | None) -> None:
    """Mata el GRUPO del proceso `claude` (lider de sesion) y cierra sus tuberias. Best-effort."""
    if proc is None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except Exception:  # noqa: BLE001 -- best-effort
            pass
    try:
        proc.wait(timeout=_ESPERA_KILL_SEG)
    except Exception:  # noqa: BLE001 -- reapeo best-effort
        pass


# Instancia unica del gestor (worker-ralph no escala). `worker_ralph` la usa directamente.
gestor = GestorRalph()
