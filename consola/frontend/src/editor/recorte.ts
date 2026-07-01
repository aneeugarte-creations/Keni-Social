// Utilidades del MODO RECORTE visual (crop con tiradores). El crop son fracciones 0..1 de la
// FUENTE: `{cx,cy,cw,ch}` = origen (esq. sup. izq.) + tamaño. El editor visual muestra la imagen
// COMPLETA y un rectángulo de recorte; estas funciones acotan ese rectángulo a [0,1] con un ancho
// y alto mínimos > 0. El render (`dibujar.mjs`) ya acota igual; aquí evitamos emitir crops inválidos.

import { geometriaImagenEnCaja } from "./capas/geometriaImagen";
import type { Ajuste, Crop } from "./documento";

// Recorte mínimo (en fracción) para no colapsar el rectángulo a 0.
export const MIN_CROP = 0.02;

// Acota un crop a [0,1] manteniendo cw,ch >= MIN_CROP y el rect dentro de la fuente.
export function clampCrop(c: Crop): Crop {
  const cw = Math.max(MIN_CROP, Math.min(1, c.cw));
  const ch = Math.max(MIN_CROP, Math.min(1, c.ch));
  const cx = Math.max(0, Math.min(1 - cw, c.cx));
  const cy = Math.max(0, Math.min(1 - ch, c.cy));
  return { cx, cy, cw, ch };
}

// Tiradores del rectángulo de recorte: 4 esquinas + 4 lados. `ew/ns` indican qué bordes mueve.
export type AsaRecorte = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w" | "mover";

// Aplica el movimiento de un tirador (delta en fracciones) sobre un crop y lo acota. `mover`
// desplaza todo el rectángulo; las asas mueven los bordes correspondientes.
export function moverAsa(c: Crop, asa: AsaRecorte, dfx: number, dfy: number): Crop {
  if (asa === "mover") {
    const cx = Math.max(0, Math.min(1 - c.cw, c.cx + dfx));
    const cy = Math.max(0, Math.min(1 - c.ch, c.cy + dfy));
    return { ...c, cx, cy };
  }
  let { cx, cy, cw, ch } = c;
  const oeste = asa === "nw" || asa === "w" || asa === "sw";
  const este = asa === "ne" || asa === "e" || asa === "se";
  const norte = asa === "nw" || asa === "n" || asa === "ne";
  const sur = asa === "sw" || asa === "s" || asa === "se";
  if (oeste) {
    const nx = Math.max(0, Math.min(cx + cw - MIN_CROP, cx + dfx));
    cw = cw + (cx - nx);
    cx = nx;
  }
  if (este) {
    cw = Math.max(MIN_CROP, Math.min(1 - cx, cw + dfx));
  }
  if (norte) {
    const ny = Math.max(0, Math.min(cy + ch - MIN_CROP, cy + dfy));
    ch = ch + (cy - ny);
    cy = ny;
  }
  if (sur) {
    ch = Math.max(MIN_CROP, Math.min(1 - cy, ch + dfy));
  }
  return clampCrop({ cx, cy, cw, ch });
}

// ── Modo recorte estilo Canva ────────────────────────────────────────────────────────────────────

// Escala el RECORTE alrededor de un ANCLA (en fracciones 0..1 de la fuente): factor `f` > 1 =
// imagen más grande dentro del marco (rectángulo de recorte más pequeño). Mantiene la PROPORCIÓN
// del recorte y ACOTA el factor para no salirse de la fuente (mínimo) ni bajar de MIN_CROP
// (máximo), en vez de deformar el rectángulo. El punto del ancla conserva su posición RELATIVA
// dentro del recorte (lo que hay bajo el ancla no se mueve), salvo el clamp final a los bordes.
export function escalarCrop(c: Crop, f: number, ax: number, ay: number): Crop {
  const fMin = Math.max(c.cw, c.ch); // por debajo, cw' o ch' superaría la fuente (1)
  const fMax = Math.min(c.cw, c.ch) / MIN_CROP; // por encima, el lado menor bajaría de MIN_CROP
  const k = Math.max(fMin, Math.min(fMax, f > 0 ? f : fMin));
  return clampCrop({
    cx: ax - (ax - c.cx) / k,
    cy: ay - (ay - c.cy) / k,
    cw: c.cw / k,
    ch: c.ch / k,
  });
}

