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

import { MAPA_MEZCLA } from "./dibujar.mjs";

// Stub mínimo de un contexto canvas-2D que registra las llamadas a `fillText` (y mide texto de
// forma determinista: ancho ∝ nº de caracteres × tamaño). Suficiente para verificar el
// posicionamiento vertical del bloque de texto y el auto-encogido por la CAJA.
function ctxFalso() {
  const fills: { texto: string; x: number; y: number; tam: number; blur: number; sombra: string }[] = [];
  const gradientes: { x0: number; y0: number; x1: number; y1: number; r1?: number; tipo: string; stops: [number, string][] }[] = [];
  // Llamadas a drawImage: registramos los argumentos (5 args legado, o 9 con recorte de fuente).
  const drawImages: number[][] = [];
  // Registra las primitivas de path usadas para construir recortes (clip) de imagen.
  const paths: { tipo: "ellipse" | "rect" | "arcTo" | "moveTo" | "lineTo"; args: number[] }[] = [];
  // Rellenos de rectángulo (fondo): registramos el fillStyle activo en cada fillRect.
  const fillRects: { estilo: string; args: number[] }[] = [];
  // Log ORDENADO de trazos de texto (stroke/fill) con el estado de sombra/estilo en ese instante.
  // Permite verificar el ORDEN (contorno DEBAJO del relleno) y que la sombra se resetee a tiempo.
  const ops: { op: "stroke" | "fill"; texto: string; blur: number; sombra: string; estilo: string }[] = [];
  // `globalCompositeOperation` activo en cada `fill()` (para verificar el modo de fusión por capa).
  const gcos: string[] = [];
  // Llamadas a translate (para verificar el PIVOTE de rotación de cada capa).
  const translates: { x: number; y: number }[] = [];
  // Llamadas a scale (para verificar el VOLTEO/flip espejo de imagen/logo).
  const scales: { x: number; y: number }[] = [];
  // Historial de strings `ctx.font` (para verificar el prefijo "italic" de la cursiva).
  const fonts: string[] = [];
  // Llamadas a stroke() con el estado del trazo (para verificar el SUBRAYADO: grosor y color).
  const strokes: { lineWidth: number; estilo: string }[] = [];
  let tamActual = 64;
  const ctx = {
    fills,
    gradientes,
    drawImages,
    paths,
    fillRects,
    ops,
    gcos,
    translates,
    scales,
    fonts,
    strokes,
    canvas: { width: 1080, height: 1080 },
    shadowColor: "transparent",
    shadowBlur: 0,
    shadowOffsetX: 0,
    shadowOffsetY: 0,
    globalCompositeOperation: "source-over",
    set font(v: string) {
      fonts.push(v);
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
    fillText: (t: string, x: number, y: number) => {
      fills.push({ texto: t, x, y, tam: tamActual, blur: ctx.shadowBlur, sombra: ctx.shadowColor });
      ops.push({ op: "fill", texto: t, blur: ctx.shadowBlur, sombra: ctx.shadowColor, estilo: String(ctx.fillStyle) });
    },
    strokeText: (t: string) => {
      ops.push({ op: "stroke", texto: t, blur: ctx.shadowBlur, sombra: ctx.shadowColor, estilo: String(ctx.strokeStyle) });
    },
    save: () => {},
    restore: () => {},
    translate: (x: number, y: number) => translates.push({ x, y }),
    rotate: () => {},
    scale: (x: number, y: number) => scales.push({ x, y }),
    beginPath: () => {},
    closePath: () => {},
    moveTo: (...args: number[]) => paths.push({ tipo: "moveTo", args }),
    lineTo: (...args: number[]) => paths.push({ tipo: "lineTo", args }),
    arcTo: (...args: number[]) => paths.push({ tipo: "arcTo", args }),
    ellipse: (...args: number[]) => paths.push({ tipo: "ellipse", args }),
    rect: (...args: number[]) => paths.push({ tipo: "rect", args }),
    clip: () => {},
    fill: () => { gcos.push(String(ctx.globalCompositeOperation)); },
    stroke: () => { strokes.push({ lineWidth: ctx.lineWidth, estilo: String(ctx.strokeStyle) }); },
    fillRect: (...args: number[]) => fillRects.push({ estilo: String(ctx.fillStyle), args }),
    strokeRect: () => {},
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    drawImage: (_img: unknown, ...args: number[]) => { drawImages.push(args); },
    setLineDash: () => {},
    createLinearGradient: (x0: number, y0: number, x1: number, y1: number) => {
      const stops: [number, string][] = [];
      gradientes.push({ x0, y0, x1, y1, stops, tipo: "lineal" });
      return { addColorStop: (o: number, c: string) => stops.push([o, c]) };
    },
    // Gradiente RADIAL: registra el centro/radio externo y sus paradas (mismo shape que el lineal,
    // con `tipo: "radial"`), para verificar lineal-vs-radial en el render.
    createRadialGradient: (x0: number, y0: number, _r0: number, x1: number, y1: number, r1: number) => {
      const stops: [number, string][] = [];
      gradientes.push({ x0, y0, x1, y1, r1, stops, tipo: "radial" });
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

describe("mayúsculas (aA) en dibujarTexto", () => {
  it("transforma EN RENDER con locale español (toLocaleUpperCase('es')) antes de pintar", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, {
      documento: docConTexto({ texto: "hola ñandú", mayusculas: true }),
      imgs: {},
      bindings: {},
    } as never);
    // El documento conserva el texto crudo; lo PINTADO va en mayúsculas (Ñ/Ú incluidas).
    expect(ctx.fills.find((f) => f.texto === "HOLA ÑANDÚ")).toBeTruthy();
    expect(ctx.fills.find((f) => f.texto === "hola ñandú")).toBeFalsy();
  });

  it("sin `mayusculas` el texto se pinta tal cual (default retrocompatible)", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, {
      documento: docConTexto({ texto: "hola ñandú", mayusculas: false }),
      imgs: {},
      bindings: {},
    } as never);
    expect(ctx.fills.find((f) => f.texto === "hola ñandú")).toBeTruthy();
  });
});

