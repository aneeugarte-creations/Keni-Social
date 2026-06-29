import { describe, expect, it } from "vitest";

import { rutaVisibleParaMarca } from "./gating-marca";

describe("rutaVisibleParaMarca", () => {
  it("muestra todo en la vista agregada (admin, marca null)", () => {
    expect(rutaVisibleParaMarca("/operacion/investigacion", null, false)).toBe(true);
    expect(rutaVisibleParaMarca("/operacion/investigacion/noticias", null, false)).toBe(true);
  });

  it("oculta el hub de Investigación (entrada y todas sus pestañas) a una marca de contenido propio", () => {
    expect(rutaVisibleParaMarca("/operacion/investigacion", "piso-15", false)).toBe(false);
    expect(rutaVisibleParaMarca("/operacion/investigacion/noticias", "piso-15", false)).toBe(false);
    expect(rutaVisibleParaMarca("/operacion/investigacion/fuentes", "piso-15", false)).toBe(false);
    expect(rutaVisibleParaMarca("/operacion/investigacion/publicaciones", "piso-15", false)).toBe(false);
  });

  it("no toca otras rutas para contenido propio", () => {
    // Solo el hub de Investigación se gatea; el resto del nav es visible para cualquier marca.
    expect(rutaVisibleParaMarca("/operacion/feed", "piso-15", false)).toBe(true);
    expect(rutaVisibleParaMarca("/contenido/imagen", "piso-15", false)).toBe(true);
  });

  it("muestra el hub de Investigación a una marca de noticias", () => {
    expect(rutaVisibleParaMarca("/operacion/investigacion", "unotv", true)).toBe(true);
    expect(rutaVisibleParaMarca("/operacion/investigacion/noticias", "unotv", true)).toBe(true);
  });

  it("por defecto (esNoticias ausente) no oculta nada", () => {
    expect(rutaVisibleParaMarca("/operacion/investigacion", "piso-15")).toBe(true);
  });
});
