/**
 * Tests de la página CarrilRapido (Carril Rápido de Breaking — Claro Sports).
 *
 * Cubre:
 *   1. Renderiza el estado vacío cuando no hay items breaking.
 *   2. Muestra las tarjetas cuando la API devuelve items.
 *   3. El botón "Preparar borrador" llama a `api.breaking.preparar`.
 *   4. Muestra "Borrador listo" cuando el item ya tiene borrador.
 *   5. La pestaña es visible para claro-sports y para "Todas" (admin).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import { MarcaActivaProvider } from "@/hooks/use-marca-activa";
import * as apiMod from "@/lib/api";
import { MARCA_CLARO_SPORTS, rutaVisibleParaMarca } from "@/components/layout/gating-marca";
import type { UsuarioSesion, BreakingItem } from "@/types";

import CarrilRapido from "./CarrilRapido";

// ── Helpers ───────────────────────────────────────────────────────────────────

function usuario(marcas: string[] = ["claro-sports"]): UsuarioSesion {
  return {
    id: "u1",
    usuario: "elias",
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
    verificarConPasskey: vi.fn(), verificarConCodigo: vi.fn(),
    cerrarSesion: vi.fn(),
    refrescar: vi.fn(),
  };
}

function renderConProviders(ui: React.ReactElement, u = usuario()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesionValor(u)}>
        <MarcaActivaProvider>
          <MemoryRouter>{ui}</MemoryRouter>
        </MarcaActivaProvider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

function breakingItem(overrides: Partial<BreakingItem> = {}): BreakingItem {
  return {
    titulo: "Gol de último minuto",
    marca: MARCA_CLARO_SPORTS,
    marca_nombre: "Claro Sports",
    senal: 120_000,
    senal_texto: "120K+",
    breaking: true,
    idioma: "es",
    fuentes: ["Google Trends"],
    enlaces: [{ titulo: "Crónica del gol", url: "https://example.com", fuente: "ESPN" }],
    fecha: "2026-06-05T10:00:00",
    estado_borrador: "ninguno",
    contenido_id: "",
    generacion_id: "",
    ...overrides,
  };
}

const RESPUESTA_VACIA = { items: [] };
const RESPUESTA_UN_ITEM = { items: [breakingItem()] };
const RESPUESTA_BORRADOR_LISTO = {
  items: [breakingItem({ estado_borrador: "listo", contenido_id: "c-99" })],
};

// ── Antes/después ─────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockBreaking: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockPreparar: any;

beforeEach(() => {
  mockBreaking = vi
    .spyOn(apiMod.api.breaking, "listar")
    .mockResolvedValue(RESPUESTA_VACIA);
  mockPreparar = vi
    .spyOn(apiMod.api.breaking, "preparar")
    .mockResolvedValue({ contenido_id: "c-nuevo", generacion_id: "gen-1" });
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("CarrilRapido", () => {
  it("muestra estado vacío cuando no hay items", async () => {
    renderConProviders(<CarrilRapido />);
    await waitFor(() => {
      expect(screen.getByText(/Sin breaking por ahora/i)).toBeDefined();
    });
  });

  it("muestra las tarjetas cuando hay items breaking", async () => {
    mockBreaking.mockResolvedValue(RESPUESTA_UN_ITEM);
    renderConProviders(<CarrilRapido />);
    await waitFor(() => {
      expect(screen.getByText("Gol de último minuto")).toBeDefined();
    });
    expect(screen.getByText("120K+")).toBeDefined();
  });

  it("el botón 'Preparar borrador' llama a api.breaking.preparar", async () => {
    mockBreaking.mockResolvedValue(RESPUESTA_UN_ITEM);
    renderConProviders(<CarrilRapido />);
    await waitFor(() => {
      expect(screen.getByText("Gol de último minuto")).toBeDefined();
    });
    const boton = screen.getByRole("button", { name: /Preparar borrador/i });
    fireEvent.click(boton);
    await waitFor(() => {
      expect(mockPreparar).toHaveBeenCalledWith(
        expect.objectContaining({ titulo: "Gol de último minuto", marca: MARCA_CLARO_SPORTS }),
      );
    });
  });

  it("muestra 'Ver borrador' cuando el item ya tiene borrador listo", async () => {
    mockBreaking.mockResolvedValue(RESPUESTA_BORRADOR_LISTO);
    renderConProviders(<CarrilRapido />);
    await waitFor(() => {
      expect(screen.getByText(/Ver borrador/i)).toBeDefined();
    });
    // El botón "Preparar borrador" no debe aparecer.
    expect(screen.queryByRole("button", { name: /Preparar borrador/i })).toBeNull();
  });

  it("muestra enlace al contexto del item", async () => {
    mockBreaking.mockResolvedValue(RESPUESTA_UN_ITEM);
    renderConProviders(<CarrilRapido />);
    await waitFor(() => {
      expect(screen.getByText("Crónica del gol")).toBeDefined();
    });
  });
});

// ── Tests de gating de ruta ──────────────────────────────────────────────────

describe("gating de ruta /operacion/revision/breaking", () => {
  const RUTA = "/operacion/revision/breaking";

  it("es visible para claro-sports", () => {
    expect(rutaVisibleParaMarca(RUTA, MARCA_CLARO_SPORTS)).toBe(true);
  });

  it("es visible para 'Todas' (admin, marcaActiva=null)", () => {
    expect(rutaVisibleParaMarca(RUTA, null)).toBe(true);
  });

  it("NO es visible para otra marca concreta", () => {
    expect(rutaVisibleParaMarca(RUTA, "unotv")).toBe(false);
  });
});
