// Adaptar un Documento a OTRO formato/red (reencuadre 1-clic).
//
// El multiplicador de la «máquina de contenido»: a partir de un arte ya montado, genera versiones
// para otras redes (Feed 4:5 -> Story 9:16 -> cuadrado 1:1 -> horizontal 16:9) reescalando y
// recolocando las capas con las PROPORCIONES adecuadas a cada formato. Es HEURÍSTICO: busca un
// resultado «decente» que el humano retoca, no perfecto. NO toca el render ni el esquema: solo
// produce otro Documento editable con las mismas capas/campos.
//
// ESTRATEGIA — mapeo del RECTÁNGULO DE CONTENIDO con escala UNIFORME
// -----------------------------------------------------------------
// Cada formato reserva sus propias ZONAS SEGURAS (en 9:16/Reels la UI tapa 220px arriba y 420px
// abajo; en feed casi nada). Adaptar «bien» = recolocar el contenido DENTRO de la zona segura del
// DESTINO, no preservar los márgenes del origen (que metían los titulares bajo la UI de Reels).
//
//   1. Rectángulo de contenido = lienzo menos las safe areas. `Co` (origen) y `Cd` (destino).
//   2. Cada capa NO a sangre se recoloca por su CENTRO como FRACCIÓN de `Co`, llevada a `Cd`
//      (mapa afín: lo centrado sigue centrado; lo pegado a una franja segura cae en la franja
//      segura equivalente del destino). El mapa es exacto, así que adaptar al mismo formato es
//      idempotente.
//   3. Los TAMAÑOS se escalan por un factor UNIFORME `k = min(Cd.w/Co.w, Cd.h/Co.h)` (no deforma:
//      el contenido cabe en la zona segura del destino conservando su aspecto).
//   4. Se escalan por `k` TODAS las propiedades en PX que definen la proporción visual: tamaño y
//      mínimo de fuente, interletra, grosor de contorno/borde, padding/radio de chip, radio del
//      texto en arco, radios de esquina de imagen/marco y los offsets/desenfoque de sombra. Sin
//      esto, a otra escala el contorno o la sombra quedaban gigantes/diminutos.
//   5. Capas A SANGRE (el HUECO DE FOTO `es_foto`, fondos, overlays/imágenes que cubrían todo el
//      lienzo) se RE-EXTIENDEN a 0,0,wDest,hDest para volver a cubrir el lienzo nuevo.
//   6. Los GRUPOS se recolocan como una unidad y sus hijas se escalan RÍGIDAMENTE por `k` (su
//      layout interno se conserva), no hija a hija.

import type {
  Capa,
  CapaGrupo,
  CapaImagen,
  CapaMarco,
  CapaTexto,
  Documento,
  Sombra,
} from "./documento";
import type { Formato } from "./formatos";

// Tolerancia (px del lienzo origen) para considerar que una capa cubría todo el lienzo (a sangre).
const TOL = 2;

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface Ctx {
  wO: number;
  hO: number;
  wD: number;
  hD: number;
  Co: Rect; // rectángulo de contenido del ORIGEN (dentro de sus safe areas)
  Cd: Rect; // rectángulo de contenido del DESTINO
  k: number; // escala uniforme de tamaños = min(Cd.w/Co.w, Cd.h/Co.h)
}

// Rectángulo de contenido = lienzo menos safe areas. Si las safe se solapan (rect inválido), cae al
// lienzo completo para no dividir por cero ni invertir el mapa.
function rectContenido(
  w: number,
  h: number,
  st: number,
  sb: number,
  sl: number,
  sr: number,
): Rect {
  const rw = w - sl - sr;
  const rh = h - st - sb;
  if (rw <= 0 || rh <= 0) return { x: 0, y: 0, w, h };
  return { x: sl, y: st, w: rw, h: rh };
}

// ¿La capa cubría TODO el lienzo origen (a sangre)? Entonces debe volver a cubrir el destino.
function cubreLienzo(c: Capa, wO: number, hO: number): boolean {
  return c.x <= TOL && c.y <= TOL && c.x + c.w >= wO - TOL && c.y + c.h >= hO - TOL;
}