// Geometría del MODO RECORTE estilo Canva: dónde cae la imagen ORIGINAL COMPLETA (en px LOCALES de
// la caja; puede desbordarla) de modo que la región del crop aterrice EXACTAMENTE donde el render
// pinta la imagen recortada. Derivada de la geometría REAL del render (cover/contain + foco + zoom
// + crop) vía su rect visible y el sub-rect fuente: x_caja(s) = vx + (s − sx)·escalaSrc.
export interface VistaRecorte {
  fx: number; // esquina sup. izq. de la imagen original completa (px de la caja)
  fy: number;
  fw: number; // tamaño de la imagen original completa (px de la caja)
  fh: number;
  escalaSrc: number; // px de caja por px de fuente
}

export function vistaRecorte(
  iw: number,
  ih: number,
  w: number,
  h: number,
  ajuste: Ajuste,
  foco: [number, number] | undefined,
  zoom = 1,
  crop?: Crop | null,
): VistaRecorte {
  const g = geometriaImagenEnCaja(iw, ih, w, h, ajuste, foco, zoom, crop);
  const escalaSrc = g.sw > 0 ? g.vw / g.sw : 1;
  return {
    fx: g.vx - g.sx * escalaSrc,
    fy: g.vy - g.sy * escalaSrc,
    fw: iw * escalaSrc,
    fh: ih * escalaSrc,
    escalaSrc,
  };
}

// ── Recorte LATERAL (tiradores laterales del marco de selección, estilo Canva) ──────────────────
// En una capa de IMAGEN, arrastrar un tirador LATERAL no estira la foto: mueve ese borde de la
// caja y COMPENSA el crop para que los píxeles visibles no se muevan ni cambien de escala
// (= recorte progresivo desde ese borde). Hacia fuera DES-recorta hasta agotar el material
// original; más allá la caja no crece. El resultado queda en forma canónica: el crop es
// EXACTAMENTE lo visible (su proporción == la de la caja), zoom 1 y foco centrado, así
// cover/contain + foco + zoom reproducen la misma vista y el export (dibujar.mjs, mismo contrato
// {cx,cy,cw,ch}) pinta idéntico.

// Tamaño mínimo del lado arrastrado, en px del documento (mismo suelo que el boundBoxFunc del
// Transformer del lienzo).
export const MIN_LADO_PX = 8;

export type LadoCaja = "izq" | "der" | "arriba" | "abajo";

// Estado de la capa al INICIO del gesto, en px del documento y coords LOCALES de la capa (sin
// rotación: la rotación/zoom del lienzo los resuelve el llamador con localADoc/docALocal).
export interface GestoLateral {
  w: number; // caja de la capa
  h: number;
  iw: number; // bitmap natural de la fuente (px)
  ih: number;
  ajuste: Ajuste;
  foco?: [number, number];
  zoom?: number;
  crop?: Crop | null;
  flipH?: boolean;
  flipV?: boolean;
  // Rect que ABRAZAN los tiradores (coords locales de PANTALLA de la capa, con el flip ya
  // aplicado): el rect visible de la foto en imágenes rectangulares simples, o la caja entera
  // [0,0,w,h] cuando la silueta la ocupa (forma/duotono).
  caja: { x: number; y: number; w: number; h: number };
}

export interface ResultadoLateral {
  // Caja nueva en coords LOCALES de la capa de partida (mismo origen/ejes que `caja`).
  x: number;
  y: number;
  w: number;
  h: number;
  crop: Crop; // normalizado: exactamente lo visible en la caja nueva
  zoom: number; // 1 (el encuadre ya vive en el crop)
  foco: [number, number]; // centrado (irrelevante: el crop llena la caja exacta)
}

