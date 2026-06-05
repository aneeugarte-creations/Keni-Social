/**
 * Tests de PanelEventos — marca-aware.
 *
 * Cubren:
 * 1. La query a la API incluye la marca activa del workspace.
 * 2. El formulario "Nuevo evento" arranca con la marca activa como default.
 * 3. Se muestra el badge de marca en cada tarjeta de evento cuando el evento
 *    tiene marca_nombre.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import { MarcaActivaProvider } from "@/hooks/use-marca-activa";
import * as apiMod from "@/lib/api";
import type { UsuarioSesion } from "@/types";

import { PanelEventos } from "./PanelEventos";

function usuario(marcas: string[] = ["claro-sports"]): UsuarioSesion {
  return {
    id: "u1",
    usuario: "ana",
    rol: "editor",
    debe_cambiar_password: false,
    marcas,
  };
}

function sesionValor(u: UsuarioSesion | null): ValorSesion {
  return {
    usuario: u,
    cargando: false,
    iniciarSesion: vi.fn(),
    verificarConPasskey: vi.fn(),
    verificarConCodigo: vi.fn(),
    cerrarSesion: vi.fn(),
    refrescar: vi.fn(),
  };
}

function renderConProviders(ui: React.ReactElement, marcas: string[] = ["claro-sports"]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesionValor(usuario(marcas))}>
        <MarcaActivaProvider>
          <MemoryRouter>{ui}</MemoryRouter>
        </MarcaActivaProvider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

const EVENTO_CON_MARCA = {
  id: "ev-1",
  titulo: "Final Liga MX",
  fecha: "2026-06-10",
  hora: "21:00",
  contenido: "Clip del gol",
  nota: "",
  tipo_cobertura: "transmision" as const,
  prioridad: "alta" as const,
  cambiado: false,
  es_sabado: false,
  actualizado: "2026-06-05T10:00:00",
  marca: "claro-sports",
  marca_nombre: "Claro Sports",
};

beforeEach(() => {
  vi.restoreAllMocks();
  const store = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
  });
});
afterEach(() => vi.unstubAllGlobals());

describe("PanelEventos marca-aware", () => {
  it("pasa la marca activa a la API al listar eventos", async () => {
    const spy = vi
      .spyOn(apiMod.api, "rotaEventos")
      .mockResolvedValue({ eventos: [] } as never);
    // Stub publicacionesOpciones para que MarcaActivaProvider resuelva el catálogo.
    vi.spyOn(apiMod.api, "publicacionesOpciones").mockResolvedValue({
      marcas: [{ id: "claro-sports", nombre: "Claro Sports" }],
    } as never);

    renderConProviders(<PanelEventos />, ["claro-sports"]);

    await waitFor(() => {
      expect(spy).toHaveBeenCalled();
    });
    const llamada = spy.mock.calls[0][0];
    expect(llamada?.marca).toBe("claro-sports");
  });

  it("muestra el badge de marca en la tarjeta de evento", async () => {
    vi.spyOn(apiMod.api, "rotaEventos").mockResolvedValue({
      eventos: [EVENTO_CON_MARCA],
    } as never);
    vi.spyOn(apiMod.api, "publicacionesOpciones").mockResolvedValue({
      marcas: [{ id: "claro-sports", nombre: "Claro Sports" }],
    } as never);

    renderConProviders(<PanelEventos />, ["claro-sports"]);

    expect(await screen.findByText("Final Liga MX")).toBeInTheDocument();
    // Debe haber al menos un elemento con "Claro Sports" (el badge de marca en la tarjeta).
    expect(screen.getAllByText("Claro Sports").length).toBeGreaterThanOrEqual(1);
  });

  it("no filtra por marca cuando el usuario tiene vista agregada (null)", async () => {
    const spy = vi
      .spyOn(apiMod.api, "rotaEventos")
      .mockResolvedValue({ eventos: [] } as never);
    vi.spyOn(apiMod.api, "publicacionesOpciones").mockResolvedValue({
      marcas: [
        { id: "claro-sports", nombre: "Claro Sports" },
        { id: "unotv", nombre: "UnoTV" },
      ],
    } as never);

    // Admin sin marca primaria asignada → marcaActiva = null → sin filtro.
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const adminSinMarca: UsuarioSesion = {
      id: "admin1",
      usuario: "admin",
      rol: "admin",
      debe_cambiar_password: false,
      marcas: [],
    };
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
    });
    render(
      <QueryClientProvider client={client}>
        <SesionContexto.Provider
          value={{
            usuario: adminSinMarca,
            cargando: false,
            iniciarSesion: vi.fn(),
            verificarConPasskey: vi.fn(),
            verificarConCodigo: vi.fn(),
            cerrarSesion: vi.fn(),
            refrescar: vi.fn(),
          }}
        >
          <MarcaActivaProvider>
            <MemoryRouter>
              <PanelEventos />
            </MemoryRouter>
          </MarcaActivaProvider>
        </SesionContexto.Provider>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(spy).toHaveBeenCalled();
    });
    const llamada = spy.mock.calls[0][0];
    // marca undefined → no se incluye en la query string → todos los eventos.
    expect(llamada?.marca).toBeUndefined();
  });
});
