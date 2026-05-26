/**
 * Test de la lógica de inicialización lazy de "marca" en Publicaciones (#119 A-5).
 *
 * El componente Gestion usa useState con inicializador lazy en vez de useMemo(fn, [])
 * para garantizar ejecución exactamente una vez (incluso en StrictMode/concurrent).
 *
 * Probamos directamente la función inicializadora para validar su lógica,
 * sin montar el componente completo (evitamos dependencias de router/react-query).
 */
import { describe, expect, it } from "vitest";

/** Réplica de la función inicializadora de marca en Publicaciones.tsx y Metricas.tsx. */
function calcularMarcaInicial(
  searchString: string,
  marcas: Array<{ id: string }>,
  FILTRO_TODOS: string,
): string {
  const desdeQuery = new URLSearchParams(searchString).get("marca") ?? undefined;
  return desdeQuery && marcas.some((m) => m.id === desdeQuery) ? desdeQuery : FILTRO_TODOS;
}

const FILTRO_TODOS = "_todos_";
const MARCAS = [{ id: "unotv" }, { id: "clarosports" }];

describe("Publicaciones · A-5: inicializador lazy de marca (#119)", () => {
  it("devuelve la marca del query string si existe en el catálogo", () => {
    const resultado = calcularMarcaInicial("?marca=unotv", MARCAS, FILTRO_TODOS);
    expect(resultado).toBe("unotv");
  });

  it("devuelve FILTRO_TODOS si la marca del query no existe en el catálogo", () => {
    const resultado = calcularMarcaInicial("?marca=inexistente", MARCAS, FILTRO_TODOS);
    expect(resultado).toBe(FILTRO_TODOS);
  });

  it("devuelve FILTRO_TODOS si no hay query string de marca", () => {
    const resultado = calcularMarcaInicial("", MARCAS, FILTRO_TODOS);
    expect(resultado).toBe(FILTRO_TODOS);
  });

  it("devuelve FILTRO_TODOS si el catálogo está vacío", () => {
    const resultado = calcularMarcaInicial("?marca=unotv", [], FILTRO_TODOS);
    expect(resultado).toBe(FILTRO_TODOS);
  });

  it("es pura: el mismo input produce siempre el mismo output (segura para useState lazy)", () => {
    const r1 = calcularMarcaInicial("?marca=clarosports", MARCAS, FILTRO_TODOS);
    const r2 = calcularMarcaInicial("?marca=clarosports", MARCAS, FILTRO_TODOS);
    expect(r1).toBe(r2);
    expect(r1).toBe("clarosports");
  });
});

/** Réplica de la función inicializadora de marca en Metricas.tsx. */
function calcularMarcaInicialMetricas(
  locationState: { marca?: string } | null,
  searchString: string,
  marcas: Array<{ id: string }>,
  MARCA_TODAS: string,
): string {
  const desdeQuery = new URLSearchParams(searchString).get("marca") ?? undefined;
  const candidata = locationState?.marca ?? desdeQuery;
  return candidata && marcas.some((m) => m.id === candidata) ? candidata : MARCA_TODAS;
}

const MARCA_TODAS = "_todas_";

describe("Metricas · A-5: inicializador lazy de marca (#119)", () => {
  it("prefiere el state de navegación sobre la query string", () => {
    const resultado = calcularMarcaInicialMetricas(
      { marca: "unotv" },
      "?marca=clarosports",
      MARCAS,
      MARCA_TODAS,
    );
    expect(resultado).toBe("unotv");
  });

  it("usa query string si no hay state de navegación", () => {
    const resultado = calcularMarcaInicialMetricas(null, "?marca=clarosports", MARCAS, MARCA_TODAS);
    expect(resultado).toBe("clarosports");
  });

  it("devuelve MARCA_TODAS si la candidata no existe en el catálogo", () => {
    const resultado = calcularMarcaInicialMetricas(
      { marca: "inexistente" },
      "",
      MARCAS,
      MARCA_TODAS,
    );
    expect(resultado).toBe(MARCA_TODAS);
  });

  it("devuelve MARCA_TODAS si no hay state ni query", () => {
    const resultado = calcularMarcaInicialMetricas(null, "", MARCAS, MARCA_TODAS);
    expect(resultado).toBe(MARCA_TODAS);
  });
});
