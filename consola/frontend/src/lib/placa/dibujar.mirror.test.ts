import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { dibujarDocumento } from "./dibujar.mjs";

// `dibujar.mjs` (frontend) es un ESPEJO BYTE A BYTE del motor de render del backend, para que la
// previa en vivo del editor coincida EXACTAMENTE con lo que compone el servidor (auto-gen). Este
// guard falla si divergen: al tocar el render hay que actualizar AMBOS (copiar el del backend).
describe("espejo del render de placa", () => {
  const aqui = dirname(fileURLToPath(import.meta.url));
  const espejo = resolve(aqui, "dibujar.mjs");
  const original = resolve(
    aqui,
    "../../../../src/keni_consola/motores/estudio_imagen/render_node/dibujar.mjs",
  );

  it("dibujar.mjs del front es idéntico al del backend (render_node)", () => {
    const a = readFileSync(espejo, "utf-8");
    const b = readFileSync(original, "utf-8");
    expect(a).toBe(b);
  });
});

// Stub mínimo de un contexto canvas-2D que registra las llamadas a `fillText` (y mide texto de
// forma determinista: ancho ∝ nº de caracteres × tamaño). Suficiente para verificar el
// posicionamiento vertical del bloque de texto y el auto-encogido por la CAJA.
function ctxFalso() {
  const fills: { texto: string; x: number; y: number; tam: number; blur: number; sombra: string }[] = [];
  const gradientes: { x0: number; y0: number; x1: number; y1: number; stops: [number, string][] }[] = [];
  let tamActual = 64;
  const ctx = {
    fills,
    gradientes,
    canvas: { width: 1080, height: 1080 },
    shadowColor: "transparent",
    shadowBlur: 0,
    shadowOffsetX: 0,
    shadowOffsetY: 0,
    set font(v: string) {
      const m = /(\d+)px/.exec(v);
      tamActual = m ? Number(m[1]) : tamActual;
    },
    get font() {
      return `${tamActual}px sans`;
    },
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 0,
    lineJoin: "",
    globalAlpha: 1,
    filter: "none",
    letterSpacing: "0px",
    textBaseline: "top",
    textAlign: "left",
    measureText: (t: string) => ({ width: t.length * tamActual * 0.5 }),
    fillText: (t: string, x: number, y: number) =>
      fills.push({ texto: t, x, y, tam: tamActual, blur: ctx.shadowBlur, sombra: ctx.shadowColor }),
    strokeText: () => {},
    save: () => {},
    restore: () => {},
    translate: () => {},
    rotate: () => {},
    scale: () => {},
    beginPath: () => {},
    closePath: () => {},
    moveTo: () => {},
    lineTo: () => {},
    arcTo: () => {},
    ellipse: () => {},
    rect: () => {},
    clip: () => {},
    fill: () => {},
    stroke: () => {},
    fillRect: () => {},
    strokeRect: () => {},
    drawImage: () => {},
    setLineDash: () => {},
    createLinearGradient: (x0: number, y0: number, x1: number, y1: number) => {
      const stops: [number, string][] = [];
      gradientes.push({ x0, y0, x1, y1, stops });
      return { addColorStop: (o: number, c: string) => stops.push([o, c]) };
    },
  };
  return ctx;
}

// Devuelve un documento mínimo (tipado laxo: el render solo necesita formato/fondo/capas).
function docConTexto(extra: Record<string, unknown>): never {
  return {
    version: 1,
    formato: { w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 },
    fondo: { tipo: "color", color: "#000000" },
    capas: [
      {
        id: "t1",
        tipo: "texto",
        x: 100,
        y: 200,
        w: 800,
        h: 0,
        z: 20,
        rotacion: 0,
        opacidad: 1,
        visible: true,
        texto: "HOLA",
        binding: null,
        familia: "Barlow",
        tamano: 100,
        peso: 700,
        color: "#FFFFFF",
        alineacion: "izquierda",
        mayusculas: false,
        interlineado: 1,
        interletra: 0,
        auto_ajuste: { max_lineas: 4, tam_min: 20 },
        sombra: null,
        contorno: null,
        chip: null,
        ancla: "arriba",
        valign: "centro",
        ...extra,
      },
    ],
  } as never;
}

