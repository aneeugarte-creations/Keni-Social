/**
 * Utilidades de formato es-MX compartidas por toda la consola.
 *
 * Centraliza el formateo de números, porcentajes, variaciones, costes y
 * duraciones para que todas las páginas hablen el mismo idioma visual:
 * separadores de miles mexicanos y abreviaturas legibles (mil / M) en KPIs,
 * ejes de gráficas, tablas y tooltips.
 *
 * Antes estas funciones vivían en `pages/metricas/formato.ts`; ahora ese
 * módulo re-exporta desde aquí para mantener la compatibilidad de importes
 * existentes mientras se migra progresivamente al path canónico `@/lib/formato`.
 */

/** Formateador base es-MX con separador de miles (ej. 1234567 → "1,234,567"). */
const nfEntero = new Intl.NumberFormat("es-MX", { maximumFractionDigits: 0 });

/** Formateador compacto es-MX (ej. 221621046 → "221.6 M"). */
const nfCompacto = new Intl.NumberFormat("es-MX", {
  notation: "compact",
  maximumFractionDigits: 1,
});

/**
 * Número compacto y legible. Para valores < 1000 muestra el entero tal cual;
 * a partir de ahí abrevia con "mil" / "M" en español de México.
 * Ej.: 221621046 → "221.6 M", 1830 → "1.8 mil", 842 → "842".
 */
export function numeroCompacto(valor: number): string {
  if (!Number.isFinite(valor)) return "—";
  if (Math.abs(valor) < 1000) return nfEntero.format(valor);
  return nfCompacto.format(valor);
}

/** Número completo con separadores de miles (para tablas y tooltips). */
export function numeroCompleto(valor: number): string {
  if (!Number.isFinite(valor)) return "—";
  return nfEntero.format(valor);
}

/**
 * Porcentaje con un decimal y el símbolo "%". El backend ya entrega el valor en
 * puntos porcentuales (ej. 1.8 → "1.8 %"), así que no multiplicamos por 100.
 */
export function porcentaje(valor: number): string {
  if (!Number.isFinite(valor)) return "—";
  return `${valor.toLocaleString("es-MX", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} %`;
}

/**
 * Variación porcentual con signo explícito (+/−) y un decimal.
 * Ej.: 12.345 → "+12.3 %", -4 → "−4.0 %", 0 → "0.0 %".
 */
export function variacion(valor: number): string {
  if (!Number.isFinite(valor)) return "—";
  const abs = Math.abs(valor).toLocaleString("es-MX", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  const signo = valor > 0 ? "+" : valor < 0 ? "−" : "";
  return `${signo}${abs} %`;
}

/**
 * Coste en dólares estadounidenses (es-MX). Usa más decimales para importes
 * pequeños típicos de un run para no perder precisión visual.
 * Ej.: 0.0381 → "$0.038", 1.5 → "$1.50", 0 → "$0.00".
 */
export function costeUsd(valor: number): string {
  if (!Number.isFinite(valor)) return "—";
  // Importes muy pequeños (< $0.10): 3 decimales; el resto, 2.
  const decimales = Math.abs(valor) > 0 && Math.abs(valor) < 0.1 ? 3 : 2;
  return valor.toLocaleString("es-MX", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  });
}

/**
 * Duración legible a partir de milisegundos (es-MX).
 * Ej.: 850 → "0.9 s", 4200 → "4.2 s", 95000 → "1 min 35 s".
 */
export function duracion(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const segundosTotales = ms / 1000;
  if (segundosTotales < 60) {
    return `${segundosTotales.toLocaleString("es-MX", {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    })} s`;
  }
  const minutos = Math.floor(segundosTotales / 60);
  const segundos = Math.round(segundosTotales % 60);
  return `${minutos} min ${segundos} s`;
}

/**
 * Duración legible de un tiempo de visualización dado en SEGUNDOS (es-MX).
 * A diferencia de `duracion` (que recibe ms y abrevia siempre con decimal), aquí
 * el dato ya viene en segundos enteros y queremos la lectura compacta típica de
 * métricas de vídeo: "Xs" hasta el minuto, "Xm Ys" a partir de ahí.
 * Ej.: 12 → "12s", 95 → "1m 35s", 60 → "1m". Negativo/no finito → "—".
 */
