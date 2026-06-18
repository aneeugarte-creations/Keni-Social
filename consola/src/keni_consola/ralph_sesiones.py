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
import tempfile
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
# dormido   -> restaurado de disco tras un reinicio de worker-ralph, sin proceso vivo. NO es
#              terminal: al primer mensaje se reanuda con `claude --resume` (memoria intacta).
ESTADO_IDLE = "idle"
ESTADO_ACTIVO = "activo"
ESTADO_ESPERANDO = "esperando"
ESTADO_ERROR = "error"
ESTADO_DORMIDO = "dormido"
ESTADOS = (ESTADO_IDLE, ESTADO_ACTIVO, ESTADO_ESPERANDO, ESTADO_ERROR, ESTADO_DORMIDO)

# Modelos ofrecidos por la burbuja Ralph (alias que `claude --model` entiende). opus por def.
MODELOS = ("opus", "sonnet", "haiku")
MODELO_DEF = "opus"

# Tipo de Ralph (contrato con el frontend):
#   operativo -> asistente del equipo de redes: usa el MCP de la app (tools keni_*) para ayudar
#                en el día a día (marcas, piezas, métricas, noticias, cola, aprobación). NO toca el
#                filesystem ni el código. Es el que ve TODO el equipo.
#   dev       -> agente de DESARROLLO sobre el repo (worktree, sin sandbox). Solo superadmin.
TIPO_OPERATIVO = "operativo"
TIPO_DEV = "dev"
TIPOS = (TIPO_OPERATIVO, TIPO_DEV)
TIPO_DEF = TIPO_OPERATIVO

# Persona del Ralph OPERATIVO (CLAUDE.md que se escribe en su cwd). El de desarrollo hereda el
# CLAUDE.md del repo (su worktree). Mantenlo breve: el detalle operativo lo da el MCP.
_PERSONA_OPERATIVA = """# Ralph — asistente operativo de keni-social

Eres el asistente del equipo de redes de keni-social (piloto AMX: UnoTV / Claro Sports).
Hablas español de México, cercano y claro. Ayudas en el día a día: consultar marcas y redes,
preparar y mover contenido, leer métricas, trabajar el pool de noticias, vigilar la cola y el
flujo de aprobación.

Tienes el MCP de la app: usa las tools `keni_*` para consultar y operar. Empieza SIEMPRE por
`keni_contexto` para conocer marcas, redes y estados válidos antes de actuar.

Reglas:
- NO tocas el sistema de ficheros ni el código (no eres un agente de desarrollo).
- De cara a las redes manda el criterio humano: preparas, propones y dejas en revisión; el
  equipo decide qué se publica. No fuerces publicaciones reales.
- Si una acción es ambigua o arriesgada, pregunta antes de ejecutarla.
"""

# Slug del repo para clonar/asegurar /repo (mismo que worker_dev).
_REPO_SLUG = "kenitech-io/keni-social"

# Persona del Ralph de DESARROLLO. Se inyecta con `--append-system-prompt` (NO sobrescribe el
# CLAUDE.md del repo, que ya está en su worktree). Le dice quién es, que su workspace YA es un
# worktree de main y CÓMO promover de verdad (no basta un commit local).
_PERSONA_DEV = (
    "Eres Ralph, un ayudante de DESARROLLO que vive DENTRO de la propia app keni-social (la "
    "Consola). Tu trabajo es arreglar BUGS y hacer cambios SIMPLES y acotados. Para cosas "
    "COMPLEJAS o ambiciosas NO improvises: existe el sistema de Sugerencias (kanban, con "
    "discovery→build); deriva ahí esas peticiones.\n\n"
    "Tu workspace YA es un git worktree de `main` recién traído (tu rama propia `ralph/<nombre>` "
    "creada desde `origin/main`). NO está vacío y NO tienes que buscar ni clonar el repo: el "
    "código está aquí, trabaja sobre él.\n\n"
    "Para que tus cambios lleguen a producción NO basta un commit local en main. Flujo "
    "OBLIGATORIO:\n"
    "1. Trabaja en tu worktree y haz commits en TU rama (`ralph/<nombre>`), no en main.\n"
    "2. Promueve con `bash scripts/promover-main.sh` desde tu worktree: hace fetch+rebase+push a "
    "main e imprime la limpieza. Si te rechaza: `git fetch && git rebase origin/main` y "
    "reintenta. NUNCA hagas push directo a main a mano.\n"
    "3. Cambio de comportamiento = tests en el MISMO commit. Comentarios limpios (qué hace el "
    "código hoy, no el historial de bugs).\n"
)

