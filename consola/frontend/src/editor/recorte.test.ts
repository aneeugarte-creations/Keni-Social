import { describe, expect, it } from "vitest";

import {
  type GestoLateral,
  MIN_CAJA_PX,
  MIN_CROP,
  MIN_LADO_PX,
  clampCrop,
  docALocal,
  escalarCrop,
  localADoc,
  moverAsa,
  recortarCaja,
  recortarCajaRotada,
  recorteLateral,
  vistaRecorte,
} from "./recorte";

describe("clampCrop", () => {
  it("acota a [0,1] y respeta el mínimo", () => {
    const c = clampCrop({ cx: -0.5, cy: 2, cw: 0, ch: 5 });
    expect(c.cx).toBeGreaterThanOrEqual(0);
    expect(c.cy).toBeGreaterThanOrEqual(0);
    expect(c.cw).toBeGreaterThanOrEqual(MIN_CROP);
    expect(c.ch).toBeGreaterThanOrEqual(MIN_CROP);
    expect(c.cx + c.cw).toBeLessThanOrEqual(1 + 1e-9);
    expect(c.cy + c.ch).toBeLessThanOrEqual(1 + 1e-9);
  });

  it("mantiene un crop ya válido", () => {
    const c = clampCrop({ cx: 0.1, cy: 0.2, cw: 0.5, ch: 0.4 });
    expect(c).toEqual({ cx: 0.1, cy: 0.2, cw: 0.5, ch: 0.4 });
  });
});

describe("moverAsa", () => {
  const base = { cx: 0.2, cy: 0.2, cw: 0.6, ch: 0.6 };

  it("'mover' desplaza el rect sin cambiar tamaño y acota a los bordes", () => {
    const m = moverAsa(base, "mover", 0.1, -0.1);
    expect(m.cw).toBe(0.6);
    expect(m.ch).toBe(0.6);
    expect(m.cx).toBeCloseTo(0.3);
    expect(m.cy).toBeCloseTo(0.1);
    // No se sale por la derecha aunque empujemos mucho.
    const tope = moverAsa(base, "mover", 1, 0);
    expect(tope.cx + tope.cw).toBeLessThanOrEqual(1 + 1e-9);
  });

  it("asa 'e' crece el ancho hacia la derecha", () => {
    const m = moverAsa(base, "e", 0.1, 0);
    expect(m.cx).toBe(0.2);
    expect(m.cw).toBeCloseTo(0.7);
  });

  it("asa 'w' mueve el borde izquierdo y reduce el ancho", () => {
    const m = moverAsa(base, "w", 0.1, 0);
    expect(m.cx).toBeCloseTo(0.3);
    expect(m.cw).toBeCloseTo(0.5);
  });

  it("asa 'nw' mueve a la vez los bordes superior e izquierdo", () => {
    const m = moverAsa(base, "nw", 0.1, 0.1);
    expect(m.cx).toBeCloseTo(0.3);
    expect(m.cy).toBeCloseTo(0.3);
    expect(m.cw).toBeCloseTo(0.5);
    expect(m.ch).toBeCloseTo(0.5);
  });

  it("no permite que un borde cruce al opuesto (mínimo MIN_CROP)", () => {
    const m = moverAsa(base, "e", -1, 0);
    expect(m.cw).toBeGreaterThanOrEqual(MIN_CROP);
  });
});