describe("visibilidad: ayuda de edición, NO afecta a la imagen final", () => {
  it("PREVIA (sin final): una capa visible:false NO se pinta", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, { documento: docConTexto({ visible: false }), imgs: {}, bindings: {} } as never);
    expect(ctx.fills.find((f) => f.texto === "HOLA")).toBeFalsy();
  });

  it("FINAL (final:true): una capa visible:false SÍ se pinta (el ocultar es solo para editar)", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, { documento: docConTexto({ visible: false }), imgs: {}, bindings: {}, final: true } as never);
    expect(ctx.fills.find((f) => f.texto === "HOLA")).toBeTruthy();
  });

  it("FINAL: una capa GRUPO oculta NO esconde sus hijas en la imagen final", () => {
    const docGrupoOculto = {
      version: 1,
      formato: { w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 },
      fondo: { tipo: "color", color: "#000000" },
      capas: [
        {
          id: "g1",
          tipo: "grupo",
          x: 0, y: 0, w: 1080, h: 1080, z: 10,
          rotacion: 0, opacidad: 1,
          visible: false, // grupo OCULTO en edición
          capas: [
            {
              id: "t1", tipo: "texto", x: 100, y: 200, w: 800, h: 0, z: 20,
              rotacion: 0, opacidad: 1, visible: true,
              texto: "HOLA", binding: null, familia: "Barlow", tamano: 100, peso: 700,
              color: "#FFFFFF", alineacion: "izquierda", mayusculas: false,
              interlineado: 1, interletra: 0, auto_ajuste: { max_lineas: 4, tam_min: 20 },
              sombra: null, contorno: null, chip: null, ancla: "arriba", valign: "centro",
            },
          ],
        },
      ],
    };
    const ctxPrevia = ctxFalso();
    dibujarDocumento(ctxPrevia as never, { documento: docGrupoOculto as never, imgs: {}, bindings: {} } as never);
    expect(ctxPrevia.fills.find((f) => f.texto === "HOLA")).toBeFalsy(); // oculto en edición

    const ctxFinal = ctxFalso();
    dibujarDocumento(ctxFinal as never, { documento: docGrupoOculto as never, imgs: {}, bindings: {}, final: true } as never);
    expect(ctxFinal.fills.find((f) => f.texto === "HOLA")).toBeTruthy(); // visible en el final
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

describe("orden sombra + contorno en texto (sombra real)", () => {
  it("con sombra real Y contorno: contorno DEBAJO del relleno, con la sombra solo en el contorno", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      {
        documento: docConTexto({
          sombra: { dx: 0, dy: 0, color: "#000000", desenfoque: 20 },
          contorno: { grosor: 6, color: "#00FF00" },
        }),
        imgs: {},
        bindings: {},
      } as never,
    );
    const ops = ctx.ops.filter((o) => o.texto === "HOLA");
    // Exactamente: 1 stroke (contorno) y luego 1 fill (relleno).
    expect(ops.map((o) => o.op)).toEqual(["stroke", "fill"]);
    // La sombra la proyecta el contorno (blur activo); el relleno va SIN sombra (reseteada).
    expect(ops[0].blur).toBe(20);
    expect(ops[1].blur).toBe(0);
    expect(ops[1].sombra).toBe("transparent");
  });

  it("con sombra real SIN contorno: un único relleno con la sombra (glow) y reset posterior", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConTexto({ sombra: { dx: 0, dy: 0, color: "#000000", desenfoque: 20 } }), imgs: {}, bindings: {} } as never,
    );
    const ops = ctx.ops.filter((o) => o.texto === "HOLA");
    expect(ops.map((o) => o.op)).toEqual(["fill"]);
    expect(ops[0].blur).toBe(20);
    expect(ctx.shadowBlur).toBe(0);
  });

  it("camino LEGADO con contorno: contorno DEBAJO del relleno (stroke antes que el fill final)", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConTexto({ contorno: { grosor: 6, color: "#00FF00" } }), imgs: {}, bindings: {} } as never,
    );
    const ops = ctx.ops.filter((o) => o.texto === "HOLA");
    expect(ops.map((o) => o.op)).toEqual(["stroke", "fill"]);
  });
});

