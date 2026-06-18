import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
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
    entrarConPasskey: vi.fn(),
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

/**
 * Sobreescrituras opcionales de las respuestas de API que el Calendario consume. Por defecto
 * van vacías (las lecturas están guardadas con `?? []`); los tests que necesitan un evento en
 * la rejilla inyectan `cobertura` (eventos), `contenido` (tareas+catálogos) y `listarTurnos`
 * (franjas vivas, sin las cuales el evento no se bucketea a ninguna celda).
 */
type OpcionesRender = {
  cobertura?: unknown;
  contenido?: unknown;
  listarTurnos?: unknown;
};

function renderRota(opts: OpcionesRender = {}) {
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
    "turnosMes",
  ] as const) {
    vi.spyOn(apiMod.api, m).mockResolvedValue({} as never);
  }
  // La pestaña «Cobertura» monta el TareasBoard: necesita estas dos.
  vi.spyOn(apiMod.api, "contenido").mockResolvedValue({
    contenidos: [],
    catalogos: { usuarios: [] },
  } as never);
  vi.spyOn(apiMod.api, "rotaEventos").mockResolvedValue({ eventos: [] } as never);

  if (opts.cobertura !== undefined)
    vi.spyOn(apiMod.api, "cobertura").mockResolvedValue(opts.cobertura as never);
  if (opts.listarTurnos !== undefined)
    vi.spyOn(apiMod.api, "listarTurnos").mockResolvedValue(opts.listarTurnos as never);
  if (opts.contenido !== undefined)
    vi.spyOn(apiMod.api, "contenido").mockResolvedValue(opts.contenido as never);

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

  it("para el admin, «Mi jornada» abre en la vista «Equipo» (turnos de todos)", async () => {
    renderRota();
    fireEvent.mouseDown(await screen.findByRole("tab", { name: "Mi jornada" }), {
      button: 0,
    });
    // El admin no está en la rota: arranca en «Equipo» (jornada de todo el equipo), no en «Yo».
    expect(
      await screen.findByRole("button", { name: /Equipo/, pressed: true }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Yo$/, pressed: false })).toBeInTheDocument();
  });

  it("en el Calendario, clicar el chip de un evento abre su tarjeta de COBERTURA (no la edición)", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-06-15T12:00:00Z")); // lunes 15 jun 2026 (CDMX)
    // Un evento «Por cubrir» (sin tarea de cobertura) en la semana en vista, a una hora que
    // cae en la franja Mañana → se bucketea a una celda y pinta su chip clicable.
    renderRota({
      cobertura: {
        eventos: [
          {
            id: "ev-int",
            titulo: "España vs Cabo Verde",
            fecha: "2026-06-16",
            hora: "10:00",
            tipo_cobertura: "transmision",
            prioridad: "media",
            cambiado: false,
          },
        ],
      },
      // Sin las franjas vivas el evento no se bucketea a ninguna celda y el chip no aparece.
      listarTurnos: {
        turnos: [],
        aprobada: false,
        franjas: [
          {
            id: "f-manana",
            lunes: "2026-06-15",
            nombre: "Mañana",
            inicio: "08:00",
            fin: "14:00",
            orden: 0,
            es_descanso: false,
            marca: "claro-sports",
            marca_nombre: "Claro Sports",
          },
        ],
      },
      // Sin tareas de cobertura → el evento queda «Por cubrir» (TarjetaEventoLibre).
      contenido: { contenidos: [], catalogos: { usuarios: [] } },
    });

    // El chip de evento es clicable (su aria-label arranca por «Cubrir …»).
    const chip = await screen.findByRole("button", { name: /España vs Cabo Verde/ });
    fireEvent.click(chip);

    // Se abre un diálogo de COBERTURA (no el editor de evento): contiene la tarjeta «Por
    // cubrir» con su badge «Sin cubrir» y el menú de acciones (Asignar/Editar/Borrar).
    const dialogo = await screen.findByRole("dialog");
    expect(dialogo).toBeInTheDocument();
    expect(within(dialogo).getByText("Sin cubrir")).toBeInTheDocument();
    expect(
      within(dialogo).getByRole("button", { name: "Más acciones" }),
    ).toBeInTheDocument();
  });
});