// Aplica el arrastre de un tirador lateral: `borde` es la posición DESEADA del borde movido en
// coords locales de pantalla (proyección del puntero sobre el eje del lado). Devuelve la caja y el
// crop compensado, o `null` si el gesto no es recortable con exactitud (sin bitmap, o los
// tiradores abrazan una región que la foto no cubre — p. ej. contain con letterbox + forma): el
// llamador cae entonces al estiramiento por defecto.
export function recorteLateral(g: GestoLateral, lado: LadoCaja, borde: number): ResultadoLateral | null {
  const { w, h, iw, ih, caja } = g;
  if (!(iw > 0) || !(ih > 0) || !(w > 0) || !(h > 0) || !(caja.w > 0) || !(caja.h > 0)) return null;
  // Imagen ORIGINAL COMPLETA en coords de CONTENIDO de la caja (la geometría real del render)…
  const v = vistaRecorte(iw, ih, w, h, g.ajuste, g.foco, g.zoom ?? 1, g.crop);
  const k = v.escalaSrc; // px locales por px de fuente (uniforme en ambos ejes)
  if (!(k > 0) || !(v.fw > 0) || !(v.fh > 0)) return null;
  // …y en coords de PANTALLA locales (el flip espeja el contenido alrededor del centro de la caja).
  const fx = g.flipH ? w - v.fx - v.fw : v.fx;
  const fy = g.flipV ? h - v.fy - v.fh : v.fy;
  // Solo es exacto si la foto CUBRE el rect de los tiradores: si la caja sobresale del material no
  // hay píxeles que recortar/des-recortar en ese hueco.
  const EPS = 0.5;
  if (caja.x < fx - EPS || caja.y < fy - EPS || caja.x + caja.w > fx + v.fw + EPS || caja.y + caja.h > fy + v.fh + EPS) {
    return null;
  }
  // Mueve SOLO el borde pedido, acotado: hacia dentro al tamaño mínimo (px y MIN_CROP de la
  // fuente), hacia fuera al límite del material original (clamp en crop completo).
  const minW = Math.min(caja.w, Math.max(MIN_LADO_PX, MIN_CROP * v.fw));
  const minH = Math.min(caja.h, Math.max(MIN_LADO_PX, MIN_CROP * v.fh));
  let { x: nx, y: ny, w: nw, h: nh } = caja;
  if (lado === "der") {
    nw = Math.max(minW, Math.min(fx + v.fw - caja.x, borde - caja.x));
  } else if (lado === "izq") {
    const izq = Math.max(fx, Math.min(caja.x + caja.w - minW, borde));
    nw = caja.x + caja.w - izq;
    nx = izq;
  } else if (lado === "abajo") {
    nh = Math.max(minH, Math.min(fy + v.fh - caja.y, borde - caja.y));
  } else {
    const arriba = Math.max(fy, Math.min(caja.y + caja.h - minH, borde));
    nh = caja.y + caja.h - arriba;
    ny = arriba;
  }
  // Crop normalizado = sub-rect de la FUENTE que queda visible en la caja nueva (deshaciendo el
  // flip para volver a coords de contenido). Su proporción == la de la caja => mismos píxeles, a
  // la misma escala, con zoom 1 y foco centrado.
  const cxc = g.flipH ? w - nx - nw : nx;
  const cyc = g.flipV ? h - ny - nh : ny;
  const crop = clampCrop({
    cx: (cxc - v.fx) / k / iw,
    cy: (cyc - v.fy) / k / ih,
    cw: nw / k / iw,
    ch: nh / k / ih,
  });
  return { x: nx, y: ny, w: nw, h: nh, crop, zoom: 1, foco: [0.5, 0.5] };
}

