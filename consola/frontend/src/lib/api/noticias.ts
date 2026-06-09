// Fragmento del cliente API: dominio «noticias». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  Historia,
  RespuestaHistorias,
  RespuestaNoticias,
  ResumenCobertura,
  SaludCobertura,
} from "@/types";

export const apiNoticias = {
  // --- Motor de ingesta persistente (Ola A): archivo a nivel de artículo ---
  // Contrato: docs/maquina-contenido/A-motor-ingesta.md
  noticias: {
    /**
     * Lista el archivo de noticias ingeridas, newest-first (`capturado_en` desc).
     * `marca` = '' / ausente → todas (admin); en caso contrario filtra por marca.
     * `estado` = 'nuevo' | 'usado' | 'descartado' | ausente → todos.
     * `desde` es una fecha ISO (YYYY-MM-DD) de corte mínimo de `capturado_en`.
     * `q` es búsqueda libre sobre título.
     * `limit`/`offset` para paginación.
     */
    listar: (
      params: {
        marca?: string;
        desde?: string;
        q?: string;
        estado?: string;
        limit?: number;
        offset?: number;
      } = {},
      signal?: AbortSignal,
    ) =>
      peticion<RespuestaNoticias>(
        `/noticias${query({
          marca: params.marca,
          desde: params.desde,
          q: params.q,
          estado: params.estado,
          limit: params.limit != null ? String(params.limit) : undefined,
          offset: params.offset != null ? String(params.offset) : undefined,
        })}`,
        { signal },
      ),

    /**
     * Lleva una noticia al tablero como pieza de contenido.
     * `redes` y `generar` son opcionales (igual que `insumos.usarItem`).
     * Marca `estado=usado` y guarda el `contenido_id`.
     * POST /api/noticias/{id}/usar
     */
    usar: (
      id: string,
      body: { redes?: string[]; generar?: boolean } = {},
    ) =>
      peticion<{ ok: boolean; contenido_id: string }>(
        `/noticias/${encodeURIComponent(id)}/usar`,
        { metodo: "POST", json: body, muestrear: false },
      ),

    /**
     * Descarta una noticia (estado=descartado). No se borra del archivo.
     * POST /api/noticias/{id}/descartar
     */
    descartar: (id: string) =>
      peticion<{ ok: boolean }>(
        `/noticias/${encodeURIComponent(id)}/descartar`,
        { metodo: "POST", muestrear: false },
      ),

    /**
     * Resumen básico de salud del motor de ingesta:
     * nº feeds activos/con error, items últimas 24h por categoría, último sondeo.
     * GET /api/noticias/cobertura
     */
    cobertura: (signal?: AbortSignal) =>
      peticion<ResumenCobertura>("/noticias/cobertura", { signal }),

    // --- Ola B: clusters de historias ---

    /**
     * Lista los clusters de historias (misma noticia, múltiples fuentes).
     * Orden: score desc. marca-aware.
     * GET /api/noticias/historias
     */
    historias: (
      params: {
        marca?: string;
        desde?: string;
        estado?: string;
        limit?: number;
        offset?: number;
      } = {},
      signal?: AbortSignal,
    ) =>
      peticion<RespuestaHistorias>(
        `/noticias/historias${query({
          marca: params.marca,
          desde: params.desde,
          estado: params.estado,
          limit: params.limit != null ? String(params.limit) : undefined,
          offset: params.offset != null ? String(params.offset) : undefined,
        })}`,
        { signal },
      ),

    /**
     * Detalle de un cluster: la historia + sus artículos corroborantes.
     * GET /api/noticias/historias/{id}
     */
    historia: (id: string, signal?: AbortSignal) =>
      peticion<{ historia: Historia; items: unknown[] }>(
        `/noticias/historias/${encodeURIComponent(id)}`,
        { signal },
      ),

    /**
     * Lleva una historia al tablero como pieza de contenido.
     * Marca el cluster + sus ítems como `usado`.
     * POST /api/noticias/historias/{id}/usar
     */
    usarHistoria: (
      id: string,
      body: { redes?: string[]; generar?: boolean } = {},
    ) =>
      peticion<{ ok: boolean; contenido_id: string }>(
        `/noticias/historias/${encodeURIComponent(id)}/usar`,
        { metodo: "POST", json: body, muestrear: false },
      ),

    /**
     * Descarta una historia (estado=descartado). No se borra del archivo.
     * POST /api/noticias/historias/{id}/descartar
     */
    descartarHistoria: (id: string) =>
      peticion<{ ok: boolean }>(
        `/noticias/historias/${encodeURIComponent(id)}/descartar`,
        { metodo: "POST", muestrear: false },
      ),

    /**
     * Descarta VARIAS historias de una (papelera estilo correo: seleccionar + descartar).
     * POST /api/noticias/historias/descartar-lote  →  { descartadas: n }
     */
    descartarHistoriasLote: (ids: string[]) =>
      peticion<{ descartadas: number }>(
        `/noticias/historias/descartar-lote`,
        { metodo: "POST", json: { ids }, muestrear: false },
      ),

    /**
     * BORRA HARD (irreversible) varias historias + sus artículos del archivo.
     * POST /api/noticias/historias/borrar-lote  →  { borradas: n }
     */
    borrarHistoriasLote: (ids: string[]) =>
      peticion<{ borradas: number }>(
        `/noticias/historias/borrar-lote`,
        { metodo: "POST", json: { ids }, muestrear: false },
      ),

    /**
     * VACÍA (hard, irreversible) el pool — "dejar a 0". Con `marca` solo esa marca; con
     * `estado` limita al filtro de la vista.
     * POST /api/noticias/historias/borrar-todo  →  { borradas: n }
     */
    borrarTodasHistorias: (body: { marca?: string; estado?: string } = {}) =>
      peticion<{ borradas: number }>(
        `/noticias/historias/borrar-todo`,
        { metodo: "POST", json: body, muestrear: false },
      ),

    // --- Ola D: salud de fuentes ---

    /**
     * Salud detallada del motor de ingesta: resumen + detalle por feed.
     * Marca-aware (?marca=).
     * GET /api/noticias/salud
     */
    salud: (marca?: string, signal?: AbortSignal) =>
      peticion<SaludCobertura>(
        `/noticias/salud${query({ marca })}`,
        { signal },
      ),
  },

};
