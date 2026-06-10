/**
 * Tests del panel de RENDER:
 *  - Sin composición guardada: botón deshabilitado CON la razón visible (no un disabled mudo).
 *  - Con composición: "Renderizar video" encola el render (POST + seguimiento de generación).
 *  - Con el mp4 listo: "Descargar MP4" baja el archivo directo (fetch blob + <a download>),
 *    además del enlace de abrir en pestaña nueva.
 *  - Mientras baja el blob el botón muestra "Descargando…" (deshabilitado) y, si la descarga
 *    falla, el error queda VISIBLE en línea (role=alert), no solo un toast efímero.
 *
 * `useGeneracion` se mockea (el sondeo/SSE real se prueba en su propio test).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as apiMod from "@/lib/api";
import type { Generacion } from "@/types";

import { PanelRender } from "./PanelRender";

const generacionMock = vi.hoisted(() => ({
  actual: {
    generacion: null as Generacion | null,
    ejecutando: false,
    iniciar: vi.fn(),
  },
}));

vi.mock("@/hooks/use-generacion", () => ({
  useGeneracion: () => generacionMock.actual,
}));

function renderPanel(composicionId: string | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PanelRender composicionId={composicionId} />
    </QueryClientProvider>,
  );
}

describe("PanelRender", () => {
  beforeEach(() => {
    generacionMock.actual = { generacion: null, ejecutando: false, iniciar: vi.fn() };
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    // Limpia los helpers inyectados sobre URL (jsdom no los trae de fábrica).
    delete (URL as unknown as { createObjectURL?: unknown }).createObjectURL;
    delete (URL as unknown as { revokeObjectURL?: unknown }).revokeObjectURL;
  });

  it("sin composición: botón deshabilitado con la RAZÓN visible", () => {
    renderPanel(null);
    const boton = screen.getByRole("button", { name: /renderizar video/i });
    expect(boton).toBeDisabled();
    expect(boton).toHaveAttribute("title", "Sube un clip base en la sección Base");
    expect(screen.getByText(/sube un clip base en la sección base/i)).toBeInTheDocument();
  });

  it("con composición: encola el render y arranca el seguimiento", async () => {
    const post = vi.spyOn(apiMod.api.video, "render").mockResolvedValue({ gen_id: "g-1" });
    const gen = { id: "g-1", estado: "ejecutando" } as Generacion;
    const getGen = vi.spyOn(apiMod.api, "generacion").mockResolvedValue({ generacion: gen } as never);
    renderPanel("comp-7");
    const boton = screen.getByRole("button", { name: /renderizar video/i });
    expect(boton).not.toBeDisabled();
    expect(screen.queryByText(/sube un clip base/i)).not.toBeInTheDocument();
    fireEvent.click(boton);
    await waitFor(() => expect(post).toHaveBeenCalledWith("comp-7"));
    await waitFor(() => expect(getGen).toHaveBeenCalledWith("g-1"));
    await waitFor(() => expect(generacionMock.actual.iniciar).toHaveBeenCalledWith(gen));
  });

  it("con el mp4 listo: 'Descargar MP4' baja el archivo directo (fetch blob + a[download])", async () => {
    generacionMock.actual = {
      generacion: {
        id: "g-1",
        estado: "completado",
        resultado: { url: "/api/media/render-final.mp4" },
      } as unknown as Generacion,
      ejecutando: false,
      iniciar: vi.fn(),
    };
    const fetchMock = vi.fn(
      async (..._args: Parameters<typeof fetch>) => new Response(new Blob(["mp4"]), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    // jsdom no implementa URL.createObjectURL/revokeObjectURL: se inyectan sobre la clase real
    // (sin reemplazarla, otras piezas siguen pudiendo hacer `new URL(...)`).
    const crearUrl = vi.fn(() => "blob:keni-mp4");
    const revocarUrl = vi.fn();
    const UrlGlobal = URL as unknown as {
      createObjectURL?: (b: Blob) => string;
      revokeObjectURL?: (u: string) => void;
    };
    UrlGlobal.createObjectURL = crearUrl;
    UrlGlobal.revokeObjectURL = revocarUrl;
    // Captura el <a download> que se clica (jsdom no navega).
    let descarga: { download: string; href: string } | null = null;
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      descarga = { download: this.download, href: this.href };
    });

    renderPanel("comp-7");
    // El video renderizado y el enlace de pestaña nueva siguen presentes.
    expect(screen.getByLabelText(/video renderizado/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /abrir el mp4/i })).toHaveAttribute(
      "href",
      "/api/media/render-final.mp4",
    );

    fireEvent.click(screen.getByRole("button", { name: /descargar mp4/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/media/render-final.mp4");
    await waitFor(() => expect(descarga).not.toBeNull());
    expect(descarga!.download).toBe("render-final.mp4");
    expect(descarga!.href).toContain("blob:keni-mp4");
    await waitFor(() => expect(revocarUrl).toHaveBeenCalledWith("blob:keni-mp4"));
  });

  it("muestra 'Descargando…' mientras baja el blob y, si falla, deja el error VISIBLE en línea", async () => {
    generacionMock.actual = {
      generacion: {
        id: "g-1",
        estado: "completado",
        resultado: { url: "/api/media/render-final.mp4" },
      } as unknown as Generacion,
      ejecutando: false,
      iniciar: vi.fn(),
    };
    // Fetch controlable: así se observa el estado intermedio y luego el fallo.
    let rechazar: (e: Error) => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise((_res, rej) => { rechazar = rej; })),
    );
    renderPanel("comp-7");
    fireEvent.click(screen.getByRole("button", { name: /descargar mp4/i }));
    // Estado de carga: spinner/texto "Descargando…" y botón deshabilitado (sin doble clic).
    const ocupado = await screen.findByRole("button", { name: /descargando…/i });
    expect(ocupado).toBeDisabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await act(async () => rechazar(new Error("red caída")));
    // Error PERSISTENTE en línea (no solo un toast), con el reintento disponible.
    expect(await screen.findByRole("alert")).toHaveTextContent(/no se pudo descargar el mp4/i);
    expect(screen.getByRole("button", { name: /descargar mp4/i })).not.toBeDisabled();
  });
});