describe("escalarCrop (modo recorte estilo Canva)", () => {
  const base = { cx: 0.25, cy: 0.25, cw: 0.5, ch: 0.5 };

  it("f=2 reduce el recorte a la mitad alrededor del ancla (imagen el doble de grande)", () => {
    const m = escalarCrop(base, 2, 0.5, 0.5);
    expect(m).toEqual({ cx: 0.375, cy: 0.375, cw: 0.25, ch: 0.25 });
  });

  it("conserva la posición RELATIVA del ancla dentro del recorte", () => {
    const ax = 0.3, ay = 0.6;
    const relX = (ax - base.cx) / base.cw;
    const relY = (ay - base.cy) / base.ch;
    const m = escalarCrop(base, 1.7, ax, ay);
    expect((ax - m.cx) / m.cw).toBeCloseTo(relX);
    expect((ay - m.cy) / m.ch).toBeCloseTo(relY);
  });

  it("al alejar (f<1) acota el factor para no salirse de la fuente", () => {
    const m = escalarCrop(base, 0.1, 0.5, 0.5);
    expect(m).toEqual({ cx: 0, cy: 0, cw: 1, ch: 1 });
  });

  it("al acercar (f grande) respeta el mínimo MIN_CROP del lado menor", () => {
    const m = escalarCrop({ cx: 0, cy: 0, cw: 0.5, ch: 0.25 }, 1000, 0, 0);
    expect(Math.min(m.cw, m.ch)).toBeGreaterThanOrEqual(MIN_CROP - 1e-9);
    // Mantiene la proporción del recorte.
    expect(m.cw / m.ch).toBeCloseTo(2);
  });

  it("un factor inválido (<= 0) no produce NaN: cae al mínimo permitido", () => {
    const m = escalarCrop(base, 0, 0.5, 0.5);
    expect(Number.isFinite(m.cx)).toBe(true);
    expect(m.cw).toBeLessThanOrEqual(1);
  });
});

describe("vistaRecorte (imagen original completa en el modo recorte)", () => {
  it("sin crop, cover con la misma proporción: la imagen completa coincide con la caja", () => {
    const v = vistaRecorte(200, 100, 100, 50, "cover", [0.5, 0.5]);
    expect(v.escalaSrc).toBeCloseTo(0.5);
    expect(v.fx).toBeCloseTo(0);
    expect(v.fy).toBeCloseTo(0);
    expect(v.fw).toBeCloseTo(100);
    expect(v.fh).toBeCloseTo(50);
  });

  it("con crop, la REGIÓN recortada aterriza exactamente en el marco", () => {
    const crop = { cx: 0.5, cy: 0.5, cw: 0.5, ch: 0.5 };
    const v = vistaRecorte(100, 100, 50, 50, "cover", [0.5, 0.5], 1, crop);
    expect(v.escalaSrc).toBeCloseTo(1);
    // La esquina del crop (fracción 0.5 de la imagen completa) cae en el origen del marco…
    expect(v.fx + crop.cx * v.fw).toBeCloseTo(0);
    expect(v.fy + crop.cy * v.fh).toBeCloseTo(0);
    // …y el ancho del crop cubre el marco entero (cover con la misma proporción).
    expect(crop.cw * v.fw).toBeCloseTo(50);
  });

  it("contain con letterbox: la imagen completa queda centrada con su banda", () => {
    const v = vistaRecorte(100, 50, 100, 100, "contain", [0.5, 0.5]);
    expect(v.escalaSrc).toBeCloseTo(1);
    expect(v.fx).toBeCloseTo(0);
    expect(v.fy).toBeCloseTo(25);
    expect(v.fw).toBeCloseTo(100);
    expect(v.fh).toBeCloseTo(50);
  });
});

