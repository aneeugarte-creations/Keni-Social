import type { UsoCuenta } from "@/hooks/use-uso-cuenta";

/**
 * Burn rate del uso de una cuenta de Claude: predice qué límite DURO va a BLOQUEAR antes.
 *
 * El indicador colapsado pinta el límite que primero tocará el 100 %, no el más alto ahora: una
 * ventana puede ir alta pero resetear antes de llenarse (no bloquea), y otra más baja pero con un
 * ritmo que la lleva al tope antes del reset (esa es la que de verdad para la generación).
 */

/** Ventana de uso que puede BLOQUEAR la generación (límite duro de Claude). */
export type LimiteUso = "sesion" | "semana" | "sonnet";

export interface PrediccionUso {
  /** Cuál de las ventanas llegará antes al 100 %. */
  limite: LimiteUso;
  /** Rótulo legible ("5h" | "Semana" | "Sonnet"). */
  etiqueta: string;
  /** % actual de esa ventana (0–100). */
  pct: number;
  /** Horas estimadas hasta el 100 % al ritmo medio desde el inicio de la ventana (0 = ya al tope). */
  horas: number;
}

const HORA_MS = 3_600_000;

/** Duración de cada ventana (horas): sesión 5 h, semanal (all-models y Sonnet) 7 días. */
const VENTANA_HORAS: Record<LimiteUso, number> = {
  sesion: 5,
  semana: 7 * 24,
  sonnet: 7 * 24,
};

const ETIQUETA: Record<LimiteUso, string> = {
  sesion: "5h",
  semana: "Semana",
  sonnet: "Sonnet",
};

interface Candidata {
  limite: LimiteUso;
  pct: number | null;
  resetIso: string | null;
}

/**
 * El límite de Claude que PRIMERO va a bloquear, por burn rate (time-to-100 %), o `null` si
 * ninguna ventana tiene datos suficientes (sin reset o sin %).
 *
 * Para cada ventana dura estima el ritmo medio desde el inicio de su ventana (`reset − duración`)
 * y proyecta cuándo tocará el 100 %; descarta la que resetee ANTES de llenarse. Devuelve la de
 * menor tiempo (desempate: mayor %, luego orden sesión < semana < Sonnet). Sonnet comparte el
 * reset semanal (el muestreo solo guarda el de la semana). `ahoraMs` es inyectable para tests.
 */
export function limiteMasUrgente(uso: UsoCuenta, ahoraMs: number = Date.now()): PrediccionUso | null {
  const candidatas: Candidata[] = [
    { limite: "sesion", pct: uso.sesion_5h_pct, resetIso: uso.reset_sesion_iso },
    { limite: "semana", pct: uso.semana_pct, resetIso: uso.reset_semana_iso },
    { limite: "sonnet", pct: uso.sonnet_pct, resetIso: uso.reset_semana_iso },
  ];

  let mejor: PrediccionUso | null = null;
  for (const c of candidatas) {
    if (c.pct == null || c.resetIso == null) continue;
    const resetMs = Date.parse(c.resetIso);
    if (Number.isNaN(resetMs)) continue;
    const ventanaMs = VENTANA_HORAS[c.limite] * HORA_MS;
    const transcurridoMs = ahoraMs - (resetMs - ventanaMs);
    const horasHastaReset = (resetMs - ahoraMs) / HORA_MS;
    if (transcurridoMs <= 0 || horasHastaReset <= 0) continue; // recién reseteada / dato viejo

    let horas: number;
    if (c.pct >= 100) {
      horas = 0; // ya al tope: bloquea ya
    } else if (c.pct <= 0) {
      continue; // sin consumo => no se llena
    } else {
      const ritmoPorHora = c.pct / (transcurridoMs / HORA_MS);
      horas = (100 - c.pct) / ritmoPorHora;
      if (horas > horasHastaReset) continue; // resetea antes de llenarse => no bloquea
    }

    if (mejor == null || horas < mejor.horas || (horas === mejor.horas && c.pct > mejor.pct)) {
      mejor = { limite: c.limite, etiqueta: ETIQUETA[c.limite], pct: c.pct, horas };
    }
  }
  return mejor;
}
