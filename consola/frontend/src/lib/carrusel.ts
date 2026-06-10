/**
 * Slides EXTRA de una pieza `formato='carrusel'` (espejo del backend, campo `carrusel`).
 *
 * La PORTADA del carrusel es la imagen compuesta de siempre (foto cruda + placa); estos
 * slides van DETRÁS, en crudo y en orden, dentro del mismo post multi-media. Se persisten
 * como JSON `[{tipo:"imagen"|"video",objeto:<media id>}, …]` en `Publicacion.carrusel`.
 */

/** Un slide extra del carrusel: media en crudo, tal cual se subió. */
export interface SlideCarrusel {
  tipo: "imagen" | "video";
  objeto: string;
}

/** Parsea el JSON persistido a slides saneados (orden preservado; basura -> []). */
export function parsearCarrusel(crudo: string | null | undefined): SlideCarrusel[] {
  if (!crudo || !crudo.trim()) return [];
  let datos: unknown;
  try {
    datos = JSON.parse(crudo);
  } catch {
    return [];
  }
  if (!Array.isArray(datos)) return [];
  const slides: SlideCarrusel[] = [];
  for (const el of datos) {
    if (typeof el !== "object" || el === null) continue;
    const objeto = String((el as { objeto?: unknown }).objeto ?? "").trim();
    if (!objeto) continue;
    const tipo = String((el as { tipo?: unknown }).tipo ?? "").trim().toLowerCase();
    slides.push({ tipo: tipo === "video" ? "video" : "imagen", objeto });
  }
  return slides;
}

/** Serializa los slides al JSON que persiste el backend ("" si no hay ninguno). */
export function serializarCarrusel(slides: SlideCarrusel[]): string {
  const limpios = slides.filter((s) => s.objeto.trim());
  return limpios.length ? JSON.stringify(limpios) : "";
}
