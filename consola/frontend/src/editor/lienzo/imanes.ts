// Cálculo PURO del imán (smart guides) del arrastre de capas: snap a bordes/centros (lienzo,
// márgenes y otras capas), distancia entre cajas para las etiquetas, y ESPACIADO IGUAL estilo
// Canva (snap a la posición donde la separación con la vecina iguala la de otro par alineado).
// Sin Konva ni React: todo en píxeles del DOCUMENTO, testeable en aislamiento.

// Umbral del imán en píxeles de PANTALLA (constante a cualquier zoom): el consumidor lo convierte
// a px del documento dividiendo por la escala efectiva.
export const UMBRAL_IMAN_PANTALLA = 6;

export interface CajaIman {
  x: number;
  y: number;
  w: number;
  h: number;
}

// Objetivo de snap de UN eje: la posición de la línea y, si proviene de una capa, su caja (para
// poder etiquetar la distancia con ella).
export interface ObjetivoIman {
  t: number;
  ref?: CajaIman;
}

// Caja ENVOLVENTE de un conjunto de cajas: el rect que se imanta al arrastrar una MULTI-selección
// (sus bordes y centro contra página, márgenes y capas no seleccionadas; el ajuste se reparte como
// delta a todas las capas del grupo). Lista vacía => null.
export function cajaEnvolvente(cajas: CajaIman[]): CajaIman | null {
  if (cajas.length === 0) return null;
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const c of cajas) {
    x0 = Math.min(x0, c.x);
    y0 = Math.min(y0, c.y);
    x1 = Math.max(x1, c.x + c.w);
    y1 = Math.max(y1, c.y + c.h);
  }
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}

export interface SnapEje {
  pos: number; // nueva posición de la caja en el eje
  guia: number; // posición de la línea guía
  ref?: CajaIman; // caja con la que se alinea (si el objetivo era una capa)
}

// Snap de UN eje: prueba los 3 bordes propios (inicio/centro/fin) contra todos los objetivos y
// elige el ajuste MÁS CERCANO dentro del umbral (empate => el primero en orden de lista).
export function calcularImanEje(
  pos: number,
  tam: number,
  objetivos: ObjetivoIman[],
  umbral: number,
): SnapEje | null {
  const bordes = [pos, pos + tam / 2, pos + tam];
  let mejor: { delta: number; guia: number; ref?: CajaIman } | null = null;
  for (const b of bordes) {
    for (const o of objetivos) {
      const delta = o.t - b;
      if (Math.abs(delta) <= umbral && (!mejor || Math.abs(delta) < Math.abs(mejor.delta))) {
        mejor = { delta, guia: o.t, ref: o.ref };
      }
    }
  }
  return mejor ? { pos: pos + mejor.delta, guia: mejor.guia, ref: mejor.ref } : null;
}

// Separación entre dos cajas PERPENDICULAR al eje del snap: para una guía vertical (snap en `x`)
// la distancia que interesa etiquetar es el hueco VERTICAL entre las cajas alineadas, y viceversa.
// `centro` es el punto medio del hueco (para colocar la etiqueta). Si se solapan => null.
export function huecoPerpendicular(
  a: CajaIman,
  b: CajaIman,
  eje: "x" | "y",
): { gap: number; centro: number } | null {
  const a0 = eje === "x" ? a.y : a.x;
  const a1 = a0 + (eje === "x" ? a.h : a.w);
  const b0 = eje === "x" ? b.y : b.x;
  const b1 = b0 + (eje === "x" ? b.h : b.w);
  if (a1 < b0) return { gap: b0 - a1, centro: (a1 + b0) / 2 };
  if (b1 < a0) return { gap: a0 - b1, centro: (b1 + a0) / 2 };
  return null;
}

// Un hueco equidistante a dibujar: intervalo [desde, hasta] sobre el eje del movimiento, a la
// altura `perp` (centro del solape perpendicular entre las cajas que lo delimitan).
export interface SegmentoEspaciado {
  desde: number;
  hasta: number;
  perp: number;
}

export interface SnapEspaciado {
  pos: number; // posición de la caja arrastrada que iguala las separaciones
  gap: number; // tamaño (idéntico) de los huecos
  segmentos: SegmentoEspaciado[]; // los dos huecos iguales, para guías + etiquetas
}

