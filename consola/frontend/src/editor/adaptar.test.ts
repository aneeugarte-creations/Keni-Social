import { describe, expect, it } from "vitest";

import { adaptarDocumento } from "./adaptar";
import {
  documentoVacio,
  nuevaCapaImagen,
  nuevaCapaTexto,
  type Capa,
  type CapaGrupo,
  type CapaImagen,
  type CapaTexto,
} from "./documento";
import { PRESETS_FORMATO, type Formato } from "./formatos";

const F45 = PRESETS_FORMATO.find((p) => p.etiqueta === "4:5")!.f;
const F916 = PRESETS_FORMATO.find((p) => p.etiqueta === "9:16")!.f;
const F11 = PRESETS_FORMATO.find((p) => p.etiqueta === "1:1")!.f;
const F169 = PRESETS_FORMATO.find((p) => p.etiqueta === "16:9")!.f;

// Factor uniforme que usa el adaptador: min de los ratios del rectángulo de contenido (lienzo menos
// safe areas) entre destino y origen. Lo recalculamos aquí para asertar la escala sin fijar píxeles.
function factor(orig: Formato, dest: Formato): number {
  const cw = (f: Formato) => f.w - (f.safe_left ?? 0) - (f.safe_right ?? 0);
  const ch = (f: Formato) => f.h - (f.safe_top ?? 0) - (f.safe_bottom ?? 0);
  return Math.min(cw(dest) / cw(orig), ch(dest) / ch(orig));
}

const texto = (out: { capas: Capa[] }) => out.capas.find((c) => c.tipo === "texto") as CapaTexto;