// ── Recorte de MARCO de FOTO (modo Recortar: tiradores que ENCOGEN el marco, estilo Canva) ────────
// En el MODO RECORTE de una IMAGEN, arrastrar un tirador del marco ENCOGE/AGRANDA la CAJA (el marco)
// y COMPENSA el crop para que los píxeles NO se muevan ni cambien de escala: CORTA la foto, no la
// amplía. La foto original completa se sigue viendo (atenuada fuera del marco); el marco es lo que
// queda. Hacia DENTRO recorta esa franja; hacia FUERA des-recorta hasta el material original y ahí
// se clava. Es `recorteLateral` extendido a las 8 asas (las esquinas mueven dos bordes). La rotación
// no entra (el modo exige rotación 0).

// Núcleo compartido: dado un sub-rect NUEVO del marco (coords locales de PANTALLA de la caja, con el
// flip ya reflejado en la geometría de la foto), devuelve la caja desplazada + el crop CANÓNICO que
// muestra ESOS MISMOS píxeles a la misma escala (crop == visible, zoom 1, foco centrado). El
// llamador entrega un rect ya válido (dentro de la foto); aquí no se re-acota a los bordes.
export function encajarRecorte(g: GestoLateral, nx: number, ny: number, nw: number, nh: number): ResultadoLateral | null {
  const { w, h, iw, ih } = g;
  if (!(iw > 0) || !(ih > 0) || !(w > 0) || !(h > 0) || !(nw > 0) || !(nh > 0)) return null;
  const v = vistaRecorte(iw, ih, w, h, g.ajuste, g.foco, g.zoom ?? 1, g.crop);
  const k = v.escalaSrc;
  if (!(k > 0)) return null;
  // Deshace el flip para leer el sub-rect de la FUENTE (coords de contenido).
  const cxc = g.flipH ? w - nx - nw : nx;
  const cyc = g.flipV ? h - ny - nh : ny;
  const crop = clampCrop({
    cx: (cxc - v.fx) / k / iw,
    cy: (cyc - v.fy) / k / ih,
    cw: nw / k / iw,
    ch: nh / k / ih,
  });
  return { x: nx, y: ny, w: nw, h: nh, crop, zoom: 1, foco: [0.5, 0.5] };
}

// Aplica el arrastre de un tirador del MARCO. `caja` de partida = el marco entero (0,0,w,h); cada
// borde arrastrado se acota al material de la foto (no crece hacia el vacío) y a un mínimo. (dx,dy)
// = delta del puntero en px del DOCUMENTO. Devuelve `null` sin bitmap.
export function recorteMarco(g: GestoLateral, asa: AsaRecorte, dx: number, dy: number): ResultadoLateral | null {
  if (asa === "mover") return null;
  const { w, h, iw, ih } = g;
  if (!(iw > 0) || !(ih > 0) || !(w > 0) || !(h > 0)) return null;
  const v = vistaRecorte(iw, ih, w, h, g.ajuste, g.foco, g.zoom ?? 1, g.crop);
  if (!(v.escalaSrc > 0) || !(v.fw > 0) || !(v.fh > 0)) return null;
  // Foto ORIGINAL completa en coords de PANTALLA locales (el flip espeja el contenido).
  const fx = g.flipH ? w - v.fx - v.fw : v.fx;
  const fy = g.flipV ? h - v.fy - v.fh : v.fy;
  const oeste = asa === "nw" || asa === "w" || asa === "sw";
  const este = asa === "ne" || asa === "e" || asa === "se";
  const norte = asa === "nw" || asa === "n" || asa === "ne";
  const sur = asa === "sw" || asa === "s" || asa === "se";
  const minW = Math.min(w, Math.max(MIN_LADO_PX, MIN_CROP * v.fw));
  const minH = Math.min(h, Math.max(MIN_LADO_PX, MIN_CROP * v.fh));
  // Bordes del marco. Solo el lado (o los dos de la esquina) del tirador se mueve; el opuesto queda.
  let left = 0;
  let top = 0;
  let right = w;
  let bottom = h;
  if (este) right = Math.max(left + minW, Math.min(fx + v.fw, w + dx));
  if (oeste) left = Math.min(right - minW, Math.max(fx, dx));
  if (sur) bottom = Math.max(top + minH, Math.min(fy + v.fh, h + dy));
  if (norte) top = Math.min(bottom - minH, Math.max(fy, dy));
  return encajarRecorte(g, left, top, right - left, bottom - top);
}

