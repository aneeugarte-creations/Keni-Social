"""Config — accesores del dominio generacion. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._config_comun import (
    _FALSOS,
    CLAUDE_TIMEOUT_DEF,
    ENV_CLAUDE_DISALLOWED_TOOLS,
    ENV_CLAUDE_MAX_TURNS,
    ENV_CLAUDE_MAX_USD,
    ENV_CLAUDE_SKIP_PERMISSIONS,
    ENV_CLAUDE_TIMEOUT,
    _crudo,
    os,
)

# --------------------------------------------------------------------------- #
# Accesores: generacion `claude -p`                                            #
# --------------------------------------------------------------------------- #


def claude_timeout() -> int:
    """Wall-timeout (s) de un job de claude (`KENI_CLAUDE_TIMEOUT`, def 600; >0)."""
    crudo = _crudo(ENV_CLAUDE_TIMEOUT)
    if crudo:
        try:
            valor = int(crudo)
        except ValueError:
            return CLAUDE_TIMEOUT_DEF
        if valor > 0:
            return valor
    return CLAUDE_TIMEOUT_DEF


def claude_max_usd() -> float | None:
    """Tope de coste en USD (`KENI_CLAUDE_MAX_USD`); None si ausente/invalido/<=0 (sin tope)."""
    crudo = _crudo(ENV_CLAUDE_MAX_USD)
    if not crudo:
        return None
    try:
        valor = float(crudo)
    except ValueError:
        return None
    return valor if valor > 0 else None


def claude_max_turns() -> int | None:
    """Tope de turnos (`KENI_CLAUDE_MAX_TURNS`); None si ausente/invalido/<=0 (sin tope)."""
    crudo = _crudo(ENV_CLAUDE_MAX_TURNS)
    if not crudo:
        return None
    try:
        valor = int(crudo)
    except ValueError:
        return None
    return valor if valor > 0 else None


def claude_skip_permisos() -> bool:
    """¿Pasar `--dangerously-skip-permissions`? (def ON; `KENI_CLAUDE_SKIP_PERMISSIONS` falsy lo apaga)."""
    crudo = os.environ.get(ENV_CLAUDE_SKIP_PERMISSIONS, "1").strip().lower()
    return crudo not in _FALSOS


# Herramientas VETADAS por defecto en la generacion (`--disallowed-tools`). Defensa en
# profundidad frente a prompt-injection (el contenido de usuario/RSS viaja en el prompt):
# corremos con skip-permissions para cargar skills/leer ficheros del cwd, PERO vetamos:
#   - `Bash` —el vector de MAYOR impacto: ejecucion de comandos arbitrarios, lectura/
#     exfiltracion de secretos de `/data` y del entorno—.
#   - `Write` y `Edit` —escritura/edicion de ficheros en disco—. NINGUN flujo de generacion
#     (copy-desde-nota, QA, hashtags, evergreen, sugerencias, NI el prompt de
#     investigacion `brief-tendencias`) escribe ficheros: su salida es
#     SIEMPRE texto que parsea el post-procesado. Vetarlas cierra un vector de persistencia/
#     manipulacion del cwd sin afectar a ningun flujo legitimo (defensa en profundidad).
# NINGUN flujo de generacion necesita Bash/Write/Edit. Web (`WebFetch`/`WebSearch`) NO se
# veta por defecto a proposito: el prompt curado `brief-tendencias`
# lo usa para confirmar frescura, y comparten este mismo constructor de argv. El riesgo
# residual de Web en el flujo copy-desde-nota lo cubre el delimitador con NONCE
# `<contenido_usuario_…>` (ver `dominio.generar.envolver_contenido_usuario`). Vetar Web SOLO
# en los flujos de copy/RSS/autogen/QA (que no la necesitan) exige `endurecer` por-callsite en
# cada lanzador (`api/hashtags`, `api/verificar_fuente`, `dominio/evergreen`,
# `autogen_redactar`, `pipeline_contenido`, `dominio/texto_lanzar`...): queda PENDIENTE de
# revision humana, porque esos lanzadores son de otros modulos (no de este endurecimiento).
# Configurable con `KENI_CLAUDE_DISALLOWED_TOOLS` (lista coma/espacio): un operador puede
# endurecer mas (p.ej. "Bash Write Edit WebFetch WebSearch") si lo desea.
CLAUDE_DISALLOWED_TOOLS_DEF = "Bash Write Edit"


def claude_disallowed_tools() -> list[str]:
    """Herramientas vetadas en la generacion (`--disallowed-tools`); lista, posiblemente vacia.

    Por defecto veta `Bash Write Edit` (`CLAUDE_DISALLOWED_TOOLS_DEF`); Web queda disponible
    para los prompts de investigacion. `KENI_CLAUDE_DISALLOWED_TOOLS` lo sobreescribe
    (separadores coma o espacio); vacio explicito ("" / solo separadores) => sin veto (lista
    vacia, para depurar). Tolerante: duplicados y espacios sobrantes se limpian conservando el
    orden.
    """
    crudo = os.environ.get(ENV_CLAUDE_DISALLOWED_TOOLS)
    if crudo is None:
        crudo = CLAUDE_DISALLOWED_TOOLS_DEF
    piezas = [p.strip() for p in crudo.replace(",", " ").split()]
    vistos: list[str] = []
    for p in piezas:
        if p and p not in vistos:
            vistos.append(p)
    return vistos
