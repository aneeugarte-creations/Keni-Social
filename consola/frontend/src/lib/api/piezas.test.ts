import { afterEach, describe, expect, it, vi } from "vitest";

import { apiPiezas } from "./piezas";

/** Respuesta JSON 200 simulada para el `fetch` del cliente. */
function respuestaJson(cuerpo: unknown): Response {
  return new Response(JSON.stringify(cuerpo), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("apiPiezas.generarCarrusel", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("hace POST con la longitud elegida y devuelve la generación", async () => {
    const generacion = { id: "g1", estado: "ejecutando" };
    const fetchMock = vi.fn().mockResolvedValue(respuestaJson({ generacion }));
    vi.stubGlobal("fetch", fetchMock);

    const r = await apiPiezas.generarCarrusel("p1", { longitud: "corto" });

    expect(r.generacion).toEqual(generacion);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/piezas/p1/generar-carrusel");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ longitud: "corto" });
  });

  it("escapa el id de la pieza en la URL y manda largo", async () => {
    const fetchMock = vi.fn().mockResolvedValue(respuestaJson({ generacion: { id: "g", estado: "ejecutando" } }));
    vi.stubGlobal("fetch", fetchMock);

    await apiPiezas.generarCarrusel("a/b", { longitud: "largo" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/piezas/a%2Fb/generar-carrusel");
    expect(JSON.parse(init.body as string)).toEqual({ longitud: "largo" });
  });

  it("manda una cantidad EXACTA en vez de la longitud, a tu gusto", async () => {
    const fetchMock = vi.fn().mockResolvedValue(respuestaJson({ generacion: { id: "g", estado: "ejecutando" } }));
    vi.stubGlobal("fetch", fetchMock);

    await apiPiezas.generarCarrusel("p1", { cantidad: 6 });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ cantidad: 6 });
  });
});

describe("apiPiezas.convertirCarrusel", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("hace POST a convertir-carrusel (conversión no destructiva) con la longitud", async () => {
    const generacion = { id: "g1", estado: "ejecutando" };
    const fetchMock = vi.fn().mockResolvedValue(respuestaJson({ generacion }));
    vi.stubGlobal("fetch", fetchMock);

    const r = await apiPiezas.convertirCarrusel("p1", { longitud: "corto" });

    expect(r.generacion).toEqual(generacion);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/piezas/p1/convertir-carrusel");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ longitud: "corto" });
  });

  it("manda una cantidad EXACTA en vez de la longitud, a tu gusto", async () => {
    const fetchMock = vi.fn().mockResolvedValue(respuestaJson({ generacion: { id: "g", estado: "ejecutando" } }));
    vi.stubGlobal("fetch", fetchMock);

    await apiPiezas.convertirCarrusel("p1", { cantidad: 7 });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ cantidad: 7 });
  });
});