// Escala los offsets/desenfoque de una sombra por k (su color/opacidad no cambian).
function escalarSombra<T extends Sombra | null | undefined>(s: T, k: number): T {
  if (!s) return s;
  const out: Sombra = { ...s, dx: Math.round(s.dx * k), dy: Math.round(s.dy * k) };
  if (s.desenfoque != null) out.desenfoque = Math.round(s.desenfoque * k);
  return out as T;
}

// Altura VISUAL de una capa de texto: su caja si `h>0`, o una línea (tamaño × interlineado) si la
// caja es automática (`h<=0`, camino legado anclado arriba/abajo).
function altoVisualTexto(c: CapaTexto): number {
  return c.h > 0 ? c.h : Math.round(c.tamano * c.interlineado);
}

// Escala las propiedades en PX de ESTILO (no la caja) por k, para conservar la proporción visual.
function escalarEstilos(c: Capa, k: number): Capa {
  switch (c.tipo) {
    case "texto": {
      const t = c;
      const cambios: Partial<CapaTexto> = {
        tamano: Math.max(1, Math.round(t.tamano * k)),
        interletra: Math.round(t.interletra * k),
        auto_ajuste: {
          ...t.auto_ajuste,
          tam_min: Math.max(1, Math.round(t.auto_ajuste.tam_min * k)),
        },
        sombra: escalarSombra(t.sombra, k),
      };
      if (t.contorno) cambios.contorno = { ...t.contorno, grosor: Math.max(0, Math.round(t.contorno.grosor * k)) };
      if (t.chip) {
        cambios.chip = {
          ...t.chip,
          pad_x: Math.round(t.chip.pad_x * k),
          pad_y: Math.round(t.chip.pad_y * k),
          radio: Math.round(t.chip.radio * k),
        };
      }
      if (t.curva) cambios.curva = { radio: Math.round(t.curva.radio * k) };
      return { ...t, ...cambios };
    }
    case "imagen": {
      const im = c;
      const cambios: Partial<CapaImagen> = {};
      if (typeof im.radio === "number") cambios.radio = Math.round(im.radio * k);
      if (im.radios) {
        cambios.radios = im.radios.map((r) => Math.round(r * k)) as [number, number, number, number];
      }
      if (im.sombra) cambios.sombra = escalarSombra(im.sombra, k);
      return { ...im, ...cambios };
    }
    case "marco": {
      const m = c;
      const cambios: Partial<CapaMarco> = { radio: Math.round(m.radio * k) };
      if (m.borde) cambios.borde = { ...m.borde, grosor: Math.max(0, Math.round(m.borde.grosor * k)) };
      if (m.radios) {
        cambios.radios = m.radios.map((r) => Math.round(r * k)) as [number, number, number, number];
      }
      if (m.sombra) cambios.sombra = escalarSombra(m.sombra, k);
      return { ...m, ...cambios };
    }
    default:
      // logo/overlay/grupo: sin px de estilo propios que reescalar (la caja la mueve quien llama).
      return c;
  }
}

// Recoloca + reescala UNA capa (no grupo): a sangre -> re-extiende; resto -> mapa de contenido.
function adaptarCapa(c: Capa, ctx: Ctx): Capa {
  // 1) A sangre (hueco de foto, fondos, overlays/imágenes a pantalla completa): re-extender.
  const esFoto = c.tipo === "imagen" && !!c.es_foto;
  if (esFoto || cubreLienzo(c, ctx.wO, ctx.hO)) {
    return { ...escalarEstilos(c, ctx.k), x: 0, y: 0, w: ctx.wD, h: ctx.hD } as Capa;
  }

  // 2) Tamaño uniforme (no deforma). La caja de texto automática (h<=0) se conserva.
  const hVis = c.tipo === "texto" ? altoVisualTexto(c) : c.h;
  const nw = c.w * ctx.k;
  const nhVis = hVis * ctx.k;
  const nhBox = c.h > 0 ? c.h * ctx.k : c.h;

  // 3) Posición por el CENTRO como fracción de `Co`, llevada a `Cd` (mapa afín, sin recortar la
  //    fracción: así adaptar al mismo formato es idempotente y lo que estaba fuera de la zona
  //    segura cae fuera de la equivalente del destino).
  const cx = c.x + c.w / 2;
  const cy = c.y + hVis / 2;
  const fx = (cx - ctx.Co.x) / ctx.Co.w;
  const fy = (cy - ctx.Co.y) / ctx.Co.h;
  const ncx = ctx.Cd.x + fx * ctx.Cd.w;
  const ncy = ctx.Cd.y + fy * ctx.Cd.h;
  // Esquina superior izquierda de la caja VISUAL, sujeta al lienzo destino (no se sale por arriba/izq).
  let nx = ncx - nw / 2;
  let visTop = ncy - nhVis / 2;
  nx = Math.min(Math.max(nx, 0), Math.max(0, ctx.wD - nw));
  visTop = Math.min(Math.max(visTop, 0), Math.max(0, ctx.hD - nhVis));

  // Para texto con caja automática anclado ABAJO, la `y` almacenada es el borde inferior visual.
  const ny =
    c.tipo === "texto" && c.h <= 0 && c.ancla === "abajo" ? visTop + nhVis : visTop;

  return {
    ...escalarEstilos(c, ctx.k),
    x: Math.round(nx),
    y: Math.round(ny),
    w: Math.round(nw),
    h: c.h > 0 ? Math.round(nhBox) : c.h,
  } as Capa;
}

