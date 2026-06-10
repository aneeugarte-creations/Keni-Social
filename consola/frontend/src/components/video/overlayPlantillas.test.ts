/**
 * Tests del puente PLANTILLAS DE DISEÑO ⇄ pista OVERLAY de video (`overlayPlantillas.ts`):
 *  - `plantillaAOverlay` adapta el documento al formato del video, fuerza fondo transparente y
 *    quita los huecos de foto (también dentro de grupos): el video hace de foto.
 *  - `overlayAPlantilla` añade el hueco de foto oculto a sangre que exige el servidor (solo si
 *    falta) y fija la marca, sin mutar el documento original.
 */
import { describe, expect, it } from "vitest";

import {
  documentoVacio,
  nuevaCapaImagen,
  nuevaCapaTexto,
  type CapaGrupo,
  type CapaImagen,
  type Documento,
} from "@/editor/documento";

import { overlayAPlantilla, plantillaAOverlay } from "./overlayPlantillas";

const FORMATO_VIDEO = { w: 1080, h: 1920 };

/** Plantilla 4:5 típica: hueco de foto a sangre + titular + fondo opaco. */
function plantillaFoto(): Documento {
  const doc = documentoVacio({ w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 }, "unotv");
  doc.fondo = { tipo: "color", color: "#FFFFFF" };
  doc.capas = [
    nuevaCapaImagen("", { x: 0, y: 0, w: 1080, h: 1350, z: 0, es_foto: true, visible: true }),
    nuevaCapaTexto({ x: 80, y: 1100, w: 920, h: 160, z: 10, texto: "Titular" }),
  ];
  return doc;
}

describe("plantillaAOverlay", () => {
  it("adapta al formato del video, deja el fondo transparente y quita los huecos de foto", () => {
    const plantilla = plantillaFoto();
    const overlay = plantillaAOverlay(plantilla, FORMATO_VIDEO, "unotv");

    expect(overlay.formato).toEqual({ w: 1080, h: 1920, safe_top: 0, safe_bottom: 0 });
    expect(overlay.fondo).toEqual({ tipo: "color", color: "#00000000" });
    // El hueco de foto desaparece (el video hace de foto); el titular sobrevive.
    expect(overlay.capas).toHaveLength(1);
    expect(overlay.capas[0].tipo).toBe("texto");
    // No muta el original.
    expect(plantilla.capas).toHaveLength(2);
    expect(plantilla.formato.h).toBe(1350);
  });

  it("quita huecos de foto también dentro de grupos", () => {
    const plantilla = plantillaFoto();
    const hija = nuevaCapaImagen("", { es_foto: true, x: 0, y: 0, w: 400, h: 400, z: 1 });
    const grupo: CapaGrupo = {
      id: "g1",
      tipo: "grupo",
      x: 0,
      y: 0,
      w: 400,
      h: 400,
      rotacion: 0,
      opacidad: 1,
      z: 5,
      visible: true,
      bloqueada: false,
      capas: [hija, nuevaCapaTexto({ x: 10, y: 10, w: 200, h: 80, z: 2 })],
    };
    plantilla.capas.push(grupo);

    const overlay = plantillaAOverlay(plantilla, FORMATO_VIDEO);
    const grupoAdaptado = overlay.capas.find((c) => c.tipo === "grupo") as CapaGrupo;
    expect(grupoAdaptado).toBeDefined();
    expect(grupoAdaptado.capas).toHaveLength(1);
    expect(grupoAdaptado.capas[0].tipo).toBe("texto");
  });

  it("es idempotente si la plantilla ya está en el formato del video", () => {
    const plantilla = plantillaFoto();
    plantilla.formato = { w: 1080, h: 1920, safe_top: 0, safe_bottom: 0 };
    const texto = plantilla.capas[1];
    const overlay = plantillaAOverlay(plantilla, FORMATO_VIDEO);
    const adaptado = overlay.capas[0];
    expect(adaptado.x).toBe(texto.x);
    expect(adaptado.y).toBe(texto.y);
    expect(adaptado.w).toBe(texto.w);
  });
});

describe("overlayAPlantilla", () => {
  /** Documento de overlay típico: transparente, sin hueco, con un texto. */
  function docOverlay(): Documento {
    return {
      version: 1,
      marca: "",
      fuentes: { sans: "Barlow", condensada: "Barlow Condensed" },
      formato: { w: 1080, h: 1920, safe_top: 0, safe_bottom: 0 },
      fondo: { tipo: "color", color: "#00000000" },
      capas: [nuevaCapaTexto({ x: 80, y: 1500, w: 920, h: 160, z: 5, texto: "Rótulo" })],
    };
  }

  it("añade un hueco de foto oculto a sangre (lo exige el servidor) y fija la marca", () => {
    const overlay = docOverlay();
    const plantilla = overlayAPlantilla(overlay, "unotv");

    expect(plantilla.marca).toBe("unotv");
    expect(plantilla.capas).toHaveLength(2);
    const hueco = plantilla.capas.find((c) => c.tipo === "imagen" && (c as CapaImagen).es_foto) as CapaImagen;
    expect(hueco).toBeDefined();
    expect(hueco.visible).toBe(false);
    expect(hueco.bloqueada).toBe(true);
    expect([hueco.x, hueco.y, hueco.w, hueco.h]).toEqual([0, 0, 1080, 1920]);
    // Debajo de todo (z menor que el resto).
    expect(hueco.z).toBeLessThan(5);
    // No muta el original.
    expect(overlay.capas).toHaveLength(1);
  });

  it("no duplica el hueco si el documento ya lo declara", () => {
    const overlay = docOverlay();
    overlay.capas.unshift(nuevaCapaImagen("", { es_foto: true, x: 0, y: 0, w: 1080, h: 1920, z: 0 }));
    const plantilla = overlayAPlantilla(overlay, "unotv");
    expect(plantilla.capas.filter((c) => c.tipo === "imagen" && (c as CapaImagen).es_foto)).toHaveLength(1);
  });
});
