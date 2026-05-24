"""Asistente de onboarding: arma/actualiza el `config.toml` local guiando a la
persona paso a paso.

El producto apunta a usuarios no tecnicos que hoy NO pueden auto-configurarse.
Este modulo expone un flujo interactivo (`python -m keni_metricas.asistente`) que:

- Elige la fuente (`muestra` offline / `real` con credenciales).
- Declara marcas + handle por plataforma.
- Declara que `marcas` gestiona esta persona (acotamiento multiusuario).
- Captura tokens por plataforma (o deja placeholders) con guia y enlaces a docs.

Disenado para ser testeable OFFLINE: TODA la logica (construccion, merge,
serializacion TOML, enmascarado) vive en funciones puras sin red ni input(). El
`main()` interactivo es una capa fina por encima. La validacion de conectividad
(`--validar`) es opt-in y esta aislada del nucleo: nunca la ejercitan los tests.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# Plataformas soportadas, en el orden en que se preguntan. Se replica aqui (en vez
# de importar el StrEnum de schema.py) para no acoplar el asistente al esquema y
# para no tener que tocar otros modulos. Coincide con `schema.Plataforma`.
PLATAFORMAS: tuple[str, ...] = ("facebook", "instagram", "youtube", "x", "tiktok")

# TikTok identifica la cuenta por el token del usuario, no por un handle/id.
PLATAFORMAS_SIN_HANDLE: frozenset[str] = frozenset({"tiktok"})

# Cada plataforma usa UN bloque de credenciales. Meta cubre facebook+instagram.
PLATAFORMA_A_BLOQUE: dict[str, str] = {
    "facebook": "meta",
    "instagram": "meta",
    "youtube": "youtube",
    "x": "x",
    "tiktok": "tiktok",
}

# Campo de token "principal" por bloque de credenciales (lo que pide el adaptador).
CAMPO_TOKEN: dict[str, str] = {
    "meta": "access_token",
    "youtube": "access_token",
    "x": "bearer_token",
    "tiktok": "access_token",
}

# Placeholder que se escribe cuando la persona aun no tiene el token.
PLACEHOLDER_TOKEN = "PENDIENTE_PON_TU_TOKEN_AQUI"

# Guia por bloque de credenciales: que token hace falta y donde mirar.
GUIA_CREDENCIALES: dict[str, dict[str, str]] = {
    "meta": {
        "titulo": "Meta (Facebook + Instagram)",
        "que": (
            "Un access_token de la Graph API con permisos pages_read_engagement, "
            "read_insights e instagram_manage_insights (requiere App Review de Meta). "
            "Recomendado: token de System User de Business Manager (no caduca); en ese "
            'caso se marca con tipo_token = "system_user".'
        ),
        "docs": (
            'docs/credenciales.md (seccion "Meta: token de System User"), '
            "docs/meta-app-review.md, docs/despliegue-hosted.md"
        ),
    },
    "youtube": {
        "titulo": "YouTube",
        "que": (
            "Un access_token OAuth con scope yt-analytics.readonly. El token de Google "
            "caduca en ~1h; opcionalmente anade client_id/client_secret/refresh_token "
            "para renovarlo solo."
        ),
        "docs": "docs/credenciales.md, docs/youtube-cuota-x-coste.md",
    },
    "x": {
        "titulo": "X (Twitter)",
        "que": "Un bearer_token de la X API v2 (requiere tier de pago). El bearer de app no caduca.",
        "docs": "docs/credenciales.md",
    },
    "tiktok": {
        "titulo": "TikTok",
        "que": (
            "Un access_token de la Display API (requiere auditoria de TikTok). "
            "Opcional: client_key/client_secret/refresh_token para renovarlo solo."
        ),
        "docs": "docs/credenciales.md, docs/tiktok-audit.md",
    },
}


# ---------------------------------------------------------------------------
# Ruta del config (replicada de config.py para no importar/acoplar; misma logica)
# ---------------------------------------------------------------------------
def ruta_config() -> Path:
    """Donde vive el config local. Igual que `config.ruta_config()`.

    Replicado aqui a proposito: el asistente no debe modificar config.py y solo
    necesita esta logica de rutas. Respeta `KENI_METRICAS_CONFIG` y `XDG_CONFIG_HOME`.
    """
    if (p := os.environ.get("KENI_METRICAS_CONFIG")):
        return Path(p).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "keni-metricas" / "config.toml"


# ---------------------------------------------------------------------------
# Modelo de datos del asistente (lo que la persona declara)
# ---------------------------------------------------------------------------
@dataclass
class MarcaEntrada:
    """Una marca/cuenta y su handle/id por plataforma."""

    id: str
    nombre: str
    plataformas: dict[str, str] = field(default_factory=dict)


@dataclass
class PlanConfig:
    """Lo que el asistente quiere dejar escrito en config.toml."""

    fuente: str = "muestra"
    marcas_cuenta: list[MarcaEntrada] = field(default_factory=list)
    # marcas (ids) que esta persona gestiona (acotamiento). Vacio = todas.
    alcance: list[str] = field(default_factory=list)
    # bloque de credenciales -> {clave: valor}
    credenciales: dict[str, dict[str, str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers puros: validacion / normalizacion
# ---------------------------------------------------------------------------
def normalizar_id_marca(texto: str) -> str:
    """Convierte un nombre libre en un id estable (minusculas, guion_bajo)."""
    limpio = []
    for ch in texto.strip().lower():
        if ch.isalnum():
            limpio.append(ch)
        elif ch in " -_":
            limpio.append("_")
        # cualquier otro caracter se descarta
    # colapsa guiones bajos repetidos y recorta extremos
    out = "_".join(p for p in "".join(limpio).split("_") if p)
    return out


def plataforma_valida(plataforma: str) -> bool:
    return plataforma in PLATAFORMAS


def normalizar_alcance(valor: str | list | None, ids_validos: list[str] | None = None) -> list[str]:
    """Normaliza la lista de marcas en alcance (de coma-separado o lista).

    Preserva orden, descarta duplicados/vacios. Si se pasan `ids_validos`, filtra
    a esos ids (silenciosamente ignora los que no existan).
    """
    if not valor:
        return []
    crudas = valor.split(",") if isinstance(valor, str) else valor
    permitidos = set(ids_validos) if ids_validos is not None else None
    vistas: list[str] = []
    for m in crudas:
        m = str(m).strip()
        if not m or m in vistas:
            continue
        if permitidos is not None and m not in permitidos:
            continue
        vistas.append(m)
    return vistas


def enmascarar_token(token: str | None, visibles: int = 4) -> str:
    """Enmascara un token para mostrarlo en consola SIN revelarlo entero.

    Deja visibles los ultimos `visibles` caracteres. Tokens cortos o placeholders
    se ocultan por completo. Nunca devuelve el token completo de un secreto real.
    """
    if not token:
        return "(vacio)"
    if token == PLACEHOLDER_TOKEN:
        return PLACEHOLDER_TOKEN
    n = len(token)
    if n <= visibles:
        return "*" * n
    return "*" * (n - visibles) + token[-visibles:]


def guia_plataforma(plataforma: str) -> dict[str, str]:
    """Devuelve la guia (titulo/que/docs) del bloque de credenciales de la plataforma."""
    bloque = PLATAFORMA_A_BLOQUE.get(plataforma, plataforma)
    return GUIA_CREDENCIALES[bloque]


def texto_guia_plataforma(plataforma: str) -> str:
    """Texto multilinea con la guia de credenciales de una plataforma."""
    g = guia_plataforma(plataforma)
    return (
        f"== {g['titulo']} ==\n"
        f"Token necesario: {g['que']}\n"
        f"Mas info: {g['docs']}"
    )


# ---------------------------------------------------------------------------
# Construccion del dict TOML a partir del plan (PURO)
# ---------------------------------------------------------------------------
def plan_a_dict(plan: PlanConfig) -> dict:
    """Convierte un PlanConfig en el dict que se serializara a TOML.

    Forma resultante (compatible con config.cargar_config):
        fuente = "muestra" | "real"
        marcas = [...]                      # solo si hay alcance
        [[cuenta]] id/nombre/[cuenta.plataformas]
        [credenciales.<bloque>] ...
    """
    datos: dict = {"fuente": plan.fuente}

    if plan.alcance:
        datos["marcas"] = list(plan.alcance)

    cuentas: list[dict] = []
    for m in plan.marcas_cuenta:
        cuenta: dict = {"id": m.id, "nombre": m.nombre}
        # solo plataformas con handle no vacio (ni las sin-handle como tiktok)
        plataformas = {
            p: v for p, v in m.plataformas.items() if v and p not in PLATAFORMAS_SIN_HANDLE
        }
        if plataformas:
            cuenta["plataformas"] = plataformas
        cuentas.append(cuenta)
    if cuentas:
        datos["cuenta"] = cuentas

    # credenciales: descarta bloques vacios
    creds = {
        bloque: dict(valores)
        for bloque, valores in plan.credenciales.items()
        if valores
    }
    if creds:
        datos["credenciales"] = creds

    return datos


# ---------------------------------------------------------------------------
# Merge con config existente (PURO): no pisa secciones ajenas
# ---------------------------------------------------------------------------
def _merge_dicts(base: dict, nuevo: dict) -> dict:
    """Merge profundo no destructivo: `nuevo` gana en hojas; dicts se fusionan.

    Las listas (p.ej. `cuenta`, `marcas`) se reemplazan enteras por la version
    nueva cuando esta presente: el asistente es la fuente de verdad para lo que
    declara, pero NO toca claves de nivel superior que el asistente no produjo.
    """
    out = dict(base)
    for clave, valor in nuevo.items():
        if isinstance(valor, dict) and isinstance(out.get(clave), dict):
            out[clave] = _merge_dicts(out[clave], valor)
        else:
            out[clave] = valor
    return out


def fusionar_config(existente: dict, nuevo: dict) -> dict:
    """Fusiona el config nuevo sobre el existente sin clobberar secciones no tocadas.

    - Secciones de nivel superior ajenas (que el asistente no genera) se preservan.
    - `credenciales` se fusiona por bloque: un bloque que el asistente no toco se
      mantiene; uno que si toco se fusiona clave a clave (no se pierden app_id/secret
      si el nuevo solo trae access_token, salvo que el nuevo los redefina).
    - `cuenta` y `marcas` se reemplazan por completo si el nuevo los trae.
    """
    return _merge_dicts(existente, nuevo)


def leer_config_existente(ruta: Path) -> dict:
    """Lee el TOML existente (o {} si no existe). Solo lectura, sin efectos."""
    if ruta.exists():
        return tomllib.loads(ruta.read_text(encoding="utf-8"))
    return {}


# ---------------------------------------------------------------------------
# Serializacion TOML (PURO). Stdlib solo LEE TOML (tomllib), no escribe; y no
# podemos anadir dependencias a pyproject.toml. Serializamos a mano EXACTAMENTE
# las estructuras que produce el asistente.
# ---------------------------------------------------------------------------
def _toml_str(valor: str) -> str:
    """Escapa una cadena para TOML basic string (comillas dobles)."""
    escapado = (
        valor.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )
    return f'"{escapado}"'


def _toml_valor(valor) -> str:
    """Serializa un valor escalar/lista a TOML (str, bool, int, list[str])."""
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, list):
        return "[" + ", ".join(_toml_valor(v) for v in valor) + "]"
    return _toml_str(str(valor))


def _es_tabla_simple(valor) -> bool:
    """True si el dict no contiene sub-dicts ni listas-de-dicts (tabla de hojas)."""
    if not isinstance(valor, dict):
        return False
    for v in valor.values():
        if isinstance(v, dict):
            return False
        if isinstance(v, list) and any(isinstance(x, dict) for x in v):
            return False
    return True


def serializar_toml(datos: dict) -> str:
    """Serializa el dict del asistente a texto TOML.

    Soporta exactamente las formas que el asistente genera:
      - escalares de nivel superior (`fuente`)
      - listas de cadenas de nivel superior (`marcas`)
      - listas de tablas (`[[cuenta]]`, con sub-tabla `[cuenta.plataformas]`)
      - tablas anidadas (`[credenciales.meta]`, etc.)
    """
    lineas: list[str] = []

    # 1) escalares y listas de hojas, primero (TOML exige las hojas antes de las tablas)
    for clave, valor in datos.items():
        if isinstance(valor, dict):
            continue
        if isinstance(valor, list) and any(isinstance(x, dict) for x in valor):
            continue
        lineas.append(f"{clave} = {_toml_valor(valor)}")

    # 2) listas de tablas: [[clave]]
    for clave, valor in datos.items():
        if isinstance(valor, list) and any(isinstance(x, dict) for x in valor):
            for elem in valor:
                lineas.append("")
                lineas.append(f"[[{clave}]]")
                _emitir_tabla(lineas, clave, elem)

    # 3) tablas anidadas: [clave] y [clave.sub]
    for clave, valor in datos.items():
        if isinstance(valor, dict):
            _emitir_seccion(lineas, clave, valor)

    texto = "\n".join(lineas).strip()
    return texto + "\n" if texto else ""


def _emitir_tabla(lineas: list[str], prefijo: str, tabla: dict) -> None:
    """Emite las hojas de una tabla (ya abierta su cabecera) y luego sus sub-tablas."""
    # hojas primero
    for clave, valor in tabla.items():
        if isinstance(valor, dict):
            continue
        lineas.append(f"{clave} = {_toml_valor(valor)}")
    # sub-tablas como [prefijo.sub]
    for clave, valor in tabla.items():
        if isinstance(valor, dict):
            lineas.append("")
            lineas.append(f"[{prefijo}.{clave}]")
            _emitir_tabla(lineas, f"{prefijo}.{clave}", valor)


def _emitir_seccion(lineas: list[str], clave: str, tabla: dict) -> None:
    """Emite una seccion de tabla [clave] (con posibles sub-tablas [clave.sub])."""
    if _es_tabla_simple(tabla):
        lineas.append("")
        lineas.append(f"[{clave}]")
        for k, v in tabla.items():
            lineas.append(f"{k} = {_toml_valor(v)}")
        return
    # tabla con sub-tablas: emite primero las hojas propias, luego cada sub-tabla
    hojas = {k: v for k, v in tabla.items() if not isinstance(v, dict)}
    if hojas:
        lineas.append("")
        lineas.append(f"[{clave}]")
        for k, v in hojas.items():
            lineas.append(f"{k} = {_toml_valor(v)}")
    for k, v in tabla.items():
        if isinstance(v, dict):
            _emitir_seccion(lineas, f"{clave}.{k}", v)


# ---------------------------------------------------------------------------
# Escritura atomica + cabecera. PURO en el sentido de no pedir input; toca disco.
# ---------------------------------------------------------------------------
CABECERA = (
    "# Config LOCAL POR PERSONA, generado por el asistente de onboarding de keni-metricas.\n"
    "# Las credenciales NUNCA salen de tu maquina. NO subas este archivo a git.\n"
    "# Reejecuta `python -m keni_metricas.asistente` para actualizarlo.\n"
)


def escribir_config_atomico(ruta: Path, datos: dict, cabecera: str = CABECERA) -> None:
    """Escribe el dict como TOML de forma atomica (tmp + os.replace) con permisos 0600.

    Crea el directorio padre si falta. No hay condicion de carrera donde quede un
    archivo a medias: se escribe a un temporal en el mismo dir y luego se renombra.
    """
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    contenido = cabecera + "\n" + serializar_toml(datos)

    fd, tmp_nombre = tempfile.mkstemp(dir=str(ruta.parent), prefix=".config-", suffix=".toml.tmp")
    tmp = Path(tmp_nombre)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(contenido)
        os.chmod(tmp, 0o600)
        os.replace(tmp, ruta)
    except BaseException:
        # limpia el temporal si algo falla antes del replace
        tmp.unlink(missing_ok=True)
        raise


def construir_y_fusionar(plan: PlanConfig, ruta: Path) -> dict:
    """Construye el dict del plan y lo fusiona con el config existente en `ruta`.

    Funcion PURA de orquestacion de datos (solo lee `ruta`, no escribe): util para
    tests que verifican el merge sin tocar disco de salida.
    """
    nuevo = plan_a_dict(plan)
    existente = leer_config_existente(ruta)
    return fusionar_config(existente, nuevo)


# ---------------------------------------------------------------------------
# Validacion de conectividad OPT-IN. AISLADA: import perezoso, jamas la llaman
# los tests, nunca es requerida por el flujo de escritura.
# ---------------------------------------------------------------------------
def validar_conectividad(datos: dict) -> list[tuple[str, bool, str]]:
    """Hace una llamada de prueba por plataforma con credenciales presentes.

    OPT-IN (flag --validar). Aislada de la logica de negocio: usa los adaptadores
    reales del paquete (import perezoso) y SOLO toca la red aqui. Devuelve una
    lista de (plataforma, ok, detalle). Nunca lanza por un fallo de red: lo reporta.
    """
    from .schema import Plataforma, resolver_rango

    resultados: list[tuple[str, bool, str]] = []
    creds = datos.get("credenciales", {})
    cuentas = datos.get("cuenta", [])
    desde, hasta, _ = resolver_rango("semana")

    # Construye adaptadores solo para bloques con token presente (no placeholder).
    from .fuentes.meta import AdaptadorMeta
    from .fuentes.tiktok import AdaptadorTikTok
    from .fuentes.x import AdaptadorX
    from .fuentes.youtube import AdaptadorYouTube

    adaptadores = {
        "facebook": lambda: AdaptadorMeta(creds.get("meta", {}), Plataforma.facebook),
        "instagram": lambda: AdaptadorMeta(creds.get("meta", {}), Plataforma.instagram),
        "youtube": lambda: AdaptadorYouTube(creds.get("youtube", {})),
        "x": lambda: AdaptadorX(creds.get("x", {})),
        "tiktok": lambda: AdaptadorTikTok(creds.get("tiktok", {})),
    }

    for cuenta in cuentas:
        plataformas = cuenta.get("plataformas", {})
        # tiktok no tiene handle pero se valida si hay token
        a_probar = dict(plataformas)
        if creds.get("tiktok", {}).get("access_token"):
            a_probar.setdefault("tiktok", "")
        for plat, handle in a_probar.items():
            fabrica = adaptadores.get(plat)
            if fabrica is None:
                continue
            ad = fabrica()
            if not ad.disponible():
                resultados.append((f"{cuenta.get('id')}/{plat}", False, "sin token"))
                continue
            try:
                m = ad.metricas(handle, desde, hasta)
                ok = m is not None
                resultados.append(
                    (f"{cuenta.get('id')}/{plat}", ok, "ok" if ok else "la API no respondio datos")
                )
            except Exception as e:  # noqa: BLE001 - reporta cualquier fallo de red
                resultados.append((f"{cuenta.get('id')}/{plat}", False, f"error: {e}"))
    return resultados


# ---------------------------------------------------------------------------
# Capa interactiva (thin). No la ejercitan los tests.
# ---------------------------------------------------------------------------
def _preguntar(texto: str, por_defecto: str = "", entrada=input) -> str:
    sufijo = f" [{por_defecto}]" if por_defecto else ""
    try:
        resp = entrada(f"{texto}{sufijo}: ").strip()
    except EOFError:
        return por_defecto
    return resp or por_defecto


def _preguntar_si_no(texto: str, por_defecto: bool = False, entrada=input) -> bool:
    defecto = "s" if por_defecto else "n"
    resp = _preguntar(f"{texto} (s/n)", defecto, entrada=entrada).lower()
    return resp.startswith("s")


def flujo_interactivo(entrada=input, salida=print) -> PlanConfig:
    """Recorre las preguntas y devuelve un PlanConfig. Capa fina sobre la logica pura."""
    plan = PlanConfig()
    salida("== Asistente de configuracion de keni-metricas ==")
    salida("Te guio para crear/actualizar tu config.toml. Tus tokens se quedan en tu maquina.\n")

    # 1) fuente
    real = _preguntar_si_no(
        "Quieres usar datos REALES de las plataformas? (no = datos de muestra offline)",
        por_defecto=False,
        entrada=entrada,
    )
    plan.fuente = "real" if real else "muestra"
    salida(f"-> fuente = {plan.fuente}\n")

    # 2) marcas
    salida("Ahora declara las marcas/cuentas que gestionas.")
    while True:
        nombre = _preguntar("Nombre de la marca (vacio para terminar)", entrada=entrada)
        if not nombre:
            break
        sugerido = normalizar_id_marca(nombre)
        marca_id = normalizar_id_marca(
            _preguntar("  id (minusculas/guion_bajo)", sugerido, entrada=entrada)
        ) or sugerido
        marca = MarcaEntrada(id=marca_id, nombre=nombre)
        for plat in PLATAFORMAS:
            if plat in PLATAFORMAS_SIN_HANDLE:
                continue
            handle = _preguntar(f"  {plat}: handle/id (vacio = no usa {plat})", entrada=entrada)
            if handle:
                marca.plataformas[plat] = handle
        plan.marcas_cuenta.append(marca)
        salida(f"  -> marca '{marca.id}' anadida.\n")

    # 3) alcance
    ids = [m.id for m in plan.marcas_cuenta]
    if ids:
        salida(f"Marcas declaradas: {', '.join(ids)}")
        crudo = _preguntar(
            "Cuales gestionas TU? (coma-separadas; vacio = todas)", entrada=entrada
        )
        plan.alcance = normalizar_alcance(crudo, ids_validos=ids)

    # 4) credenciales (solo si fuente real)
    if plan.fuente == "real":
        salida("\nAhora las credenciales por plataforma. Si no la tienes aun, dejala vacia y se guarda un placeholder.")
        bloques_usados = _bloques_para_marcas(plan.marcas_cuenta)
        for bloque in bloques_usados:
            campo = CAMPO_TOKEN[bloque]
            g = GUIA_CREDENCIALES[bloque]
            salida("")
            salida(f"== {g['titulo']} ==")
            salida(f"Token necesario: {g['que']}")
            salida(f"Mas info: {g['docs']}")
            token = _preguntar(f"  {campo}", entrada=entrada)
            valores: dict[str, str] = {campo: token or PLACEHOLDER_TOKEN}
            if bloque == "meta":
                if _preguntar_si_no(
                    "  Es un token de System User (no caduca)?", por_defecto=False, entrada=entrada
                ):
                    valores["tipo_token"] = "system_user"
            plan.credenciales[bloque] = valores
            salida(f"  -> {campo} = {enmascarar_token(valores[campo])}")

    return plan


def _bloques_para_marcas(marcas: list[MarcaEntrada]) -> list[str]:
    """Bloques de credenciales relevantes segun las plataformas declaradas (orden estable)."""
    bloques: list[str] = []
    # siempre considera tiktok si alguna marca lo gestiona via token (no tiene handle):
    # aqui solo miramos las plataformas con handle declaradas + tiktok opcional al final.
    for plat in PLATAFORMAS:
        bloque = PLATAFORMA_A_BLOQUE[plat]
        if bloque in bloques:
            continue
        if plat in PLATAFORMAS_SIN_HANDLE:
            # tiktok: lo ofrecemos siempre (no se infiere de un handle)
            bloques.append(bloque)
            continue
        if any(plat in m.plataformas for m in marcas):
            bloques.append(bloque)
    return bloques


def resumen_plan(plan: PlanConfig) -> str:
    """Resumen legible del plan, con tokens SIEMPRE enmascarados."""
    lineas = [f"fuente = {plan.fuente}"]
    if plan.alcance:
        lineas.append(f"gestionas (alcance) = {', '.join(plan.alcance)}")
    else:
        lineas.append("gestionas (alcance) = todas")
    for m in plan.marcas_cuenta:
        plats = ", ".join(f"{p}={v}" for p, v in m.plataformas.items()) or "(sin handles)"
        lineas.append(f"  marca {m.id} ({m.nombre}): {plats}")
    for bloque, valores in plan.credenciales.items():
        partes = []
        for clave, valor in valores.items():
            if clave in ("access_token", "bearer_token", "refresh_token", "app_secret", "client_secret"):
                partes.append(f"{clave}={enmascarar_token(valor)}")
            else:
                partes.append(f"{clave}={valor}")
        lineas.append(f"  credenciales[{bloque}]: {', '.join(partes)}")
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m keni_metricas.asistente",
        description="Asistente guiado para crear/actualizar el config.toml de keni-metricas.",
    )
    parser.add_argument(
        "--ruta",
        type=Path,
        default=None,
        help="Ruta del config.toml (por defecto, la de keni-metricas / $KENI_METRICAS_CONFIG).",
    )
    parser.add_argument(
        "--validar",
        action="store_true",
        help="Tras escribir, hace una llamada de prueba por plataforma con token (requiere red).",
    )
    parser.add_argument(
        "--solo-mostrar",
        action="store_true",
        help="Recorre el flujo y muestra el TOML resultante SIN escribir nada.",
    )
    args = parser.parse_args(argv)

    ruta = args.ruta or ruta_config()

    plan = flujo_interactivo()
    print("\n== Resumen ==")
    print(resumen_plan(plan))

    datos = construir_y_fusionar(plan, ruta)

    if args.solo_mostrar:
        print("\n== TOML (no escrito) ==")
        print(serializar_toml(datos))
        return 0

    if not _preguntar_si_no(f"\nEscribir en {ruta}?", por_defecto=True):
        print("Cancelado. No se escribio nada.")
        return 1

    escribir_config_atomico(ruta, datos)
    print(f"Escrito {ruta}")

    if args.validar:
        print("\n== Validacion de conectividad ==")
        for nombre, ok, detalle in validar_conectividad(datos):
            marca = "OK " if ok else "FALLO"
            print(f"  [{marca}] {nombre}: {detalle}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
