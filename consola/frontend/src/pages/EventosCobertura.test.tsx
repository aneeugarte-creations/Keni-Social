/**
 * Tests de la página EventosCobertura (hub Fuentes › Eventos y programas).
 *
 * Cubren:
 * 1. Renderiza el encabezado y la sub-pestaña "Eventos" con PanelEventos.
 * 2. Lista los eventos que devuelve `/api/rota/eventos`.
 * 3. Muestra el atajo "Cobertura en Turnos" (marca = Todas/Claro Sports por defecto).
 * 4. La sub-pestaña "Programas" renderiza el PanelProgramas (lista /api/rota/programas).
 * 5. Lista los programas que devuelve la API.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import { MarcaActivaProvider } from "@/hooks/use-marca-activa";
import * as apiMod from "@/lib/api";
import type { UsuarioSesion } from "@/types";

import EventosCobertura from "./EventosCobertura";

function usuario(): UsuarioSesion {
  return {
    id: "u1",
    usuario: "ana",
    rol: "admin",
    debe_cambiar_password: false,
    marcas: ["claro-sports"],
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

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesionValor(usuario())}>
        <MarcaActivaProvider>
          <MemoryRouter>{ui}</MemoryRouter>
        </MarcaActivaProvider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

const EVENTO = {
  id: "ev-1",
  titulo: "Cruz Azul vs América",
  fecha: "2026-06-10",
  hora: "21:00",
  contenido: "Clip del gol",
  nota: "",
  tipo_cobertura: "transmision" as const,
  prioridad: "alta" as const,
  cambiado: false,
  es_sabado: false,
  actualizado: "2026-06-05T10:00:00",
  creado: "2026-06-05T10:00:00",
};

const PROGRAMA = {
  id: "prog-1",
  nombre: "Álvaro Fidalgo",
  descripcion: "Programa del jugador",
  color: "#3b82f6",
  inicio: "2026-01-01",
  fin: "2026-12-31",
  activo: true,
  creado: "2026-01-01T00:00:00",
  actualizado: "2026-01-01T00:00:00",
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

describe("EventosCobertura", () => {
  it("renderiza el encabezado y el formulario de nuevo evento", async () => {
    vi.spyOn(apiMod.api, "rotaEventos").mockResolvedValue({ eventos: [] } as never);
    renderConProviders(<EventosCobertura />);

    expect(
      await screen.findByRole("heading", { name: "Eventos y programas" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Nuevo evento")).toBeInTheDocument();
  });

  it("lista los eventos que devuelve la API", async () => {
    vi.spyOn(apiMod.api, "rotaEventos").mockResolvedValue({ eventos: [EVENTO] } as never);
    renderConProviders(<EventosCobertura />);

    expect(await screen.findByText("Cruz Azul vs América")).toBeInTheDocument();
  });

  it("muestra el atajo a la cobertura en Turnos por defecto (marca Todas)", async () => {
    vi.spyOn(apiMod.api, "rotaEventos").mockResolvedValue({ eventos: [] } as never);
    renderConProviders(<EventosCobertura />);

    await screen.findByRole("heading", { name: "Eventos y programas" });
    const enlace = screen.getByRole("link", { name: /Cobertura en Turnos/i });
    expect(enlace).toHaveAttribute("href", "/operacion/calendario/turnos");
  });

  it("muestra las sub-pestañas Eventos y Programas", async () => {
    vi.spyOn(apiMod.api, "rotaEventos").mockResolvedValue({ eventos: [] } as never);
    renderConProviders(<EventosCobertura />);

    await screen.findByRole("heading", { name: "Eventos y programas" });
    expect(screen.getByRole("tab", { name: "Eventos" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Programas" })).toBeInTheDocument();
  });

  it("la sub-pestaña Programas renderiza el catálogo al hacer clic", async () => {
    vi.spyOn(apiMod.api, "rotaEventos").mockResolvedValue({ eventos: [] } as never);
    vi.spyOn(apiMod.api, "listarProgramasRota").mockResolvedValue({
      programas: [PROGRAMA],
    } as never);
    renderConProviders(<EventosCobertura />);

    await screen.findByRole("heading", { name: "Eventos y programas" });

    // Radix UI Tabs usa `onMouseDown` para el cambio de pestaña.
    const tabProgramas = screen.getByRole("tab", { name: "Programas" });
    fireEvent.mouseDown(tabProgramas);

    await waitFor(() => {
      expect(screen.getByText("Álvaro Fidalgo")).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it("la sub-pestaña Programas muestra «Sin programas» si la API devuelve lista vacía", async () => {
    vi.spyOn(apiMod.api, "rotaEventos").mockResolvedValue({ eventos: [] } as never);
    vi.spyOn(apiMod.api, "listarProgramasRota").mockResolvedValue({
      programas: [],
    } as never);
    renderConProviders(<EventosCobertura />);

    await screen.findByRole("heading", { name: "Eventos y programas" });

    // Radix UI Tabs usa `onMouseDown` para el cambio de pestaña.
    const tabProgramas = screen.getByRole("tab", { name: "Programas" });
    fireEvent.mouseDown(tabProgramas);

    await waitFor(() => {
      expect(screen.getByText("Sin programas")).toBeInTheDocument();
    }, { timeout: 3000 });
  });
});
