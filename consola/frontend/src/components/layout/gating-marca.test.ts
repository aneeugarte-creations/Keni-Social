import { describe, expect, it } from "vitest";

import { rutaVisibleParaMarca } from "./gating-marca";

describe("rutaVisibleParaMarca", () => {
  it("muestra todo en la vista agregada (admin, marca null)", () => {
    expect(rutaVisibleParaMarca("/datos/investigacion", null, false)).toBe(true);
    expect(rutaVisibleParaMarca("/maquina/investigacion", null, false)).toBe(true);
  });

  it("oculta el panel de Noticias a una marca de contenido propio", () => {
    // Pestaña "Noticias" (índice del hub) y cockpit de Investigación.
    expect(rutaVisibleParaMarca("/datos/investigacion", "piso-15", false)).toBe(false);
    expect(rutaVisibleParaMarca("/maquina/investigacion", "piso-15", false)).toBe(false);
  });

  it("conserva las hermanas del hub para contenido propio (match exacto del índice)", () => {
    // 'Noticias' es exacta: Publicaciones y Fuentes siguen visibles.
    expect(rutaVisibleParaMarca("/datos/investigacion/contenidos", "piso-15", false)).toBe(true);
    expect(rutaVisibleParaMarca("/datos/investigacion/fuentes", "piso-15", false)).toBe(true);
  });

  it("muestra el panel de Noticias a una marca de noticias", () => {
    expect(rutaVisibleParaMarca("/datos/investigacion", "unotv", true)).toBe(true);
    expect(rutaVisibleParaMarca("/maquina/investigacion", "unotv", true)).toBe(true);
  });

  it("por defecto (esNoticias ausente) no oculta nada", () => {
    expect(rutaVisibleParaMarca("/datos/investigacion", "piso-15")).toBe(true);
  });
});