# Documentos EDITABLES (biblioteca de prompts, clase `desarrollo`) que gobiernan la persona de
# cada Ralph. Son los que se ven/editan en la UI: Contexto → pestaña Desarrollo. Editarlos cambia
# el comportamiento del Ralph SIN tocar código (lo recoge el siguiente Ralph que se lance).
_DOC_PERSONA_DEV = "editorial/desarrollo/ralph"
_DOC_PERSONA_OPERATIVA = "editorial/desarrollo/ralph-operativo"


def _persona_doc(doc_id: str, respaldo: str) -> str:
    """Lee el cuerpo del doc editable `doc_id` de la biblioteca; si no se puede (libprompts/IO),
    devuelve `respaldo` (texto base en código). Best-effort: nunca casca."""
    try:
        from .libprompts import cuerpo_efectivo

        cuerpo = cuerpo_efectivo(doc_id)
        if cuerpo and cuerpo.strip():
            return cuerpo
    except Exception:  # noqa: BLE001 -- libprompts/IO best-effort: usa el respaldo
        _log.warning("Ralph: no se pudo leer la persona editable %s; uso el respaldo", doc_id, exc_info=True)
    return respaldo


def _persona_dev() -> str:
    """Persona del Ralph de DESARROLLO (doc editable `editorial/desarrollo/ralph`)."""
    return _persona_doc(_DOC_PERSONA_DEV, _PERSONA_DEV)


def _persona_operativa() -> str:
    """Persona del Ralph OPERATIVO (doc editable `editorial/desarrollo/ralph-operativo`)."""
    return _persona_doc(_DOC_PERSONA_OPERATIVA, _PERSONA_OPERATIVA)


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
    # session_id de `claude` (evento `system`/`init`): la clave para reanudar con `--resume`.
    session_id: str = ""

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

        if evento.get("type") == "system":
            sid = evento.get("session_id")
            if isinstance(sid, str) and sid:
                self.session_id = sid

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
                # buffer) y limpia el acumulador para el siguiente turno. El texto completo del
                # turno viaja como clave extra `completo` (el front la ignora; el gestor la usa
                # para guardar la transcripcion).
                if self.texto:
                    eventos.append(
                        {"tipo": "mensaje", "delta": "", "fin": True, "completo": self.texto}
                    )
                self.texto = ""
            eventos.append({"tipo": "estado", "estado": nuevo})
        return eventos


