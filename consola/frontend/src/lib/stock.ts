/**
 * Fotos de STOCK: ayuda visual NUNCA publicable sin autorizar.
 *
 * Una foto de stock se baja de una API gratuita o de la imagen original del artículo (RSS) y se
 * adjunta a la pieza como referencia. Mientras un humano no confirme que tiene derechos, la pieza
 * queda `imagen_origen="stock"` y `imagen_autorizada=false`: el back deja `falta_imagen` activo y
 * bloquea publicar (409). El front la pinta ATENUADA + watermark "SIN LICENCIA".
 */
import type { Pieza } from "@/types";

/** Valor de `imagen_origen` cuando la imagen adjunta es una foto de stock (ayuda visual). */
export const ORIGEN_STOCK = "stock";

/** Subconjunto de campos de stock que comparten `Pieza` y las respuestas de los endpoints stock. */
export interface DatosStock {
  imagen_origen?: string;
  imagen_proveedor?: string;
  imagen_autor?: string;
  imagen_licencia?: string;
  imagen_credito_url?: string;
  imagen_autorizada?: boolean;
}

/** ¿Esta pieza lleva una imagen de stock (autorizada o no)? */
export function esStock(p: DatosStock): boolean {
  return (p.imagen_origen ?? "") === ORIGEN_STOCK;
}

/** Valor de `imagen_origen` cuando la imagen es una foto LICENCIADA de agencia (AFP). */
export const ORIGEN_LICENCIADA = "licenciada";

/**
 * ¿Esta pieza lleva una foto LICENCIADA de agencia? A diferencia del stock, es PUBLICABLE directa
 * (sin autorizar, sin overlay "SIN LICENCIA"), pero arrastra un CRÉDITO/BYLINE obligatorio.
 */
export function esLicenciada(d: { imagen_origen?: string }): boolean {
  return (d.imagen_origen ?? "") === ORIGEN_LICENCIADA;
}

/**
 * STOCK_NO_AUTORIZADO: foto de stock que un humano AÚN no ha autorizado a publicar. Es la condición
 * que dispara el tratamiento visual (atenuada + "SIN LICENCIA") y el bloqueo de publicar en la UI.
 */
export function stockNoAutorizado(p: DatosStock): boolean {
  return esStock(p) && !p.imagen_autorizada;
}

/** Stock que un humano YA autorizó: la imagen vale como real (badge sutil, sin overlay). */
export function stockAutorizado(p: DatosStock): boolean {
  return esStock(p) && !!p.imagen_autorizada;
}

/** Mensaje único del bloqueo de publicar por stock sin licencia (tooltips/toasts/avisos). */
export const MENSAJE_BLOQUEO_STOCK =
  "Imagen de stock SIN LICENCIA: autorízala o sustitúyela antes de publicar.";

/** Nombre legible de un proveedor de stock para badges/atribución. */
export function nombreProveedor(proveedor: string | undefined): string {
  const p = (proveedor ?? "").trim().toLowerCase();
  const nombres: Record<string, string> = {
    pexels: "Pexels",
    pixabay: "Pixabay",
    wikimedia: "Wikimedia",
    nasa: "NASA",
    openverse: "Openverse",
    afp: "AFP",
    rss: "Fuente original",
    stock: "Stock",
  };
  return nombres[p] || (p ? p.charAt(0).toUpperCase() + p.slice(1) : "Stock");
}

/** Agencias con licencia libre clara y uniforme: una marca "Autorizar" (no "Sin licencia"). */
export const PROVEEDORES_LIBRES: ReadonlySet<string> = new Set(["pexels", "pixabay"]);

/** ¿El proveedor da una licencia libre clara (Pexels/Pixabay)? Decide el tratamiento de la UI. */
export function esProveedorLibre(proveedor: string | undefined): boolean {
  return PROVEEDORES_LIBRES.has((proveedor ?? "").trim().toLowerCase());
}

/**
 * Los 3 tratamientos legales de una foto de stock, según su LICENCIA REAL:
 *  - "libre": uso comercial sin atribución obligatoria (CC0, dominio público, Pexels/Pixabay).
 *  - "atribucion": uso comercial permitido PERO hay que mantener el crédito (CC BY / CC BY-SA).
 *  - "restringida": no usable con garantías (NC/ND, o licencia desconocida/genérica/vacía).
 */
export type NivelLicencia = "libre" | "atribucion" | "restringida";

/** ¿La licencia CC lleva una cláusula NC (no comercial) o ND (sin obra derivada)? */
function tieneClausulaRestrictiva(lic: string): boolean {
  return (
    lic.includes("-nc") ||
    lic.includes("nc-") ||
    lic.includes("noncommercial") ||
    lic.includes("non-commercial") ||
    lic.includes("-nd") ||
    lic.includes("nd-") ||
    lic.includes("noderiv")
  );
}