// ESPACIADO IGUAL (estilo Canva) al arrastrar `caja` a lo largo de `eje` entre otras capas cuya
// proyección PERPENDICULAR se solapa con ella (misma "fila"/"columna"). Detecta dos patrones:
//   · CENTRADA entre sus dos vecinas: hueco anterior == hueco posterior.
//   · CADENA: replica el hueco que la vecina inmediata guarda con la siguiente capa de la fila
//     (… A ─g─ B ─g─ caja …), hacia atrás y hacia delante.
// Devuelve la opción que requiere el ajuste más pequeño dentro del umbral, o null.
export function calcularEspaciado(
  caja: CajaIman,
  otras: CajaIman[],
  eje: "x" | "y",
  umbral: number,
): SnapEspaciado | null {
  const ini = (c: CajaIman) => (eje === "x" ? c.x : c.y);
  const fin = (c: CajaIman) => (eje === "x" ? c.x + c.w : c.y + c.h);
  const p0 = (c: CajaIman) => (eje === "x" ? c.y : c.x);
  const p1 = (c: CajaIman) => (eje === "x" ? c.y + c.h : c.x + c.w);
  const solapa = (a: CajaIman, b: CajaIman) => Math.min(p1(a), p1(b)) - Math.max(p0(a), p0(b)) > 0;
  const centroSolape = (a: CajaIman, b: CajaIman) => (Math.max(p0(a), p0(b)) + Math.min(p1(a), p1(b))) / 2;

  const fila = otras.filter((o) => solapa(caja, o));
  // Vecinas inmediatas: la que termina justo antes de la caja y la que empieza justo después
  // (con la tolerancia del umbral, porque la caja se mueve cerca de la posición de snap).
  let antes: CajaIman | null = null;
  let despues: CajaIman | null = null;
  for (const o of fila) {
    if (fin(o) <= ini(caja) + umbral && (!antes || fin(o) > fin(antes))) antes = o;
    if (ini(o) >= fin(caja) - umbral && (!despues || ini(o) < ini(despues))) despues = o;
  }

  const tam = eje === "x" ? caja.w : caja.h;
  const opciones: SnapEspaciado[] = [];
  if (antes && despues) {
    // CENTRADA entre las vecinas: mismo hueco a ambos lados.
    const pos = (fin(antes) + ini(despues) - tam) / 2;
    const gap = pos - fin(antes);
    if (gap > 0) {
      opciones.push({
        pos,
        gap,
        segmentos: [
          { desde: fin(antes), hasta: pos, perp: centroSolape(antes, caja) },
          { desde: pos + tam, hasta: ini(despues), perp: centroSolape(caja, despues) },
        ],
      });
    }
  }
  if (antes) {
    // CADENA hacia atrás: replica el hueco entre la vecina y la capa anterior a ella.
    const a = antes;
    let antes2: CajaIman | null = null;
    for (const o of fila) {
      if (o !== a && fin(o) <= ini(a) && (!antes2 || fin(o) > fin(antes2))) antes2 = o;
    }
    if (antes2 && solapa(antes2, a)) {
      const gap = ini(a) - fin(antes2);
      if (gap > 0) {
        opciones.push({
          pos: fin(a) + gap,
          gap,
          segmentos: [
            { desde: fin(antes2), hasta: ini(a), perp: centroSolape(antes2, a) },
            { desde: fin(a), hasta: fin(a) + gap, perp: centroSolape(a, caja) },
          ],
        });
      }
    }
  }
  if (despues) {
    // CADENA hacia delante: replica el hueco entre la vecina y la capa siguiente a ella.
    const d = despues;
    let despues2: CajaIman | null = null;
    for (const o of fila) {
      if (o !== d && ini(o) >= fin(d) && (!despues2 || ini(o) < ini(despues2))) despues2 = o;
    }
    if (despues2 && solapa(despues2, d)) {
      const gap = ini(despues2) - fin(d);
      if (gap > 0) {
        opciones.push({
          pos: ini(d) - gap - tam,
          gap,
          segmentos: [
            { desde: ini(d) - gap, hasta: ini(d), perp: centroSolape(caja, d) },
            { desde: fin(d), hasta: ini(despues2), perp: centroSolape(d, despues2) },
          ],
        });
      }
    }
  }

  let mejor: SnapEspaciado | null = null;
  for (const op of opciones) {
    const delta = Math.abs(op.pos - ini(caja));
    if (delta <= umbral && (!mejor || delta < Math.abs(mejor.pos - ini(caja)))) mejor = op;
  }
  return mejor;
}
