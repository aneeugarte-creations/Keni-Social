import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  MarcaActivaContexto,
  type ValorMarcaActiva,
} from "@/hooks/marca-activa-contexto";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import * as apiMod from "@/lib/api";
import type { UsuarioSesion } from "@/types";

import Rota from "./index";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

function usuario(): UsuarioSesion {
  return {
    id: "u1",
    usuario: "yo",
    rol: "admin",
    debe_cambiar_password: false,
    marcas: ["claro-sports"],
  };
}

function sesionValor(): ValorSesion {
  return {
    usuario: usuario(),
    cargando: false,
    iniciarSesion: vi.fn(),
    verificarConPasskey: vi.fn(),
    verificarConCodigo: vi.fn(),
    cerrarSesion: vi.fn(),
    refrescar: vi.fn(),
  };
}

function valorMarca(): ValorMarcaActiva {
  return {
    marcaActiva: "claro-sports",
    marcaPrimaria: "claro-sports",
    enMarcaPrimaria: true,
    esMultiMarca: false,
    puedeTodas: false,
    marcasParaSwitch: [],
    nombreActiva: "Claro Sports",
    cambiarMarca: vi.fn(),
    volverAPrimaria: vi.fn(),
  };
}

function renderRota() {
  // El Calendario de Turnos dispara varias consultas de rota; las dejamos vacías (sus
  // lecturas están guardadas con `?? []`) para centrarnos en la pestaña «Cobertura».
  for (const m of [
    "cobertura",
    "listarTurnos",
    "rotaEquipo",
    "rotaEquipoTodos",
    "rotaAusencias",
    "listarCoordinacionSemana",
    "misTurnos",
    "misTurnosMes",
  ] as const) {
    vi.spyOn(apiMod.api, m).mockResolvedValue({} as never);
  }
  // La pestaña «Cobertura» monta el TareasBoard: necesita estas dos.
  vi.spyOn(apiMod.api, "contenido").mockResolvedValue({
    contenidos: [],
    catalogos: { usuarios: [] },
  } as never);
  vi.spyOn(apiMod.api, "rotaEventos").mockResolvedValue({ eventos: [] } as never);

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesionValor()}>
        <MarcaActivaContexto.Provider value={valorMarca()}>
          <MemoryRouter>
            <Rota />
          </MemoryRouter>
        </MarcaActivaContexto.Provider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("Turnos — integra el tablero de Tareas en la pestaña «Cobertura»", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("abre en la semana ACTUAL (la que contiene hoy), no en la siguiente", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-06-15T12:00:00Z")); // lunes 15 jun 2026 (CDMX)
    renderRota();
    // El Calendario pide los turnos de la semana por defecto: el lunes de HOY (no el siguiente).
    await vi.waitFor(() =>
      expect(
        vi
          .mocked(apiMod.api.listarTurnos)
          .mock.calls.some(([arg]) => (arg as { lunes?: string })?.lunes === "2026-06-15"),
      ).toBe(true),
    );
  });

  it("muestra la pestaña «Cobertura» junto a «Calendario», con el Calendario por defecto", async () => {
    renderRota();
    expect(await screen.findByRole("tab", { name: "Calendario" })).toHaveAttribute(
      "data-state",
      "active",
    );
    expect(screen.getByRole("tab", { name: "Cobertura" })).toBeInTheDocument();
    // No se rompe la barra de Turnos: el «Añadir» de Tareas NO está visible aún (otra pestaña).
    expect(screen.queryByRole("button", { name: "Añadir" })).toBeNull();
  });

  it("al abrir «Cobertura» aparece el tablero (Panorama + «Añadir» inline)", async () => {
    renderRota();
    // Radix Tabs activa en pointer-down (patrón de la suite).
    fireEvent.mouseDown(await screen.findByRole("tab", { name: "Cobertura" }), { button: 0 });

    // El tablero embebido pinta su botón «Añadir» inline (barra) y, al cargar, el atajo «Añadir»
    // del Panorama: dos botones «Añadir». Basta con que aparezca alguno (el tablero ya montó).
    expect((await screen.findAllByRole("button", { name: "Añadir" })).length).toBeGreaterThan(0);
    expect(
      await screen.findByRole("button", { name: "Ver solo lo por cubrir" }),
    ).toBeInTheDocument();
  });

  it("«Mis turnos» vacío ofrece al admin saltar al Calendario", async () => {
    renderRota();
    fireEvent.mouseDown(await screen.findByRole("tab", { name: "Mis turnos" }), {
      button: 0,
    });
    // El admin no está en la rota: el vacío trae un CTA hacia el Calendario.
    const ir = await screen.findByRole("button", {
      name: /Ver el calendario del equipo/,
    });
    fireEvent.click(ir);
    // Al pulsarlo, la pestaña Calendario vuelve a estar activa.
    expect(await screen.findByRole("tab", { name: "Calendario" })).toHaveAttribute(
      "data-state",
      "active",
    );
  });
});
