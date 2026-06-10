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

/** Etiqueta legible de una categoría: del catálogo o, si es texto libre, prettificada. */
export function etiquetaCategoria(valor?: string | null): string {
  const slug = normalizarCategoria(valor);
  const conocida = _ETIQUETA_POR_SLUG.get(slug);
  if (conocida) return conocida;
  const texto = slug.replace(/-/g, " ");
  return texto.charAt(0).toUpperCase() + texto.slice(1);
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

/** Agrupa por categoría (normalizada), en orden de catálogo. */
export function agruparPorCategoria(
  plantillas: PlantillaDiseno[],
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
    etiqueta: etiquetaCategoria(slug),
    plantillas: grupos.get(slug) ?? [],
  }));
}

/** ¿La plantilla coincide con la búsqueda? Por nombre y por categoría, acento-insensible. */
export function coincideBusqueda(p: PlantillaDiseno, q: string): boolean {
  const nq = _plano(q.trim());
  if (!nq) return true;
  if (_plano(p.nombre || "").includes(nq)) return true;
  if (!/[a-z0-9]/.test(nq)) return false;
  const slug = normalizarCategoria(p.categoria);
  return slug.includes(normalizarCategoria(q)) || _plano(etiquetaCategoria(slug)).includes(nq);
}
