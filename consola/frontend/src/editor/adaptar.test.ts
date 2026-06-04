import { describe, expect, it } from "vitest";

import { adaptarDocumento } from "./adaptar";
import { documentoVacio, nuevaCapaTexto, type CapaImagen, type CapaTexto } from "./documento";
import { PRESETS_FORMATO } from "./formatos";

const F45 = PRESETS_FORMATO.find((p) => p.etiqueta === "4:5")!.f;
const F916 = PRESETS_FORMATO.find((p) => p.etiqueta === "9:16")!.f;
const F11 = PRESETS_FORMATO.find((p) => p.etiqueta === "1:1")!.f;

describe("adaptarDocumento", () => {
  it("escala el lienzo al formato destino sin mutar el original", () => {
    const doc = documentoVacio(F45, "uno");
    const out = adaptarDocumento(doc, F916);
    expect(out.formato).toEqual({ ...F916 });
    // El original no cambia.
    expect(doc.formato).toEqual(F45);
    expect(out).not.toBe(doc);
  });

  it("re-extiende el hueco de foto a sangre del nuevo lienzo", () => {
    const doc = documentoVacio(F45, "uno");
    const out = adaptarDocumento(doc, F916);
    const foto = out.capas.find((c) => c.tipo === "imagen" && (c as CapaImagen).es_foto) as CapaImagen;
    expect(foto.x).toBe(0);
    expect(foto.y).toBe(0);
    expect(foto.w).toBe(F916.w);
    expect(foto.h).toBe(F916.h);
  });

  it("re-centra horizontalmente lo que estaba centrado", () => {
    const doc = documentoVacio(F45, "uno");
    // Caja centrada en X (1080 ancho, w=600 -> x=240).
    doc.capas.push(nuevaCapaTexto({ x: 240, y: 100, w: 600, h: 120, tamano: 60 }));
    const out = adaptarDocumento(doc, F11); // 1080x1080: sx=1, sy=0.8, s=min=0.8
    const txt = out.capas.find((c) => c.tipo === "texto") as CapaTexto;
    // El texto escala su caja por eje (sx=1 -> ancho 600), pero el TAMAÑO de fuente por s=0.8.
    // Centrado en X (sx=1) -> sigue centrado: x = (1080-600)/2 = 240.
    expect(txt.w).toBe(600);
    expect(txt.x).toBe(240);
    expect(txt.tamano).toBe(48); // 60*0.8
  });

  it("mantiene los titulares de la franja inferior pegados al safe_bottom nuevo", () => {
    const doc = documentoVacio(F45, "uno");
    // Texto al pie: fondo de la caja cerca del borde inferior, dentro del safe_bottom origen (96).
    // y=1200, h=100 -> fondo=1300, a 50px del borde (1350). Está en la mitad inferior.
    doc.capas.push(nuevaCapaTexto({ x: 80, y: 1200, w: 600, h: 100, tamano: 50 }));
    const out = adaptarDocumento(doc, F916); // h destino 1920
    const txt = out.capas.find((c) => c.tipo === "texto") as CapaTexto;
    // sx=1, sy=1920/1350=1.422, s=min=1. La caja de texto escala su alto por sy: nh=round(100*1.422)=142.
    // desdeBorde origen = 50, escalado por s=1 -> ny = 1920-142-50 = 1728. Sigue pegado al pie.
    expect(txt.y).toBe(1728);
    // Sigue en la franja inferior del lienzo destino.
    expect(txt.y + txt.h).toBeGreaterThan(F916.h * 0.6);
  });

  it("es idempotente al adaptar al mismo formato", () => {
    const doc = documentoVacio(F45, "uno");
    doc.capas.push(nuevaCapaTexto({ x: 100, y: 200, w: 500, h: 120, tamano: 64 }));
    const out = adaptarDocumento(doc, F45);
    const a = doc.capas.find((c) => c.tipo === "texto") as CapaTexto;
    const b = out.capas.find((c) => c.tipo === "texto") as CapaTexto;
    expect(b.x).toBe(a.x);
    expect(b.y).toBe(a.y);
    expect(b.w).toBe(a.w);
    expect(b.tamano).toBe(a.tamano);
  });
});