describe("hexRGBA respeta el alfa de 8 dígitos (#RRGGBBAA)", () => {
  it("sombra real con color de 8 dígitos: el par alfa multiplica la opacidad", () => {
    const ctx = ctxFalso();
    // #00000080 => alfa 0x80/255 ≈ 0.5; opacidad 0.5 => rgba final con alfa ≈ 0.25.
    dibujarDocumento(
      ctx as never,
      { documento: docConTexto({ sombra: { dx: 0, dy: 0, color: "#00000080", opacidad: 0.5 } }), imgs: {}, bindings: {} } as never,
    );
    const op = ctx.ops.find((o) => o.texto === "HOLA");
    expect(op).toBeTruthy();
    // El shadowColor (registrado como `sombra`) debe llevar el alfa combinado (~0.25), no 0.5.
    const m = /rgba\(0,0,0,([0-9.]+)\)/.exec(op!.sombra);
    expect(m).toBeTruthy();
    expect(Number(m![1])).toBeCloseTo(0.25, 2);
  });

  it("overlay inferior con color de 8 dígitos atenúa el alfa máximo de la rampa", () => {
    const ctx = ctxFalso();
    const doc = {
      version: 1,
      formato: { w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 },
      fondo: { tipo: "color", color: "#000000" },
      capas: [
        { id: "ov", tipo: "overlay", x: 0, y: 0, w: 1080, h: 1080, z: 1, rotacion: 0, opacidad: 1, visible: true, color: "#11131580", alto_frac: 0.5, alpha: 255 },
      ],
    };
    dibujarDocumento(ctx as never, { documento: doc as never, imgs: {}, bindings: {} } as never);
    const g = ctx.gradientes[ctx.gradientes.length - 1];
    // Última parada (t=1): alfa = (255/255) * (0x80/255) ≈ 0.502, no 1.
    const ultima = g.stops[g.stops.length - 1][1];
    const m = /rgba\(\d+,\d+,\d+,([0-9.]+)\)/.exec(ultima);
    expect(Number(m![1])).toBeCloseTo(0.502, 2);
  });
});

describe("texto curvo (texto en arco)", () => {
  it("RETROCOMPAT: sin `curva` el texto se dibuja recto (un solo fillText con la palabra entera)", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, { documento: docConTexto({}), imgs: {}, bindings: {} } as never);
    // Camino legado: la línea completa "HOLA" se pinta de una sola vez.
    const fills = ctx.fills.filter((f) => f.texto === "HOLA");
    expect(fills.length).toBe(1);
  });

  it("con `curva` el texto se dibuja GLYPH a GLYPH sobre el arco (un fillText por carácter)", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConTexto({ curva: { radio: 600 } }), imgs: {}, bindings: {} } as never,
    );
    // Una llamada por carácter de "HOLA" (4), no la línea entera.
    const porGlyph = ctx.fills.filter((f) => ["H", "O", "L", "A"].includes(f.texto));
    expect(porGlyph.length).toBe(4);
    expect(ctx.fills.some((f) => f.texto === "HOLA")).toBe(false);
  });

  it("`curva.radio` 0 (o ausente) NO activa el arco: sigue el camino recto", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConTexto({ curva: { radio: 0 } }), imgs: {}, bindings: {} } as never,
    );
    expect(ctx.fills.filter((f) => f.texto === "HOLA").length).toBe(1);
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

// Documento mínimo con UNA capa imagen (tipado laxo). `img` se inyecta luego en `imgs[objeto]`.
function docConImagen(extra: Record<string, unknown>): never {
  return {
    version: 1,
    formato: { w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 },
    fondo: { tipo: "color", color: "#000000" },
    capas: [
      {
        id: "i1", tipo: "imagen", x: 100, y: 100, w: 400, h: 400, z: 5,
        rotacion: 0, opacidad: 1, visible: true,
        objeto: "foto.png", ajuste: "cover", foco: [0.5, 0.5], zoom: 1, filtros: null,
        ...extra,
      },
    ],
  } as never;
}