describe("adaptarDocumento", () => {
  it("escala el lienzo al formato destino sin mutar el original", () => {
    const doc = documentoVacio(F45, "uno");
    const out = adaptarDocumento(doc, F916);
    expect(out.formato).toEqual({ ...F916 });
    expect(doc.formato).toEqual(F45);
    expect(out).not.toBe(doc);
  });

  it("re-extiende el hueco de foto a sangre del nuevo lienzo", () => {
    const doc = documentoVacio(F45, "uno");
    doc.capas.push(nuevaCapaImagen("foto", { x: 0, y: 0, w: F45.w, h: F45.h, es_foto: true }));
    const out = adaptarDocumento(doc, F916);
    const foto = out.capas.find((c) => c.tipo === "imagen" && (c as CapaImagen).es_foto) as CapaImagen;
    expect(foto.x).toBe(0);
    expect(foto.y).toBe(0);
    expect(foto.w).toBe(F916.w);
    expect(foto.h).toBe(F916.h);
  });

  it("re-centra horizontalmente lo centrado y escala la fuente por el factor uniforme", () => {
    const doc = documentoVacio(F45, "uno");
    doc.capas.push(nuevaCapaTexto({ x: 240, y: 100, w: 600, h: 120, tamano: 60 }));
    const out = adaptarDocumento(doc, F11);
    const txt = texto(out);
    const k = factor(F45, F11);
    // Centrado en X -> sigue centrado en el destino.
    expect(Math.abs(txt.x + txt.w / 2 - F11.w / 2)).toBeLessThanOrEqual(1);
    // Caja y fuente escaladas por el MISMO factor uniforme (no deforma).
    expect(Math.abs(txt.w - 600 * k)).toBeLessThanOrEqual(1);
    expect(txt.tamano).toBe(Math.round(60 * k));
  });

  it("recoloca el titular al pie DENTRO de la zona segura del formato destino (no bajo la UI de Reels)", () => {
    const doc = documentoVacio(F45, "uno");
    // Titular al pie, dentro de la zona segura del 4:5 (fondo 1200 < 1350-96=1254).
    doc.capas.push(nuevaCapaTexto({ x: 80, y: 1100, w: 600, h: 100, tamano: 50 }));
    const out = adaptarDocumento(doc, F916);
    const txt = texto(out);
    // El 9:16 reserva 220px arriba y 420px abajo: el titular NO debe invadir esas franjas…
    expect(txt.y).toBeGreaterThanOrEqual(F916.safe_top);
    expect(txt.y + txt.h).toBeLessThanOrEqual(F916.h - F916.safe_bottom);
    // …y sigue siendo un titular BAJO (mitad inferior), no recolocado al centro.
    expect(txt.y).toBeGreaterThan(F916.h / 2);
  });

  it("encoge el contenido para caber en la zona segura, más corta, del horizontal 16:9", () => {
    const doc = documentoVacio(F45, "uno");
    doc.capas.push(nuevaCapaTexto({ x: 140, y: 600, w: 800, h: 200, tamano: 80 }));
    const out = adaptarDocumento(doc, F169);
    const txt = texto(out);
    const k = factor(F45, F169); // < 1: el 16:9 tiene mucha menos altura útil
    expect(k).toBeLessThan(1);
    expect(txt.tamano).toBe(Math.round(80 * k));
    // El bloque cabe verticalmente dentro de la zona segura del 16:9.
    expect(txt.y).toBeGreaterThanOrEqual(F169.safe_top - 1);
    expect(txt.y + txt.h).toBeLessThanOrEqual(F169.h - F169.safe_bottom + 1);
  });

  it("escala las propiedades de estilo en px (contorno, interletra) por el factor uniforme", () => {
    const doc = documentoVacio(F45, "uno");
    doc.capas.push(
      nuevaCapaTexto({ x: 80, y: 200, w: 600, h: 160, tamano: 60, interletra: 8, contorno: { color: "#000000", grosor: 12 } }),
    );
    const out = adaptarDocumento(doc, F11);
    const txt = texto(out);
    const k = factor(F45, F11);
    expect(txt.tamano).toBe(Math.round(60 * k));
    expect(txt.interletra).toBe(Math.round(8 * k));
    expect(txt.contorno?.grosor).toBe(Math.round(12 * k));
  });

  it("escala los grupos rígidamente: conserva el layout interno (posiciones relativas) escalado por k", () => {
    const doc = documentoVacio(F45, "uno");
    const grupo: CapaGrupo = {
      ...nuevaCapaTexto({ x: 100, y: 100, w: 400, h: 400 }),
      id: "g1",
      tipo: "grupo",
      capas: [
        nuevaCapaTexto({ x: 120, y: 120, w: 200, h: 80, tamano: 40 }),
        nuevaCapaTexto({ x: 120, y: 300, w: 200, h: 80, tamano: 40 }),
      ],
    } as unknown as CapaGrupo;
    doc.capas.push(grupo);
    const out = adaptarDocumento(doc, F11);
    const g = out.capas.find((c) => c.tipo === "grupo") as CapaGrupo;
    const k = factor(F45, F11);
    expect(g.capas).toHaveLength(2);
    const [a, b] = g.capas as CapaTexto[];
    // Separación vertical entre hijas escalada por k (layout interno conservado, no aplastado).
    expect(Math.abs((b.y - a.y) - 180 * k)).toBeLessThanOrEqual(2);
    // Tamaño de las hijas escalado por k.
    expect(Math.abs(a.w - 200 * k)).toBeLessThanOrEqual(2);
    expect(a.tamano).toBe(Math.round(40 * k));
  });

  it("es idempotente al adaptar al mismo formato", () => {
    const doc = documentoVacio(F45, "uno");
    doc.capas.push(nuevaCapaTexto({ x: 100, y: 200, w: 500, h: 120, tamano: 64 }));
    const out = adaptarDocumento(doc, F45);
    const a = doc.capas.find((c) => c.tipo === "texto") as CapaTexto;
    const b = texto(out);
    expect(b.x).toBe(a.x);
    expect(b.y).toBe(a.y);
    expect(b.w).toBe(a.w);
    expect(b.tamano).toBe(a.tamano);
  });
});
