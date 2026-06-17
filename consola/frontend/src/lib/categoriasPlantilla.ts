// Catálogo de CATEGORÍAS de plantillas de diseño (organización estilo Canva).
//
// La categoría es TEXTO LIBRE normalizado a slug (sin enum en BD; el backend normaliza igual en
// `api/plantillas_diseno.py`): este catálogo solo aporta las etiquetas legibles y el ORDEN de las
// categorías conocidas (noticias UnoTV + deportes Claro Sports). Cualquier slug fuera del catálogo
// se muestra "prettificado" (guiones -> espacios, inicial mayúscula). "general" es el fallback:
// toda plantilla sin categoría (o con el legado "post") cae ahí.

import type { PlantillaDiseno } from "@/lib/api";

export interface CategoriaPlantilla {
  slug: string;
  etiqueta: string;
}

/**
 * Catálogo de etiquetas de UNA marca (override del catálogo estático): rótulos personalizados que el
 * equipo puso al renombrar y el conjunto de slugs gestionados. Lo inyecta el llamante desde la API
 * (`/api/etiquetas-plantilla`). Cuando se OMITE en las funciones de abajo, estas usan el catálogo
 * estático global (comportamiento histórico, p. ej. en tests o mientras carga la query).
 */
export interface CatalogoEtiquetas {
  /** Rótulo personalizado por slug (solo entradas con override NO vacío). */
  rotulos: Map<string, string>;
  /** Slugs con etiqueta gestionada para la marca (aparecen como opción aunque ninguna pieza los use). */
  slugs: Set<string>;
}

/** Construye el catálogo POR MARCA a partir de las filas de `/api/etiquetas-plantilla`. */
export function construirCatalogosEtiquetas(
  filas: { marca: string; slug: string; etiqueta: string }[],
): Map<string, CatalogoEtiquetas> {
  const out = new Map<string, CatalogoEtiquetas>();
  for (const f of filas) {
    const slug = normalizarCategoria(f.slug);
    let cat = out.get(f.marca);
    if (!cat) {
      cat = { rotulos: new Map(), slugs: new Set() };
      out.set(f.marca, cat);
    }
    cat.slugs.add(slug);
    const et = (f.etiqueta || "").trim();
    if (et) cat.rotulos.set(slug, et);
  }
  return out;
}

/** Slug del fallback: plantillas sin categoría (o con el legado "post"). */
export const CATEGORIA_GENERAL = "general";

/** Catálogo ordenado: primero noticias, luego deportes, "General" al final. */
export const CATEGORIAS_PLANTILLA: CategoriaPlantilla[] = [
  { slug: "ultima-hora", etiqueta: "Última hora" },
  { slug: "titular-del-dia", etiqueta: "Titular del día" },
  { slug: "cita-declaracion", etiqueta: "Cita / Declaración" },
  { slug: "dato-cifra", etiqueta: "Dato / Cifra" },
  { slug: "efemerides", etiqueta: "Efemérides" },
  { slug: "en-vivo", etiqueta: "En vivo" },
  { slug: "marcador", etiqueta: "Marcador" },
  { slug: "previa-partido", etiqueta: "Previa de partido" },
  { slug: "alineacion", etiqueta: "Alineación" },
  { slug: "tabla-medallero", etiqueta: "Tabla / Medallero" },
  { slug: "fichaje", etiqueta: "Fichaje" },
  { slug: "jugador-del-partido", etiqueta: "Jugador del partido" },
  { slug: "promo-programa", etiqueta: "Promo de programa" },
  { slug: CATEGORIA_GENERAL, etiqueta: "General" },
];

const _ETIQUETA_POR_SLUG = new Map(CATEGORIAS_PLANTILLA.map((c) => [c.slug, c.etiqueta]));
const _ORDEN_POR_SLUG = new Map(CATEGORIAS_PLANTILLA.map((c, i) => [c.slug, i]));