// Punto en coords LOCALES de una capa (origen = su esquina sup. izq., ejes girados `rot`°, como el
// nodo Konva) -> coords del DOCUMENTO, y la inversa (para proyectar el puntero sobre la capa).
export function localADoc(x0: number, y0: number, rot: number, px: number, py: number): { x: number; y: number } {
  const a = (rot * Math.PI) / 180;
  const cos = Math.cos(a);
  const sin = Math.sin(a);
  return { x: x0 + px * cos - py * sin, y: y0 + px * sin + py * cos };
}

export function docALocal(x0: number, y0: number, rot: number, px: number, py: number): { x: number; y: number } {
  const a = (rot * Math.PI) / 180;
  const cos = Math.cos(a);
  const sin = Math.sin(a);
  const dx = px - x0;
  const dy = py - y0;
  return { x: dx * cos + dy * sin, y: -dx * sin + dy * cos };
}

// ── Recorte de CAJA (objetos no-imagen: formas, líneas, logos) ────────────────────────────────────
//
// Para una imagen, "recortar" recorta sus PÍXELES (campo `crop`). Para un objeto sin píxeles (marco,
// línea, logo) "recortar" = encoger su RECUADRO desde un borde: el borde OPUESTO al tirador queda
// fijo y el arrastrado avanza, con un mínimo para no colapsarlo. Deltas en px del DOCUMENTO sobre la
// caja de ENTRADA del gesto (no acumula sobre estados intermedios), espejo de `moverAsa` pero en px.

export interface CajaRecorte {
  x: number;
  y: number;
  w: number;
  h: number;
}

export const MIN_CAJA_PX = 8;

// Relación de aspecto FIJA de un recorte: ancho/alto a mantener. `null` = libre (sin acotar).
export type Aspecto = number | null;

// Ajusta el par (w,h) a la relación `aspecto` = w/h manteniendo el LADO MÁS RESTRICTIVO (el que
// obliga a encoger el otro), para que el rect quepa dentro del deseado. `eje` fuerza qué lado manda
// cuando el gesto lo determina (un tirador lateral fija su propio eje; una esquina deja decidir al
// más restrictivo). Devuelve w,h > 0 acotados al mínimo.
function ajustarAspecto(w: number, h: number, aspecto: number, min: number, eje: "w" | "h" | "auto"): { w: number; h: number } {
  const wPorH = h * aspecto; // ancho que impondría el alto actual
  const hPorW = w / aspecto; // alto que impondría el ancho actual
  let nw = w;
  let nh = h;
  if (eje === "w" || (eje === "auto" && wPorH <= w)) {
    nw = w;
    nh = hPorW;
  } else {
    nh = h;
    nw = wPorH;
  }
  if (nw < min) {
    nw = min;
    nh = min / aspecto;
  }
  if (nh < min) {
    nh = min;
    nw = min * aspecto;
  }
  return { w: nw, h: nh };
}