def construir_argv(
    modelo: str,
    tipo: str = TIPO_DEF,
    *,
    mcp_config: str | None = None,
    resume: str | None = None,
    system_extra: str | None = None,
) -> list[str]:
    """argv de un `claude` interactivo multi-turno (stream-json IN/OUT).

    `--input-format stream-json` mantiene stdin abierto (multi-turno); `--output-format
    stream-json --include-partial-messages --verbose` da los deltas en vivo; `-p` corre headless;
    `--dangerously-skip-permissions` deja correr las tools sin aprobacion interactiva.
    - `dev`: sin restriccion de tools (Bash/Write/Edit) sobre el worktree del repo.
    - `operativo`: VETA Bash/Write/Edit (no toca el filesystem) y engancha el MCP de la app
      (`--mcp-config` + `--strict-mcp-config`) para que use las tools `keni_*`.
    Con `resume`, antepone `--resume <id>` tras `-p` para reanudar una sesion guardada (memoria
    intacta) en lugar de empezar una nueva. PURO (solo compone la lista)."""
    argv = [_CLAUDE, "-p"]
    if resume:
        argv += ["--resume", resume]
    argv += [
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
    if system_extra:
        argv += ["--append-system-prompt", system_extra]
    if tipo == TIPO_OPERATIVO:
        argv += ["--disallowed-tools", "Bash", "Edit", "Write"]
        if mcp_config:
            argv += ["--mcp-config", mcp_config, "--strict-mcp-config"]
    return argv


def _escribir_persona_operativa(destino_dir: str) -> None:
    """Escribe el CLAUDE.md del Ralph operativo en su cwd (best-effort), desde el doc EDITABLE
    `editorial/desarrollo/ralph-operativo` (UI: Contexto → Desarrollo) o su respaldo."""
    try:
        with open(os.path.join(destino_dir, "CLAUDE.md"), "w", encoding="utf-8") as fh:
            fh.write(_persona_operativa())
    except OSError:
        _log.warning("Ralph operativo: no se pudo escribir CLAUDE.md en %s", destino_dir)


def _mcp_config(destino_dir: str, usuario_id: str | None = None) -> str | None:
    """Escribe el `--mcp-config` que engancha el MCP de la app (`/mcp`) y devuelve su ruta.

    Apunta a `KENI_MCP_URL` (def `http://back:8765/mcp`) con `Authorization: Bearer
    KENI_MCP_BEARER`. Si viene `usuario_id`, añade `X-Keni-Usuario-Id` para que el MCP actúe
    como ESE usuario (acotado a sus permisos) en vez del usuario fijo. Sin bearer, el MCP no está
    disponible: devuelve None (el Ralph arranca igual, sin tools del MCP) en vez de fallar."""
    url = os.environ.get("KENI_MCP_URL", "http://back:8765/mcp")
    bearer = os.environ.get("KENI_MCP_BEARER", "")
    if not bearer:
        _log.warning("Ralph operativo: sin KENI_MCP_BEARER; arranca sin tools del MCP")
        return None
    headers = {"Authorization": f"Bearer {bearer}"}
    if usuario_id:
        headers["X-Keni-Usuario-Id"] = usuario_id
    cfg = {
        "mcpServers": {
            "keni": {
                "type": "http",
                "url": url,
                "headers": headers,
            }
        }
    }
    ruta = os.path.join(destino_dir, ".mcp-keni.json")
    try:
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
    except OSError:
        _log.warning("Ralph operativo: no se pudo escribir el mcp-config en %s", destino_dir)
        return None
    return ruta


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
    tipo: str = TIPO_DEF
    proc: subprocess.Popen | None = None
    worktree: str = ""
    rama: str = ""
    estado: str = ESTADO_IDLE
    detalle: str = ""  # mensaje de error legible cuando estado == error
    # session_id de `claude` (para `--resume`) y usuario que lo creo (para reconstruir el MCP).
    session_id: str = ""
    usuario_id: str = ""
    # Turnos cerrados: [{"autor": "tu"|"ralph", "texto": str}]. Se persiste y se re-siembra en
    # `eventos` al restaurar, para que el SSE reproduzca el historial tras un reinicio.
    transcripcion: list[dict] = field(default_factory=list)
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
            "tipo": self.tipo,
            "estado": self.estado,
            "creado": self.creado,
        }