describe("caja de texto y valign en dibujarTexto", () => {
  it("valign 'centro' centra el bloque verticalmente dentro de la caja", () => {
    const ctx = ctxFalso();
    // 1 línea, interlineado 1, tamaño 100 => blockH ≈ 100. Caja [200, 200+400] => centro top = 350.
    dibujarDocumento(ctx as never, { documento: docConTexto({ h: 400, valign: "centro" }), imgs: {}, bindings: {} } as never);
    const fill = ctx.fills.find((f) => f.texto === "HOLA");
    expect(fill).toBeTruthy();
    expect(fill!.y).toBeCloseTo(350, 0);
  });

  it("valign 'abajo' pega el bloque al borde inferior de la caja", () => {
    const ctx = ctxFalso();
    // blockH ≈ 100; caja [200, 600] => top = 200 + 400 - 100 = 500.
    dibujarDocumento(ctx as never, { documento: docConTexto({ h: 400, valign: "abajo" }), imgs: {}, bindings: {} } as never);
    const fill = ctx.fills.find((f) => f.texto === "HOLA");
    expect(fill!.y).toBeCloseTo(500, 0);
  });

  it("el texto ENCOGE si no cabe en el alto de la caja", () => {
    const ctx = ctxFalso();
    // Caja muy baja (h=60) con tamaño 100: el ajuste baja el tamaño hasta caber en alto.
    dibujarDocumento(ctx as never, { documento: docConTexto({ h: 60, valign: "arriba", tamano: 100 }), imgs: {}, bindings: {} } as never);
    const fill = ctx.fills.find((f) => f.texto === "HOLA");
    expect(fill).toBeTruthy();
    expect(fill!.tam).toBeLessThan(100);
    expect(fill!.tam).toBeLessThanOrEqual(60);
  });

  it("camino LEGADO (h<=0): respeta 'ancla' y NO se ve afectado por la caja", () => {
    const ctx = ctxFalso();
    // ancla 'abajo', h=0 => top = y - blockH = 200 - 100 = 100.
    dibujarDocumento(ctx as never, { documento: docConTexto({ h: 0, ancla: "abajo" }), imgs: {}, bindings: {} } as never);
    const fill = ctx.fills.find((f) => f.texto === "HOLA");
    expect(fill!.y).toBeCloseTo(100, 0);
  });
});

describe("sombra de texto: legado vs sombra real (blur/opacidad)", () => {
  it("RETROCOMPAT: sombra plana (sin blur ni opacidad) usa el camino legado (fillText desplazado, sin shadowBlur)", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConTexto({ sombra: { dx: 4, dy: 6, color: "#000000" } }), imgs: {}, bindings: {} } as never,
    );
    // Dos fillText: la sombra desplazada (dx,dy) y el relleno — NINGUNO con shadowBlur activo.
    const conSombraDesplazada = ctx.fills.find((f) => f.texto === "HOLA" && f.x === 104);
    const relleno = ctx.fills.find((f) => f.texto === "HOLA" && f.x === 100);
    expect(conSombraDesplazada).toBeTruthy();
    expect(relleno).toBeTruthy();
    expect(ctx.fills.every((f) => f.blur === 0)).toBe(true);
  });

  it("sombra con desenfoque usa la sombra REAL del canvas (shadowBlur en el fillText del relleno) y la resetea", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConTexto({ sombra: { dx: 0, dy: 0, color: "#000000", desenfoque: 20 } }), imgs: {}, bindings: {} } as never,
    );
    // Glow = un único fillText del relleno con blur activo (dx=dy=0, blur alto).
    const fills = ctx.fills.filter((f) => f.texto === "HOLA");
    expect(fills.length).toBe(1);
    expect(fills[0].blur).toBe(20);
    // Tras pintar, la sombra del canvas queda reseteada (no contamina capas siguientes).
    expect(ctx.shadowBlur).toBe(0);
    expect(ctx.shadowColor).toBe("transparent");
  });

  it("sombra con opacidad<1 activa la sombra real aunque no haya desenfoque", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConTexto({ sombra: { dx: 2, dy: 2, color: "#000000", opacidad: 0.5 } }), imgs: {}, bindings: {} } as never,
    );
    const fills = ctx.fills.filter((f) => f.texto === "HOLA");
    expect(fills.length).toBe(1); // un solo fillText (relleno con sombra real), no el doble legado
  });
});