// Encoge el RECUADRO de un objeto sin píxeles desde un borde/esquina (el opuesto queda fijo). Con
// `aspecto` (w/h) NO fijado (null) recorta libre; fijado, mantiene la proporción anclando la esquina
// opuesta al tirador (los lados fijan su propio eje; las esquinas dejan mandar al lado más restrictivo).
export function recortarCaja(
  c: CajaRecorte,
  asa: AsaRecorte,
  dx: number,
  dy: number,
  min = MIN_CAJA_PX,
  aspecto: Aspecto = null,
): CajaRecorte {
  if (asa === "mover") return { x: c.x + dx, y: c.y + dy, w: c.w, h: c.h };
  const der = c.x + c.w; // borde derecho/inferior: fijo salvo que se arrastre ese lado
  const aba = c.y + c.h;
  let { x, y, w, h } = c;
  const oeste = asa === "nw" || asa === "w" || asa === "sw";
  const este = asa === "ne" || asa === "e" || asa === "se";
  const norte = asa === "nw" || asa === "n" || asa === "ne";
  const sur = asa === "sw" || asa === "s" || asa === "se";
  if (oeste) {
    x = Math.min(c.x + dx, der - min); // no pasar del borde derecho menos el mínimo
    w = der - x;
  }
  if (este) {
    w = Math.max(min, c.w + dx);
  }
  if (norte) {
    y = Math.min(c.y + dy, aba - min);
    h = aba - y;
  }
  if (sur) {
    h = Math.max(min, c.h + dy);
  }
  if (aspecto && aspecto > 0) {
    const lado = (este || oeste) && (norte || sur);
    const soloH = (este || oeste) && !(norte || sur); // tirador lateral izq/der => manda el ancho
    const aj = ajustarAspecto(w, h, aspecto, min, lado ? "auto" : soloH ? "w" : "h");
    w = aj.w;
    h = aj.h;
    // Re-ancla el borde/esquina OPUESTO al tirador (el fijo): izquierda/arriba se recalculan.
    if (oeste) x = der - w;
    if (norte) y = aba - h;
  }
  return { x, y, w, h };
}

// Nueva CAJA con la relación `aspecto` (w/h) INSCRITA en la actual (`w×h`) y CENTRADA sobre ella
// (mismo centro): el lado que sobra se encoge. Para el marco de una FOTO en recorte, fijar un aspecto
// = re-encuadrar el marco a esa proporción sin salirse del sitio que ocupaba. Devuelve x,y RELATIVOS
// al origen de la caja original (0,0 si el aspecto ya coincide).
export function cajaConAspecto(w: number, h: number, aspecto: number, min = MIN_CAJA_PX): CajaRecorte {
  if (!(aspecto > 0) || !(w > 0) || !(h > 0)) return { x: 0, y: 0, w, h };
  let nw = Math.min(w, h * aspecto);
  let nh = nw / aspecto;
  if (nh > h) {
    nh = h;
    nw = nh * aspecto;
  }
  nw = Math.max(min, nw);
  nh = Math.max(min, nh);
  return { x: (w - nw) / 2, y: (h - nh) / 2, w: nw, h: nh };
}

// Igual que `recortarCaja` pero para un objeto ROTADO `rot`° (su recuadro se recorta a lo largo de
// SUS PROPIOS ejes, como en Canva): el delta del puntero (en px del documento) se proyecta a los ejes
// LOCALES del objeto, se recorta el recuadro local (origen 0,0) y el nuevo origen se devuelve a coords
// del documento. `x,y` es la esquina sup-izq local (= pivote de rotación de Konva). Con `rot` 0 es
// `recortarCaja` directo.
export function recortarCajaRotada(
  c: CajaRecorte,
  rot: number,
  asa: AsaRecorte,
  dx: number,
  dy: number,
  min = MIN_CAJA_PX,
  aspecto: Aspecto = null,
): CajaRecorte {
  if (!rot) return recortarCaja(c, asa, dx, dy, min, aspecto);
  const dLocal = docALocal(0, 0, rot, dx, dy); // delta del puntero en los ejes locales del objeto
  const local = recortarCaja({ x: 0, y: 0, w: c.w, h: c.h }, asa, dLocal.x, dLocal.y, min, aspecto);
  const origen = localADoc(c.x, c.y, rot, local.x, local.y); // nuevo origen local -> documento
  return { x: origen.x, y: origen.y, w: local.w, h: local.h };
}
