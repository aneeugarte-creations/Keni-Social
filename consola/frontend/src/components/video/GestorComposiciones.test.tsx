/**
 * Tests del GESTOR de composiciones de video (= gestor de transcripciones).
 *  - Lista las composiciones de la marca activa con su formato.
 *  - Muestra el ESTADO de subtítulos por fila (de `subtitulosDe`).
 *  - Refleja si la pieza ligada ya tiene su video o le falta (de `publicaciones`).
 *  - "Abrir" invoca onAbrir con el id de la composición (reabrir en el editor).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as apiMod from "@/lib/api";
import type { ComposicionResumen, Subtitulo } from "@/lib/video";

import { GestorComposiciones } from "./GestorComposiciones";

function comp(over: Partial<ComposicionResumen> = {}): ComposicionResumen {
  return {
    id: "comp-1",
    contenido_id: "",
    marca: "unotv",
    marca_nombre: "UnoTV",
    creado: "2026-06-01T10:00:00Z",
    actualizado: "2026-06-02T12:00:00Z",
    documento: {
      version: 1,
      marca: "unotv",
      formato: { w: 1080, h: 1920, fps: 30, preset: "9:16" },
      duracion_ms: 0,
      pistas: [{ id: "base", tipo: "video", clips: [] }],
    },
    ...over,
  };
}

function renderGestor(onAbrir = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <GestorComposiciones marca="unotv" onAbrir={onAbrir} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return onAbrir;
}

beforeEach(() => {
  vi.spyOn(apiMod.api, "publicaciones").mockResolvedValue({
    publicaciones: [],
    paginacion: { total: 0, limite: 0, desplazamiento: 0 },
  } as never);
  vi.spyOn(apiMod.api.video, "subtitulosDe").mockResolvedValue({ subtitulo: null });
});

afterEach(() => vi.restoreAllMocks());

describe("GestorComposiciones", () => {
  it("lista las composiciones de la marca con su formato", async () => {
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({
      composiciones: [comp({ id: "comp-9x16", documento: comp().documento })],
    });
    renderGestor();
    expect(await screen.findByText("comp-9x16")).toBeInTheDocument();
    expect(screen.getByText("9:16")).toBeInTheDocument();
  });

  it("muestra el estado de subtítulos de la composición (gestor de transcripciones)", async () => {
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({
      composiciones: [comp({ id: "comp-subs" })],
    });
    vi.spyOn(apiMod.api.video, "subtitulosDe").mockResolvedValue({
      subtitulo: { id: "s1", estado: "listo" } as Subtitulo,
    });
    renderGestor();
    expect(await screen.findByText(/subtítulos listos/i)).toBeInTheDocument();
  });

  it("estado por defecto 'pendiente' cuando la composición no tiene subtítulos", async () => {
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({
      composiciones: [comp({ id: "comp-sin-subs" })],
    });
    renderGestor();
    expect(await screen.findByText(/subtítulos pendientes/i)).toBeInTheDocument();
  });

  it("refleja que falta el video en la pieza ligada (honestidad de producto)", async () => {
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({
      composiciones: [comp({ id: "comp-pieza", contenido_id: "cont-1" })],
    });
    // La pieza ligada NO tiene video adjunto (video vacío).
    vi.spyOn(apiMod.api, "publicaciones").mockResolvedValue({
      publicaciones: [{ contenido_id: "cont-1", video: "" }],
      paginacion: { total: 1, limite: 0, desplazamiento: 0 },
    } as never);
    renderGestor();
    expect(await screen.findByText(/falta el video en la pieza/i)).toBeInTheDocument();
  });

  it("refleja video adjunto cuando la pieza ligada ya tiene su mp4", async () => {
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({
      composiciones: [comp({ id: "comp-pieza2", contenido_id: "cont-2" })],
    });
    vi.spyOn(apiMod.api, "publicaciones").mockResolvedValue({
      publicaciones: [{ contenido_id: "cont-2", video: "render/abc.mp4" }],
      paginacion: { total: 1, limite: 0, desplazamiento: 0 },
    } as never);
    renderGestor();
    expect(await screen.findByText(/video adjunto a la pieza/i)).toBeInTheDocument();
  });

  it("'Abrir' invoca onAbrir con el id de la composición (reabrir en el editor)", async () => {
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({
      composiciones: [comp({ id: "comp-abrir" })],
    });
    const onAbrir = renderGestor();
    const boton = await screen.findByRole("button", { name: /abrir/i });
    fireEvent.click(boton);
    expect(onAbrir).toHaveBeenCalledWith("comp-abrir");
  });

  it("muestra vacío cuando no hay composiciones para la marca", async () => {
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({ composiciones: [] });
    renderGestor();
    await waitFor(() =>
      expect(screen.getByText(/aún no hay composiciones para esta marca/i)).toBeInTheDocument(),
    );
  });
});
