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

  it("hace POST a /piezas/{id}/generar-carrusel y devuelve la generación", async () => {
    const generacion = { id: "g1", estado: "ejecutando" };
    const fetchMock = vi.fn().mockResolvedValue(respuestaJson({ generacion }));
    vi.stubGlobal("fetch", fetchMock);

    const r = await apiPiezas.generarCarrusel("p1");

    expect(r.generacion).toEqual(generacion);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/piezas/p1/generar-carrusel");
    expect(init.method).toBe("POST");
  });

  it("escapa el id de la pieza en la URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(respuestaJson({ generacion: { id: "g", estado: "ejecutando" } }));
    vi.stubGlobal("fetch", fetchMock);

    await apiPiezas.generarCarrusel("a/b");

    expect((fetchMock.mock.calls[0] as [string])[0]).toBe("/api/piezas/a%2Fb/generar-carrusel");
  });
});
