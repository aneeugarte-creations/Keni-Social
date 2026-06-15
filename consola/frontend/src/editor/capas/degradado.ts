// Geometría y paradas de un degradado para Konva. PURO (sin Konva): se testea sin montar el
// canvas. Compartido por el render de capas (`CapaNodo`) y el del fondo (`FondoNodo`). Mismas
// fórmula/convención que `dibujar.mjs` del servidor, de modo que la previa del editor y el
// export coinciden.

import type { RellenoDegradado } from "../documento";

// Vertical (↓): el default histórico y el respaldo cuando el ángulo no es usable.
const ANGULO_DEFECTO = 180;
// Color de respaldo para una parada sin color: `addColorStop(pos, undefined)` LANZA y borra el
// relleno, así que preferimos un degradado feo (negro) a uno invisible.
const COLOR_RESPALDO = "#000000";

// Puntos inicial/final de un degradado lineal sobre una caja w×h según `angulo` (grados), con la
// MISMA convención que `gradienteLineal` de dibujar.mjs: 0°=↑, 90°=→, 180°=↓ (vertical), 270°=←.
// Konva usa puntos relativos al nodo (origen 0,0), así que el centro de la caja es (w/2,h/2).
export function puntosGradiente(w: number, h: number, angulo: number = ANGULO_DEFECTO) {
  // DEFENSA: un `angulo` NO finito (NaN de un valor no numérico, Infinity de "1e999", o un dato
  // malformado de una plantilla inicializada en la BD / doc auto-producido o importado que NO pasó por
  // el control `Num`) daría start/end {x:NaN,y:NaN}; Konva los pasa a `ctx.createLinearGradient(NaN…)`,
  // que por la spec del canvas LANZA y deja el relleno —y a veces las capas hermanas del Layer— SIN
  // PINTAR: el degradado "desaparece y no se sabe a dónde va". Caemos al vertical 180 (igual que el
  // `?? 180` del render del servidor), nunca a NaN. El default de param solo cubre `undefined`.
  const n = angulo == null ? ANGULO_DEFECTO : Number(angulo);
  const ang = Number.isFinite(n) ? n : ANGULO_DEFECTO;
  const a = (ang * Math.PI) / 180;
  const ux = Math.sin(a), uy = -Math.cos(a);
  const cx = w / 2, cy = h / 2;
  const semi = (Math.abs(w * ux) + Math.abs(h * uy)) / 2;
  return {
    start: { x: cx - ux * semi, y: cy - uy * semi },
    end: { x: cx + ux * semi, y: cy + uy * semi },
  };
}

// Paradas [pos, color, pos, color, …] de un degradado para Konva (`fill*GradientColorStops`).
// Usa `stops` (multi-parada) si vienen ≥2 VÁLIDAS, si no desde/hasta (espejo de `paradasDegradado`
// del render). DEFENSA: descarta paradas sin color, normaliza `pos` no finito a 0 y respalda
// desde/hasta ausentes — cualquiera de esos tres haría que `addColorStop` LANCE y borre el relleno.
export function colorStopsKonva(deg: RellenoDegradado): (number | string)[] {
  const validas = Array.isArray(deg.stops)
    ? deg.stops.filter((s): s is { pos: number; color: string } => !!s && typeof s.color === "string")
    : null;
  if (validas && validas.length >= 2) {
    return validas
      .map((s) => ({ pos: Math.max(0, Math.min(1, Number.isFinite(s.pos) ? s.pos : 0)), color: s.color }))
      .sort((a, b) => a.pos - b.pos)
      .flatMap((s) => [s.pos, s.color]);
  }
  return [0, deg.desde || COLOR_RESPALDO, 1, deg.hasta || COLOR_RESPALDO];
}