describe("forma de la imagen: recorte rect (default) vs elipse", () => {
  const img = { width: 800, height: 600 } as never;

  it("RETROCOMPAT: imagen sin forma recorta con rect (mismo clip de siempre), sin ellipse", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, { documento: docConImagen({}), imgs: { "foto.png": img }, bindings: {} } as never);
    // Recorte rectangular en la caja (100,100,400,400) y NINGUNA elipse.
    expect(ctx.paths.some((p) => p.tipo === "rect" && p.args.join(",") === "100,100,400,400")).toBe(true);
    expect(ctx.paths.some((p) => p.tipo === "ellipse")).toBe(false);
  });

  it("forma 'elipse' recorta con una elipse centrada en la caja (no rect)", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConImagen({ forma: "elipse" }), imgs: { "foto.png": img }, bindings: {} } as never,
    );
    // Elipse inscrita: centro (300,300), radios (200,200).
    const el = ctx.paths.find((p) => p.tipo === "ellipse");
    expect(el).toBeTruthy();
    expect(el!.args.slice(0, 4)).toEqual([300, 300, 200, 200]);
    // Con elipse NO se usa el rect de recorte de la caja.
    expect(ctx.paths.some((p) => p.tipo === "rect" && p.args.join(",") === "100,100,400,400")).toBe(false);
  });

  it("forma rect con radio>0 redondea las esquinas (arcTo) en vez de rect plano", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConImagen({ radio: 40 }), imgs: { "foto.png": img }, bindings: {} } as never,
    );
    expect(ctx.paths.some((p) => p.tipo === "arcTo")).toBe(true);
    expect(ctx.paths.some((p) => p.tipo === "rect" && p.args.join(",") === "100,100,400,400")).toBe(false);
  });

  it("forma 'triangulo' recorta con un polígono (moveTo + 2 lineTo en la caja), sin rect ni elipse", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConImagen({ forma: "triangulo" }), imgs: { "foto.png": img }, bindings: {} } as never,
    );
    // Vértices del triángulo en la caja (100,100,400,400): cima (300,100), base-der (500,500), base-izq (100,500).
    const mv = ctx.paths.find((p) => p.tipo === "moveTo");
    expect(mv!.args).toEqual([300, 100]);
    const lineas = ctx.paths.filter((p) => p.tipo === "lineTo");
    expect(lineas.some((p) => p.args.join(",") === "500,500")).toBe(true);
    expect(lineas.some((p) => p.args.join(",") === "100,500")).toBe(true);
    expect(ctx.paths.some((p) => p.tipo === "rect" && p.args.join(",") === "100,100,400,400")).toBe(false);
    expect(ctx.paths.some((p) => p.tipo === "ellipse")).toBe(false);
  });

  it("forma 'estrella' recorta con 10 vértices (5 puntas) y nada de rect/elipse", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConImagen({ forma: "estrella" }), imgs: { "foto.png": img }, bindings: {} } as never,
    );
    const verts = ctx.paths.filter((p) => p.tipo === "moveTo" || p.tipo === "lineTo");
    expect(verts.length).toBe(10);
    expect(ctx.paths.some((p) => p.tipo === "rect" && p.args.join(",") === "100,100,400,400")).toBe(false);
  });
});

describe("volteo (flip) horizontal/vertical de imagen", () => {
  const img = { width: 800, height: 600 } as never;

  it("RETROCOMPAT: sin flip NO aplica ningún scale espejo", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, { documento: docConImagen({}), imgs: { "foto.png": img }, bindings: {} } as never);
    expect(ctx.scales.length).toBe(0);
  });

  it("flip_h aplica scale(-1,1) alrededor del CENTRO de la caja (translate centro, scale, vuelta)", () => {
    const ctx = ctxFalso();
    // Caja (100,100,400,400) => centro (300,300).
    dibujarDocumento(ctx as never, { documento: docConImagen({ flip_h: true }), imgs: { "foto.png": img }, bindings: {} } as never);
    expect(ctx.scales).toContainEqual({ x: -1, y: 1 });
    expect(ctx.translates).toContainEqual({ x: 300, y: 300 });
    expect(ctx.translates).toContainEqual({ x: -300, y: -300 });
  });

  it("flip_v aplica scale(1,-1)", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, { documento: docConImagen({ flip_v: true }), imgs: { "foto.png": img }, bindings: {} } as never);
    expect(ctx.scales).toContainEqual({ x: 1, y: -1 });
  });

  it("flip_h + flip_v aplica scale(-1,-1)", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, { documento: docConImagen({ flip_h: true, flip_v: true }), imgs: { "foto.png": img }, bindings: {} } as never);
    expect(ctx.scales).toContainEqual({ x: -1, y: -1 });
  });
});

describe("overlay posicionable: la banda se pinta DENTRO de la caja de la capa", () => {
  function docConOverlay(extra: Record<string, unknown>): never {
    return {
      version: 1,
      formato: { w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 },
      fondo: { tipo: "color", color: "#000000" },
      capas: [
        { id: "ov", tipo: "overlay", x: 0, y: 0, w: 1080, h: 1080, z: 1, rotacion: 0, opacidad: 1, visible: true, color: "#111315", alto_frac: 0.5, alpha: 255, ...extra },
      ],
    } as never;
  }

  it("RETROCOMPAT: overlay a (0,0,W,H) pinta la banda histórica (0, H-band, W, band)", () => {
    const ctx = ctxFalso();
    // band = floor(1080 * 0.5) = 540 => fillRect(0, 540, 1080, 540).
    dibujarDocumento(ctx as never, { documento: docConOverlay({}), imgs: {}, bindings: {} } as never);
    const fr = ctx.fillRects[ctx.fillRects.length - 1];
    expect(fr.args).toEqual([0, 540, 1080, 540]);
  });

  it("overlay MOVIDO usa su (x,y,w,h): la banda cae dentro de la caja (x, y+h-band, w, band)", () => {
    const ctx = ctxFalso();
    // Caja (200,300,600,400), band = floor(400*0.5)=200 => fillRect(200, 300+400-200, 600, 200).
    dibujarDocumento(ctx as never, { documento: docConOverlay({ x: 200, y: 300, w: 600, h: 400 }), imgs: {}, bindings: {} } as never);
    const fr = ctx.fillRects[ctx.fillRects.length - 1];
    expect(fr.args).toEqual([200, 500, 600, 200]);
  });
});

