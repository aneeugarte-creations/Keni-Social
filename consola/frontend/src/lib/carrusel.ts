/**
 * Slides EXTRA de una pieza `formato='carrusel'` (espejo del backend, campo `carrusel`).
 *
 * La PORTADA del carrusel es la imagen compuesta de siempre (foto cruda + placa); estos
 * slides van DETRÁS, en orden, dentro del mismo post multi-media. Se persisten como JSON
 * `[{tipo,objeto, …procedencia?}, …]` en `Publicacion.carrusel`.
 *
 * `objeto` es el media PUBLICABLE del slide (su PNG/MP4). En un carrusel EDITORIAL cada slide
 * es una placa horneada; entonces lleva además su PROCEDENCIA (`foto`/`titular`/`plantillaId`/
 * `fotoEncuadre`) para poder RE-EDITARLO como placa (cambiar plantilla/titular/foto y re-hornear).
 * Los slides crudos (subidos a mano, cajón Presidencia) no la traen: solo se reordenan/sustituyen.
 */

/** Un slide del carrusel: su media publicable (`objeto`) + procedencia opcional para re-editar. */
export interface SlideCarrusel {
  tipo: "imagen" | "video";
  objeto: string;
  /** Media id de la foto de FONDO con la que se compuso la placa (procedencia). */
  foto?: string;
  /** Texto-en-imagen (titular) del slide. */
  titular?: string;
  /** Plantilla de diseño elegida; "" o ausente = la EFECTIVA de la marca (como la portada). */
  plantillaId?: string;
  /** Reencuadre de la foto: JSON `{"foco":[x,y],"zoom":z}` o "" (sin reencuadrar). */
  fotoEncuadre?: string;
  /** "Sin placa": el slide es la foto cruda (sin plantilla encima), como el "quitar plantilla"
   * de la portada. Ausente/false = lleva placa. */
  sinPlaca?: boolean;
}

/**
 * ¿El slide se puede editar como PLACA? Solo las IMÁGENES con procedencia (titular o foto):
 * un slide crudo sin receta no se puede recomponer, y un video tampoco lleva placa.
 */
export function slidePlacaEditable(s: SlideCarrusel): boolean {
  return s.tipo === "imagen" && (!!s.titular?.trim() || !!s.foto?.trim());
}

/** Parsea el JSON persistido a slides reparados (orden preservado; basura -> []). */
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
    const slide: SlideCarrusel = { tipo: tipo === "video" ? "video" : "imagen", objeto };
    // Procedencia opcional: solo se adopta si viene como string no vacío (toleramos basura).
    const foto = String((el as { foto?: unknown }).foto ?? "").trim();
    if (foto) slide.foto = foto;
    const titular = (el as { titular?: unknown }).titular;
    if (typeof titular === "string" && titular.trim()) slide.titular = titular;
    const plantillaId = String((el as { plantillaId?: unknown }).plantillaId ?? "").trim();
    if (plantillaId) slide.plantillaId = plantillaId;
    const fotoEncuadre = String((el as { fotoEncuadre?: unknown }).fotoEncuadre ?? "").trim();
    if (fotoEncuadre) slide.fotoEncuadre = fotoEncuadre;
    if ((el as { sinPlaca?: unknown }).sinPlaca === true) slide.sinPlaca = true;
    slides.push(slide);
  }
  return slides;
}

/** Serializa los slides al JSON que persiste el backend ("" si no hay ninguno). */
export function serializarCarrusel(slides: SlideCarrusel[]): string {
  const limpios = slides
    .filter((s) => s.objeto.trim())
    .map((s) => {
      // Solo se emiten los campos de procedencia presentes (los slides crudos quedan {tipo,objeto}).
      const out: SlideCarrusel = { tipo: s.tipo, objeto: s.objeto };
      if (s.foto?.trim()) out.foto = s.foto;
      if (s.titular?.trim()) out.titular = s.titular;
      if (s.plantillaId?.trim()) out.plantillaId = s.plantillaId;
      if (s.fotoEncuadre?.trim()) out.fotoEncuadre = s.fotoEncuadre;
      if (s.sinPlaca) out.sinPlaca = true;
      return out;
    });
  return limpios.length ? JSON.stringify(limpios) : "";
}