describe("relleno por degradado en texto", () => {
  it("RETROCOMPAT: sin relleno_degradado NO crea ningún gradiente lineal", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, { documento: docConTexto({}), imgs: {}, bindings: {} } as never);
    expect(ctx.gradientes.length).toBe(0);
  });

  it("con relleno_degradado crea un gradiente con los colores desde/hasta", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConTexto({ relleno_degradado: { desde: "#FF0000", hasta: "#0000FF", angulo: 90 } }), imgs: {}, bindings: {} } as never,
    );
    expect(ctx.gradientes.length).toBe(1);
    expect(ctx.gradientes[0].stops).toEqual([
      [0, "#FF0000"],
      [1, "#0000FF"],
    ]);
  });
});

// Documento mínimo con UN marco (tipado laxo).
function docConMarco(extra: Record<string, unknown>): never {
  return {
    version: 1,
    formato: { w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 },
    fondo: { tipo: "color", color: "#000000" },
    capas: [
      {
        id: "m1", tipo: "marco", x: 100, y: 100, w: 400, h: 200, z: 10,
        rotacion: 0, opacidad: 1, visible: true,
        forma: "rect", relleno: "#FF0000", borde: null, radio: 0,
        ...extra,
      },
    ],
  } as never;
}

describe("marco: degradado de relleno y ángulo de fondo", () => {
  it("marco con relleno_degradado pinta un gradiente con sus colores (en vez del relleno sólido)", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConMarco({ relleno_degradado: { desde: "#111111", hasta: "#222222", angulo: 45 } }), imgs: {}, bindings: {} } as never,
    );
    expect(ctx.gradientes.length).toBe(1);
    expect(ctx.gradientes[0].stops).toEqual([
      [0, "#111111"],
      [1, "#222222"],
    ]);
  });

  it("fondo degradado SIN ángulo es vertical (default 180): el gradiente va de arriba a abajo en el centro", () => {
    const ctx = ctxFalso();
    const doc = {
      version: 1,
      formato: { w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 },
      fondo: { tipo: "degradado", degradado: { desde: "#000000", hasta: "#FFFFFF" } },
      capas: [],
    };
    dibujarDocumento(ctx as never, { documento: doc as never, imgs: {}, bindings: {} } as never);
    const g = ctx.gradientes[0];
    // Default 180 (↓): el eje es vertical (x0≈x1), de y≈0 a y≈h.
    expect(g.x0).toBeCloseTo(g.x1, 5);
    expect(g.y0).toBeCloseTo(0, 5);
    expect(g.y1).toBeCloseTo(1080, 5);
  });

  it("fondo degradado con ángulo 90 (→) es horizontal: el eje va de izquierda a derecha", () => {
    const ctx = ctxFalso();
    const doc = {
      version: 1,
      formato: { w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 },
      fondo: { tipo: "degradado", degradado: { desde: "#000000", hasta: "#FFFFFF", angulo: 90 } },
      capas: [],
    };
    dibujarDocumento(ctx as never, { documento: doc as never, imgs: {}, bindings: {} } as never);
    const g = ctx.gradientes[0];
    expect(g.y0).toBeCloseTo(g.y1, 5);
    expect(g.x0).toBeCloseTo(0, 5);
    expect(g.x1).toBeCloseTo(1080, 5);
  });
});
