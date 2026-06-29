/**
 * Test mínimo de render de la subpágina de detalle de una historia (`DetalleHistoriaPagina`):
 *   - Carga la historia por id (GET /api/noticias/historias/{id}) y pinta sus secciones:
 *     cabecera (titular + frase de corroboración), Score, Fuentes/titulares similares.
 *   - Una historia en el pool ofrece «Empujar al feed» y «Descartar» (con confirmación).
 *   - Una pieza ya en el feed NO ofrece esas acciones.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { confirmar } from "@/components/comunes/confirmar";
import * as apiMod from "@/lib/api";
import type { Historia } from "@/types";

import DetalleHistoriaPagina from "./DetalleHistoriaPagina";

vi.mock("@/components/comunes/confirmar", () => ({ confirmar: vi.fn() }));

function historia(overrides: Partial<Historia> = {}): Historia {
  return {
    id: "h-1",
    titulo: "Sismo de 6.2 en Guerrero",
    resumen: "Resumen del cluster.",
    marca: "unotv",
    marca_nombre: "UnoTV",
    categoria: "mx",
    geo: "MX",
    n_items: 3,
    n_fuentes: 2,
    idiomas: ["es"],
    senal: 100,
    score: 0.55,
    breaking: 0,
    primer_visto: "2026-06-05T09:00:00",
    ultimo_visto: "2026-06-05T10:00:00",
    estado: "nuevo",
    publicacion_id: "",
    enlaces: [{ titulo: "Reforma cubre el sismo", url: "https://example.com/1", fuente: "Reforma" }],
    fuentes: [
      { fuente: "Reforma", fuente_id: "f1", peso: 1, tier: "normal", primer_visto: "2026-06-05T09:00:00", n_items: 2 },
      { fuente: "El Universal", fuente_id: "f2", peso: 1, tier: "normal", primer_visto: "2026-06-05T09:40:00", n_items: 1 },
    ],
    primera_fuente_nombre: "Reforma",
    peso_fuentes: 2,
    ...overrides,
  };
}

function renderPagina(h: Historia) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/operacion/investigacion/historia/${h.id}`]}>
        <Routes>
          <Route
            path="/operacion/investigacion/historia/:id"
            element={<DetalleHistoriaPagina />}
          />
          <Route path="/operacion/investigacion/noticias" element={<div>Mesa</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockHistoria: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockUsar: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockDescartar: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockDevolver: any;

beforeEach(() => {
  mockHistoria = vi.spyOn(apiMod.api.noticias, "historia").mockResolvedValue({
    historia: historia(),
    items: [],
  });
  mockUsar = vi
    .spyOn(apiMod.api.noticias, "usarHistoria")
    .mockResolvedValue({ ok: true, publicacion_id: "c-1" });
  mockDescartar = vi
    .spyOn(apiMod.api.noticias, "descartarHistoria")
    .mockResolvedValue({ ok: true });
  mockDevolver = vi
    .spyOn(apiMod.api.noticias, "devolverHistoria")
    .mockResolvedValue({ historia: historia() });
  vi.mocked(confirmar).mockResolvedValue(true);
});

afterEach(() => vi.restoreAllMocks());

describe("DetalleHistoriaPagina", () => {
  it("carga la historia por id y pinta sus secciones", async () => {
    renderPagina(historia());
    await waitFor(() => expect(mockHistoria).toHaveBeenCalledWith("h-1", expect.anything()));
    expect(await screen.findByText("Sismo de 6.2 en Guerrero")).toBeTruthy();
    expect(screen.getByTestId("frase-corroboracion")).toBeTruthy();
    expect(screen.getByTestId("calculo-score")).toBeTruthy();
    expect(screen.getByTestId("timeline-fuentes")).toBeTruthy();
    expect(screen.getByTestId("lista-enlaces")).toBeTruthy();
  });

  it("una historia en el pool ofrece Empujar al feed", async () => {
    renderPagina(historia());
    fireEvent.click(await screen.findByTestId("btn-empujar"));
    await waitFor(() => expect(mockUsar).toHaveBeenCalledWith("h-1", { generar: true }));
  });

  it("Descartar pide confirmación antes de borrar (irreversible)", async () => {
    renderPagina(historia());
    fireEvent.click(await screen.findByTestId("btn-descartar"));
    await waitFor(() =>
      expect(confirmar).toHaveBeenCalledWith(
        expect.objectContaining({ destructivo: true, textoConfirmar: "Descartar" }),
      ),
    );
    await waitFor(() => expect(mockDescartar).toHaveBeenCalledWith("h-1"));
  });

  it("Descartar cancelado en el confirm NO llama a la API", async () => {
    vi.mocked(confirmar).mockResolvedValue(false);
    renderPagina(historia());
    fireEvent.click(await screen.findByTestId("btn-descartar"));
    await waitFor(() => expect(confirmar).toHaveBeenCalled());
    expect(mockDescartar).not.toHaveBeenCalled();
  });

  it("una historia atascada (en_cola) ofrece Devolver a Noticias", async () => {
    mockHistoria.mockResolvedValue({
      historia: historia({ estado: "usado", publicacion_id: "c-1", pieza_estado: "en_cola" }),
      items: [],
    });
    renderPagina(historia());
    fireEvent.click(await screen.findByTestId("btn-devolver"));
    await waitFor(() => expect(confirmar).toHaveBeenCalled());
    await waitFor(() => expect(mockDevolver).toHaveBeenCalledWith("h-1"));
  });

  it("una historia en el pool no ofrece Devolver", async () => {
    renderPagina(historia());
    await screen.findByTestId("btn-empujar");
    expect(screen.queryByTestId("btn-devolver")).toBeNull();
  });

  it("una pieza ya en el feed no ofrece empujar/descartar", async () => {
    mockHistoria.mockResolvedValue({
      historia: historia({ estado: "usado", publicacion_id: "c-1", pieza_estado: "en_feed" }),
      items: [],
    });
    renderPagina(historia());
    await screen.findByText("Sismo de 6.2 en Guerrero");
    expect(screen.queryByTestId("btn-empujar")).toBeNull();
    expect(screen.queryByTestId("btn-descartar")).toBeNull();
    expect(screen.getByText(/En el feed/i)).toBeTruthy();
  });
});
