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

/** Placeholder del contrato de salida (lo gestiona el backend; el editor lo oculta). */
export const PLACEHOLDER_CONTRATO = "{{CONTRATO_SALIDA}}";

/**
 * Quita el placeholder `{{CONTRATO_SALIDA}}` del FINAL del cuerpo: en los prompts estructurados
 * el contrato de salida no se edita desde la Prompts (vive en código y se pinta read-only
 * aparte), así que el editor no debe mostrar su placeholder. Se readjunta al guardar con
 * `componerCuerpoTexto`. No-op si el cuerpo no lo lleva.
 */
export function quitarContratoSalida(cuerpo: string): string {
  return cuerpo.replace(
    new RegExp(`\\s*${PLACEHOLDER_CONTRATO.replace(/[{}]/g, "\\$&")}\\s*$`),
    "",
  );
}

/**
 * Recompone el cuerpo COMPLETO que se persiste: frontmatter oculto + lo visible (editado) +,
 * si el doc es estructurado, el placeholder del contrato al final. Espejo de `separarFrontmatter`
 * + `quitarContratoSalida`.
 */
export function componerCuerpoTexto(
  frontmatterOculto: string,
  visible: string,
  conContrato: boolean,
): string {
  const base = frontmatterOculto + visible;
  return conContrato ? `${base.replace(/\s+$/, "")}\n\n${PLACEHOLDER_CONTRATO}\n` : base;
}
