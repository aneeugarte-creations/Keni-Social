import { describe, expect, it } from "vitest";

import { faltaMarcaAsignada, responsableDeLente } from "./GestionPublicaciones";

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

/**
 * El aviso "no tienes marca asignada" distingue `marcas` DESCONOCIDA (la forma mínima
 * del login no trae la clave) de VACÍA (el `me` la serializa siempre): solo la segunda
 * debe avisar. Sin la distinción, todo editor veía el falso aviso toda la sesión.
 */
describe("faltaMarcaAsignada — aviso de usuario sin marca", () => {
  it("avisa solo con la lista de marcas CONOCIDA y vacía (editor)", () => {
    expect(faltaMarcaAsignada({ rol: "editor", marcas: [] })).toBe(true);
  });

  it("NO avisa si `marcas` aún no se conoce (forma mínima del login)", () => {
    expect(faltaMarcaAsignada({ rol: "editor" })).toBe(false);
  });

  it("NO avisa con marcas asignadas, a admins ni sin sesión", () => {
    expect(faltaMarcaAsignada({ rol: "editor", marcas: ["claro-sports"] })).toBe(false);
    expect(faltaMarcaAsignada({ rol: "admin", marcas: [] })).toBe(false);
    expect(faltaMarcaAsignada(null)).toBe(false);
  });
});
