/**
 * Tests del GESTOR de composiciones de video (= gestor de transcripciones).
 *  - Lista las composiciones de la marca activa como TARJETAS con su formato.
 *  - Muestra el ESTADO de subtítulos por tarjeta (de `subtitulosDe`).
 *  - Refleja si la pieza ligada ya tiene su video o le falta (de `piezas`).
 *  - Clic en la tarjeta = abrir en el editor (onAbrir con el id).
 *  - Clic en el TÍTULO = renombrar inline.
 *  - Duplicar / Eliminar / Renombrar viven en el menú contextual (kebab), no en botones periféricos.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { confirmar } from "@/components/comunes/confirmar";
import * as apiMod from "@/lib/api";
import type { ComposicionResumen, Subtitulo } from "@/lib/video";

import { GestorComposiciones } from "./GestorComposiciones";

// La app NO usa el confirm del navegador: el borrado pasa por `confirmar()`
// (Promise<boolean>). Lo mockeamos para controlar la respuesta del usuario.
vi.mock("@/components/comunes/confirmar", () => ({
  confirmar: vi.fn(),
}));

function comp(over: Partial<ComposicionResumen> = {}): ComposicionResumen {
  return {
    id: "comp-1",
    publicacion_id: "",
    marca: "unotv",
    marca_nombre: "UnoTV",
    titulo: "",
    estado: "borrador",
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

/** Abre el menú contextual de una tarjeta (kebab "Más acciones"). */
function abrirMenu() {
  fireEvent.click(screen.getByRole("button", { name: /más acciones/i }));
}