describe("fondo transparente (#RRGGBBAA con alfa 00)", () => {
  it("un fondo color transparente NO pinta color opaco: el fillRect del fondo va con alfa 00", () => {
    const ctx = ctxFalso();
    const doc = {
      version: 1,
      formato: { w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 },
      fondo: { tipo: "color", color: "#00000000" },
      capas: [],
    };
    dibujarDocumento(ctx as never, { documento: doc as never, imgs: {}, bindings: {} } as never);
    // El único fillRect (el del fondo) usa el color transparente como fillStyle (no un opaco).
    expect(ctx.fillRects.length).toBe(1);
    expect(ctx.fillRects[0].estilo).toBe("#00000000");
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

describe("recorte (crop) no destructivo de la fuente", () => {
  const img = { width: 800, height: 600 } as never;

  it("RETROCOMPAT: sin crop el drawImage usa 5 args (toda la fuente) — idéntico al legado", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, { documento: docConImagen({}), imgs: { "foto.png": img }, bindings: {} } as never);
    expect(ctx.drawImages.length).toBe(1);
    // 9 args: sx,sy,sw,sh = fuente completa (0,0,800,600).
    expect(ctx.drawImages[0].slice(0, 4)).toEqual([0, 0, 800, 600]);
  });

  it("con crop recorta la FUENTE: el sub-rect [sx,sy,sw,sh] sale de las fracciones × dims de la imagen", () => {
    const ctx = ctxFalso();
    // crop centrado: cx=0.25, cy=0.1, cw=0.5, ch=0.5 sobre 800×600 => sx=200, sy=60, sw=400, sh=300.
    dibujarDocumento(
      ctx as never,
      { documento: docConImagen({ crop: { cx: 0.25, cy: 0.1, cw: 0.5, ch: 0.5 } }), imgs: { "foto.png": img }, bindings: {} } as never,
    );
    expect(ctx.drawImages.length).toBe(1);
    expect(ctx.drawImages[0].slice(0, 4)).toEqual([200, 60, 400, 300]);
  });
});

describe("degradado radial vs lineal y multi-stop", () => {
  it("fondo degradado LINEAL (default) usa createLinearGradient (no radial)", () => {
    const ctx = ctxFalso();
    const doc = {
      version: 1,
      formato: { w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 },
      fondo: { tipo: "degradado", degradado: { desde: "#000000", hasta: "#FFFFFF" } },
      capas: [],
    };
    dibujarDocumento(ctx as never, { documento: doc as never, imgs: {}, bindings: {} } as never);
    expect(ctx.gradientes[0].tipo).toBe("lineal");
  });

  it("fondo degradado RADIAL usa createRadialGradient centrado en la caja", () => {
    const ctx = ctxFalso();
    const doc = {
      version: 1,
      formato: { w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 },
      fondo: { tipo: "degradado", degradado: { desde: "#000000", hasta: "#FFFFFF", tipo: "radial" } },
      capas: [],
    };
    dibujarDocumento(ctx as never, { documento: doc as never, imgs: {}, bindings: {} } as never);
    const g = ctx.gradientes[0];
    expect(g.tipo).toBe("radial");
    expect(g.x1).toBeCloseTo(540, 5);
    expect(g.y1).toBeCloseTo(540, 5);
  });

  it("degradado multi-stop emite TODAS las paradas (no solo desde/hasta)", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      {
        documento: docConMarco({
          relleno_degradado: {
            desde: "#000000",
            hasta: "#FFFFFF",
            stops: [
              { pos: 0, color: "#FF0000" },
              { pos: 0.5, color: "#00FF00" },
              { pos: 1, color: "#0000FF" },
            ],
          },
        }),
        imgs: {},
        bindings: {},
      } as never,
    );
    expect(ctx.gradientes.length).toBe(1);
    expect(ctx.gradientes[0].stops).toEqual([
      [0, "#FF0000"],
      [0.5, "#00FF00"],
      [1, "#0000FF"],
    ]);
  });
});

describe("filtro duotono", () => {
  const img = { width: 800, height: 600 } as never;

  it("RETROCOMPAT: sin duotono NO añade fills de tinte (multiply/lighten) sobre la imagen", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, { documento: docConImagen({}), imgs: { "foto.png": img }, bindings: {} } as never);
    // El globalCompositeOperation nunca pasa por "multiply"/"lighten" del tinte.
    expect(ctx.gcos.includes("multiply")).toBe(false);
    expect(ctx.gcos.includes("lighten")).toBe(false);
  });

  it("con duotono aplica DOS tintes: multiply (luz) y lighten (sombra) tras la imagen", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      {
        documento: docConImagen({ filtros: { duotono: { sombra: "#111315", luz: "#E30613" } } }),
        imgs: { "foto.png": img },
        bindings: {},
      } as never,
    );
    // Dos fill() del tinte: uno en multiply, otro en lighten.
    expect(ctx.gcos.includes("multiply")).toBe(true);
    expect(ctx.gcos.includes("lighten")).toBe(true);
  });
});

