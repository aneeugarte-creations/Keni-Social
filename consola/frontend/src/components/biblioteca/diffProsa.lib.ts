/**
 * Helpers PUROS para el diff de prosa: proyectan el markdown editorial a un texto plano
 * legible ANTES de diffear, para que la persona de redes nunca vea markdown crudo
 * (`##`, `**`, `>`, `- `, enlaces, frontmatter) ni "saltos de línea / caracteres extraños".
 *
 * Decisión (camino "b" del encargo, el más robusto y mantenible para un DIFF a nivel de
 * palabra): NO renderizamos un segundo árbol WYSIWYG, sino que normalizamos AMBOS lados con
 * EXACTAMENTE el mismo pipeline (mismo strip de frontmatter + misma limpieza de markup +
 * misma normalización de whitespace). Al normalizar igual los dos textos, los diffs fantasma
 * de formato (viñeta `*` vs `-`, hard-breaks de tiptap, espacios sobrantes) se cancelan y
 * solo sobreviven los cambios de CONTENIDO real.
 *
 * Lo único que se conserva intacto es la sintaxis de variables `{{VARIABLE}}`: el componente
 * la pinta como pastilla, así que aquí la protegemos de cualquier transformación.
 */

/** `{{VARIABLE}}` como unidad: para proteger las variables al limpiar inline markdown. */
const RE_VARIABLE = /(\{\{[A-Z_]+\}\})/g;
/** Igual que `RE_VARIABLE` pero anclado y SIN flag global (para `.test`, sin `lastIndex`). */
const RE_ES_VARIABLE = /^\{\{[A-Z_]+\}\}$/;

/**
 * Quita el bloque frontmatter YAML inicial (`---\n...\n---`) si lo hay. Solo cuenta al
 * principio del texto; metadatos jamás deben entrar al diff (ni como cambio ni como ruido).
 */
export function quitarFrontmatter(texto: string): string {
  const t = texto.replace(/\r\n/g, "\n");
  if (!t.startsWith("---\n")) return t;
  // Cierre del frontmatter: una línea `---` posterior (al final o seguida de salto).
  const cierre = /\n---[ \t]*(?:\n|$)/.exec(t.slice(3));
  if (!cierre) return t;
  return t.slice(3 + cierre.index + cierre[0].length);
}

/** ¿Es esta línea una regla horizontal markdown (`---`, `***`, `___`)? */
function esReglaHorizontal(linea: string): boolean {
  return /^\s{0,3}(?:([-*_])[ \t]*){3,}$/.test(linea);
}

/** Limpia los marcadores markdown de PRINCIPIO de línea (estructura), no el contenido. */
function limpiarLinea(linea: string): string {
  let l = linea.replace(/[ \t]+$/, ""); // trailing spaces fuera (no es contenido).
  if (esReglaHorizontal(l)) return ""; // separador visual -> línea en blanco.
  l = l.replace(/^(?:\s{0,3}>[ \t]?)+/, ""); // citas `>` (incluido anidado).
  l = l.replace(/^\s{0,3}#{1,6}[ \t]+/, ""); // encabezados `#`..`######`.
  // Viñetas `-`/`*`/`+` -> un único marcador `• `, así `*` vs `-` no es un cambio.
  l = l.replace(/^(\s*)[-*+][ \t]+/, "$1• ");
  return l;
}

/** Aplica las transformaciones inline de markdown a un fragmento SIN variables. */
function limpiarInline(fragmento: string): string {
  return (
    fragmento
      // Imágenes y enlaces -> su texto visible (antes que nada, por los `[]()`).
      .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
      .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
      // Código inline -> su contenido (antes de `*`/`_` por si los contiene).
      .replace(/`([^`]+)`/g, "$1")
      // Negrita, tachado e itálica.
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/__([^_]+)__/g, "$1")
      .replace(/~~([^~]+)~~/g, "$1")
      .replace(/\*([^*]+)\*/g, "$1")
      .replace(/(?<![A-Za-z0-9])_([^_]+)_(?![A-Za-z0-9])/g, "$1")
  );
}

/**
 * Proyecta el markdown a texto plano legible: quita frontmatter, marcadores de bloque y
 * markup inline, y normaliza el whitespace. CONSERVA `{{VARIABLE}}` intacto (el componente
 * la pinta como pastilla) y la estructura de párrafos (líneas en blanco) para el diff.
 */
export function aProsaPlana(texto: string): string {
  let t = quitarFrontmatter(texto);
  // Marcadores de bloque, línea a línea.
  t = t
    .split("\n")
    .map(limpiarLinea)
    .join("\n");
  // Markup inline, protegiendo las variables de cualquier sustitución.
  t = t
    .split(RE_VARIABLE)
    .map((parte) => (RE_ES_VARIABLE.test(parte) ? parte : limpiarInline(parte)))
    .join("");
  // Whitespace: colapsa rachas de espacios/tabs (no de saltos) y limita líneas en blanco.
  t = t
    .replace(/[ \t]{2,}/g, " ")
    .replace(/[ \t]+$/gm, "")
    .replace(/\n{3,}/g, "\n\n");
  return t.trim();
}

/** ¿El fragmento es PURO whitespace? Un cambio de solo whitespace no se resalta. */
export function esSoloEspacios(texto: string): boolean {
  return texto.length > 0 && /^\s+$/.test(texto);
}
