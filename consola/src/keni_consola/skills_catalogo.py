"""Catalogo de SKILLS respaldado por ARCHIVOS (files-as-truth).

Cada skill es una carpeta `<dir_skills>/<id>/` con DOS archivos:

  - `SKILL.md`   las instrucciones que sigue Claude (frontmatter `name`+`description`
                 + cuerpo). Lo lee/escribe el plugin de Claude Code; aqui se expone
                 para que la pagina de gestion lo edite.
  - `keni.yaml`  los METADATOS de la app (lo que esta consola necesita para pintar el
                 formulario de generacion y orquestar la salida): nombre, explicacion,
                 grupo, si aplica a redes, tipo de salida, si es media, orden y la lista
                 de CAMPOS del formulario + la plantilla de invocacion.

La GENERACION es DINAMICA: el formulario y la invocacion salen de `keni.yaml`, no de un
"pega texto + elige redes" fijo. `render_invocacion` materializa la `plantilla_invocacion`
sustituyendo `{marca}` y `{<campo_id>}`, anade la instruccion de "sin emojis" y, solo si
la skill `aplica_redes` y se pidieron redes, la instruccion ADITIVA de redes (reutilizada
de `dominio.skills._instruccion_redes`).

SEGURIDAD: el `id`/slug se sanea contra traversal (`[a-z0-9-]`, reutilizando el slug de
`agentes`); las rutas se resuelven y se comprueba que caen ESTRICTAMENTE dentro de
`dir_skills()`; las escrituras son ATOMICAS (tmp + os.replace). Todo error sale en espanol.

El directorio raiz se puede sobreescribir con el env `KENI_SKILLS_DIR` (los tests lo
apuntan a un tmp con skills falsas, para NO tocar el `skills-copy/` real del repo).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from keni_shared.esquema_yaml import migrar, sellar

from .io_atomico import escribir_atomico

# --------------------------------------------------------------------------- #
# Constantes y errores                                                        #
# --------------------------------------------------------------------------- #

_ARCHIVO_META = "keni.yaml"
_ARCHIVO_SKILL = "SKILL.md"

# Subcarpeta dentro del cwd de skills donde viven las skills (estructura del plugin).
_SUBDIR_SKILLS = Path("skills-copy") / ".claude" / "skills"

# Valores permitidos de los enums de `keni.yaml`.
GRUPOS = ("validadas", "experimentales")
SALIDAS = ("piezas", "documento")
TIPOS_CAMPO = ("textarea", "texto", "archivo", "select", "fecha")

# Etiqueta humana de cada grupo + si es experimental (para la UI).
ETIQUETA_GRUPO = {
    "validadas": ("Validadas con el equipo", False),
    "experimentales": ("Experimentales (no validadas con el piloto)", True),
}

# slug: minusculas, digitos y guiones; sin guiones colgando.
_RE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SkillCatalogoError(RuntimeError):
    """Error del catalogo con mensaje ya en espanol, apto para mostrar al usuario."""


# --------------------------------------------------------------------------- #
# Dataclasses del esquema                                                     #
# --------------------------------------------------------------------------- #


@dataclass
class Campo:
    """Un campo del formulario de generacion de una skill (driver del frontend)."""

    id: str
    etiqueta: str
    tipo: str = "textarea"  # textarea | texto | archivo | select | fecha
    requerido: bool = False
    placeholder: str = ""
    ayuda: str = ""
    opciones: list[str] = field(default_factory=list)  # solo tipo=select
    media_tipos: str = ""  # solo tipo=archivo, p.ej. "video/*,audio/*"

    def a_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "etiqueta": self.etiqueta,
            "tipo": self.tipo,
            "requerido": self.requerido,
            "placeholder": self.placeholder,
            "ayuda": self.ayuda,
            "opciones": list(self.opciones),
            "media_tipos": self.media_tipos,
        }


@dataclass
class SkillDef:
    """Definicion completa de una skill (metadatos de `keni.yaml` + su id de carpeta)."""

    id: str
    nombre: str
    explicacion: str = ""
    grupo: str = "validadas"  # validadas | experimentales
    aplica_redes: bool = False
    salida: str = "documento"  # piezas | documento
    media: bool = False
    orden: int = 100
    campos: list[Campo] = field(default_factory=list)
    plantilla_invocacion: str = ""

    def a_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "nombre": self.nombre,
            "explicacion": self.explicacion,
            "grupo": self.grupo,
            "aplica_redes": self.aplica_redes,
            "salida": self.salida,
            "media": self.media,
            "orden": self.orden,
            "campos": [c.a_dict() for c in self.campos],
            "plantilla_invocacion": self.plantilla_invocacion,
        }

    def campos_requeridos(self) -> list[Campo]:
        return [c for c in self.campos if c.requerido]

    def campo(self, campo_id: str) -> Campo | None:
        for c in self.campos:
            if c.id == campo_id:
                return c
        return None

    def primer_campo_texto(self) -> Campo | None:
        """Primer campo de texto (textarea/texto), para el back-compat de `construir_prompt`."""
        for c in self.campos:
            if c.tipo in ("textarea", "texto"):
                return c
        return self.campos[0] if self.campos else None

    def campo_archivo(self) -> Campo | None:
        """Primer campo de tipo archivo (la skill media tiene exactamente uno)."""
        for c in self.campos:
            if c.tipo == "archivo":
                return c
        return None


# --------------------------------------------------------------------------- #
# Localizacion del directorio de skills                                       #
# --------------------------------------------------------------------------- #


def dir_skills() -> Path:
    """Directorio donde viven las carpetas de skills (`<cwd>/skills-copy/.claude/skills`).

    Preferencia: env `KENI_SKILLS_DIR` (apunta directo a la carpeta de skills; lo usan
    los tests con un tmp) -> `<KENI_SKILLS_CWD|repo|cwd>/skills-copy/.claude/skills`.
    """
    env = os.environ.get("KENI_SKILLS_DIR")
    if env:
        return Path(env)
    # Import PEREZOSO del dominio (no de `api/`, hallazgo N13) para reutilizar la logica de
    # cwd sin crear ciclo: `dominio.skills` importa `skills_catalogo` a nivel de modulo.
    from .dominio import skills as dom_skills

    return dom_skills.cwd_skills() / _SUBDIR_SKILLS


def _ruta_carpeta(skill_id: str) -> Path:
    """Resuelve `<dir_skills>/<id>/` garantizando que cae ESTRICTAMENTE dentro de la raiz."""
    base = dir_skills()
    seguro = Path(skill_id).name
    if not seguro or seguro != skill_id or seguro in (".", ".."):
        raise SkillCatalogoError("Identificador de skill no válido.")
    destino = (base / seguro).resolve()
    if destino.parent != base.resolve():
        raise SkillCatalogoError("Ruta de skill fuera del directorio de skills.")
    return destino


# --------------------------------------------------------------------------- #
# Escritura atomica + lectura tolerante                                       #
# --------------------------------------------------------------------------- #


def _escribir_atomico(ruta: Path, texto: str) -> None:
    """Escribe `texto` en `ruta` de forma ATOMICA (delega en `io_atomico`)."""
    escribir_atomico(ruta, texto)


def _leer_yaml(ruta: Path) -> dict[str, object] | None:
    """Lee un YAML como dict, o None si no existe / esta corrupto / no es un mapa.

    `migrar("skill", ...)` sube de version el `keni.yaml` legado en memoria (#125).
    """
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        datos = yaml.safe_load(texto)
    except yaml.YAMLError:
        return None
    if not isinstance(datos, dict):
        return None
    return migrar("skill", datos)


# --------------------------------------------------------------------------- #
# Parseo / validacion del esquema                                             #
# --------------------------------------------------------------------------- #


def _campo_desde_dict(crudo: object) -> Campo | None:
    """Construye un `Campo` desde un dict crudo; None si no es utilizable (sin id/etiqueta)."""
    if not isinstance(crudo, dict):
        return None
    cid = crudo.get("id")
    etiqueta = crudo.get("etiqueta")
    if not isinstance(cid, str) or not cid.strip():
        return None
    tipo = crudo.get("tipo")
    if not isinstance(tipo, str) or tipo not in TIPOS_CAMPO:
        tipo = "textarea"
    opciones_crudas = crudo.get("opciones")
    opciones = [o for o in opciones_crudas if isinstance(o, str)] if isinstance(opciones_crudas, list) else []
    return Campo(
        id=cid.strip(),
        etiqueta=etiqueta.strip() if isinstance(etiqueta, str) else cid.strip(),
        tipo=tipo,
        requerido=bool(crudo.get("requerido")),
        placeholder=crudo.get("placeholder") if isinstance(crudo.get("placeholder"), str) else "",
        ayuda=crudo.get("ayuda") if isinstance(crudo.get("ayuda"), str) else "",
        opciones=opciones,
        media_tipos=crudo.get("media_tipos") if isinstance(crudo.get("media_tipos"), str) else "",
    )


def _skilldef_desde_meta(skill_id: str, datos: dict[str, object]) -> SkillDef:
    """Construye un `SkillDef` tolerante desde el dict de `keni.yaml` (valores por defecto)."""
    nombre = datos.get("nombre")
    nombre = nombre.strip() if isinstance(nombre, str) and nombre.strip() else skill_id

    grupo = datos.get("grupo")
    grupo = grupo if isinstance(grupo, str) and grupo in GRUPOS else "validadas"

    salida = datos.get("salida")
    salida = salida if isinstance(salida, str) and salida in SALIDAS else "documento"

    orden = datos.get("orden")
    orden = orden if isinstance(orden, int) and not isinstance(orden, bool) else 100

    campos_crudos = datos.get("campos")
    campos: list[Campo] = []
    if isinstance(campos_crudos, list):
        for c in campos_crudos:
            campo = _campo_desde_dict(c)
            if campo is not None:
                campos.append(campo)

    media = bool(datos.get("media")) or any(c.tipo == "archivo" for c in campos)

    plantilla = datos.get("plantilla_invocacion")
    plantilla = plantilla if isinstance(plantilla, str) else ""

    return SkillDef(
        id=skill_id,
        nombre=nombre,
        explicacion=datos.get("explicacion") if isinstance(datos.get("explicacion"), str) else "",
        grupo=grupo,
        aplica_redes=bool(datos.get("aplica_redes")),
        salida=salida,
        media=media,
        orden=orden,
        campos=campos,
        plantilla_invocacion=plantilla,
    )


def _meta_desde_skilldef(skill: SkillDef) -> dict[str, object]:
    """Serializa un `SkillDef` al dict que se escribe en `keni.yaml` (orden estable)."""
    return {
        "nombre": skill.nombre,
        "explicacion": skill.explicacion,
        "grupo": skill.grupo,
        "aplica_redes": skill.aplica_redes,
        "salida": skill.salida,
        "media": skill.media,
        "orden": skill.orden,
        "campos": [c.a_dict() for c in skill.campos],
        "plantilla_invocacion": skill.plantilla_invocacion,
    }


# --------------------------------------------------------------------------- #
# Lectura del catalogo                                                        #
# --------------------------------------------------------------------------- #


def listar() -> list[SkillDef]:
    """Todas las skills (carpetas con `keni.yaml`), ordenadas por (orden, id).

    Tolerante: una carpeta sin `keni.yaml` o con YAML corrupto se SALTA, no rompe el listado.
    """
    base = dir_skills()
    if not base.is_dir():
        return []
    skills: list[SkillDef] = []
    for hijo in base.iterdir():
        if not hijo.is_dir():
            continue
        datos = _leer_yaml(hijo / _ARCHIVO_META)
        if datos is None:
            continue
        skills.append(_skilldef_desde_meta(hijo.name, datos))
    skills.sort(key=lambda s: (s.orden, s.id))
    return skills


def obtener(skill_id: str) -> SkillDef | None:
    """Una skill por id, o None si no existe / id invalido / `keni.yaml` corrupto."""
    if not isinstance(skill_id, str) or not skill_id:
        return None
    try:
        carpeta = _ruta_carpeta(skill_id)
    except SkillCatalogoError:
        return None
    datos = _leer_yaml(carpeta / _ARCHIVO_META)
    if datos is None:
        return None
    return _skilldef_desde_meta(skill_id, datos)


def existe(skill_id: str) -> bool:
    """True si la skill existe en el catalogo (tiene carpeta + `keni.yaml`)."""
    return obtener(skill_id) is not None


def leer_skill_md(skill_id: str) -> str:
    """Contenido del `SKILL.md` de una skill (lanza si no existe la skill)."""
    carpeta = _ruta_carpeta(skill_id)
    ruta = carpeta / _ARCHIVO_SKILL
    if not ruta.is_file():
        raise SkillCatalogoError("Esa skill no existe.")
    try:
        return ruta.read_text(encoding="utf-8")
    except OSError as e:
        raise SkillCatalogoError("No se pudo leer el SKILL.md de la skill.") from e


def guardar_skill_md(skill_id: str, contenido: str) -> None:
    """Reescribe el `SKILL.md` de una skill (atomico). Lanza si la skill no existe."""
    carpeta = _ruta_carpeta(skill_id)
    if not (carpeta / _ARCHIVO_META).is_file():
        raise SkillCatalogoError("Esa skill no existe.")
    if not isinstance(contenido, str) or not contenido.strip():
        raise SkillCatalogoError("El contenido del SKILL.md no puede estar vacío.")
    _escribir_atomico(carpeta / _ARCHIVO_SKILL, contenido)


# --------------------------------------------------------------------------- #
# Creacion / actualizacion / borrado                                          #
# --------------------------------------------------------------------------- #


def _slug_de_nombre(nombre: str) -> str:
    """Deriva un slug seguro (`[a-z0-9-]`) desde un nombre humano (reutiliza `agentes`)."""
    from . import agentes

    try:
        return agentes._slug_de_nombre(nombre)
    except agentes.NombreAgenteInvalido as e:
        raise SkillCatalogoError(str(e)) from e


def _scaffold_skill_md(skill_id: str, nombre: str, explicacion: str) -> str:
    """Esqueleto inicial de `SKILL.md` (frontmatter name+description + cuerpo arranque)."""
    descripcion = explicacion.strip() or f"Skill {nombre} de AMX Contenido."
    return (
        "---\n"
        f"name: {skill_id}\n"
        f"description: {descripcion}\n"
        "allowed-tools: Read, Glob, Bash(date:*)\n"
        "---\n\n"
        f"# {skill_id}\n\n"
        f"{descripcion}\n\n"
        "Modo dry-run: preparas y previsualizas; no publicas ni haces peticiones de red.\n\n"
        "## Pasos\n\n"
        "1. Lee la fuente que te indique el usuario.\n"
        "2. Produce el resultado en la voz de la marca.\n"
        "3. Cierra con una auto-verificación honesta.\n\n"
        "## Reglas\n\n"
        "- No inventes datos que no estén en la fuente.\n"
        "- El humano aprueba. Tu salida es un borrador verificado, no una publicación.\n"
    )


def crear(
    nombre: str,
    *,
    explicacion: str = "",
    grupo: str = "experimentales",
    aplica_redes: bool = False,
    salida: str = "documento",
) -> SkillDef:
    """Crea una skill nueva: carpeta + `SKILL.md` (scaffold) + `keni.yaml` (defaults).

    Deriva un slug seguro del nombre. Por defecto un solo campo textarea "fuente",
    `aplica_redes=False`, `salida=documento`, grupo `experimentales`. Lanza si el nombre
    no produce un slug valido o si ya existe una skill con ese id.
    """
    if not isinstance(nombre, str) or not nombre.strip():
        raise SkillCatalogoError("El nombre de la skill no puede estar vacío.")
    skill_id = _slug_de_nombre(nombre)
    if grupo not in GRUPOS:
        grupo = "experimentales"
    if salida not in SALIDAS:
        salida = "documento"
    carpeta = _ruta_carpeta(skill_id)
    if carpeta.exists():
        raise SkillCatalogoError("Ya existe una skill con ese nombre.")

    skill = SkillDef(
        id=skill_id,
        nombre=nombre.strip(),
        explicacion=explicacion.strip() if isinstance(explicacion, str) else "",
        grupo=grupo,
        aplica_redes=bool(aplica_redes),
        salida=salida,
        media=False,
        orden=100,
        campos=[
            Campo(
                id="fuente",
                etiqueta="Fuente",
                tipo="textarea",
                requerido=True,
                placeholder="Pega aquí la fuente…",
            )
        ],
        plantilla_invocacion=f"usa {skill_id} con la siguiente fuente, marca {{marca}}:\n\n{{fuente}}",
    )
    carpeta.mkdir(parents=True, exist_ok=False)
    _escribir_atomico(carpeta / _ARCHIVO_SKILL, _scaffold_skill_md(skill_id, skill.nombre, skill.explicacion))
    _escribir_meta(skill)
    return skill


def _validar_meta(datos: dict[str, object]) -> SkillDef:
    """Valida (estricto) el dict de metadatos de un PUT y devuelve el `SkillDef`.

    A diferencia de la lectura tolerante, aqui rechazamos enums fuera de rango y
    campos mal formados con un error en espanol (es entrada del usuario via API).
    """
    if not isinstance(datos, dict):
        raise SkillCatalogoError("Los metadatos de la skill no son válidos.")
    nombre = datos.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip():
        raise SkillCatalogoError("El nombre de la skill es obligatorio.")
    grupo = datos.get("grupo", "validadas")
    if grupo not in GRUPOS:
        raise SkillCatalogoError("El grupo debe ser 'validadas' o 'experimentales'.")
    salida = datos.get("salida", "documento")
    if salida not in SALIDAS:
        raise SkillCatalogoError("La salida debe ser 'piezas' o 'documento'.")
    orden = datos.get("orden", 100)
    if not isinstance(orden, int) or isinstance(orden, bool):
        raise SkillCatalogoError("El orden debe ser un número entero.")

    campos_crudos = datos.get("campos", [])
    if not isinstance(campos_crudos, list):
        raise SkillCatalogoError("Los campos deben ser una lista.")
    campos: list[Campo] = []
    vistos: set[str] = set()
    for crudo in campos_crudos:
        if not isinstance(crudo, dict):
            raise SkillCatalogoError("Cada campo debe ser un objeto con id y etiqueta.")
        cid = crudo.get("id")
        if not isinstance(cid, str) or not cid.strip():
            raise SkillCatalogoError("Cada campo necesita un id.")
        cid = cid.strip()
        if cid in vistos:
            raise SkillCatalogoError(f"Hay un campo repetido: '{cid}'.")
        vistos.add(cid)
        tipo = crudo.get("tipo", "textarea")
        if not isinstance(tipo, str) or tipo not in TIPOS_CAMPO:
            raise SkillCatalogoError(
                f"El tipo del campo '{cid}' debe ser uno de: {', '.join(TIPOS_CAMPO)}."
            )
        campo = _campo_desde_dict(crudo)
        if campo is None:
            raise SkillCatalogoError(f"El campo '{cid}' no es válido.")
        campos.append(campo)

    media = bool(datos.get("media")) or any(c.tipo == "archivo" for c in campos)
    plantilla = datos.get("plantilla_invocacion", "")
    if not isinstance(plantilla, str):
        raise SkillCatalogoError("La plantilla de invocación debe ser texto.")

    return SkillDef(
        id="",  # lo fija el llamante
        nombre=nombre.strip(),
        explicacion=datos.get("explicacion") if isinstance(datos.get("explicacion"), str) else "",
        grupo=grupo,
        aplica_redes=bool(datos.get("aplica_redes")),
        salida=salida,
        media=media,
        orden=orden,
        campos=campos,
        plantilla_invocacion=plantilla,
    )


def actualizar(skill_id: str, metadata: dict[str, object]) -> SkillDef:
    """Reescribe el `keni.yaml` de una skill con metadatos validados. Lanza si no existe."""
    carpeta = _ruta_carpeta(skill_id)
    if not (carpeta / _ARCHIVO_META).is_file():
        raise SkillCatalogoError("Esa skill no existe.")
    skill = _validar_meta(metadata)
    skill.id = skill_id
    _escribir_meta(skill)
    return skill


def _escribir_meta(skill: SkillDef) -> None:
    """Escribe el `keni.yaml` de una skill (atomico, unicode, orden de claves estable).

    `sellar("skill", ...)` estampa la `version` de esquema DESPUES de pasar el
    `SkillDef` a dict (#125).
    """
    carpeta = _ruta_carpeta(skill.id)
    texto = yaml.safe_dump(
        sellar("skill", _meta_desde_skilldef(skill)),
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=4096,
    )
    _escribir_atomico(carpeta / _ARCHIVO_META, texto)


def borrar(skill_id: str) -> None:
    """Borra la carpeta de una skill (defensivo: debe caer dentro de `dir_skills()`)."""
    import shutil

    carpeta = _ruta_carpeta(skill_id)
    if not carpeta.is_dir():
        raise SkillCatalogoError("Esa skill no existe.")
    # Defensa en profundidad: re-comprobamos que la carpeta resuelta cuelga de la raiz.
    base = dir_skills().resolve()
    if carpeta.resolve().parent != base:
        raise SkillCatalogoError("No se puede borrar fuera del directorio de skills.")
    shutil.rmtree(carpeta)


# --------------------------------------------------------------------------- #
# Renderizado de la invocacion (prompt dinamico)                              #
# --------------------------------------------------------------------------- #


def render_invocacion(
    skill: SkillDef,
    marca: str,
    valores: dict[str, str],
    redes_ids: list[str] | None = None,
) -> str:
    """Materializa la `plantilla_invocacion` -> texto de invocacion para Claude.

    Sustituye `{marca}` (id de marca) y `{<campo_id>}` (valor de cada campo) por
    `str.replace`. Luego anade la instruccion de "sin emojis" y, SOLO si la skill
    `aplica_redes` y hay `redes_ids`, la instruccion ADITIVA de redes (bloque json).
    Para campos `archivo`, el valor substituido es la RUTA del temporal guardado.
    """
    # Import local (no a nivel de modulo) para evitar el ciclo
    # `dominio.skills -> skills_catalogo -> dominio.skills`. La instruccion de "sin
    # emojis" y la de redes viven ya en el DOMINIO (antes en `api.skills`, H6).
    from .dominio import skills as dom_skills

    plantilla = skill.plantilla_invocacion or ""
    texto = plantilla.replace("{marca}", marca)
    for campo in skill.campos:
        valor = valores.get(campo.id, "")
        if not isinstance(valor, str):
            valor = ""
        texto = texto.replace("{" + campo.id + "}", valor)

    texto = f"{texto}\n\n{dom_skills._INSTRUCCION_SIN_EMOJIS}"
    if skill.aplica_redes and redes_ids:
        texto = f"{texto}\n\n{dom_skills._instruccion_redes(redes_ids)}"
    return texto
