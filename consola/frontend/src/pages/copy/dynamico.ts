/**
 * Lógica del formulario DINÁMICO de Generar copy.
 *
 * Cada skill define sus propios `campos`; aquí vive la lógica pura (sin React)
 * que el formulario usa para inicializar valores, validar y decidir si el envío
 * es multipart (cuando hay un campo de tipo archivo). Se mantiene aparte para
 * poder testearla sin montar componentes.
 */
import type { Campo, GrupoSkills, Skill } from "@/types";

/** Devuelve el primer campo de tipo archivo de la skill, o `undefined`. */
export function campoArchivo(skill: Skill | undefined): Campo | undefined {
  return skill?.campos.find((c) => c.tipo === "archivo");
}

/** `true` si la skill se envía como multipart (tiene un campo archivo). */
export function esSkillConArchivo(skill: Skill | undefined): boolean {
  return campoArchivo(skill) !== undefined;
}

/**
 * `true` si la skill es de IMAGEN: tiene un campo de tipo archivo cuyo
 * `media_tipos` (accept) incluye "image" (p. ej. estudio-imagen, breaking-express,
 * revisa-imagen). Las de video/audio (clip-a-copy: "video/*,audio/*") NO lo son.
 * Es la condición que separa la pestaña "Imágenes" de "Generar copy".
 */
export function esSkillDeImagen(skill: Skill | undefined): boolean {
  const campo = campoArchivo(skill);
  if (!campo) return false;
  return (campo.media_tipos ?? "").includes("image");
}

/**
 * Filtra los grupos de skills dejando solo las que cumplen `predicado` y
 * descartando los grupos que se quedan vacíos. Es la base del reparto entre las
 * pestañas "Generar copy" (skills NO de imagen) e "Imágenes" (skills de imagen).
 */
export function filtrarGrupos(
  grupos: GrupoSkills[],
  predicado: (skill: Skill) => boolean,
): GrupoSkills[] {
  return grupos
    .map((grupo) => ({ ...grupo, skills: grupo.skills.filter(predicado) }))
    .filter((grupo) => grupo.skills.length > 0);
}

/**
 * Valores iniciales del formulario para una skill: cada campo de texto/select/
 * fecha arranca vacío. Los campos de archivo no entran en el mapa de valores
 * (se gestionan con un `File` aparte).
 */
export function valoresIniciales(skill: Skill | undefined): Record<string, string> {
  const valores: Record<string, string> = {};
  if (!skill) return valores;
  for (const campo of skill.campos) {
    if (campo.tipo === "archivo") continue;
    valores[campo.id] = "";
  }
  return valores;
}

/**
 * `true` si todos los campos REQUERIDOS de texto están rellenos. Los campos de
 * archivo se validan aparte (con el `File` seleccionado), así que se ignoran aquí.
 */
export function camposTextoCompletos(
  skill: Skill | undefined,
  valores: Record<string, string>,
): boolean {
  if (!skill) return false;
  return skill.campos
    .filter((c) => c.tipo !== "archivo" && c.requerido)
    .every((c) => (valores[c.id] ?? "").trim().length > 0);
}

/**
 * Decide si el botón "Generar" debe estar habilitado:
 *  - todos los campos de texto requeridos rellenos;
 *  - si hay campo archivo y es requerido, debe haber `archivo`;
 *  - si la skill aplica a redes, al menos una red seleccionada.
 */
export function puedeGenerarSkill(opciones: {
  skill: Skill | undefined;
  valores: Record<string, string>;
  archivo: File | null;
  redes: Set<string>;
}): boolean {
  const { skill, valores, archivo, redes } = opciones;
  if (!skill) return false;
  if (!camposTextoCompletos(skill, valores)) return false;

  const campoArch = campoArchivo(skill);
  if (campoArch?.requerido && archivo === null) return false;

  if (skill.aplica_redes && redes.size === 0) return false;

  return true;
}

/** Recorta los espacios de todos los valores de texto (para el envío). */
export function valoresRecortados(valores: Record<string, string>): Record<string, string> {
  const limpio: Record<string, string> = {};
  for (const [id, valor] of Object.entries(valores)) limpio[id] = valor.trim();
  return limpio;
}
