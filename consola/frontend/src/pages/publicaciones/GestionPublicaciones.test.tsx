import { describe, expect, it } from "vitest";

import {
  debeAvisarProgramadasSinSalir,
  faltaMarcaAsignada,
  paramsPaginaFeed,
  responsableDeLente,
} from "./GestionPublicaciones";

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

/**
 * La LISTA pagina por keyset: la 1ª página llega SIN cursor pero CON `feed:"1"` (sin esa
 * marca el backend caería al modo COMPLETO y traería todo de golpe). Las páginas 2+ llevan
 * el cursor de la última fila vista.
 */
describe("paramsPaginaFeed — parámetros de una página del feed (keyset)", () => {
  const base = { marca: "claro-sports", red: undefined, linea: undefined, responsable: "u1" };

  it("la 1ª página activa el modo feed (feed:'1') SIN cursor", () => {
    const p = paramsPaginaFeed(base, "");
    expect(p.feed).toBe("1");
    expect(p.cursor).toBeUndefined();
    expect(p.limite).toBe("30");
    // Arrastra los filtros base (marca/responsable) a la query.
    expect(p.marca).toBe("claro-sports");
    expect(p.responsable).toBe("u1");
  });

  it("las páginas 2+ llevan el cursor de la última fila vista", () => {
    const p = paramsPaginaFeed(base, "2026-06-10T00:00|abc");
    expect(p.feed).toBe("1");
    expect(p.cursor).toBe("2026-06-10T00:00|abc");
  });

  it("respeta un tamaño de página explícito", () => {
    expect(paramsPaginaFeed(base, "", 10).limite).toBe("10");
  });
});

/**
 * El banner "Publicación automática desactivada" se basa en el TOTAL del servidor (no en las
 * páginas ya cargadas): con keyset la 1ª página podía no traer ninguna programada aunque las
 * hubiera. Solo avisa con el posteo real APAGADO y existiendo >=1 pieza programada.
 */
describe("debeAvisarProgramadasSinSalir — banner según el total del servidor", () => {
  it("avisa con el posteo real apagado y al menos una programada", () => {
    expect(debeAvisarProgramadasSinSalir(false, 1)).toBe(true);
    expect(debeAvisarProgramadasSinSalir(false, 42)).toBe(true);
  });

  it("NO avisa si el posteo real está encendido (saldrán solas)", () => {
    expect(debeAvisarProgramadasSinSalir(true, 5)).toBe(false);
  });

  it("NO avisa si no hay ninguna programada", () => {
    expect(debeAvisarProgramadasSinSalir(false, 0)).toBe(false);
  });
});
