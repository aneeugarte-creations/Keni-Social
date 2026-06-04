// Adaptar un Documento a OTRO formato/red (reencuadre 1-clic).
//
// El multiplicador de la «máquina de contenido»: a partir de un arte ya montado, genera versiones
// para otras redes (Feed 4:5 -> Story 9:16 -> cuadrado 1:1 -> horizontal 16:9) reescalando y
// recolocando las capas de forma proporcional, respetando las zonas seguras. Es HEURÍSTICO: busca
// un resultado «decente» que el humano retoca, no perfecto. NO toca el render ni el esquema: solo
// produce otro Documento editable con las mismas capas/campos.
//
// ESTRATEGIA (resumen)
// --------------------
// Factores por eje: sx = wDest/wOrig, sy = hDest/hOrig. Para no DEFORMAR imágenes/logos/marcos
// usamos un factor UNIFORME s = min(sx, sy) en sus tamaños, y recolocamos por ANCLAS RELATIVAS:
//   - Centro: si la capa estaba centrada (h/v) en el lienzo origen, se vuelve a centrar en el destino.
//   - Márgenes: si no, se conserva el margen al borde más cercano, escalado por s (izq/der, arr/abj).
// Capas A SANGRE (cubrían todo el lienzo: el HUECO DE FOTO `es_foto`, fondos, overlays/imágenes que
// tapaban 0,0,wOrig,hOrig) se RE-EXTIENDEN a 0,0,wDest,hDest para volver a cubrir el lienzo nuevo.
// Texto: el tamaño de fuente y la caja se reescalan por s (la caja por sx/sy para mantener su forma
// relativa), y se reposiciona respetando las nuevas safe areas: lo que estaba en la franja inferior
// (dentro del safe_bottom) sigue pegado abajo dentro del nuevo safe_bottom; ídem arriba.
//
// Los grupos se adaptan recursivamente (sus hijas en coordenadas absolutas se escalan con los mismos
// factores). El fondo imagen se mantiene (cubre por patrón en el render); nada que recolocar.

import type { Capa, CapaGrupo, CapaTexto, Documento } from "./documento";
import type { Formato } from "./formatos";

// Tolerancia (px del lienzo origen) para considerar que una capa «tocaba» un borde o el centro.
const TOL = 2;

interface Factores {
  wO: number;
  hO: number;
  wD: number;
  hD: number;
  sx: number;
  sy: number;
  s: number; // uniforme = min(sx, sy)
}

// ¿La capa cubría TODO el lienzo origen (a sangre)? Entonces debe volver a cubrir el destino.
function cubreLienzo(c: Capa, wO: number, hO: number): boolean {
  return (
    c.x <= TOL &&
    c.y <= TOL &&
    c.x + c.w >= wO - TOL &&
    c.y + c.h >= hO - TOL
  );
}