// Escala una capa RÍGIDAMENTE por k conservando su posición relativa al grupo: (gx,gy) del grupo
// origen pasa a (ox,oy) del grupo destino. Recursivo para grupos anidados.
function escalarRigido(c: Capa, k: number, ox: number, oy: number, gx: number, gy: number): Capa {
  const nx = ox + (c.x - gx) * k;
  const ny = oy + (c.y - gy) * k;
  const nw = c.w * k;
  const nh = c.h > 0 ? c.h * k : c.h;
  const caja = {
    x: Math.round(nx),
    y: Math.round(ny),
    w: Math.round(nw),
    h: c.h > 0 ? Math.round(nh) : c.h,
  };
  if (c.tipo === "grupo") {
    return {
      ...(escalarEstilos(c, k) as CapaGrupo),
      ...caja,
      capas: c.capas.map((h) => escalarRigido(h, k, nx, ny, c.x, c.y)),
    };
  }
  return { ...escalarEstilos(c, k), ...caja } as Capa;
}

// Adapta un grupo: recoloca su caja con el mapa de contenido y escala sus hijas rígidamente por k.
function adaptarGrupo(g: CapaGrupo, ctx: Ctx): CapaGrupo {
  const caja = adaptarCapa({ ...g, capas: [] }, ctx) as CapaGrupo;
  return { ...caja, capas: g.capas.map((h) => escalarRigido(h, ctx.k, caja.x, caja.y, g.x, g.y)) };
}

/**
 * Devuelve un Documento NUEVO con el lienzo en `formatoDestino` y todas las capas reescaladas y
 * recolocadas con las proporciones del destino (ver estrategia arriba). No muta el original.
 * Adaptar al mismo formato es idempotente (el mapa de contenido es la identidad).
 */
export function adaptarDocumento(doc: Documento, formatoDestino: Formato): Documento {
  const wO = doc.formato.w;
  const hO = doc.formato.h;
  const wD = formatoDestino.w;
  const hD = formatoDestino.h;
  const Co = rectContenido(
    wO,
    hO,
    doc.formato.safe_top ?? 0,
    doc.formato.safe_bottom ?? 0,
    doc.formato.safe_left ?? 0,
    doc.formato.safe_right ?? 0,
  );
  const Cd = rectContenido(
    wD,
    hD,
    formatoDestino.safe_top ?? 0,
    formatoDestino.safe_bottom ?? 0,
    formatoDestino.safe_left ?? 0,
    formatoDestino.safe_right ?? 0,
  );
  const k = Math.min(Cd.w / Co.w, Cd.h / Co.h);
  const ctx: Ctx = { wO, hO, wD, hD, Co, Cd, k };

  const capas = doc.capas.map((c) => (c.tipo === "grupo" ? adaptarGrupo(c, ctx) : adaptarCapa(c, ctx)));

  return {
    ...structuredClone(doc),
    formato: { ...formatoDestino },
    capas: structuredClone(capas),
  };
}