/**
 * Clasifica una foto de stock por su LICENCIA REAL (no por proveedor) en 3 niveles. El proveedor
 * solo decide en las agencias con licencia propia (Pexels/Pixabay), no en las APIs de CC.
 */
export function nivelLicencia(d: { licencia?: string; proveedor?: string }): NivelLicencia {
  const lic = (d.licencia ?? "").trim().toLowerCase();
  const prov = (d.proveedor ?? "").trim().toLowerCase();
  // 1. NC/ND: uso comercial o edición restringidos -> nunca con garantías.
  if (tieneClausulaRestrictiva(lic)) return "restringida";
  // 2. Agencias con licencia propia libre (Pexels/Pixabay): se clasifican por proveedor.
  if (prov === "pexels" || prov === "pixabay") return "libre";
  // 3. Dominio público / CC0 / obra de gobierno: libre, sin atribución obligatoria.
  if (
    lic.includes("cc0") ||
    lic.includes("publicdomain") ||
    lic.includes("public domain") ||
    lic.includes("dominio público") ||
    lic.includes("dominio publico") ||
    lic.includes("pdm") ||
    lic.includes("us government") ||
    lic === "pd"
  )
    return "libre";
  // 4. CC BY-SA: comercial con crédito y, además, share-alike.
  if (lic.includes("by-sa") || lic.includes("by sa")) return "atribucion";
  // 5. CC BY: comercial con crédito.
  if (lic.includes("by")) return "atribucion";
  // 6. Vacío / genérico (Wikimedia/Openverse sin licencia concreta) / desconocido: por prudencia.
  return "restringida";
}

/** ¿La licencia es share-alike (BY-SA): editar la foto obliga a licenciar igual la publicación? */
export function esShareAlike(licencia: string | undefined): boolean {
  const lic = (licencia ?? "").trim().toLowerCase();
  return lic.includes("by-sa") || lic.includes("by sa");
}

/** Texto de la marca central sobre la foto de stock no autorizada, según su licencia/proveedor. */
export function etiquetaOverlayStock(d: { licencia?: string; proveedor?: string }): string {
  return nivelLicencia(d) === "restringida" ? "Sin licencia" : "Autorizar";
}

/** Aviso de bloqueo de publicar (las usables no se rotulan "SIN LICENCIA"). */
export function mensajeBloqueoStock(d: { licencia?: string; proveedor?: string }): string {
  return nivelLicencia(d) === "restringida"
    ? MENSAJE_BLOQUEO_STOCK
    : "Foto de stock pendiente de autorizar antes de publicar.";
}

/** Título del diálogo de autorizar, según el nivel de licencia. */
export function tituloAutorizarStock(d: { licencia?: string; proveedor?: string }): string {
  return nivelLicencia(d) === "restringida"
    ? "Autorizar imagen de stock"
    : "Autorizar foto de stock";
}

/** Los 2 riesgos editoriales que el humano debe descartar en una foto de stock con licencia libre. */
export const RIESGOS_STOCK_LIBRE: readonly string[] = [
  "Que no induzca a error: que no parezca una foto real de la noticia.",
  "Que no muestre personas o marcas reconocibles en un contexto que las perjudique.",
];

/**
 * Consulta inicial del buscador de stock a partir del TÍTULO del tema de la pieza. El título suele
 * traer un sufijo " — <vertical>" (p. ej. "Negociaciones EE.UU.-Irán — Diplomacia"): lo cortamos y
 * usamos solo el tema, para que las APIs gratuitas devuelvan fotos relevantes y no aleatorias.
 */
export function temaDeTitulo(titulo: string | undefined): string {
  return (titulo ?? "").split(" — ")[0].trim();
}

/**
 * Consulta por defecto del buscador de fotos de stock: prefiere la KEYWORD visual que propone
 * Sugerir hashtags (`imagen_clave`, sujeto visual de 2-4 palabras), y cae al TEMA del título si no
 * la hay. Así la primera búsqueda da fotos del sujeto, no del titular largo.
 */
export function keywordBusqueda(p: { imagen_clave?: string; titulo?: string }): string {
  return p.imagen_clave?.trim() || temaDeTitulo(p.titulo);
}

/** Pie de atribución de una candidata/imagen de stock: "autor · licencia · proveedor". */
export function atribucionStock(d: {
  autor?: string;
  licencia?: string;
  proveedor?: string;
}): string {
  return [d.autor, d.licencia, nombreProveedor(d.proveedor)].filter((x) => !!x?.trim()).join(" · ");
}

/** Misma condición sobre una `Pieza` completa (azúcar de tipado para los consumidores). */
export function piezaStockNoAutorizado(p: Pieza): boolean {
  return stockNoAutorizado(p);
}