describe("recorteLateral (tiradores laterales que recortan, estilo Canva)", () => {
  // Capa "canónica": caja == foto a escala 1:2 (fuente 800×600 en caja 400×300), cover sin
  // crop/zoom/flip; los tiradores abrazan la caja entera.
  const base = (extra: Partial<GestoLateral> = {}): GestoLateral => ({
    w: 400,
    h: 300,
    iw: 800,
    ih: 600,
    ajuste: "cover",
    foco: [0.5, 0.5],
    zoom: 1,
    crop: null,
    caja: { x: 0, y: 0, w: 400, h: 300 },
    ...extra,
  });

  // Píxel FUENTE bajo un punto LOCAL de pantalla de la caja (deshace flip y geometría del render):
  // la vara de medir de que el gesto NO mueve ni reescala los píxeles visibles.
  const fuenteEn = (p: GestoLateral, x: number, y: number) => {
    const v = vistaRecorte(p.iw, p.ih, p.w, p.h, p.ajuste, p.foco, p.zoom ?? 1, p.crop);
    const xc = p.flipH ? p.w - x : x;
    const yc = p.flipV ? p.h - y : y;
    return { u: (xc - v.fx) / v.escalaSrc, v: (yc - v.fy) / v.escalaSrc, k: v.escalaSrc };
  };

  it("arrastrar el borde derecho hacia dentro recorta ese lado sin mover la caja ni la foto", () => {
    const r = recorteLateral(base(), "der", 300);
    expect(r).not.toBeNull();
    expect(r!.x).toBe(0);
    expect(r!.y).toBe(0);
    expect(r!.w).toBe(300);
    expect(r!.h).toBe(300);
    // Se pierde solo el 25% derecho de la fuente; el resto queda intacto.
    expect(r!.crop).toEqual({ cx: 0, cy: 0, cw: 0.75, ch: 1 });
    expect(r!.zoom).toBe(1);
  });

  it("mantiene los píxeles visibles (posición y escala) ante crop+zoom+foco previos", () => {
    const p = base({
      zoom: 1.4,
      foco: [0.3, 0.6],
      crop: { cx: 0.1, cy: 0.05, cw: 0.7, ch: 0.8 },
    });
    const r = recorteLateral(p, "der", 260)!;
    expect(r).not.toBeNull();
    const despues: GestoLateral = { ...p, w: r.w, h: r.h, foco: r.foco, zoom: r.zoom, crop: r.crop, caja: { x: 0, y: 0, w: r.w, h: r.h } };
    // Mismo punto del documento (la caja no movió su origen): mismo píxel fuente y misma escala.
    for (const [x, y] of [[20, 30], [150, 200], [r.w - 1, r.h - 1]] as const) {
      const antes = fuenteEn(p, x + r.x, y + r.y);
      const ahora = fuenteEn(despues, x, y);
      expect(ahora.u).toBeCloseTo(antes.u, 6);
      expect(ahora.v).toBeCloseTo(antes.v, 6);
      expect(ahora.k).toBeCloseTo(antes.k, 6);
    }
  });

  it("hacia fuera des-recorta hasta el material original y ahí se clava (clamp)", () => {
    // Crop previo: falta el 20% izquierdo de la fuente => hay 80 px locales de material a la izq.
    const p = base({
      w: 320,
      h: 240,
      crop: { cx: 0.2, cy: 0, cw: 0.8, ch: 0.8 },
      caja: { x: 0, y: 0, w: 320, h: 240 },
    });
    const r = recorteLateral(p, "izq", -500)!; // mucho más allá del material
    expect(r.x).toBeCloseTo(-80);
    expect(r.w).toBeCloseTo(400);
    expect(r.crop.cx).toBeCloseTo(0);
    expect(r.crop.cx + r.crop.cw).toBeCloseTo(0.2 + 0.8);
  });

  it("sin material que des-recortar, el borde no crece", () => {
    const r = recorteLateral(base(), "der", 999)!;
    expect(r.w).toBe(400);
    expect(r.crop.cw).toBeCloseTo(1);
  });

  it("respeta el tamaño mínimo al recortar a fondo", () => {
    const r = recorteLateral(base(), "der", -999)!;
    expect(r.w).toBeGreaterThanOrEqual(MIN_LADO_PX);
    expect(r.crop.cw).toBeGreaterThanOrEqual(MIN_CROP - 1e-9);
  });

  it("borde superior: mueve `y` y compensa cy/ch", () => {
    const r = recorteLateral(base(), "arriba", 75)!;
    expect(r.y).toBe(75);
    expect(r.h).toBe(225);
    expect(r.x).toBe(0);
    expect(r.w).toBe(400);
    expect(r.crop).toEqual({ cx: 0, cy: 0.25, cw: 1, ch: 0.75 });
  });

  it("con flipH, arrastrar el borde derecho (pantalla) recorta el lado IZQUIERDO de la fuente", () => {
    const r = recorteLateral(base({ flipH: true }), "der", 300)!;
    expect(r.w).toBe(300);
    // En pantalla se pierde la franja derecha; en la fuente (espejada) es la franja izquierda.
    expect(r.crop).toEqual({ cx: 0.25, cy: 0, cw: 0.75, ch: 1 });
    // Y los píxeles visibles no se mueven.
    const p = base({ flipH: true });
    const despues: GestoLateral = { ...p, w: r.w, h: r.h, foco: r.foco, zoom: r.zoom, crop: r.crop, caja: { x: 0, y: 0, w: r.w, h: r.h } };
    const antes = fuenteEn(p, 10, 20);
    const ahora = fuenteEn(despues, 10 - r.x, 20 - r.y);
    expect(ahora.u).toBeCloseTo(antes.u, 6);
    expect(ahora.v).toBeCloseTo(antes.v, 6);
  });

  it("con flipV, arrastrar el borde inferior (pantalla) recorta la franja SUPERIOR de la fuente", () => {
    const r = recorteLateral(base({ flipV: true }), "abajo", 200)!;
    expect(r.h).toBe(200);
    expect(r.crop.cx).toBe(0);
    expect(r.crop.cw).toBe(1);
    expect(r.crop.cy).toBeCloseTo(1 / 3);
    expect(r.crop.ch).toBeCloseTo(2 / 3);
  });

  it("contain con letterbox: si los tiradores abrazan la caja entera (forma), no es recortable", () => {
    // Foto 100×50 contain en caja 100×100: bandas arriba/abajo. La caja entera NO está cubierta.
    const conForma = base({ iw: 100, ih: 50, w: 100, h: 100, ajuste: "contain", caja: { x: 0, y: 0, w: 100, h: 100 } });
    expect(recorteLateral(conForma, "der", 80)).toBeNull();
    // Pero si abrazan el rect VISIBLE de la foto (imagen rectangular simple), sí.
    const simple = base({ iw: 100, ih: 50, w: 100, h: 100, ajuste: "contain", caja: { x: 0, y: 25, w: 100, h: 50 } });
    const r = recorteLateral(simple, "der", 80)!;
    expect(r).not.toBeNull();
    expect(r.y).toBe(25);
    expect(r.h).toBe(50);
    expect(r.w).toBe(80);
    expect(r.crop.cw).toBeCloseTo(0.8);
  });

  it("sin bitmap no hay gesto", () => {
    expect(recorteLateral(base({ iw: 0, ih: 0 }), "der", 300)).toBeNull();
  });

  it("el resultado siempre es un crop válido del contrato {cx,cy,cw,ch} ∈ [0,1]", () => {
    for (const lado of ["izq", "der", "arriba", "abajo"] as const) {
      for (const borde of [-1000, -10, 0, 150, 400, 1000]) {
        const r = recorteLateral(base({ flipH: lado === "izq", crop: { cx: 0.1, cy: 0.1, cw: 0.8, ch: 0.8 } }), lado, borde);
        if (!r) continue;
        expect(r.crop.cx).toBeGreaterThanOrEqual(0);
        expect(r.crop.cy).toBeGreaterThanOrEqual(0);
        expect(r.crop.cx + r.crop.cw).toBeLessThanOrEqual(1 + 1e-9);
        expect(r.crop.cy + r.crop.ch).toBeLessThanOrEqual(1 + 1e-9);
        expect(r.w).toBeGreaterThan(0);
        expect(r.h).toBeGreaterThan(0);
      }
    }
  });
});

