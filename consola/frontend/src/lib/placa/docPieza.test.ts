import { describe, expect, it } from "vitest";

import type { Documento } from "@/editor/documento";

import { capaFotoDoc, capaTitularDoc, mediaIdsDe, prepararDocumento } from "./docPieza";

function doc(capas: Documento["capas"]): Documento {
  return {
    version: 1,
    marca: "claro-sports",
    fuentes: { sans: "Barlow", condensada: "Barlow Condensed" },
    formato: { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 },
    fondo: { tipo: "color", color: "#111315" },
    capas,
  };
}

const img = (o: Partial<Documento["capas"][number]> & { objeto: string }) =>
  ({
    id: o.objeto, tipo: "imagen", x: 0, y: 0, w: 1080, h: 1350,
    rotacion: 0, opacidad: 1, z: 0, visible: true, bloqueada: false, ajuste: "cover",
    foco: [0.5, 0.5], zoom: 1, filtros: null, ...o,
  }) as Documento["capas"][number];

describe("docPieza", () => {
  it("capaFotoDoc prefiere es_foto, respalda en imagen a sangre, ignora logos", () => {
    const marcada = doc([
      img({ objeto: "bg", w: 1080, h: 1350 }),
      img({ objeto: "marca", w: 200, h: 200, es_foto: true }),
    ]);
    expect(capaFotoDoc(marcada)?.objeto).toBe("marca");
    const sangre = doc([img({ objeto: "bg", w: 1080, h: 1350 }), img({ objeto: "logo", w: 110, h: 110 })]);
    expect(capaFotoDoc(sangre)?.objeto).toBe("bg");
    const soloLogo = doc([img({ objeto: "logo", w: 110, h: 110 })]);
    expect(capaFotoDoc(soloLogo)).toBeNull();
  });

  it("capaTitularDoc encuentra el texto con binding copy_in", () => {
    const d = doc([
      img({ objeto: "bg", es_foto: true }),
      {
        id: "t", tipo: "texto", texto: "", binding: "copy_in", x: 56, y: 1254, w: 968,
        rotacion: 0, opacidad: 1, z: 20, visible: true, bloqueada: false, familia: "Barlow",
        tamano: 78, peso: 800, color: "#fff", alineacion: "izquierda", mayusculas: false,
        interlineado: 1.14, interletra: 0, auto_ajuste: { max_lineas: 3, tam_min: 40 },
        sombra: null, contorno: null, chip: null, ancla: "abajo",
      } as Documento["capas"][number],
    ]);
    expect(capaTitularDoc(d)?.id).toBe("t");
    expect(capaTitularDoc(doc([img({ objeto: "bg" })]))).toBeNull();
  });

  it("mediaIdsDe junta objetos sin repetir ni vacíos", () => {
    const d = doc([img({ objeto: "bg", es_foto: true }), img({ objeto: "" }), img({ objeto: "bg" })]);
    expect(mediaIdsDe(d).sort()).toEqual(["bg"]);
  });

  it("prepararDocumento mete la foto en el hueco + reencuadre, sin mutar el original", () => {
    const d = doc([img({ objeto: "muestra", es_foto: true })]);
    const out = prepararDocumento(d, { foto: "real.png", encuadre: { foco: [0.2, 0.8], zoom: 1.5 } });
    const hueco = capaFotoDoc(out);
    expect(hueco?.objeto).toBe("real.png");
    expect(hueco?.foco).toEqual([0.2, 0.8]);
    expect(hueco?.zoom).toBe(1.5);
    expect(capaFotoDoc(d)?.objeto).toBe("muestra"); // original intacto
  });
});
