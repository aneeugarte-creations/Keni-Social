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
  const fills: { texto: string; x: number; y: number; tam: number }[] = [];
  let tamActual = 64;
  const ctx = {
    fills,
    canvas: { width: 1080, height: 1080 },
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
    fillText: (t: string, x: number, y: number) => fills.push({ texto: t, x, y, tam: tamActual }),
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
    createLinearGradient: () => ({ addColorStop: () => {} }),
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
