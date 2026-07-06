import { afterEach, describe, expect, it, vi } from "vitest";

import { etiquetaMejorHora, fetchMejorHora } from "./programacion";

/** Respuesta JSON simulada para el `fetch` del cliente. */
function respuestaJson(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("fetchMejorHora", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("devuelve hora y día del backend", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(respuestaJson({ hora: "20:00", dia: "miércoles" }));
    vi.stubGlobal("fetch", fetchMock);

    const r = await fetchMejorHora("claro_sports", "instagram");

    expect(r).toEqual({ hora: "20:00", dia: "miércoles" });
    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toContain("/api/programacion/mejor-hora");
    expect(url).toContain("marca=claro_sports");
    expect(url).toContain("red=instagram");
  });

  it("degrada a ambos null cuando falta marca o red", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    expect(await fetchMejorHora("", "instagram")).toEqual({ hora: null, dia: null });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("degrada a ambos null ante un 404 (endpoint aún no desplegado)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(respuestaJson({}, 404));
    vi.stubGlobal("fetch", fetchMock);

    expect(await fetchMejorHora("claro_sports", "instagram")).toEqual({
      hora: null,
      dia: null,
    });
  });

  it("propaga la cancelación de react-query (AbortError)", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValue(new DOMException("cancelado", "AbortError"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchMejorHora("claro_sports", "instagram")).rejects.toThrow();
  });
});

describe("etiquetaMejorHora", () => {
  it("compone «día · hora» cuando hay ambos", () => {
    expect(etiquetaMejorHora({ hora: "19:00", dia: "martes" })).toBe("martes · 19:00");
  });

  it("muestra solo la hora si no hay día", () => {
    expect(etiquetaMejorHora({ hora: "19:00", dia: null })).toBe("19:00");
  });

  it("es null cuando no hay hora", () => {
    expect(etiquetaMejorHora({ hora: null, dia: "martes" })).toBeNull();
    expect(etiquetaMejorHora(null)).toBeNull();
  });
});