describe("modo de fusión (mezcla) por capa", () => {
  it("el mapa etiqueta->GCO cubre los modos y traduce 'normal' a source-over", () => {
    expect(MAPA_MEZCLA).toMatchObject({
      normal: "source-over",
      multiplicar: "multiply",
      trama: "screen",
      superponer: "overlay",
      aclarar: "lighten",
      oscurecer: "darken",
    });
  });

  it("RETROCOMPAT: capa SIN mezcla pinta con source-over (no cambia el render)", () => {
    const ctx = ctxFalso();
    // Marco con relleno sólido => un fill(); la capa no trae `mezcla`.
    dibujarDocumento(ctx as never, { documento: docConMarco({}), imgs: {}, bindings: {} } as never);
    expect(ctx.gcos.length).toBeGreaterThan(0);
    expect(ctx.gcos.every((g) => g === "source-over")).toBe(true);
  });

  it("capa con mezcla 'multiplicar' fija el globalCompositeOperation a 'multiply' al pintarla", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, { documento: docConMarco({ mezcla: "multiplicar" }), imgs: {}, bindings: {} } as never);
    expect(ctx.gcos).toContain("multiply");
  });

  it("capa con mezcla 'normal' explícita sigue siendo source-over (no la activa)", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, { documento: docConMarco({ mezcla: "normal" }), imgs: {}, bindings: {} } as never);
    expect(ctx.gcos.every((g) => g === "source-over")).toBe(true);
  });
});

// El PIVOTE de rotación debe coincidir con el editor (Konva/CapaNodo): esquina superior izquierda
// (x,y) para todas las capas, salvo el marco ELIPSE (Konva lo posiciona por su centro). Antes el
// render usaba SIEMPRE el centro: una línea horizontal rotada 90° aterrizaba en el centro del
// lienzo en vez de a un lado (el marco salía como una "+").
describe("pivote de rotación (espejo de Konva)", () => {
  it("capa NO-elipse rota alrededor de su esquina superior izquierda (x,y)", () => {
    const ctx = ctxFalso();
    // Marco en (100,100) 400×200, rotado 90°. Pivote esperado = (x,y) = (100,100).
    dibujarDocumento(ctx as never, { documento: docConMarco({ rotacion: 90 }), imgs: {}, bindings: {} } as never);
    expect(ctx.translates[0]).toEqual({ x: 100, y: 100 });
    expect(ctx.translates[1]).toEqual({ x: -100, y: -100 });
  });

  it("marco ELIPSE rota alrededor de su centro (como Konva, que lo posiciona por el centro)", () => {
    const ctx = ctxFalso();
    // Elipse en (100,100) 400×200, rotada 45°. Pivote esperado = centro = (300,200).
    dibujarDocumento(
      ctx as never,
      { documento: docConMarco({ forma: "elipse", rotacion: 45 }), imgs: {}, bindings: {} } as never,
    );
    expect(ctx.translates[0]).toEqual({ x: 300, y: 200 });
    expect(ctx.translates[1]).toEqual({ x: -300, y: -200 });
  });

  it("sin rotación no toca translate (no hay cambio de pivote)", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, { documento: docConMarco({ rotacion: 0 }), imgs: {}, bindings: {} } as never);
    expect(ctx.translates).toHaveLength(0);
  });
});

import { FAMILIAS_CON_CURSIVA, tieneCursiva } from "./dibujar.mjs";

describe("cursiva (itálica real, nunca sintética)", () => {
  it("el catálogo de familias con itálica es el esperado y `tieneCursiva` lo refleja", () => {
    expect(FAMILIAS_CON_CURSIVA).toEqual(["Barlow", "Barlow Condensed", "Montserrat", "Lora", "Exo 2", "Lato", "Poppins"]);
    expect(tieneCursiva("Barlow")).toBe(true);
    expect(tieneCursiva("Lora")).toBe(true);
    expect(tieneCursiva("Poppins")).toBe(true);
    // Sin cara itálica registrada: ni Anton/Oswald/Archivo Black, ni las gemelas OFL solo-upright
    // (Roboto Condensed/Mulish/Nunito Sans), ni una tipografía de marca.
    expect(tieneCursiva("Anton")).toBe(false);
    expect(tieneCursiva("Oswald")).toBe(false);
    expect(tieneCursiva("Archivo Black")).toBe(false);
    expect(tieneCursiva("Roboto Condensed")).toBe(false);
    expect(tieneCursiva("Mulish")).toBe(false);
    expect(tieneCursiva("Nunito Sans")).toBe(false);
    expect(tieneCursiva("Mi Fuente De Marca")).toBe(false);
  });

  it("capa con `cursiva` en familia CON itálica (Barlow) pone 'italic' en el font del canvas", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, { documento: docConTexto({ cursiva: true }), imgs: {}, bindings: {} } as never);
    expect(ctx.fonts.some((f) => f.startsWith("italic "))).toBe(true);
  });

  it("RETROCOMPAT: sin `cursiva` ningún font lleva 'italic'", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, { documento: docConTexto({}), imgs: {}, bindings: {} } as never);
    expect(ctx.fonts.every((f) => !f.includes("italic"))).toBe(true);
  });

  it("`cursiva` en familia SIN itálica (Anton) se IGNORA: no se sintetizan oblicuas", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      // `familiaReal` identidad para que "Anton" llegue tal cual al dibujante.
      { documento: docConTexto({ cursiva: true, familia: "Anton" }), imgs: {}, bindings: {}, familiaReal: (l: string) => l } as never,
    );
    expect(ctx.fonts.length).toBeGreaterThan(0);
    expect(ctx.fonts.every((f) => !f.includes("italic"))).toBe(true);
  });

  it("la cursiva también viaja al texto CURVO (el fontFor es compartido)", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConTexto({ cursiva: true, curva: { radio: 600 } }), imgs: {}, bindings: {} } as never,
    );
    expect(ctx.fonts.some((f) => f.startsWith("italic "))).toBe(true);
  });
});

