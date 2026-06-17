import { describe, expect, it } from "vitest";

import type { PlantillaDiseno } from "@/lib/api";
import {
  agruparPorCategoria,
  construirCatalogosEtiquetas,
  etiquetaCategoria,
  opcionesCategoria,
} from "./categoriasPlantilla";

const plantilla = (marca: string, categoria: string): PlantillaDiseno =>
  ({ id: `${marca}-${categoria}`, marca, categoria, nombre: "", tipo: "foto" } as unknown as PlantillaDiseno);

describe("categoriasPlantilla · catálogo de etiquetas por marca", () => {
  it("construye el catálogo por marca: slugs gestionados + solo overrides no vacíos", () => {
    const cats = construirCatalogosEtiquetas([
      { marca: "fundacion", slug: "ultima-hora", etiqueta: "Lo último" },
      { marca: "fundacion", slug: "exposicion", etiqueta: "" }, // gestionada, sin override
      { marca: "claro-sports", slug: "marcador", etiqueta: "Marcador final" },
    ]);
    const f = cats.get("fundacion")!;
    expect([...f.slugs].sort()).toEqual(["exposicion", "ultima-hora"]);
    expect(f.rotulos.get("ultima-hora")).toBe("Lo último");
    expect(f.rotulos.has("exposicion")).toBe(false); // override vacío no entra
    expect(cats.get("claro-sports")!.rotulos.get("marcador")).toBe("Marcador final");
  });

  it("etiquetaCategoria: override de marca gana al catálogo estático; el de otra marca no aplica", () => {
    const cats = construirCatalogosEtiquetas([
      { marca: "fundacion", slug: "ultima-hora", etiqueta: "Lo último" },
    ]);
    expect(etiquetaCategoria("ultima-hora", cats.get("fundacion"))).toBe("Lo último");
    // Sin override (otra marca / sin catálogo) cae al rótulo estático del catálogo conocido.
    expect(etiquetaCategoria("ultima-hora", cats.get("claro-sports"))).toBe("Última hora");
    expect(etiquetaCategoria("ultima-hora")).toBe("Última hora");
  });

  it("opcionesCategoria con catálogo: base = slugs de la marca + general (NO la lista global ni el slugsPresentes multi-marca)", () => {
    const cats = construirCatalogosEtiquetas([
      { marca: "fundacion", slug: "exposicion", etiqueta: "Exposición" },
      { marca: "fundacion", slug: "coleccion", etiqueta: "" },
    ]);
    // El slugsPresentes (de toda la galería, multi-marca; aquí «marcador» de otra marca) se IGNORA
    // en modo catálogo: el scope sale de `cat.slugs`.
    const slugs = opcionesCategoria(["marcador"], null, cats.get("fundacion")).map((c) => c.slug);
    expect(new Set(slugs)).toEqual(new Set(["exposicion", "coleccion", "general"]));
    expect(slugs).not.toContain("marcador");
    // El rótulo gestionado preserva acentos/mayúsculas.
    expect(opcionesCategoria([], null, cats.get("fundacion")).find((c) => c.slug === "exposicion")!.etiqueta).toBe(
      "Exposición",
    );
  });

  it("opcionesCategoria sin catálogo conserva el comportamiento histórico (catálogo estático global)", () => {
    const slugs = opcionesCategoria([], null).map((c) => c.slug);
    expect(slugs).toContain("ultima-hora");
    expect(slugs).toContain("marcador");
    expect(slugs).toContain("general");
  });

  it("agruparPorCategoria rotula las cabeceras con el override de la marca", () => {
    const cats = construirCatalogosEtiquetas([
      { marca: "fundacion", slug: "ultima-hora", etiqueta: "Lo último" },
    ]);
    const grupos = agruparPorCategoria([plantilla("fundacion", "ultima-hora")], cats.get("fundacion"));
    expect(grupos[0].etiqueta).toBe("Lo último");
  });
});