class GestorRalph:
    """Registro de Ralphs vivos. spawn / enviar / leer_stream / kill / listar."""

    def __init__(self) -> None:
        self._sesiones: dict[str, SesionRalph] = {}
        self._lock = threading.Lock()
        self._restaurar()

    # -- consulta ---------------------------------------------------------- #

    def listar(self) -> list[dict]:
        with self._lock:
            return [s.info() for s in self._sesiones.values()]

    def obtener(self, ralph_id: str) -> SesionRalph | None:
        with self._lock:
            return self._sesiones.get(ralph_id)

    # -- ciclo de vida ----------------------------------------------------- #

    def spawn(
        self,
        prompt: str,
        modelo: str | None = None,
        tipo: str | None = None,
        usuario_id: str | None = None,
    ) -> dict:
        """Crea un Ralph y lanza `claude` interactivo con el `prompt` inicial.

        `tipo` decide el entorno: `operativo` (asistente del equipo, MCP de la app, sin
        filesystem) o `dev` (worktree del repo, sin sandbox). Devuelve la info del Ralph. Si se
        alcanza el tope (`KENI_MAX_RALPH`) lanza `RuntimeError`. Si algo falla, el Ralph queda en
        estado `error` con `detalle` (nunca casca el listener)."""
        from . import config

        modelo = modelo if modelo in MODELOS else MODELO_DEF
        tipo = tipo if tipo in TIPOS else TIPO_DEF
        with self._lock:
            if len(self._sesiones) >= config.ralph_max():
                raise RuntimeError("limite de Ralphs alcanzado")
            nombre = siguiente_nombre(s.nombre for s in self._sesiones.values())
            ralph_id = uuid.uuid4().hex
            sesion = SesionRalph(
                id=ralph_id,
                nombre=nombre,
                modelo=modelo,
                tipo=tipo,
                creado=time.time(),
                usuario_id=usuario_id or "",
            )
            self._sesiones[ralph_id] = sesion

        if tipo == TIPO_DEV:
            try:
                sesion.worktree, sesion.rama = _crear_worktree(config.dev_repo(), nombre)
            except Exception as e:  # noqa: BLE001 -- sin repo no hay carril dev: error claro
                # El Ralph de desarrollo NECESITA el repo: si no se puede clonar (GitHub sin
                # conectar) lo dejamos en error explícito en vez de arrancar en un dir vacío que
                # confunde al agente ("el directorio está vacío").
                _log.warning("Ralph %s: no se pudo preparar el worktree: %s", nombre, e)
                self._marcar_error(
                    sesion,
                    "no se pudo preparar el repo de desarrollo (conecta GitHub en "
                    "Sistema → Proveedores)",
                )
                return sesion.info()
        else:
            # Operativo: dir de trabajo plano; la persona (CLAUDE.md) y el MCP los escribe el
            # lanzador al arrancar el proceso.
            sesion.worktree = _dir_trabajo_plano(nombre)

        if not self._lanzar_proceso(sesion, reanudar=False):
            return sesion.info()

        self._guardar()
        if prompt and prompt.strip():
            self.enviar(ralph_id, prompt)
        return sesion.info()

    def enviar(self, ralph_id: str, texto: str) -> dict:
        """Escribe un turno del humano en el stdin del Ralph. {ok, error?}.

        Si el proceso esta dormido (restaurado de disco) o murio, lo reanuda con `--resume`
        ANTES de escribir: el primer mensaje tras un reinicio revive al Ralph con memoria intacta.
        """
        sesion = self.obtener(ralph_id)
        if sesion is None:
            return {"ok": False, "error": "Ralph desconocido"}
        if sesion.proc is None or sesion.proc.poll() is not None:
            if not self._reanudar(sesion):
                return {"ok": False, "error": sesion.detalle or "no se pudo reanudar el Ralph"}
        if sesion.proc is None or sesion.proc.stdin is None:
            return {"ok": False, "error": "Ralph no esta activo"}
        sesion.transcripcion.append({"autor": "tu", "texto": texto})
        self._guardar()
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
        # Ya no esta en `_sesiones`: el snapshot lo deja fuera del estado persistido (kill = descartar).
        self._guardar()
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
                    elif ev.get("tipo") == "mensaje" and ev.get("fin") and "completo" in ev:
                        # Cierre de un turno del Ralph: guarda el texto completo en la
                        # transcripcion y NO lo difunde (el front recibe solo {delta:"",fin:true}).
                        completo = ev.pop("completo")
                        sesion.transcripcion.append({"autor": "ralph", "texto": completo})
                        self._emitir(sesion, ev)
                        self._guardar()
                    else:
                        self._emitir(sesion, ev)
                # session_id de `claude` (lo emite el evento `system`/`init`): persistelo en cuanto
                # aparezca o cambie, para poder reanudar con `--resume` tras un reinicio.
                if sesion.parser.session_id and sesion.parser.session_id != sesion.session_id:
                    sesion.session_id = sesion.parser.session_id
                    self._guardar()
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

    # -- lanzamiento / reanudacion ---------------------------------------- #

    def _lanzar_proceso(self, sesion: SesionRalph, *, reanudar: bool) -> bool:
        """Lanza el proceso `claude` de la sesion y arranca su hilo lector. Devuelve True si
        arranco; si falla deja la sesion en error y devuelve False.

        Con `reanudar` y un `session_id` guardado, usa `--resume <id>` para continuar la
        conversacion con memoria intacta. Para operativo (re)escribe la persona y el mcp-config
        en el cwd (reconstruido con `sesion.usuario_id`)."""
        mcp_cfg: str | None = None
        system_extra: str | None = None
        if sesion.tipo == TIPO_OPERATIVO:
            _escribir_persona_operativa(sesion.worktree)
            mcp_cfg = _mcp_config(sesion.worktree, sesion.usuario_id or None)
        else:
            system_extra = _persona_dev()
        resume = sesion.session_id if (reanudar and sesion.session_id) else None
        try:
            sesion.proc = subprocess.Popen(  # noqa: S603 -- argv lista, sin shell
                construir_argv(
                    sesion.modelo, sesion.tipo, mcp_config=mcp_cfg, resume=resume,
                    system_extra=system_extra,
                ),
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
            return False
        except OSError as e:
            self._marcar_error(sesion, f"no se pudo lanzar claude: {e}")
            return False
        hilo = threading.Thread(
            target=self._bucle_lector, args=(sesion,), name=f"ralph-{sesion.nombre}", daemon=True
        )
        hilo.start()
        return True

    def _reanudar(self, sesion: SesionRalph) -> bool:
        """Revive un Ralph dormido o muerto: relanza `claude --resume` con memoria intacta.

        Resetea el lector y el flag de cierre, recrea el cwd si desaparecio (operativo) y vuelve a
        `esperando`. Devuelve False (dejando la sesion en error) si no puede reanudarse."""
        if sesion.proc is not None and sesion.proc.poll() is None:
            return True
        if not sesion.worktree or not os.path.isdir(sesion.worktree):
            if sesion.tipo == TIPO_OPERATIVO:
                sesion.worktree = _dir_trabajo_plano(sesion.nombre)
            else:
                self._marcar_error(
                    sesion, "el worktree del Ralph ya no existe; no se puede reanudar"
                )
                return False
        sesion.detalle = ""
        sesion.parser = ParserRalph()
        with sesion.cond:
            sesion.cerrado = False
        self._fijar_estado(sesion, ESTADO_ESPERANDO)
        return self._lanzar_proceso(sesion, reanudar=True)

    # -- persistencia ----------------------------------------------------- #

    def _guardar(self) -> None:
        """Persiste (JSON atomico) los Ralphs resumibles (con `session_id`). Best-effort: si la
        IO falla, avisa y nunca casca. Toma el snapshot bajo lock y escribe fuera de el."""
        try:
            with self._lock:
                registros = [_registro(s) for s in self._sesiones.values() if s.session_id]
            ruta = _ruta_estado()
            tmp = f"{ruta}.{uuid.uuid4().hex}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"sesiones": registros}, fh, ensure_ascii=False)
            os.replace(tmp, ruta)
        except Exception as e:  # noqa: BLE001 -- persistencia best-effort: nunca tumba el gestor
            _log.warning("Ralph: no se pudo persistir el estado: %s", e)

    def _restaurar(self) -> None:
        """Carga el estado persistido y reconstruye las sesiones como DORMIDO (sin proceso vivo).

        No arranca procesos: la reanudacion es perezosa (al primer mensaje). Siembra `eventos` con
        la transcripcion para que un cliente que reconecte por SSE reproduzca el historial."""
        ruta = _ruta_estado()
        try:
            with open(ruta, encoding="utf-8") as fh:
                datos = json.load(fh)
        except (OSError, ValueError):
            return
        registros = datos.get("sesiones") if isinstance(datos, dict) else None
        if not isinstance(registros, list):
            return
        for reg in registros:
            if not isinstance(reg, dict) or not reg.get("id"):
                continue
            try:
                sesion = _desde_registro(reg)
            except Exception as e:  # noqa: BLE001 -- un registro corrupto no tumba el arranque
                _log.warning("Ralph: registro persistido ilegible (%s); se omite", e)
                continue
            self._sesiones[sesion.id] = sesion


# --------------------------------------------------------------------------- #
# Persistencia del estado de los Ralphs (JSON en $KENI_DATA_DIR, sobrevive reinicios).        #
# --------------------------------------------------------------------------- #


def _ruta_estado() -> str:
    """Ruta del JSON con el estado de los Ralphs. Bajo `$KENI_DATA_DIR` (volumen persistente) en
    el servidor; en el temporal del sistema si no esta definido (tests/local)."""
    base = os.environ.get("KENI_DATA_DIR") or tempfile.gettempdir()
    return os.path.join(base, "ralph-estado.json")


def _registro(sesion: SesionRalph) -> dict:
    """Vista serializable de un Ralph para persistir (sin proceso ni locks). La transcripcion se
    copia para poder volcarla a JSON fuera del lock sin carreras."""
    return {
        "id": sesion.id,
        "nombre": sesion.nombre,
        "modelo": sesion.modelo,
        "tipo": sesion.tipo,
        "creado": sesion.creado,
        "worktree": sesion.worktree,
        "rama": sesion.rama,
        "usuario_id": sesion.usuario_id,
        "session_id": sesion.session_id,
        "transcripcion": [dict(t) for t in sesion.transcripcion],
    }


def _desde_registro(reg: dict) -> SesionRalph:
    """Reconstruye una SesionRalph DORMIDO desde su registro persistido, sembrando `eventos` con
    la transcripcion (cada turno: delta + cierre) y un estado final `dormido`."""
    transcripcion = [dict(t) for t in (reg.get("transcripcion") or []) if isinstance(t, dict)]
    sesion = SesionRalph(
        id=reg["id"],
        nombre=reg.get("nombre", ""),
        modelo=reg.get("modelo", MODELO_DEF),
        creado=reg.get("creado", time.time()),
        tipo=reg.get("tipo", TIPO_DEF),
        worktree=reg.get("worktree", ""),
        rama=reg.get("rama", ""),
        usuario_id=reg.get("usuario_id", ""),
        session_id=reg.get("session_id", ""),
        transcripcion=transcripcion,
        estado=ESTADO_DORMIDO,
    )
    for turno in transcripcion:
        autor = turno.get("autor", "")
        texto = turno.get("texto", "")
        sesion.eventos.append({"tipo": "mensaje", "autor": autor, "delta": texto})
        sesion.eventos.append({"tipo": "mensaje", "autor": autor, "delta": "", "fin": True})
    sesion.eventos.append({"tipo": "estado", "estado": ESTADO_DORMIDO})
    return sesion


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


def _asegurar_repo_git(repo: str) -> None:
    """Garantiza que `repo` sea un clon git utilizable; si falta, lo clona con `gh`.

    Configura antes el credential-helper de gh (`gh auth setup-git`) para que `git push` funcione.
    Sube `RuntimeError` si no se puede clonar (p.ej. GitHub sin conectar) — el llamante lo traduce
    a un error legible en la burbuja."""
    if os.path.isdir(os.path.join(repo, ".git")):
        return
    subprocess.run(  # noqa: S603 -- argv lista, sin shell
        ["gh", "auth", "setup-git"], check=False, capture_output=True, text=True, timeout=60
    )
    padre = os.path.dirname(os.path.abspath(repo)) or "/"
    os.makedirs(padre, exist_ok=True)
    try:
        res = subprocess.run(  # noqa: S603 -- argv lista, sin shell
            ["gh", "repo", "clone", _REPO_SLUG, repo],
            capture_output=True, text=True, timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise RuntimeError(f"no se pudo clonar el repo: {e}") from e
    if res.returncode != 0 or not os.path.isdir(os.path.join(repo, ".git")):
        detalle = (res.stderr or res.stdout or "").strip()[:200]
        raise RuntimeError("no se pudo clonar el repo (¿GitHub conectado?): " + (detalle or "gh"))


def _crear_worktree(repo: str, nombre: str) -> tuple[str, str]:
    """Crea un worktree+rama del `repo` para un Ralph. Devuelve (ruta_worktree, rama).

    Garantiza el clon (`_asegurar_repo_git`), trae `main` fresco y basa el worktree en
    `origin/main`: el workspace del Ralph es una COPIA de main al día (rama propia
    `ralph/<nombre>`), sin que tenga que buscar ni clonar nada. Worktree en
    `$KENI_DATA_DIR/ralph-worktrees/<nombre>-<sufijo>`. Sube la excepcion si git/gh falla."""
    _asegurar_repo_git(repo)
    rama = f"ralph/{nombre}"
    sufijo = uuid.uuid4().hex[:8]
    base = _base_escribible("ralph-worktrees", repo)
    destino = os.path.join(base, f"{nombre}-{sufijo}")
    # Trae main al día; si no hay red/origin se sigue con lo local (best-effort).
    subprocess.run(  # noqa: S603 -- argv lista, sin shell
        ["git", "-C", repo, "fetch", "origin", "main"],
        check=False, capture_output=True, text=True, timeout=120,
    )
    res = subprocess.run(  # noqa: S603 -- argv lista, sin shell
        ["git", "-C", repo, "worktree", "add", "-B", rama, destino, "origin/main"],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        # Sin `origin/main` (repo recién clonado en local sin remoto resuelto): basa en HEAD.
        subprocess.run(  # noqa: S603 -- argv lista, sin shell
            ["git", "-C", repo, "worktree", "add", "-B", rama, destino],
            check=True, capture_output=True, text=True,
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