describe("localADoc / docALocal (coords locales de capa con rotación)", () => {
  it("con rotación 0 es una traslación", () => {
    expect(localADoc(100, 50, 0, 10, 20)).toEqual({ x: 110, y: 70 });
    expect(docALocal(100, 50, 0, 110, 70)).toEqual({ x: 10, y: 20 });
  });

  it("rota alrededor del origen de la capa (90°: el eje X local apunta hacia abajo)", () => {
    const p = localADoc(100, 50, 90, 10, 0);
    expect(p.x).toBeCloseTo(100);
    expect(p.y).toBeCloseTo(60);
  });

  it("ida y vuelta exacta con rotación arbitraria", () => {
    const d = localADoc(33, -7, 37.5, 12.3, -4.2);
    const l = docALocal(33, -7, 37.5, d.x, d.y);
    expect(l.x).toBeCloseTo(12.3, 9);
    expect(l.y).toBeCloseTo(-4.2, 9);
  });
});

describe("recortarCaja (recorte de RECUADRO para objetos sin píxeles)", () => {
  const caja = { x: 100, y: 100, w: 200, h: 100 };

  it("arrastrar el borde DERECHO/INFERIOR cambia solo el tamaño (el origen queda fijo)", () => {
    expect(recortarCaja(caja, "e", -50, 0)).toEqual({ x: 100, y: 100, w: 150, h: 100 });
    expect(recortarCaja(caja, "s", 0, 40)).toEqual({ x: 100, y: 100, w: 200, h: 140 });
  });

  it("arrastrar el borde IZQUIERDO/SUPERIOR mueve el origen y el borde opuesto queda fijo", () => {
    // Izquierda +30: x avanza a 130 y el borde derecho (300) no se mueve => w = 170.
    expect(recortarCaja(caja, "w", 30, 0)).toEqual({ x: 130, y: 100, w: 170, h: 100 });
    // Arriba +20: y baja a 120 y el borde inferior (200) no se mueve => h = 80.
    expect(recortarCaja(caja, "n", 0, 20)).toEqual({ x: 100, y: 120, w: 200, h: 80 });
  });

  it("una esquina mueve los DOS bordes que la tocan", () => {
    // nw: izquierda +10 y arriba +10 (bordes der=300 / inf=200 fijos).
    expect(recortarCaja(caja, "nw", 10, 10)).toEqual({ x: 110, y: 110, w: 190, h: 90 });
  });

  it("no colapsa por debajo del mínimo y el borde opuesto NO se cruza", () => {
    // Empujar la izquierda muy a la derecha: x se topa en der - MIN y w = MIN.
    const r = recortarCaja(caja, "w", 1000, 0);
    expect(r.w).toBe(MIN_CAJA_PX);
    expect(r.x).toBe(300 - MIN_CAJA_PX); // pegado al borde derecho fijo
    // Empujar el borde derecho hacia dentro hasta colapsar: w se topa en MIN.
    expect(recortarCaja(caja, "e", -1000, 0).w).toBe(MIN_CAJA_PX);
  });

  it("'mover' desplaza el recuadro entero sin cambiar tamaño", () => {
    expect(recortarCaja(caja, "mover", 15, -5)).toEqual({ x: 115, y: 95, w: 200, h: 100 });
  });
});

