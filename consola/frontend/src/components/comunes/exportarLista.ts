/**
 * Helpers PUROS para exportar listas (tendencias / plan del día) en formato
 * copiar-pegar: Markdown listo para Word, WhatsApp o email. Sin dependencias de
 * React ni del DOM, para poder testearlos como funciones puras.
 */

/** Un enlace de un ítem exportable (título + URL + medio). */
export interface EnlaceExportable {
  titulo: string;
  url: string;
  fuente?: string;
}

/** Un ítem de una lista exportable (tendencia o posteo del plan del día). */
export interface ItemExportable {
  titulo: string;
  /** Señal/etiqueta corta (p. ej. "50 mil+"); opcional. */
  senal?: string;
  /** Fuentes que reportan el tema (p. ej. "Google Trends"); opcional. */
  fuentes?: string[];
  /** "Por qué sube" / razón editorial; opcional. */
  porQue?: string;
  /** Enlaces "por qué" del tema; opcionales. */
  enlaces?: EnlaceExportable[];
}

/**
 * Construye un documento Markdown a partir de un título de sección y una lista de
 * ítems. Cada ítem es un punto numerado con su título y, si las trae, su señal,
 * fuentes, "por qué" y enlaces. Pensado para pegar tal cual en Word/WhatsApp/email:
 * los enlaces van como `[título](url)` y el resto como texto plano.
 *
 * Es PURA y determinista: misma entrada => misma salida. No toca el portapapeles ni
 * el DOM (de eso se encargan los botones que la usan).
 */
export function construirMarkdownLista(titulo: string, items: ItemExportable[]): string {
  const lineas: string[] = [`# ${titulo}`, ""];
  if (items.length === 0) {
    lineas.push("_Sin elementos._");
    return lineas.join("\n");
  }
  items.forEach((item, i) => {
    const meta: string[] = [];
    if (item.senal) meta.push(item.senal);
    if (item.fuentes && item.fuentes.length > 0) meta.push(item.fuentes.join(", "));
    const sufijo = meta.length > 0 ? ` _(${meta.join(" · ")})_` : "";
    lineas.push(`${i + 1}. **${item.titulo}**${sufijo}`);
    if (item.porQue) lineas.push(`   ${item.porQue}`);
    for (const enlace of item.enlaces ?? []) {
      if (!enlace.url && !enlace.titulo) continue;
      const etiqueta = enlace.titulo || enlace.url;
      const medio = enlace.fuente ? ` — ${enlace.fuente}` : "";
      lineas.push(enlace.url ? `   - [${etiqueta}](${enlace.url})${medio}` : `   - ${etiqueta}${medio}`);
    }
  });
  return lineas.join("\n");
}

/** Nombre de fichero seguro (slug ascii) para la descarga .txt de una lista. */
export function nombreArchivoLista(titulo: string): string {
  const slug = titulo
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  const fecha = new Date().toISOString().slice(0, 10);
  return `${slug || "lista"}-${fecha}.txt`;
}
