/**
 * Tests de los helpers PUROS del motor de video (`lib/video.ts`):
 *  - `composicionVacia` produce un sobre válido del contrato (4 pistas, formato del preset).
 *  - `setClipBase` fija el clip a pantalla completa y la duración.
 *  - `cambiarAspecto` reescala las cajas de los clips de video.
 *  - `setCajaPip` hace clamp dentro del lienzo.
 *  - `setRecorteBase` clampa el trim del clip base (mínimo 1 s) y recalcula la duración.
 *  - `normalizarSegmentos` acepta start/end/text y inicio/fin/texto, y garantiza id estable.
 *  - `formatearTiempo` / `segmentoEn` / `formatearDuracionMs`.
 */
import { describe, expect, it } from "vitest";

import {
  cambiarAspecto,
  composicionVacia,
  formatearDuracionMs,
  formatearTiempo,
  MIN_RECORTE_MS,
  normalizarSegmentos,
  pistaBase,
  pistaPip,
  presetParaAspecto,
  quitarPip,
  segmentoEn,
  setCajaPip,
  setClipBase,
  setClipPip,
  setRecorteBase,
  setReencuadreBase,
  setSubtitulos,
  tituloBorradorPorDefecto,
} from "./video";

describe("composicionVacia", () => {
  it("produce el sobre del contrato (4 pistas, formato del preset 9:16)", () => {
    const doc = composicionVacia("9:16", "claro-sports");
    expect(doc.version).toBe(1);
    expect(doc.marca).toBe("claro-sports");
    expect(doc.formato).toEqual({ w: 1080, h: 1920, fps: 30, preset: "9:16" });
    expect(doc.duracion_ms).toBe(0);
    const ids = doc.pistas.map((p) => p.id).sort();
    expect(ids).toEqual(["base", "overlay", "pip", "subs"]);
    const tipos = new Set(doc.pistas.map((p) => p.tipo));
    expect(tipos).toEqual(new Set(["video", "overlay", "subtitulos"]));
  });

  it("usa el preset correcto por aspecto", () => {
    expect(presetParaAspecto("1:1")).toMatchObject({ w: 1080, h: 1080 });
    expect(presetParaAspecto("16:9")).toMatchObject({ w: 1920, h: 1080 });
    // aspecto desconocido cae al default 9:16
    expect(presetParaAspecto("xx")).toMatchObject({ w: 1080, h: 1920 });
  });
});

describe("setClipBase", () => {
  it("fija el clip base a pantalla completa con la duración dada", () => {
    const doc = setClipBase(composicionVacia("9:16"), "videos/abc.mp4", 30000);
    const clip = pistaBase(doc)?.clips[0];
    expect(doc.duracion_ms).toBe(30000);
    expect(clip).toMatchObject({
      media_id: "videos/abc.mp4",
      x: 0,
      y: 0,
      w: 1080,
      h: 1920,
      ajuste: "cover",
    });
    expect(clip?.foco).toEqual([0.5, 0.5]);
  });

  it("setReencuadreBase actualiza ajuste y foco del clip base", () => {
    let doc = setClipBase(composicionVacia("9:16"), "videos/abc.mp4", 1000);
    doc = setReencuadreBase(doc, { ajuste: "contain", foco: [0.2, 0.8] });
    const clip = pistaBase(doc)?.clips[0];
    expect(clip?.ajuste).toBe("contain");
    expect(clip?.foco).toEqual([0.2, 0.8]);
  });
});

describe("cambiarAspecto", () => {
  it("reescala las cajas de los clips al nuevo lienzo", () => {
    let doc = setClipBase(composicionVacia("9:16"), "videos/a.mp4", 1000); // 1080x1920
    doc = setClipPip(doc, "videos/b.mp4", 1000);
    const pipAntes = pistaPip(doc)!.clips[0];
    doc = cambiarAspecto(doc, "16:9"); // 1920x1080
    expect(doc.formato).toMatchObject({ w: 1920, h: 1080, preset: "16:9" });
    // base llena el lienzo nuevo
    expect(pistaBase(doc)!.clips[0]).toMatchObject({ w: 1920, h: 1080 });
    // pip reescala proporcionalmente (x *= 1920/1080, y *= 1080/1920)
    const pipDespues = pistaPip(doc)!.clips[0];
    expect(pipDespues.x).toBe(Math.round(pipAntes.x * (1920 / 1080)));
    expect(pipDespues.y).toBe(Math.round(pipAntes.y * (1080 / 1920)));
  });
});

describe("PiP", () => {
  it("setClipPip coloca una ventana dentro del lienzo y quitarPip la borra", () => {
    let doc = setClipPip(composicionVacia("9:16"), "videos/p.mp4", 5000);
    const clip = pistaPip(doc)!.clips[0];
    expect(clip.x + clip.w).toBeLessThanOrEqual(1080);
    expect(clip.y + clip.h).toBeLessThanOrEqual(1920);
    doc = quitarPip(doc);
    expect(pistaPip(doc)!.clips).toHaveLength(0);
  });

  it("setCajaPip hace clamp dentro del lienzo", () => {
    let doc = setClipPip(composicionVacia("9:16"), "videos/p.mp4", 5000);
    doc = setCajaPip(doc, { x: 99999, y: -50, w: 99999, h: 200 });
    const clip = pistaPip(doc)!.clips[0];
    expect(clip.w).toBeLessThanOrEqual(1080);
    expect(clip.x).toBeGreaterThanOrEqual(0);
    expect(clip.x + clip.w).toBeLessThanOrEqual(1080);
    expect(clip.y).toBeGreaterThanOrEqual(0);
  });
});