describe("recortarCajaRotada (recorte a lo largo de los ejes locales del objeto)", () => {
  const caja = { x: 100, y: 100, w: 200, h: 20 }; // p. ej. una línea (rotada se ve vertical)

  it("sin rotación es idéntico a recortarCaja", () => {
    expect(recortarCajaRotada(caja, 0, "e", -50, 0)).toEqual(recortarCaja(caja, "e", -50, 0));
    expect(recortarCajaRotada(caja, 0, "w", 30, 0)).toEqual(recortarCaja(caja, "w", 30, 0));
  });

  it("rotado 90°: arrastrar el borde local 'e' a lo largo del eje local acorta el largo", () => {
    // A 90° el eje X local apunta hacia ABAJO en el documento. Arrastrar 30px hacia ARRIBA (dy=-30)
    // recorta el extremo local 'e' (el de abajo): largo 200 -> 170, origen fijo.
    const r = recortarCajaRotada(caja, 90, "e", 0, -30);
    expect(r).toMatchObject({ x: 100, y: 100, w: 170, h: 20 });
  });

  it("rotado 90°: el borde local 'w' mueve el origen por el eje local (no por el del documento)", () => {
    // Arrastrar 'w' 30px hacia abajo (dy=+30): el origen se desplaza por el eje local -> en documento
    // baja en Y; el largo se acorta a 170.
    const r = recortarCajaRotada(caja, 90, "w", 0, 30);
    expect(r.w).toBe(170);
    expect(r.x).toBeCloseTo(100, 6);
    expect(r.y).toBeCloseTo(130, 6);
  });
});