describe("subrayado (espejo de la geometría de Konva)", () => {
  // Capa por defecto de `docConTexto`: "HOLA" en (100,200) w=800 h=0, tamaño 100, interlineado 1
  // => top de línea 200, altoLinea 100; subrayado a y = 200 + 100/2 + 100/2 = 300; ancho medido
  // 4×100×0.5 = 200 (stub). Grosor = tam/15; color = relleno.
  it("traza una línea bajo el texto: grosor tam/15, color del relleno, ancho de la línea", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, { documento: docConTexto({ subrayado: true }), imgs: {}, bindings: {} } as never);
    expect(ctx.strokes).toHaveLength(1);
    expect(ctx.strokes[0].lineWidth).toBeCloseTo(100 / 15, 5);
    expect(ctx.strokes[0].estilo).toBe("#FFFFFF");
    expect(ctx.paths.some((p) => p.tipo === "moveTo" && p.args.join(",") === "100,300")).toBe(true);
    expect(ctx.paths.some((p) => p.tipo === "lineTo" && p.args.join(",") === "300,300")).toBe(true);
  });

  it("RETROCOMPAT: sin `subrayado` no se traza nada (cero strokes)", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, { documento: docConTexto({}), imgs: {}, bindings: {} } as never);
    expect(ctx.strokes).toHaveLength(0);
  });

  it("respeta la alineación: centrado, la línea queda centrada en la caja", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConTexto({ subrayado: true, alineacion: "centro" }), imgs: {}, bindings: {} } as never,
    );
    // tx = 100 + 800/2 = 500; ancho 200 => de 400 a 600.
    expect(ctx.paths.some((p) => p.tipo === "moveTo" && p.args.join(",") === "400,300")).toBe(true);
    expect(ctx.paths.some((p) => p.tipo === "lineTo" && p.args.join(",") === "600,300")).toBe(true);
  });

  it("con sombra LEGADA pinta primero la copia desplazada en el color de la sombra", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConTexto({ subrayado: true, sombra: { dx: 4, dy: 6, color: "#000000" } }), imgs: {}, bindings: {} } as never,
    );
    expect(ctx.strokes).toHaveLength(2);
    expect(ctx.strokes[0].estilo).toBe("#000000");
    expect(ctx.strokes[1].estilo).toBe("#FFFFFF");
    expect(ctx.paths.some((p) => p.tipo === "moveTo" && p.args.join(",") === "104,306")).toBe(true);
    expect(ctx.paths.some((p) => p.tipo === "moveTo" && p.args.join(",") === "100,300")).toBe(true);
  });

  it("JUSTIFICADO: las líneas no-últimas se subrayan a todo el ancho de la caja; la última, a su medida", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      {
        // Wrap del stub: "AAAA BBBB CCCC" (700px) + "DDDD" (200px) en caja de 800.
        documento: docConTexto({ subrayado: true, alineacion: "justificado", texto: "AAAA BBBB CCCC DDDD" }),
        imgs: {},
        bindings: {},
      } as never,
    );
    expect(ctx.strokes).toHaveLength(2);
    // Línea 1 (no última): ancho completo de la caja, de x=100 a x=900, en y=300.
    expect(ctx.paths.some((p) => p.tipo === "moveTo" && p.args.join(",") === "100,300")).toBe(true);
    expect(ctx.paths.some((p) => p.tipo === "lineTo" && p.args.join(",") === "900,300")).toBe(true);
    // Línea 2 (última): solo su ancho medido (200), de x=100 a x=300, en y=400.
    expect(ctx.paths.some((p) => p.tipo === "moveTo" && p.args.join(",") === "100,400")).toBe(true);
    expect(ctx.paths.some((p) => p.tipo === "lineTo" && p.args.join(",") === "300,400")).toBe(true);
  });

  it("el texto en ARCO no se subraya (paridad con el editor, que tampoco lo pinta)", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConTexto({ subrayado: true, curva: { radio: 600 } }), imgs: {}, bindings: {} } as never,
    );
    expect(ctx.strokes).toHaveLength(0);
  });
});