describe("setSubtitulos", () => {
  it("liga el subtitulo_id y mezcla el estilo", () => {
    const doc = setSubtitulos(composicionVacia("9:16"), {
      subtitulo_id: "sub-1",
      estilo: { tam: 80, posicion: "superior" },
    });
    const subs = doc.pistas.find((p) => p.tipo === "subtitulos");
    expect(subs).toMatchObject({ subtitulo_id: "sub-1" });
    expect((subs as { estilo: { tam: number; posicion: string } }).estilo).toMatchObject({
      tam: 80,
      posicion: "superior",
      fuente: "Barlow", // los demás campos del default se conservan
    });
  });
});

describe("normalizarSegmentos", () => {
  it("acepta start/end/text (faster-whisper) y asigna id estable", () => {
    const segs = normalizarSegmentos([
      { start: 0, end: 1.5, text: " Hola " },
      { start: 1.5, end: 3, text: "mundo" },
    ]);
    expect(segs).toHaveLength(2);
    expect(segs[0]).toMatchObject({ id: "seg-0", inicio: 0, fin: 1.5, texto: "Hola" });
    expect(segs[1]).toMatchObject({ id: "seg-1", inicio: 1.5, fin: 3, texto: "mundo" });
  });

  it("acepta inicio/fin/texto y palabras word-level", () => {
    const segs = normalizarSegmentos([
      { id: "x", inicio: 2, fin: 4, texto: "ya es-MX", palabras: [{ start: 2, end: 2.5, word: "ya" }] },
    ]);
    expect(segs[0].id).toBe("x");
    expect(segs[0].palabras).toEqual([{ inicio: 2, fin: 2.5, texto: "ya" }]);
  });

  it("devuelve [] ante entradas no-lista o vacías", () => {
    expect(normalizarSegmentos(null)).toEqual([]);
    expect(normalizarSegmentos(undefined)).toEqual([]);
    expect(normalizarSegmentos("nope")).toEqual([]);
  });
});

describe("tituloBorradorPorDefecto", () => {
  it("incluye el aspecto y la fecha en formato es-MX", () => {
    const t = tituloBorradorPorDefecto("9:16", new Date("2026-06-07T12:00:00"));
    expect(t).toContain("Borrador 9:16");
    expect(t).toContain("07/06/26");
  });

  it("refleja el aspecto recibido", () => {
    expect(tituloBorradorPorDefecto("16:9", new Date("2026-01-02T00:00:00"))).toContain(
      "Borrador 16:9",
    );
  });
});

describe("formatearTiempo / segmentoEn", () => {
  it("formatea segundos a mm:ss.s", () => {
    expect(formatearTiempo(0)).toBe("00:00.0");
    expect(formatearTiempo(65.4)).toBe("01:05.4");
    expect(formatearTiempo(-5)).toBe("00:00.0");
  });

  it("encuentra el segmento activo en un tiempo dado", () => {
    const segs = normalizarSegmentos([
      { inicio: 0, fin: 2, texto: "a" },
      { inicio: 2, fin: 5, texto: "b" },
    ]);
    expect(segmentoEn(segs, 1)?.texto).toBe("a");
    expect(segmentoEn(segs, 3)?.texto).toBe("b");
    expect(segmentoEn(segs, 10)).toBeNull();
  });
});

describe("formatearDuracionMs", () => {
  it("formatea milisegundos a mm:ss (truncando los decimales de segundo)", () => {
    expect(formatearDuracionMs(0)).toBe("00:00");
    expect(formatearDuracionMs(30000)).toBe("00:30");
    expect(formatearDuracionMs(65400)).toBe("01:05");
    expect(formatearDuracionMs(3600000)).toBe("60:00");
  });

  it("trata valores negativos o no finitos como 0", () => {
    expect(formatearDuracionMs(-5000)).toBe("00:00");
    expect(formatearDuracionMs(Number.NaN)).toBe("00:00");
    expect(formatearDuracionMs(Number.POSITIVE_INFINITY)).toBe("00:00");
  });
});

describe("setRecorteBase", () => {
  const doc30 = () => setClipBase(composicionVacia("9:16"), "videos/abc.mp4", 30000);

  it("fija recorte_in/out_ms y recalcula fin_ms del clip y duracion_ms del documento", () => {
    const doc = setRecorteBase(doc30(), 2000, 5000);
    const clip = pistaBase(doc)?.clips[0];
    expect(clip).toMatchObject({ recorte_in_ms: 2000, recorte_out_ms: 5000, fin_ms: 3000 });
    expect(doc.duracion_ms).toBe(3000);
  });

  it("clampa a [0, maxMs] (la duración real del clip)", () => {
    const doc = setRecorteBase(doc30(), -500, 99000, 30000);
    const clip = pistaBase(doc)?.clips[0];
    expect(clip).toMatchObject({ recorte_in_ms: 0, recorte_out_ms: 30000 });
  });

  it("garantiza el mínimo de 1 s entre in y out", () => {
    expect(MIN_RECORTE_MS).toBe(1000);
    const doc = setRecorteBase(doc30(), 29950, 30000, 30000);
    const clip = pistaBase(doc)?.clips[0];
    expect(clip).toMatchObject({ recorte_in_ms: 29000, recorte_out_ms: 30000 });
    expect(doc.duracion_ms).toBe(1000);
  });

  it("sin clip base o sin cambio real devuelve el MISMO objeto (autoguardado por referencia)", () => {
    const vacia = composicionVacia("9:16");
    expect(setRecorteBase(vacia, 0, 5000)).toBe(vacia);
    const doc = doc30();
    expect(setRecorteBase(doc, 0, 30000, 30000)).toBe(doc);
  });
});
