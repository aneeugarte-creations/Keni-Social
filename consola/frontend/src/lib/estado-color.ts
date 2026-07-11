/**
 * Fuente CENTRAL de color por estado de cobertura (taxonomía estilo Planday).
 *
 * El color de cada estado/fase de un evento se pintaba INLINE en varios sitios del cockpit
 * (`SemaforoCobertura` en `pages/tareas/tarjetas.tsx`, los cortes de `pages/tareas/KpiCobertura.tsx`).
 * Este módulo unifica esas clases Tailwind en un único mapa tipado para que todos los componentes
 * hablen el MISMO lenguaje de color y la taxonomía evolucione en un solo sitio.
 *
 * TAXONOMÍA (color SOLO con significado, SIEMPRE acompañado de texto/icono; outline gris por defecto):
 *  - AMARILLO (yellow) → `sin-cubrir`: hueco real, pide decisión.
 *  - ÁMBAR (amber)     → `empieza-en`: PRE-LIVE, el saque está cerca → a moverse.
 *  - VERDE  → `en-vivo` / cobertura tomada / terminado-OK: en marcha o resuelto.
 *  - GRIS   (`text-muted-foreground` / slate) → `programado`: aún falta, neutro.
 *  - OUTLINE gris → estado por defecto (borrador), sin color de significado.
 *
 * Las clases aquí son EXACTAMENTE las que ya se usaban inline (incluye `dark:`): este módulo es
 * centralización, NO un cambio visible. Importa los tipos canónicos de `@/lib/cobertura`.
 */
import type { EstadoCobertura, Semaforo } from "@/lib/cobertura";

/**
 * Clases de color de una FASE del semáforo: badge (borde+texto), punto e icono. Son exactamente las
 * que pintaba `SemaforoCobertura` inline (con `dark:`).
 */
export interface EstiloSemaforo {
  /** Clases del Badge outline (borde + texto, con `dark:`). */
  badge: string;
  /** Clases del punto `•` (fondo). */
  dot: string;
  /** Clases del icono suelto (Check del semáforo terminado, en su variante compacta). */
  icon: string;
}

/**
 * Estilo por FASE temporal del semáforo (`Semaforo`). Replica `SemaforoCobertura`:
 *  - `en-vivo`   → verde, punto verde.
 *  - `empieza-en`→ ámbar, punto ámbar.
 *  - `terminado` → verde (resuelto), Check con su color en la variante compacta.
 *  - `programado`→ gris/muted, punto slate.
 */
export const SEMAFORO_ESTILO: Record<Semaforo, EstiloSemaforo> = {
  "en-vivo": {
    badge: "border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
    dot: "bg-emerald-500",
    icon: "text-emerald-600 dark:text-emerald-400",
  },
  "empieza-en": {
    badge: "border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-300",
    dot: "bg-amber-500",
    icon: "text-amber-600 dark:text-amber-400",
  },
  terminado: {
    badge: "border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
    dot: "bg-emerald-500",
    icon: "text-emerald-600 dark:text-emerald-400",
  },
  programado: {
    badge: "text-muted-foreground",
    dot: "bg-slate-400 dark:bg-slate-500",
    icon: "text-muted-foreground",
  },
};

/**
 * Texto de color por ESTADO de cobertura (`EstadoCobertura`), para los CORTES del KPI (solo texto,
 * con `dark:`). Replica `KpiCobertura`:
 *  - `sin-cubrir`    → amarillo (hueco real, pide decisión).
 *  - `cubierto-turno`/`cogido` → verde (resuelto / en marcha; el KPI los agrega como «cubiertos»).
 */
export const COBERTURA_TEXTO: Record<EstadoCobertura, string> = {
  "sin-cubrir": "text-yellow-700 dark:text-yellow-300",
  "cubierto-turno": "text-emerald-700 dark:text-emerald-300",
  cogido: "text-emerald-700 dark:text-emerald-300",
};

/**
 * Badge de TINTE (fondo suave + texto, receta 700/300 del sistema de diseño) por estado de
 * cobertura, para el chip del calendario de la rota. Es la píldora compacta de cobertura del
 * chip de evento:
 *  - `cubierto-turno`/`cogido` → verde («Cubierto · <nombres>»: lo cubre quien está de turno).
 *  - `sin-cubrir`              → AMARILLO («Sin cubrir»: hueco real). Mismo amarillo (con
 *    significado «pide decisión») que el KPI: el estado «sin cubrir» habla UN solo color en
 *    toda la app. Es `yellow`, NO `amber`: el ámbar queda reservado a `empieza-en` (PRE-LIVE),
 *    un eje distinto (tiempo, no cobertura).
 */
export const COBERTURA_BADGE: Record<EstadoCobertura, string> = {
  "cubierto-turno": "border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  cogido: "border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  "sin-cubrir": "border-transparent bg-yellow-500/15 text-yellow-700 dark:text-yellow-300",
};

// FASE 2 (preparado, SIN consumidor todavía — no se añaden entradas para no dejar código muerto que
// moleste a eslint): cuando el cockpit muestre el estado de PUBLICACIÓN de una pieza, esta taxonomía
// crece con:
//   borrador:  outline gris (sin color de significado) → estado por defecto editable.
//   publicado: verde/check → ya salió.
// Hasta que exista un consumidor real (con su test que fije las clases), no se añaden.
