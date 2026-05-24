"""`doctor`: autodiagnostico del entorno de keni-metricas y de la skill clip-a-copy.

Pensado para gente NO tecnica: ejecuta `python -m keni_metricas.doctor` y obtienes
un informe legible de ✅/⚠️/❌ que dice si tu maquina esta lista para usar el MCP
de metricas y para transcribir video/audio en local.

Comprueba (todo OFFLINE por defecto, sin red):
  - que el archivo de configuracion exista y sea parseable;
  - que la fuente configurada se pueda construir (`construir_fuente`);
  - que marcas/cuentas tienes configuradas;
  - que plataformas tienen credenciales y cuales no (SIN imprimir los secretos);
  - para clip-a-copy: `whisper-cli` y `ffmpeg` en el PATH, y un modelo de whisper
    en las rutas conocidas;
  - la version de Python.

La logica vive en funciones puras que devuelven `Resultado` estructurados; la CLI
solo los renderiza. Con `--validar` intenta ademas una comprobacion ligera de
conectividad por plataforma configurada (importacion perezosa de los adaptadores,
los errores se tragan en el informe; NUNCA hace red en el camino por defecto).

Sale con codigo != 0 si hay algun ❌, para que sea usable en scripts.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# Importaciones de solo lectura del paquete (no se modifican esos modulos).
from .config import (
    Config,
    ConfigInvalida,
    cargar_config,
    construir_fuente,
    ruta_config,
)

# Centinela: distingue "no inyectado" (lee del entorno) de un None explicito
# (los tests fuerzan el escaneo de rutas sin tocar la env var real).
_DEL_ENTORNO = object()

# --- Estado de cada comprobacion --------------------------------------------


class Estado(Enum):
    """Resultado de una comprobacion. El valor es el icono que se imprime."""

    OK = "✅"
    AVISO = "⚠️"
    ERROR = "❌"


@dataclass
class Resultado:
    """Resultado estructurado de UNA comprobacion (puro, sin imprimir nada)."""

    nombre: str
    estado: Estado
    detalle: str = ""
    # datos extra para inspeccion programatica / tests (no se renderizan crudos)
    extra: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.estado is Estado.OK

    @property
    def es_error(self) -> bool:
        return self.estado is Estado.ERROR


# --- Mapa plataforma -> bloque de credenciales y clave del token ------------
#
# El config agrupa credenciales por proveedor: facebook + instagram comparten el
# bloque `meta`. Cada bloque "tiene credenciales" si trae alguna de las claves de
# token esperadas. NO se imprime ningun valor: solo si la clave esta presente.
PLATAFORMAS_CRED: dict[str, tuple[str, tuple[str, ...]]] = {
    "facebook": ("meta", ("access_token",)),
    "instagram": ("meta", ("access_token",)),
    "youtube": ("youtube", ("access_token",)),
    "x": ("x", ("bearer_token", "access_token")),
    "tiktok": ("tiktok", ("access_token",)),
}

# Modelos de whisper en el orden en que los busca transcribir.sh
# (env KENI_WHISPER_MODEL > rutas habituales).
ENV_MODELO_WHISPER = "KENI_WHISPER_MODEL"


def _rutas_modelo_whisper() -> list[Path]:
    """Rutas conocidas donde puede vivir el modelo de whisper (sin la env var)."""
    home = Path.home()
    return [
        home / "models" / "ggml-large-v3-turbo.bin",
        home / ".cache" / "whisper" / "ggml-large-v3-turbo.bin",
    ]


# --- Comprobaciones puras ---------------------------------------------------


def comprobar_python(version: tuple[int, ...] | None = None) -> Resultado:
    """Version de Python. El paquete pide >=3.11."""
    v = version or sys.version_info[:3]
    texto = ".".join(str(p) for p in v)
    if v[:2] >= (3, 11):
        return Resultado("Python", Estado.OK, f"Python {texto}", extra={"version": v})
    return Resultado(
        "Python",
        Estado.ERROR,
        f"Python {texto} es demasiado viejo (se requiere >= 3.11)",
        extra={"version": v},
    )


def comprobar_config(ruta: Path | None = None) -> Resultado:
    """El archivo de configuracion existe y es TOML parseable.

    No existir NO es error: el MCP funciona con la fuente `muestra` por defecto.
    Existir pero estar roto SI es error.
    """
    import tomllib

    ruta = ruta or ruta_config()
    if not ruta.exists():
        return Resultado(
            "Configuracion",
            Estado.AVISO,
            f"No hay config en {ruta} (se usara la fuente de muestra por defecto)",
            extra={"ruta": str(ruta), "existe": False},
        )
    try:
        tomllib.loads(ruta.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as e:
        return Resultado(
            "Configuracion",
            Estado.ERROR,
            f"El config en {ruta} no se puede leer/parsear: {e}",
            extra={"ruta": str(ruta), "existe": True},
        )
    return Resultado(
        "Configuracion",
        Estado.OK,
        f"Config valido en {ruta}",
        extra={"ruta": str(ruta), "existe": True},
    )


def comprobar_fuente(cfg: Config) -> Resultado:
    """La fuente configurada se puede construir con `construir_fuente`."""
    try:
        fuente = construir_fuente(cfg)
    except Exception as e:  # noqa: BLE001 - cualquier fallo de construccion es un ❌
        return Resultado(
            "Fuente",
            Estado.ERROR,
            f"No se pudo construir la fuente {cfg.fuente!r}: {e}",
            extra={"fuente": cfg.fuente},
        )
    nombre = getattr(fuente, "nombre", cfg.fuente)
    return Resultado(
        "Fuente",
        Estado.OK,
        f"Fuente {nombre!r} construida correctamente",
        extra={"fuente": nombre},
    )


def comprobar_marcas(cfg: Config) -> Resultado:
    """Que marcas/cuentas tienes configuradas (y su alcance)."""
    cuentas = [(c.id, c.nombre) for c in cfg.cuentas]
    alcance = list(cfg.marcas)
    if not cuentas:
        detalle = "No hay cuentas en el config (la fuente de muestra trae sus propias marcas demo)"
        estado = Estado.AVISO
    else:
        nombres = ", ".join(f"{cid} ({nom})" for cid, nom in cuentas)
        detalle = f"{len(cuentas)} cuenta(s): {nombres}"
        estado = Estado.OK
    if alcance:
        detalle += f" | alcance limitado a: {', '.join(alcance)}"
    return Resultado(
        "Cuentas",
        estado,
        detalle,
        extra={"cuentas": cuentas, "alcance": alcance},
    )


def comprobar_credenciales(cfg: Config) -> list[Resultado]:
    """Una linea por plataforma: tiene credenciales vs no (sin imprimir secretos).

    Solo informa de presencia/ausencia de las claves de token esperadas; NUNCA
    incluye su valor. Si la fuente es `muestra`, no se necesitan credenciales: es
    un aviso suave, no un error.
    """
    es_muestra = cfg.fuente == "muestra"
    resultados: list[Resultado] = []
    for plataforma, (bloque, claves) in PLATAFORMAS_CRED.items():
        creds = cfg.credenciales.get(bloque, {}) or {}
        tiene = any(bool(creds.get(k)) for k in claves)
        nombre = f"Credenciales {plataforma}"
        if tiene:
            resultados.append(
                Resultado(
                    nombre,
                    Estado.OK,
                    f"{plataforma}: credenciales presentes (bloque [credenciales.{bloque}])",
                    extra={"plataforma": plataforma, "bloque": bloque, "tiene": True},
                )
            )
        elif es_muestra:
            resultados.append(
                Resultado(
                    nombre,
                    Estado.AVISO,
                    f"{plataforma}: sin credenciales (no hacen falta con fuente de muestra)",
                    extra={"plataforma": plataforma, "bloque": bloque, "tiene": False},
                )
            )
        else:
            resultados.append(
                Resultado(
                    nombre,
                    Estado.AVISO,
                    f"{plataforma}: sin credenciales (esta plataforma se omitira en fuente real)",
                    extra={"plataforma": plataforma, "bloque": bloque, "tiene": False},
                )
            )
    return resultados


def comprobar_binario(
    nombre_binario: str,
    *,
    pista: str,
    which=None,
) -> Resultado:
    """Un binario esta en el PATH (via `shutil.which`, inyectable para tests)."""
    which = which or shutil.which  # resolver en tiempo de llamada (monkeypatch-friendly)
    ruta = which(nombre_binario)
    if ruta:
        return Resultado(
            f"binario {nombre_binario}",
            Estado.OK,
            f"{nombre_binario} encontrado en {ruta}",
            extra={"binario": nombre_binario, "ruta": ruta},
        )
    return Resultado(
        f"binario {nombre_binario}",
        Estado.ERROR,
        f"{nombre_binario} no esta en el PATH. {pista}",
        extra={"binario": nombre_binario, "ruta": None},
    )


def comprobar_modelo_whisper(
    *,
    env_modelo: str | None = None,
    rutas=None,
) -> Resultado:
    """Hay un modelo de whisper en las rutas conocidas o en KENI_WHISPER_MODEL.

    `env_modelo` y `rutas` se inyectan en los tests para no tocar el entorno real.
    """
    if env_modelo:
        p = Path(env_modelo).expanduser()
        if p.is_file():
            return Resultado(
                "modelo whisper",
                Estado.OK,
                f"modelo encontrado via {ENV_MODELO_WHISPER}={p}",
                extra={"ruta": str(p), "origen": "env"},
            )
        return Resultado(
            "modelo whisper",
            Estado.ERROR,
            f"{ENV_MODELO_WHISPER}={p} apunta a un archivo que no existe",
            extra={"ruta": str(p), "origen": "env"},
        )
    candidatas = list(rutas if rutas is not None else _rutas_modelo_whisper())
    for cand in candidatas:
        cand = Path(cand)
        if cand.is_file():
            return Resultado(
                "modelo whisper",
                Estado.OK,
                f"modelo encontrado en {cand}",
                extra={"ruta": str(cand), "origen": "ruta"},
            )
    listadas = ", ".join(str(c) for c in candidatas) or "(ninguna)"
    return Resultado(
        "modelo whisper",
        Estado.ERROR,
        f"no se encontro modelo de whisper. Define {ENV_MODELO_WHISPER} o coloca el .bin en una de: {listadas}",
        extra={"ruta": None, "candidatas": [str(c) for c in candidatas]},
    )


def validar_conectividad(cfg: Config) -> list[Resultado]:
    """Comprobacion LIGERA de conectividad por plataforma con credenciales.

    Importa los adaptadores de forma perezosa y comprueba si se construyen y se
    consideran `disponible()`. Cualquier error se traga y se convierte en un
    aviso dentro del informe. Esto NO se ejecuta en el camino por defecto y los
    tests nunca lo requieren (no hay red garantizada).
    """
    resultados: list[Resultado] = []
    try:
        fuente = construir_fuente(cfg)
    except Exception as e:  # noqa: BLE001
        return [Resultado("Conectividad", Estado.AVISO, f"no se pudo construir la fuente: {e}")]

    # Solo tiene sentido validar la fuente real; la de muestra es offline.
    if getattr(fuente, "nombre", cfg.fuente) == "muestra":
        return [
            Resultado(
                "Conectividad",
                Estado.AVISO,
                "fuente de muestra (offline): no hay nada que validar contra la red",
            )
        ]

    try:
        adaptadores = _adaptadores_desde_config(cfg)
    except Exception as e:  # noqa: BLE001
        return [Resultado("Conectividad", Estado.AVISO, f"no se pudieron cargar los adaptadores: {e}")]

    if not adaptadores:
        return [
            Resultado(
                "Conectividad",
                Estado.AVISO,
                "ningun adaptador con credenciales suficientes: nada que validar",
            )
        ]

    for plataforma, ad in adaptadores.items():
        try:
            disponible = bool(ad.disponible())
        except Exception as e:  # noqa: BLE001
            resultados.append(
                Resultado(
                    f"Conectividad {plataforma}",
                    Estado.AVISO,
                    f"{plataforma}: el adaptador fallo al comprobarse ({e})",
                    extra={"plataforma": plataforma},
                )
            )
            continue
        if disponible:
            resultados.append(
                Resultado(
                    f"Conectividad {plataforma}",
                    Estado.OK,
                    f"{plataforma}: adaptador disponible (credenciales con forma valida)",
                    extra={"plataforma": plataforma},
                )
            )
        else:
            resultados.append(
                Resultado(
                    f"Conectividad {plataforma}",
                    Estado.AVISO,
                    f"{plataforma}: adaptador no disponible (credenciales insuficientes)",
                    extra={"plataforma": plataforma},
                )
            )
    return resultados


def _adaptadores_desde_config(cfg: Config) -> dict:
    """Construye los adaptadores reales con credenciales suficientes (lazy import)."""
    from .fuentes.meta import AdaptadorMeta
    from .fuentes.tiktok import AdaptadorTikTok
    from .fuentes.x import AdaptadorX
    from .fuentes.youtube import AdaptadorYouTube
    from .schema import Plataforma

    creds = cfg.credenciales
    posibles = {
        Plataforma.facebook.value: AdaptadorMeta(creds.get("meta", {}), Plataforma.facebook),
        Plataforma.instagram.value: AdaptadorMeta(creds.get("meta", {}), Plataforma.instagram),
        Plataforma.youtube.value: AdaptadorYouTube(creds.get("youtube", {})),
        Plataforma.x.value: AdaptadorX(creds.get("x", {})),
        Plataforma.tiktok.value: AdaptadorTikTok(creds.get("tiktok", {})),
    }
    return {p: a for p, a in posibles.items() if a.disponible()}


# --- Orquestacion (sigue siendo pura: devuelve resultados, no imprime) ------


def ejecutar_chequeos(
    cfg: Config | None = None,
    *,
    validar: bool = False,
    which=None,
    env_modelo: str | None | object = _DEL_ENTORNO,
    rutas_modelo=None,
) -> list[Resultado]:
    """Ejecuta todas las comprobaciones y devuelve la lista de `Resultado`.

    Funcion pura respecto a la salida: no imprime ni sale del proceso. Las
    dependencias del entorno (`which`, env del modelo, rutas) son inyectables
    para poder testear offline sin tocar la maquina real. Por defecto el modelo
    de whisper se lee de `KENI_WHISPER_MODEL` (como hace transcribir.sh); pasar
    `env_modelo=None` explicitamente fuerza el escaneo de rutas (lo usan los tests).
    """
    # Cargar la config de forma defensiva: un config corrupto/invalido NO debe
    # tumbar el doctor (es justo lo que el doctor existe para diagnosticar). Si
    # `cargar_config` lanza `ConfigInvalida`, se reporta como ❌ y se omiten los
    # chequeos que dependen de la config.
    config_error: ConfigInvalida | None = None
    if cfg is None:
        try:
            cfg = cargar_config()
        except ConfigInvalida as e:
            config_error = e
            cfg = None
    which = which or shutil.which  # resolver en tiempo de llamada (monkeypatch-friendly)
    if env_modelo is _DEL_ENTORNO:
        env_modelo = os.environ.get("KENI_WHISPER_MODEL") or None

    resultados: list[Resultado] = [comprobar_python()]
    if cfg is None:
        resultados.append(
            Resultado(
                "Configuracion",
                Estado.ERROR,
                str(config_error)
                if config_error
                else "No se pudo cargar la configuracion",
                extra={"ruta": str(ruta_config())},
            )
        )
    else:
        resultados.append(comprobar_config())
        resultados.append(comprobar_fuente(cfg))
        resultados.append(comprobar_marcas(cfg))
        resultados.extend(comprobar_credenciales(cfg))

    # clip-a-copy (transcripcion local)
    resultados.append(
        comprobar_binario(
            "whisper-cli",
            pista="Instala whisper.cpp: brew install whisper-cpp",
            which=which,
        )
    )
    resultados.append(
        comprobar_binario(
            "ffmpeg",
            pista="Instala ffmpeg: brew install ffmpeg",
            which=which,
        )
    )
    resultados.append(
        comprobar_modelo_whisper(env_modelo=env_modelo, rutas=rutas_modelo)
    )

    if validar and cfg is not None:
        resultados.extend(validar_conectividad(cfg))

    return resultados


# --- Renderizado (la CLI solo formatea lo que devuelven las funciones puras) ---


def resumen_humano(resultados: list[Resultado]) -> str:
    """Una frase de cabecera, en lenguaje no tecnico, segun el estado global.

    Sin ❌: tranquiliza a quien no es tecnico (los avisos de credenciales/config
    son normales con datos de muestra). Con ❌: deja claro que algo hay que
    arreglar. No mira los codigos de salida; solo formula el mensaje.
    """
    if any(r.es_error for r in resultados):
        n = sum(1 for r in resultados if r.es_error)
        return (
            f"❌ Hay {n} problema(s) que impiden usar el sistema. "
            "Revisa las lineas con ❌ de abajo."
        )
    return (
        "✅ Todo listo para la demo (con datos de muestra). "
        "Los avisos de credenciales/config son normales sin conectar cuentas reales."
    )


def renderizar(resultados: list[Resultado]) -> str:
    """Genera el informe legible a partir de los resultados estructurados."""
    lineas: list[str] = [
        "Autodiagnostico de keni-metricas",
        "=" * 40,
        "",
        resumen_humano(resultados),
        "",
    ]
    for r in resultados:
        lineas.append(f"{r.estado.value} {r.nombre}: {r.detalle}")
    lineas.append("")
    errores = sum(1 for r in resultados if r.es_error)
    avisos = sum(1 for r in resultados if r.estado is Estado.AVISO)
    oks = sum(1 for r in resultados if r.ok)
    lineas.append(f"Resumen: {oks} ✅  {avisos} ⚠️  {errores} ❌")
    if errores:
        lineas.append("Hay errores que debes resolver antes de usar el sistema.")
    else:
        lineas.append("Entorno listo (los avisos ⚠️ son opcionales segun tu uso).")
    return "\n".join(lineas)


def codigo_salida(resultados: list[Resultado]) -> int:
    """0 si no hay ningun ❌, 1 si hay al menos uno (para scripts)."""
    return 1 if any(r.es_error for r in resultados) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m keni_metricas.doctor",
        description="Autodiagnostico del entorno de keni-metricas y de clip-a-copy.",
    )
    parser.add_argument(
        "--validar",
        action="store_true",
        help="Ademas, intenta una comprobacion ligera de conectividad por plataforma "
        "configurada (importa los adaptadores; los errores van al informe).",
    )
    args = parser.parse_args(argv)

    # No cargamos la config aqui: `ejecutar_chequeos` lo hace de forma defensiva
    # (un config corrupto se reporta como ❌, no tumba el doctor).
    resultados = ejecutar_chequeos(validar=args.validar)
    print(renderizar(resultados))
    return codigo_salida(resultados)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