describe("tachado (line-through, espejo de la geometría de Konva)", () => {
  // Capa por defecto de `docConTexto`: "HOLA" en (100,200) w=800 h=0, tamaño 100, interlineado 1
  // => top de línea 200, altoLinea 100; tachado a MEDIA altura: y = 200 + 100/2 = 250; ancho
  // medido 4×100×0.5 = 200 (stub). Grosor = tam/15; color = relleno.
  it("traza la línea a media altura: grosor tam/15, color del relleno, ancho de la línea", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, { documento: docConTexto({ tachado: true }), imgs: {}, bindings: {} } as never);
    expect(ctx.strokes).toHaveLength(1);
    expect(ctx.strokes[0].lineWidth).toBeCloseTo(100 / 15, 5);
    expect(ctx.strokes[0].estilo).toBe("#FFFFFF");
    expect(ctx.paths.some((p) => p.tipo === "moveTo" && p.args.join(",") === "100,250")).toBe(true);
    expect(ctx.paths.some((p) => p.tipo === "lineTo" && p.args.join(",") === "300,250")).toBe(true);
  });

  it("RETROCOMPAT: sin `tachado` no se traza nada (cero strokes)", () => {
    const ctx = ctxFalso();
    dibujarDocumento(ctx as never, { documento: docConTexto({}), imgs: {}, bindings: {} } as never);
    expect(ctx.strokes).toHaveLength(0);
  });

  it("COMBINABLE con subrayado: dos trazos, subrayado bajo la línea (300) y tachado a media (250)", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConTexto({ subrayado: true, tachado: true }), imgs: {}, bindings: {} } as never,
    );
    expect(ctx.strokes).toHaveLength(2);
    expect(ctx.paths.some((p) => p.tipo === "moveTo" && p.args.join(",") === "100,300")).toBe(true);
    expect(ctx.paths.some((p) => p.tipo === "moveTo" && p.args.join(",") === "100,250")).toBe(true);
  });

  it("respeta la alineación: centrado, la línea queda centrada en la caja", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConTexto({ tachado: true, alineacion: "centro" }), imgs: {}, bindings: {} } as never,
    );
    // tx = 100 + 800/2 = 500; ancho 200 => de 400 a 600, a media altura (250).
    expect(ctx.paths.some((p) => p.tipo === "moveTo" && p.args.join(",") === "400,250")).toBe(true);
    expect(ctx.paths.some((p) => p.tipo === "lineTo" && p.args.join(",") === "600,250")).toBe(true);
  });

  it("con sombra LEGADA pinta primero la copia desplazada en el color de la sombra", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConTexto({ tachado: true, sombra: { dx: 4, dy: 6, color: "#000000" } }), imgs: {}, bindings: {} } as never,
    );
    expect(ctx.strokes).toHaveLength(2);
    expect(ctx.strokes[0].estilo).toBe("#000000");
    expect(ctx.strokes[1].estilo).toBe("#FFFFFF");
    expect(ctx.paths.some((p) => p.tipo === "moveTo" && p.args.join(",") === "104,256")).toBe(true);
    expect(ctx.paths.some((p) => p.tipo === "moveTo" && p.args.join(",") === "100,250")).toBe(true);
  });

  it("JUSTIFICADO: las líneas no-últimas se tachan a todo el ancho de la caja; la última, a su medida", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      {
        // Wrap del stub: "AAAA BBBB CCCC" (700px) + "DDDD" (200px) en caja de 800.
        documento: docConTexto({ tachado: true, alineacion: "justificado", texto: "AAAA BBBB CCCC DDDD" }),
        imgs: {},
        bindings: {},
      } as never,
    );
    expect(ctx.strokes).toHaveLength(2);
    // Línea 1 (no última): ancho completo de la caja, de x=100 a x=900, en y=250 (media altura).
    expect(ctx.paths.some((p) => p.tipo === "moveTo" && p.args.join(",") === "100,250")).toBe(true);
    expect(ctx.paths.some((p) => p.tipo === "lineTo" && p.args.join(",") === "900,250")).toBe(true);
    // Línea 2 (última): solo su ancho medido (200), de x=100 a x=300, en y=350.
    expect(ctx.paths.some((p) => p.tipo === "moveTo" && p.args.join(",") === "100,350")).toBe(true);
    expect(ctx.paths.some((p) => p.tipo === "lineTo" && p.args.join(",") === "300,350")).toBe(true);
  });

  it("el texto en ARCO no se tacha (paridad con el editor, que tampoco lo pinta)", () => {
    const ctx = ctxFalso();
    dibujarDocumento(
      ctx as never,
      { documento: docConTexto({ tachado: true, curva: { radio: 600 } }), imgs: {}, bindings: {} } as never,
    );
    expect(ctx.strokes).toHaveLength(0);
  });
});
