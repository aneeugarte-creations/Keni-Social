/**
 * Cliente del endpoint NUEVO `GET /api/texto/estrategia?marca=` (backend en construcción
 * en paralelo). Vive aquí —no en `lib/api/texto.ts`— para que el rediseño sea autónomo:
 * cuando el contrato se asiente puede promoverse al cliente compartido.
 */
import { peticion, query } from "@/lib/api/_core";

import type { RespuestaEstrategia } from "./tipos";

/** Prefijo de la clave de query (invalida la estrategia de TODAS las marcas). */
export const claveEstrategiaBase = ["texto-estrategia"] as const;

/** Clave de query del endpoint nuevo (por marca). */
export const claveEstrategia = (marca: string) => [...claveEstrategiaBase, marca] as const;

export const apiEstrategia = {
  estrategia: (marca: string, signal?: AbortSignal) =>
    peticion<RespuestaEstrategia>(`/texto/estrategia${query({ marca })}`, { signal }),
};
