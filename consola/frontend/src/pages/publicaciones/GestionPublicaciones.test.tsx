import { describe, expect, it } from "vitest";

import { responsableDeLente } from "./GestionPublicaciones";

/**
 * Mapeo de los chips del reparto ("la lista" de ClaroSports) al filtro `responsable`
 * de `/api/publicaciones`. Unit puro: la función está exportada para no montar la página.
 */
describe("responsableDeLente — lente del reparto → filtro `responsable`", () => {
  it('"todas" no filtra por responsable (con o sin sesión)', () => {
    expect(responsableDeLente("todas", "u1")).toBeUndefined();
    expect(responsableDeLente("todas", null)).toBeUndefined();
  });

  it('"libres" pide las piezas SIN responsable (centinela "sin" del backend)', () => {
    expect(responsableDeLente("libres", "u1")).toBe("sin");
    expect(responsableDeLente("libres", null)).toBe("sin");
  });

  it('"mias" filtra por el id del usuario de la sesión', () => {
    expect(responsableDeLente("mias", "u1")).toBe("u1");
  });

  it('"mias" SIN sesión no puede saber quién mira: cae a no filtrar', () => {
    expect(responsableDeLente("mias", null)).toBeUndefined();
  });
});
