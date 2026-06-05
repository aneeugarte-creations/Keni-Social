/**
 * Tests de la página EventosCobertura (hub Fuentes › Eventos).
 *
 * Cubren:
 * 1. Renderiza el encabezado y el formulario "Nuevo evento" (PanelEventos).
 * 2. Lista los eventos que devuelve `/api/rota/eventos`.
 * 3. Muestra el atajo "Cobertura en Turnos" (marca = Todas/Claro Sports por defecto).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
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
    verificarMfa: vi.fn(),
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
      await screen.findByRole("heading", { name: "Eventos" }),
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

    await screen.findByRole("heading", { name: "Eventos" });
    const enlace = screen.getByRole("link", { name: /Cobertura en Turnos/i });
    expect(enlace).toHaveAttribute("href", "/operacion/calendario/turnos");
  });
});