// Reposiciona+reescala UNA capa (no grupo) según los factores y las safe areas ORIGEN (las usamos
// para clasificar dónde estaba la capa; la reposición conserva su distancia al borde escalada por s,
// lo que la mantiene dentro de la franja segura del destino sin necesitar el safe destino explícito).
function adaptarCapa(c: Capa, f: Factores, safeTopO: number, safeBotO: number): Capa {
  // 1) Capas a sangre (hueco de foto, fondos, overlays/imágenes a pantalla completa): re-extender.
  // El hueco de foto SIEMPRE se trata así aunque, por reencuadres previos, no toque justo los bordes:
  // su rol es cubrir el lienzo.
  const esFoto = c.tipo === "imagen" && !!c.es_foto;
  if (esFoto || cubreLienzo(c, f.wO, f.hO)) {
    return { ...c, x: 0, y: 0, w: f.wD, h: f.hD } as Capa;
  }

  // 2) Tamaño nuevo. Imágenes/logos/marcos/grupos: uniforme (no deformar). Texto/overlay: por eje
  // (la caja puede cambiar de proporción sin daño; el texto se auto-encoge dentro).
  const uniforme = c.tipo === "imagen" || c.tipo === "logo" || c.tipo === "marco";
  const nw = uniforme ? c.w * f.s : c.w * f.sx;
  const nh = uniforme ? c.h * f.s : c.h * f.sy;

  // 3) Reposición por anclas relativas en cada eje.
  // Horizontal.
  const centradoH = Math.abs(c.x + c.w / 2 - f.wO / 2) <= TOL;
  let nx: number;
  if (centradoH) {
    nx = (f.wD - nw) / 2;
  } else {
    const margenIzq = c.x;
    const margenDer = f.wO - (c.x + c.w);
    // Se ancla al borde MÁS CERCANO, conservando ese margen escalado por s.
    if (margenIzq <= margenDer) nx = margenIzq * f.s;
    else nx = f.wD - nw - margenDer * f.s;
  }

  // Vertical: respeta safe areas. Si la capa estaba dentro de la franja segura inferior, se ancla
  // abajo dentro del nuevo safe_bottom; si dentro de la superior, arriba dentro del nuevo safe_top.
  const fondoO = c.y + c.h;
  const enFranjaInferior = fondoO >= f.hO - safeBotO - TOL && c.y >= f.hO / 2;
  const enFranjaSuperior = c.y <= safeTopO + TOL && fondoO <= f.hO / 2;
  const centradoV = Math.abs(c.y + c.h / 2 - f.hO / 2) <= TOL;
  let ny: number;
  if (centradoV) {
    ny = (f.hD - nh) / 2;
  } else if (enFranjaInferior) {
    // Distancia desde el fondo de la capa al inicio del safe_bottom origen, escalada por s.
    const desdeBorde = f.hO - fondoO; // px por debajo de la capa hasta el borde
    ny = f.hD - nh - desdeBorde * f.s;
    // No invadir por debajo del lienzo.
    ny = Math.min(ny, f.hD - nh);
  } else if (enFranjaSuperior) {
    ny = c.y * f.s;
  } else {
    // Resto: conserva el margen al borde más cercano, escalado por s.
    const margenArr = c.y;
    const margenAbj = f.hO - fondoO;
    if (margenArr <= margenAbj) ny = margenArr * f.s;
    else ny = f.hD - nh - margenAbj * f.s;
  }

  const cambios: Partial<Capa> = {
    x: Math.round(nx),
    y: Math.round(ny),
    w: Math.round(nw),
    h: Math.round(nh),
  };

  // Texto: además reescala el tamaño de fuente y el mínimo de auto-ajuste por s.
  if (c.tipo === "texto") {
    const t = c as CapaTexto;
    (cambios as Partial<CapaTexto>).tamano = Math.max(1, Math.round(t.tamano * f.s));
    if (t.auto_ajuste) {
      (cambios as Partial<CapaTexto>).auto_ajuste = {
        ...t.auto_ajuste,
        tam_min: Math.max(1, Math.round(t.auto_ajuste.tam_min * f.s)),
      };
    }
  }

  return { ...c, ...cambios } as Capa;
}

// Adapta un grupo: reescala su caja y sus hijas (absolutas) con los mismos factores/safe areas.
function adaptarGrupo(g: CapaGrupo, f: Factores, safeTopO: number, safeBotO: number): CapaGrupo {
  const adaptado = adaptarCapa(g, f, safeTopO, safeBotO) as CapaGrupo;
  return {
    ...adaptado,
    capas: g.capas.map((h) =>
      h.tipo === "grupo"
        ? adaptarGrupo(h, f, safeTopO, safeBotO)
        : adaptarCapa(h, f, safeTopO, safeBotO),
    ),
  };
}

/**
 * Devuelve un Documento NUEVO con el lienzo en `formatoDestino` y todas las capas reescaladas y
 * recolocadas (ver estrategia arriba). No muta el original. Si el formato es el mismo, devuelve una
 * copia con el formato fijado (idempotente).
 */
export function adaptarDocumento(doc: Documento, formatoDestino: Formato): Documento {
  const wO = doc.formato.w;
  const hO = doc.formato.h;
  const wD = formatoDestino.w;
  const hD = formatoDestino.h;
  const sx = wD / wO;
  const sy = hD / hO;
  const f: Factores = { wO, hO, wD, hD, sx, sy, s: Math.min(sx, sy) };
  const safeTopO = doc.formato.safe_top ?? 0;
  const safeBotO = doc.formato.safe_bottom ?? 0;

  const capas = doc.capas.map((c) =>
    c.tipo === "grupo"
      ? adaptarGrupo(c as CapaGrupo, f, safeTopO, safeBotO)
      : adaptarCapa(c, f, safeTopO, safeBotO),
  );

  return {
    ...structuredClone(doc),
    formato: { ...formatoDestino },
    capas: structuredClone(capas),
  };
}