/** Quita acentos y baja a minúsculas (para slugs y para búsqueda acento-insensible). */
function _plano(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

/**
 * Normaliza cualquier texto de categoría al slug canónico: minúsculas, sin acentos, separadores a
 * guiones, máx 40. Vacío y el legado "post" caen a "general". MISMA regla que el backend.
 */
export function normalizarCategoria(valor?: string | null): string {
  const slug = _plano(valor ?? "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40)
    .replace(/-+$/g, "");
  if (!slug || slug === "post") return CATEGORIA_GENERAL;
  return slug;
}

/** Rótulo de un slug ya normalizado: override de la marca → catálogo estático → prettificado. */
function _rotulo(slug: string, cat?: CatalogoEtiquetas): string {
  const override = cat?.rotulos.get(slug);
  if (override) return override;
  const conocida = _ETIQUETA_POR_SLUG.get(slug);
  if (conocida) return conocida;
  const texto = slug.replace(/-/g, " ");
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

/**
 * Etiqueta legible de una categoría: el rótulo personalizado de la marca (`cat`) si lo hay, si no del
 * catálogo estático y, si es texto libre, prettificada.
 */
export function etiquetaCategoria(valor?: string | null, cat?: CatalogoEtiquetas): string {
  return _rotulo(normalizarCategoria(valor), cat);
}

/** Orden estable de slugs: catálogo primero (en su orden), texto libre después (alfabético). */
function _compararSlugs(a: string, b: string): number {
  const ia = _ORDEN_POR_SLUG.get(a);
  const ib = _ORDEN_POR_SLUG.get(b);
  if (ia !== undefined && ib !== undefined) return ia - ib;
  if (ia !== undefined) return -1;
  if (ib !== undefined) return 1;
  return a.localeCompare(b);
}

/** Slugs de categoría PRESENTES en la lista (normalizados, sin duplicados, en orden de catálogo). */
export function categoriasPresentes(plantillas: PlantillaDiseno[]): string[] {
  const vistos = new Set(plantillas.map((p) => normalizarCategoria(p.categoria)));
  return [...vistos].sort(_compararSlugs);
}

/**
 * Opciones del selector de etiqueta: catálogo + las etiquetas de texto libre que el equipo ya creó
 * en otras piezas (`slugsPresentes`) + `extraSlug` opcional (la etiqueta de la pieza actual, por si
 * no estuviera en los datos cargados). Deduplicado por slug y ordenado: catálogo primero, texto
 * libre después (alfabético). Sin esto, una etiqueta creada en una pieza no se podría asignar a otra.
 */
export function opcionesCategoria(
  slugsPresentes: string[],
  extraSlug?: string | null,
  cat?: CatalogoEtiquetas,
): CategoriaPlantilla[] {
  // Con catálogo de marca, la BASE son SUS etiquetas (gestionadas + presentes, ya reunidas por el
  // llamante en `cat.slugs`): así una marca solo ve sus categorías, no la lista global ni las de otra
  // marca. En ese modo el `slugsPresentes` (de TODA la galería, multi-marca) se ignora. Sin catálogo
  // se mantiene el comportamiento histórico (catálogo estático + presentes). «General» siempre.
  const slugs = cat ? new Set([...cat.slugs, CATEGORIA_GENERAL]) : new Set(CATEGORIAS_PLANTILLA.map((c) => c.slug));
  if (!cat) for (const s of slugsPresentes) slugs.add(normalizarCategoria(s));
  if (extraSlug) slugs.add(normalizarCategoria(extraSlug));
  return [...slugs]
    .sort(_compararSlugs)
    .map((slug) => ({ slug, etiqueta: _rotulo(slug, cat) }));
}

/** Agrupa por categoría (normalizada), en orden de catálogo. Rótulo según el catálogo de marca (`cat`). */
export function agruparPorCategoria(
  plantillas: PlantillaDiseno[],
  cat?: CatalogoEtiquetas,
): { slug: string; etiqueta: string; plantillas: PlantillaDiseno[] }[] {
  const grupos = new Map<string, PlantillaDiseno[]>();
  for (const p of plantillas) {
    const slug = normalizarCategoria(p.categoria);
    const arr = grupos.get(slug);
    if (arr) arr.push(p);
    else grupos.set(slug, [p]);
  }
  return [...grupos.keys()].sort(_compararSlugs).map((slug) => ({
    slug,
    etiqueta: _rotulo(slug, cat),
    plantillas: grupos.get(slug) ?? [],
  }));
}

/** ¿La plantilla coincide con la búsqueda? Por nombre y por categoría (rótulo de marca), acento-insensible. */
export function coincideBusqueda(p: PlantillaDiseno, q: string, cat?: CatalogoEtiquetas): boolean {
  const nq = _plano(q.trim());
  if (!nq) return true;
  if (_plano(p.nombre || "").includes(nq)) return true;
  if (!/[a-z0-9]/.test(nq)) return false;
  const slug = normalizarCategoria(p.categoria);
  return slug.includes(normalizarCategoria(q)) || _plano(_rotulo(slug, cat)).includes(nq);
}
