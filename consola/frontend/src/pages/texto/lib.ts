/**
 * Helpers de la página Texto extraídos del contenedor (`pages/Texto.tsx`).
 */

/**
 * Separa un bloque de "frontmatter" al INICIO del cuerpo (un bloque `---\n…\n---`) del
 * resto del texto. El store ya quita el frontmatter real; pero algunos documentos llevan
 * ADEMÁS un bloque de metadatos al principio del cuerpo, que no aporta nada al editor.
 * Lo separamos para EDITARLO oculto y readjuntarlo al guardar (no se pierde del fichero).
 * Guarda: solo separa si el bloque PARECE metadatos (líneas `clave: valor` o comentarios `#`),
 * para no tragarse un separador `---` legítimo de prosa.
 */
export function separarFrontmatter(cuerpo: string): { oculto: string; visible: string } {
  const m = /^---\r?\n([\s\S]*?)\r?\n---[ \t]*\r?\n[ \t\r\n]*/.exec(cuerpo);
  if (!m || m.index !== 0) return { oculto: "", visible: cuerpo };
  const lineas = m[1].split(/\r?\n/).filter((l) => l.trim());
  const pareceMeta = lineas.length > 0 && lineas.every((l) => /^\s*(#|[\w.-]+\s*:)/.test(l));
  if (!pareceMeta) return { oculto: "", visible: cuerpo };
  return { oculto: m[0], visible: cuerpo.slice(m[0].length) };
}