beforeEach(() => {
  vi.spyOn(apiMod.api, "piezas").mockResolvedValue({
    piezas: [],
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
      composiciones: [comp({ id: "comp-pieza", publicacion_id: "cont-1" })],
    });
    // La pieza ligada NO tiene video adjunto (video vacío).
    vi.spyOn(apiMod.api, "piezas").mockResolvedValue({
      piezas: [{ publicacion_id: "cont-1", video: "" }],
      paginacion: { total: 1, limite: 0, desplazamiento: 0 },
    } as never);
    renderGestor();
    expect(await screen.findByText(/falta el video en la pieza/i)).toBeInTheDocument();
  });

  it("refleja video adjunto cuando la pieza ligada ya tiene su mp4", async () => {
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({
      composiciones: [comp({ id: "comp-pieza2", publicacion_id: "cont-2" })],
    });
    vi.spyOn(apiMod.api, "piezas").mockResolvedValue({
      piezas: [{ publicacion_id: "cont-2", video: "render/abc.mp4" }],
      paginacion: { total: 1, limite: 0, desplazamiento: 0 },
    } as never);
    renderGestor();
    expect(await screen.findByText(/video adjunto a la pieza/i)).toBeInTheDocument();
  });

  it("clic en la TARJETA invoca onAbrir con el id (reabrir en el editor)", async () => {
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({
      composiciones: [comp({ id: "comp-abrir" })],
    });
    const onAbrir = renderGestor();
    // El cuerpo de la tarjeta (no un botón) dispara la acción primaria.
    fireEvent.click(await screen.findByText("9:16"));
    expect(onAbrir).toHaveBeenCalledWith("comp-abrir");
  });

  it("clic en el TÍTULO entra en modo edición y NO abre la composición", async () => {
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({
      composiciones: [comp({ id: "comp-edit", titulo: "Mi reel" })],
    });
    const onAbrir = renderGestor();
    fireEvent.click(await screen.findByRole("button", { name: "Mi reel" }));
    expect(screen.getByRole("textbox", { name: /nuevo título/i })).toBeInTheDocument();
    expect(onAbrir).not.toHaveBeenCalled();
  });

  it("muestra vacío cuando no hay composiciones para la marca", async () => {
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({ composiciones: [] });
    renderGestor();
    await waitFor(() =>
      expect(screen.getByText(/aún no hay composiciones/i)).toBeInTheDocument(),
    );
  });

  it("muestra el TÍTULO del borrador (no el id) y un badge de estado", async () => {
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({
      composiciones: [comp({ id: "comp-x", titulo: "Mi reel del finde", estado: "listo" })],
    });
    renderGestor();
    expect(await screen.findByText("Mi reel del finde")).toBeInTheDocument();
    // Badge "Listo" presente.
    expect(screen.getByText(/^Listo$/)).toBeInTheDocument();
  });

  it("cae al id cuando el borrador no tiene título", async () => {
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({
      composiciones: [comp({ id: "comp-sin-titulo", titulo: "" })],
    });
    renderGestor();
    expect(await screen.findByText("comp-sin-titulo")).toBeInTheDocument();
    // Borrador por defecto.
    expect(screen.getByText(/^Borrador$/)).toBeInTheDocument();
  });

  it("RENOMBRA un borrador desde el menú (PUT solo título) y refresca", async () => {
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({
      composiciones: [comp({ id: "comp-r", titulo: "Viejo" })],
    });
    const renombrar = vi
      .spyOn(apiMod.api.video, "renombrarComposicion")
      .mockResolvedValue({ composicion: { id: "comp-r", titulo: "Nuevo", estado: "borrador" } });
    renderGestor();
    await screen.findByText("Viejo");
    abrirMenu();
    fireEvent.click(await screen.findByRole("menuitem", { name: /renombrar/i }));
    const input = screen.getByRole("textbox", { name: /nuevo título/i });
    fireEvent.change(input, { target: { value: "Nuevo" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(renombrar).toHaveBeenCalledWith("comp-r", "Nuevo"));
  });

  it("ELIMINA un borrador desde el menú tras confirmar", async () => {
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({
      composiciones: [comp({ id: "comp-del", titulo: "Borrar esto" })],
    });
    const eliminar = vi
      .spyOn(apiMod.api.video, "eliminarComposicion")
      .mockResolvedValue({ ok: true });
    vi.mocked(confirmar).mockResolvedValue(true);
    renderGestor();
    await screen.findByText("Borrar esto");
    abrirMenu();
    fireEvent.click(await screen.findByRole("menuitem", { name: /^eliminar$/i }));
    expect(confirmar).toHaveBeenCalled();
    await waitFor(() => expect(eliminar).toHaveBeenCalledWith("comp-del"));
  });

  it("NO elimina si el usuario cancela la confirmación", async () => {
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({
      composiciones: [comp({ id: "comp-keep", titulo: "Conservar" })],
    });
    const eliminar = vi.spyOn(apiMod.api.video, "eliminarComposicion");
    vi.mocked(confirmar).mockResolvedValue(false);
    renderGestor();
    await screen.findByText("Conservar");
    abrirMenu();
    fireEvent.click(await screen.findByRole("menuitem", { name: /^eliminar$/i }));
    await waitFor(() => expect(confirmar).toHaveBeenCalled());
    expect(eliminar).not.toHaveBeenCalled();
  });

  it("DUPLICA una composición desde el menú llamando a crearComposicion con título '(copia)'", async () => {
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({
      composiciones: [comp({ id: "comp-dup", titulo: "Mi reel" })],
    });
    const crear = vi
      .spyOn(apiMod.api.video, "crearComposicion")
      .mockResolvedValue({ id: "comp-dup-copia" });
    renderGestor();
    await screen.findByText("Mi reel");
    abrirMenu();
    fireEvent.click(await screen.findByRole("menuitem", { name: /duplicar/i }));
    await waitFor(() =>
      expect(crear).toHaveBeenCalledWith(
        expect.objectContaining({
          documento: comp().documento,
          titulo: "Mi reel (copia)",
          estado: "borrador",
        }),
      ),
    );
  });

  it("FILTRA por estado (Borradores / Listos)", async () => {
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({
      composiciones: [
        comp({ id: "comp-b", titulo: "Un borrador", estado: "borrador" }),
        comp({ id: "comp-l", titulo: "Uno listo", estado: "listo" }),
      ],
    });
    renderGestor();
    await screen.findByText("Un borrador");
    expect(screen.getByText("Uno listo")).toBeInTheDocument();
    // Filtra a Listos: el borrador desaparece.
    fireEvent.click(screen.getByRole("tab", { name: /^listos$/i }));
    await waitFor(() => expect(screen.queryByText("Un borrador")).not.toBeInTheDocument());
    expect(screen.getByText("Uno listo")).toBeInTheDocument();
  });
});
