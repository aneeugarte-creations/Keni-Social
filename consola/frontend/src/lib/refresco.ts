/**
 * Cadencias de REFRESCO únicas de toda la consola (refetchInterval de react-query).
 *
 *  - VIVO (3 s): estado operacional que cambia en segundos y se mira en directo
 *    (cola de generación del Monitor).
 *  - PANEL (8 s): salud de paneles (recursos, daemons, síntesis de cola en Sistema).
 *  - DETALLE (15 s): detalle de una entidad en curso (run de pipeline abierta).
 *  - SERIE (30 s): listas e históricos (series por día, lista de pipelines).
 *  - LENTO (32 s): lo que cambia como mucho unas veces al día (backups, S3).
 */

export const INTERVALO_VIVO_MS = 3_000;
export const INTERVALO_PANEL_MS = 8_000;
export const INTERVALO_DETALLE_MS = 15_000;
export const INTERVALO_SERIE_MS = 30_000;
export const INTERVALO_LENTO_MS = 32_000;