export function tiempoVis(segundos: number): string {
  if (!Number.isFinite(segundos) || segundos < 0) return "—";
  const total = Math.round(segundos);
  if (total < 60) return `${total}s`;
  const min = Math.floor(total / 60);
  const seg = total % 60;
  return seg === 0 ? `${min}m` : `${min}m ${seg}s`;
}

/**
 * Conteo con sustantivo pluralizado (es-MX). Evita los feos "1 comentario(s)".
 * Ej.: `plural(1, "comentario")` → "1 comentario"; `plural(3, "comentario")` →
 * "3 comentarios". El plural por defecto es `singular + "s"`; para irregulares,
 * pásalo explícito: `plural(2, "pieza", "piezas")`.
 */
export function plural(n: number, singular: string, formaPlural?: string): string {
  const palabra = n === 1 ? singular : (formaPlural ?? `${singular}s`);
  return `${n} ${palabra}`;
}

// ---------------------------------------------------------------------------
// Etiquetas legibles de marca / red / formato
//
// El backend emite ids crudos (`claro_sports`, `instagram`, `feed_image`) en las
// vistas de métricas. Estos helpers los traducen a su forma legible de marca para
// que la UI no muestre el id técnico. Degradación honesta: si no sabemos el nombre,
// capitalizamos el id (nunca inventamos un nombre distinto del que viene).
// ---------------------------------------------------------------------------

/** Capitaliza la primera letra de un id; "" → "—". */
function capitalizar(id: string): string {
  return id ? id.charAt(0).toUpperCase() + id.slice(1) : "—";
}

/**
 * Nombre legible de una red a partir de su id de plataforma (`facebook`,
 * `instagram`, `tiktok`, …). `twitter` se normaliza a "X". Para ids desconocidos,
 * capitaliza la primera letra (degradación honesta). "" → "—".
 */
const NOMBRES_RED: Record<string, string> = {
  facebook: "Facebook",
  instagram: "Instagram",
  tiktok: "TikTok",
  youtube: "YouTube",
  x: "X",
  twitter: "X",
  linkedin: "LinkedIn",
  threads: "Threads",
  bluesky: "Bluesky",
};

export function nombreRed(red: string): string {
  if (!red) return "—";
  return NOMBRES_RED[red.toLowerCase()] ?? capitalizar(red);
}

/**
 * Nombre legible de un formato de pieza a partir de su id crudo. Maneja el prefijo
 * `feed_` de Meta (feed_image → "Feed image", feed_carousel_album → "Carrusel",
 * feed_video → "Vídeo", feed_reel → "Reel") y los ids genéricos (reel, foto/photo,
 * carrusel/carousel, video, link, texto/text). `null`/"" → "Sin formato"; un id
 * desconocido se capitaliza (degradación honesta).
 */
const NOMBRES_FORMATO: Record<string, string> = {
  feed_image: "Feed image",
  feed_carousel_album: "Carrusel",
  feed_video: "Vídeo",
  feed_reel: "Reel",
  reel: "Reel",
  foto: "Foto",
  photo: "Foto",
  carrusel: "Carrusel",
  carousel: "Carrusel",
  video: "Vídeo",
  link: "Enlace",
  texto: "Texto",
  text: "Texto",
};

export function nombreFormato(f: string | null): string {
  if (!f || !f.trim()) return "Sin formato";
  const clave = f.trim().toLowerCase();
  return NOMBRES_FORMATO[clave] ?? capitalizar(f.trim());
}

/**
 * Nombre legible de una marca a partir de su id y el catálogo de opciones
 * (`opciones.marcas` = `[{ id, nombre }]`). Si el id no está en el catálogo,
 * devuelve el id tal cual (degradación honesta: nunca inventa un nombre). Acepta
 * el catálogo como lista `{id, nombre}` o como `Map<id, nombre>` ya resuelto.
 * "" → "—".
 */
export function nombreMarca(
  id: string,
  marcas: ReadonlyArray<{ id: string; nombre: string }> | ReadonlyMap<string, string>,
): string {
  if (!id) return "—";
  if (marcas instanceof Map) return marcas.get(id) ?? id;
  const encontrada = (marcas as ReadonlyArray<{ id: string; nombre: string }>).find(
    (m) => m.id === id,
  );
  return encontrada?.nombre ?? id;
}
