import { afterEach, describe, expect, it, vi } from "vitest";

import { apiActividad } from "./actividad";

/** Respuesta JSON 200 simulada para el `fetch` del cliente. */
function respuestaJson(cuerpo: unknown): Response {
  return new Response(JSON.stringify(cuerpo), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("apiActividad.colaEliminar", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("hace POST a /actividad/cola/eliminar con el gen_id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(respuestaJson({ eliminado: true, gen_id: "g1" }));
    vi.stubGlobal("fetch", fetchMock);

    const r = await apiActividad.colaEliminar("g1");

    expect(r).toEqual({ eliminado: true, gen_id: "g1" });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/actividad/cola/eliminar");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ gen_id: "g1" });
  });
});

describe("apiActividad.colaPriorizar", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sin opts manda solo el gen_id (retrocompatible)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(respuestaJson({ priorizado: true, gen_id: "g1" }));
    vi.stubGlobal("fetch", fetchMock);

    await apiActividad.colaPriorizar("g1");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ gen_id: "g1" });
  });

  it("con `prioridad` clava el valor en el body", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(respuestaJson({ priorizado: true, gen_id: "g1", prioridad: 75 }));
    vi.stubGlobal("fetch", fetchMock);

    const r = await apiActividad.colaPriorizar("g1", { prioridad: 75 });

    expect(r.prioridad).toBe(75);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ gen_id: "g1", prioridad: 75 });
  });

  it("con `a_tope` lo manda en el body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(respuestaJson({ priorizado: true, gen_id: "g1" }));
    vi.stubGlobal("fetch", fetchMock);

    await apiActividad.colaPriorizar("g1", { a_tope: true });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ gen_id: "g1", a_tope: true });
  });
});
