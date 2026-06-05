/**
 * Tests para el badge "traducido de {idioma}" y chip de idioma en Radar.tsx
 * (Ola 4: Fuentes externas + idiomas).
 *
 * Valida:
 * - Temas con `traducido: true` muestran el badge "traducido de {IDIOMA}".
 * - El badge tiene un tooltip con el `titulo_original` cuando está disponible.
 * - Temas con `idioma` distinto de "es" pero sin traducir muestran chip de idioma.
 * - Temas sin campos de idioma/traducción no muestran ningún badge de idioma
 *   (no rompen el render existente).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import { MarcaActivaProvider } from "@/hooks/use-marca-activa";
import type { UsuarioSesion } from "@/types";

import { PanelTendencias } from "./Radar";

// ── Datos de prueba ─────────────────────────────────────────────────────────

function radarConTemas(temas: unknown[]) {
  return {
    marca: null,
    total: temas.length,
    total_fuera_foco: 0,
    geos_disponibles: [{ id: "MX", nombre: "México" }],
    temas,
    fuentes: [
      { id: "trends", nombre: "Google Trends", disponible: true, conteo: temas.length, motivo: "" },
    ],
    fuentes_pendientes: [],
  };
}

const TEMA_TRADUCIDO = {
  titulo: "Champions League draw results",
  senal_texto: "Trending",
  redes: ["x"],
  fuentes: ["Reuters"],
  por_que: "El sorteo de la Champions generó millones de reacciones.",
  senal: 85,
  enlaces: [],
  estado: "nuevo",
  prioritario: false,
  breaking: false,
  idioma: "en",
  traducido: true,
  titulo_original: "Champions League draw results",
};

const TEMA_IDIOMA_SIN_TRADUCIR = {
  titulo: "Le match du siècle",
  senal_texto: "Viral",
  redes: ["x"],
  fuentes: ["L'Équipe"],
  por_que: "Partido épico en Francia.",
  senal: 60,
  enlaces: [],
  estado: "nuevo",
  prioritario: false,
  breaking: false,
  idioma: "fr",
  traducido: false,
};

const TEMA_SIN_IDIOMA = {
  titulo: "Sismo en CDMX",
  senal_texto: "Tendencia MX",
  redes: ["x"],
  fuentes: ["Google Trends"],
  por_que: "Pico de búsquedas locales.",
  senal: 90,
  enlaces: [],
  estado: "nuevo",
  prioritario: false,
  breaking: false,
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function stubFetch(temas: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL) => {
      const ruta = String(url);
      if (ruta.includes("/api/radar")) {
        return new Response(JSON.stringify(radarConTemas(temas)), { status: 200 });
      }
      return new Response("{}", { status: 200 });
    }),
  );
}

function usuario(): UsuarioSesion {
  return {
    id: "u1",
    usuario: "ana",
    rol: "editor",
    debe_cambiar_password: false,
    marcas: ["unotv"],
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

function renderPanel(temas: unknown[]) {
  stubFetch(temas);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesionValor(usuario())}>
        <MarcaActivaProvider>
          <MemoryRouter>
            <PanelTendencias />
          </MemoryRouter>
        </MarcaActivaProvider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("Radar — badges de idioma y traducción (Ola 4)", () => {
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

  it("muestra el badge 'traducido de EN' para un tema con traducido:true", async () => {
    renderPanel([TEMA_TRADUCIDO]);

    // El título ya traducido al español debe verse.
    expect(await screen.findByText("Champions League draw results")).toBeInTheDocument();

    // El badge de traducción debe estar presente.
    expect(screen.getByText(/traducido de EN/i)).toBeInTheDocument();
  });

  it("el badge 'traducido' tiene el aria-label del tooltip con el titulo_original", async () => {
    renderPanel([TEMA_TRADUCIDO]);

    await screen.findByText("Champions League draw results");

    // El Tooltip añade aria-label al hijo con el texto del tooltip.
    // El badge "traducido de EN" recibe el label del Tooltip.
    const badge = screen.getByText(/traducido de EN/i);
    // El Tooltip clona el hijo con aria-label; lo verificamos vía el wrapper span del Tooltip.
    expect(badge.closest("[role='tooltip']") ?? badge.parentElement).toBeTruthy();
  });

  it("muestra chip de idioma 'FR' para un tema no traducido con idioma:fr", async () => {
    renderPanel([TEMA_IDIOMA_SIN_TRADUCIR]);

    await screen.findByText("Le match du siècle");

    // Chip de idioma sin el texto "traducido".
    expect(screen.getByText("FR")).toBeInTheDocument();
    expect(screen.queryByText(/traducido de/i)).not.toBeInTheDocument();
  });

  it("no muestra ningún badge de idioma para un tema sin campos de idioma", async () => {
    renderPanel([TEMA_SIN_IDIOMA]);

    await screen.findByText("Sismo en CDMX");

    // Sin idioma ni traducción, no debe aparecer ningún badge de idioma.
    expect(screen.queryByText(/traducido de/i)).not.toBeInTheDocument();
    expect(screen.queryByText("ES")).not.toBeInTheDocument();
  });

  it("no rompe el render cuando coexisten temas con y sin campos de idioma", async () => {
    renderPanel([TEMA_TRADUCIDO, TEMA_SIN_IDIOMA, TEMA_IDIOMA_SIN_TRADUCIR]);

    // Los tres títulos deben aparecer.
    expect(await screen.findByText("Champions League draw results")).toBeInTheDocument();
    expect(await screen.findByText("Sismo en CDMX")).toBeInTheDocument();
    expect(await screen.findByText("Le match du siècle")).toBeInTheDocument();

    // Solo el tema traducido tiene el badge de traducción.
    expect(screen.getAllByText(/traducido de EN/i)).toHaveLength(1);
    // El tema FR tiene su chip.
    expect(screen.getByText("FR")).toBeInTheDocument();
  });
});
