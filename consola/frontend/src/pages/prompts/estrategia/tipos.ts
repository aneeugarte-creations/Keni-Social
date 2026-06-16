/**
 * Tipos del rediseño "Estrategia de marca" de la Prompts.
 *
 * Contrato con `GET /api/prompts/estrategia?marca=` (backend EN CONSTRUCCIÓN en paralelo):
 * todo es OPCIONAL/defensivo — el componente normaliza (`datos.ts`) y degrada con
 * elegancia si el endpoint aún no responde (fallback desde `/api/prompts` + `/validacion`).
 */
import type { ProduccionTexto } from "@/types";

/** Un pilar (o doc extra) tal y como lo manda `GET /api/prompts/estrategia`. */
export interface PilarEstrategiaApi {
  /** Clase editorial: marca | voz | tropicalizacion | plataforma | reglas (o "" en extras). */
  clase?: string;
  /** Título del documento (humano). */
  titulo?: string;
  /** Id del documento, o `null` si el pilar aún no tiene documento. */
  doc_id?: string | null;
  /** `true` si el pilar no tiene contenido útil. */
  vacio?: boolean;
  /** `true` si es una capa GLOBAL compartida entre marcas. */
  global?: boolean;
  produccion?: ProduccionTexto | null;
  sha_actual?: string | null;
  sin_publicar?: boolean;
  actualizado?: string;
  /** Campos extra que el backend PUEDE añadir (no exigidos por el contrato). */
  cuerpo?: string;
  extracto?: string;
  descripcion?: string;
}

export interface CompletitudEstrategia {
  completa?: boolean;
  faltan?: string[];
  recomendacion?: string;
}

/** `GET /api/prompts/estrategia?marca=` (forma completa; todo defensivo). */
export interface RespuestaEstrategia {
  marca?: string;
  completitud?: CompletitudEstrategia;
  pilares?: PilarEstrategiaApi[];
  extras?: PilarEstrategiaApi[];
  orden_inyeccion?: string[];
}

/** Un pilar ya NORMALIZADO para la UI (siempre los 5, en orden fijo). */
export interface PilarNormalizado {
  clase: string;
  /** Título humano fijo del pilar (Identidad de marca, Voz, …). */
  titulo: string;
  /** Título real del documento (si existe; para chips y tooltips). */
  tituloDoc: string;
  docId: string | null;
  vacio: boolean;
  global: boolean;
  publicado: boolean;
  sinPublicar: boolean;
  actualizado: string;
  /** Primeras líneas del contenido en texto plano ("" si no hay). */
  extracto: string;
}

/** Estado completo de la estrategia de una marca, listo para pintar. */
export interface EstrategiaNormalizada {
  completa: boolean;
  faltan: string[];
  recomendacion: string;
  /** Pilares obligatorios CON contenido (numerador del anillo). */
  cubiertos: number;
  /** Pilares obligatorios totales (denominador; 4). */
  total: number;
  /** SIEMPRE los 5 pilares, en el orden fijo de `CLASES_PILAR`. */
  pilares: PilarNormalizado[];
  /** Documentos de apoyo (p. ej. patrones medidos). */
  extras: PilarNormalizado[];
  /** Orden real de inyección: doc_ids con etiqueta legible. */
  orden: { docId: string; etiqueta: string }[];
}
