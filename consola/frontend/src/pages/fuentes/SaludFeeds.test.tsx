/**
 * Tests de SaludFeeds (la salud del motor de ingesta, antes sub-vista "Salud" de
 * Cobertura/Noticias, ahora una pestaña de Fuentes). Cubre:
 *   1. Llama a api.noticias.salud con la marca activa (y undefined en "Todas").
 *   2. Resumen con chips de estado y lista de huecos de cobertura.
 *   3. Tabla de feeds; botón Reactivar solo en auto-desactivados → fuentes.reactivar.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  MarcaActivaContexto,
  type ValorMarcaActiva,
} from "@/hooks/marca-activa-contexto";
import * as apiMod from "@/lib/api";
import type { SaludCobertura } from "@/types";

import { SaludFeeds } from "./SaludFeeds";

// ── Fixtures ──────────────────────────────────────────────────────────────────

const SALUD_COBERTURA: SaludCobertura = {
  resumen: {
    feeds_total: 20,
    activos: 15,
    auto_desactivados: 2,
    fallando: 1,
    stale: 3,
    items_24h: 420,
    por_categoria: { mx: 200, deportes: 120, internacional: 100 },
    por_idioma: { es: 300, en: 120 },
    huecos: ["gaming", "ciencia-tech"],
    frescura_global_min: 45,
  },
  feeds: [
    {
      id: "feed-1",
      nombre: "Reforma RSS",
      categoria: "mx",
      marca: "unotv",
      marca_nombre: "UnoTV",
      activo: 1,
      desactivado_auto: 0,
      ultima_actualizacion: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
      ultimo_error: "",
      errores_seguidos: 0,
      items_24h: 45,
      frescura_min: 30,
    },
    {
      id: "feed-2",
      nombre: "Feed caído",
      categoria: "deportes",
      marca: "unotv",
      marca_nombre: "UnoTV",
      activo: 0,
      desactivado_auto: 1,
      ultima_actualizacion: new Date(Date.now() - 5 * 3600 * 1000).toISOString(),
      ultimo_error: "Connection refused",
      errores_seguidos: 9,
      items_24h: 0,
      frescura_min: null,
    },
  ],
};

const SALUD_VACIA: SaludCobertura = {
  resumen: {
    feeds_total: 0,
    activos: 0,
    auto_desactivados: 0,
    fallando: 0,
    stale: 0,
    items_24h: 0,
    por_categoria: {},
    por_idioma: {},
    huecos: [],
    frescura_global_min: 0,
  },
  feeds: [],
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function valorMarcaActiva(marcaActiva: string | null): ValorMarcaActiva {
  return {
    marcaActiva,
    marcaPrimaria: marcaActiva,
    enMarcaPrimaria: true,
    esMultiMarca: false,
    puedeTodas: false,
    marcasParaSwitch: [],
    nombreActiva: marcaActiva,
    cambiarMarca: vi.fn(),
    volverAPrimaria: vi.fn(),
  };
}

function renderSalud(marcaActiva: string | null = "unotv") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MarcaActivaContexto.Provider value={valorMarcaActiva(marcaActiva)}>
        <SaludFeeds />
      </MarcaActivaContexto.Provider>
    </QueryClientProvider>,
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockSalud: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockReactivar: any;

beforeEach(() => {
  mockSalud = vi.spyOn(apiMod.api.noticias, "salud").mockResolvedValue(SALUD_VACIA);
  mockReactivar = vi
    .spyOn(apiMod.api.fuentes, "reactivar")
    .mockResolvedValue({ ok: true });
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("SaludFeeds · carga marca-aware", () => {
  it("llama a api.noticias.salud con la marca activa", async () => {
    renderSalud("unotv");
    await waitFor(() => {
      expect(mockSalud).toHaveBeenCalledWith("unotv", expect.anything());
    });
  });

  it("con marcaActiva=null pasa undefined a api.noticias.salud (vista admin)", async () => {
    renderSalud(null);
    await waitFor(() => {
      expect(mockSalud).toHaveBeenCalledWith(undefined, expect.anything());
    });
  });
});

describe("SaludFeeds · resumen y huecos", () => {
  it("muestra el resumen con chips de estado", async () => {
    mockSalud.mockResolvedValue(SALUD_COBERTURA);
    renderSalud();
    await waitFor(() => {
      expect(screen.getByTestId("salud-resumen")).toBeTruthy();
    });
    expect(screen.getByText(/15 activos/i)).toBeTruthy();
    expect(screen.getByText(/2 auto-desactivados/i)).toBeTruthy();
    expect(screen.getByText(/420/)).toBeTruthy();
  });

  it("muestra la lista de huecos de cobertura cuando los hay", async () => {
    mockSalud.mockResolvedValue(SALUD_COBERTURA);
    renderSalud();
    await waitFor(() => {
      expect(screen.getByTestId("salud-huecos-lista")).toBeTruthy();
    });
    expect(screen.getByText(/gaming/i)).toBeTruthy();
    expect(screen.getByText(/ciencia-tech/i)).toBeTruthy();
  });

  it("no muestra el bloque de huecos cuando no hay ninguno", async () => {
    mockSalud.mockResolvedValue(SALUD_VACIA);
    renderSalud();
    await waitFor(() => {
      expect(screen.getByText(/Sin feeds registrados/i)).toBeTruthy();
    });
    expect(screen.queryByTestId("salud-huecos-lista")).toBeNull();
  });
});

describe("SaludFeeds · tabla de feeds", () => {
  it("muestra la tabla de feeds con nombre y estado", async () => {
    mockSalud.mockResolvedValue(SALUD_COBERTURA);
    renderSalud();
    await waitFor(() => {
      expect(screen.getByTestId("salud-tabla-feeds")).toBeTruthy();
    });
    expect(screen.getByText("Reforma RSS")).toBeTruthy();
    expect(screen.getByText("Feed caído")).toBeTruthy();
  });

  it("ordena PROBLEMAS PRIMERO: el feed auto-desactivado va antes que el sano", async () => {
    mockSalud.mockResolvedValue(SALUD_COBERTURA);
    renderSalud();
    await waitFor(() => {
      expect(screen.getByTestId("salud-tabla-feeds")).toBeTruthy();
    });
    const filas = screen.getAllByRole("row").map((r) => r.textContent ?? "");
    const iCaido = filas.findIndex((t) => t.includes("Feed caído"));
    const iSano = filas.findIndex((t) => t.includes("Reforma RSS"));
    expect(iCaido).toBeGreaterThan(0);
    expect(iCaido).toBeLessThan(iSano); // el monitor enseña lo roto arriba
  });

  it("muestra el botón Reactivar solo para feeds auto-desactivados", async () => {
    mockSalud.mockResolvedValue(SALUD_COBERTURA);
    renderSalud();
    await waitFor(() => {
      expect(screen.getByTestId("btn-reactivar-feed-2")).toBeTruthy();
    });
    expect(screen.queryByTestId("btn-reactivar-feed-1")).toBeNull();
  });

  it("el botón Reactivar llama a api.fuentes.reactivar con el id del feed", async () => {
    mockSalud.mockResolvedValue(SALUD_COBERTURA);
    renderSalud();
    await waitFor(() => {
      expect(screen.getByTestId("btn-reactivar-feed-2")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("btn-reactivar-feed-2"));
    await waitFor(() => {
      expect(mockReactivar).toHaveBeenCalledWith("feed-2");
    });
  });
});
