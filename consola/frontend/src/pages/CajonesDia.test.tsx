/**
 * Tests de la página CajonesDia.
 *
 * Cubren:
 * 1. Renderiza las 4 tarjetas de cajones.
 * 2. Permite cambiar el día (selector de fecha).
 * 3. Muestra los ítems parseados cuando la API devuelve datos.
 * 4. El botón "Llevar al tablero" llama a `api.insumos.usarItem`.
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

import CajonesDia from "./CajonesDia";

// ── Helpers ───────────────────────────────────────────────────────────────────

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

// ── Fixtures ──────────────────────────────────────────────────────────────────

const INSUMOS_VACIOS = {
  fecha: "2026-06-05",
  cajones: [
    { cajon: "portal", lotes: [], items: [] },
    { cajon: "corresponsales", lotes: [], items: [] },
    { cajon: "reporteros", lotes: [], items: [] },
    { cajon: "eventos_claro", lotes: [], items: [] },
  ],
};

const ITEM_PARSED = {
  id: "item-1",
  lote_id: "lote-1",
  fecha: "2026-06-05",
  cajon: "portal" as const,
  marca: "unotv",
  marca_nombre: "UnoTV",
  linea: "Nacional",
  titulo: "Sismo en CDMX de 5.4 grados",
  resumen: "Sismo registrado esta madrugada sin daños.",
  hora: "06:00",
  lugar: "CDMX",
  estado_material: "" as const,
  tipo: "nota" as const,
  idioma: "es",
  usado: false,
  contenido_id: "",
  orden: 1,
  creado: "2026-06-05T06:00:00",
  frescura: "fresco" as const,
};

const ITEM_CADUCADO = {
  ...ITEM_PARSED,
  id: "item-2",
  titulo: "Noticia de ayer vencida",
  frescura: "caduco" as const,
};

const LOTE_PORTAL = {
  id: "lote-1",
  fecha: "2026-06-05",
  cajon: "portal",
  marca: "",
  origen_texto: "1.- SISMO EN CDMX",
  origen_archivo: "",
  estado: "listo",
  error: "",
  total_items: 1,
  creado: "2026-06-05T06:00:00",
};

const INSUMOS_CON_ITEM = {
  fecha: "2026-06-05",
  cajones: [
    {
      cajon: "portal",
      lotes: [LOTE_PORTAL],
      items: [ITEM_PARSED],
    },
    { cajon: "corresponsales", lotes: [], items: [] },
    { cajon: "reporteros", lotes: [], items: [] },
    { cajon: "eventos_claro", lotes: [], items: [] },
  ],
};

const INSUMOS_CON_CADUCADO = {
  fecha: "2026-06-05",
  cajones: [
    {
      cajon: "portal",
      lotes: [LOTE_PORTAL],
      items: [ITEM_CADUCADO],
    },
    { cajon: "corresponsales", lotes: [], items: [] },
    { cajon: "reporteros", lotes: [], items: [] },
    { cajon: "eventos_claro", lotes: [], items: [] },
  ],
};

const DIAS_HISTORIAL = {
  dias: [
    { fecha: "2026-06-05", total: 1, por_cajon: { portal: 1, corresponsales: 0, reporteros: 0, eventos_claro: 0 } },
    { fecha: "2026-06-04", total: 5, por_cajon: { portal: 2, corresponsales: 2, reporteros: 1, eventos_claro: 0 } },
  ],
};

// ── Setup y teardown ──────────────────────────────────────────────────────────

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

// ── Helpers de mock ───────────────────────────────────────────────────────────

function mockApiInsumos(
  listarPayload: object = INSUMOS_VACIOS,
  diasPayload: object = { dias: [] },
) {
  vi.spyOn(apiMod.api.insumos, "listar").mockResolvedValue(listarPayload as never);
  vi.spyOn(apiMod.api.insumos, "dias").mockResolvedValue(diasPayload as never);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("CajonesDia", () => {
  it("renderiza las 4 tarjetas de cajón", async () => {
    mockApiInsumos();
    renderConProviders(<CajonesDia />);

    expect(await screen.findByText("Portal / SMS")).toBeInTheDocument();
    expect(screen.getByText("Corresponsales")).toBeInTheDocument();
    expect(screen.getByText("Reporteros (agenda PDF)")).toBeInTheDocument();
    expect(screen.getByText("Eventos Claro (Excel/CSV)")).toBeInTheDocument();
  });

  it("muestra el encabezado de página", async () => {
    mockApiInsumos();
    renderConProviders(<CajonesDia />);

    expect(
      await screen.findByRole("heading", { name: "Cajones del día" }),
    ).toBeInTheDocument();
  });

  it("permite cambiar el día con el selector de fecha", async () => {
    mockApiInsumos();
    renderConProviders(<CajonesDia />);

    await screen.findByText("Portal / SMS");

    const input = screen.getByLabelText("Seleccionar fecha");
    fireEvent.change(input, { target: { value: "2026-06-04" } });

    // El query se re-dispara con la nueva fecha; verificamos que se llamó con ella.
    await waitFor(() => {
      expect(apiMod.api.insumos.listar).toHaveBeenCalledWith(
        "2026-06-04",
        expect.anything(),
        expect.anything(), // soloFrescos param
      );
    });
  });

  it("muestra el selector de historial cuando hay días registrados", async () => {
    mockApiInsumos(INSUMOS_VACIOS, DIAS_HISTORIAL);
    renderConProviders(<CajonesDia />);

    // El selector de historial debe aparecer
    expect(await screen.findByLabelText("Historial de días")).toBeInTheDocument();
  });

  it("muestra los ítems parseados en el cajón Portal", async () => {
    mockApiInsumos(INSUMOS_CON_ITEM, { dias: [] });
    renderConProviders(<CajonesDia />);

    // Espera a que aparezca el título del ítem
    expect(
      await screen.findByText("Sismo en CDMX de 5.4 grados"),
    ).toBeInTheDocument();
    expect(screen.getByText("Sismo registrado esta madrugada sin daños.")).toBeInTheDocument();
    // Badge de marca
    expect(screen.getByText("UnoTV")).toBeInTheDocument();
    // Badge de línea
    expect(screen.getByText("Nacional")).toBeInTheDocument();
  });

  it("el botón 'Llevar al tablero' llama a api.insumos.usarItem", async () => {
    // Configurar mocks antes de renderizar
    const usarMock = vi.spyOn(apiMod.api.insumos, "usarItem").mockResolvedValue({
      item: { ...ITEM_PARSED, usado: true },
      contenido_id: "c-nuevo",
    } as never);
    vi.spyOn(apiMod.api.insumos, "listar").mockResolvedValue(INSUMOS_CON_ITEM as never);
    vi.spyOn(apiMod.api.insumos, "dias").mockResolvedValue({ dias: [] } as never);

    renderConProviders(<CajonesDia />);

    // Esperar a que los ítems aparezcan (la carga puede estar en skeleton primero)
    await screen.findByText("Sismo en CDMX de 5.4 grados");

    // Ahora encontrar y hacer clic en el botón "Llevar al tablero"
    const boton = screen.getByRole("button", { name: "Llevar al tablero" });
    fireEvent.click(boton);

    await waitFor(() => {
      expect(usarMock).toHaveBeenCalledWith("item-1", { generar: true });
    });
  });

  it("muestra el badge 'Caducado' en ítems con frescura='caduco'", async () => {
    vi.spyOn(apiMod.api.insumos, "listar").mockResolvedValue(INSUMOS_CON_CADUCADO as never);
    vi.spyOn(apiMod.api.insumos, "dias").mockResolvedValue({ dias: [] } as never);

    renderConProviders(<CajonesDia />);

    await screen.findByText("Noticia de ayer vencida");
    expect(screen.getByTestId("badge-caducado")).toBeInTheDocument();
    expect(screen.getByText("Caducado")).toBeInTheDocument();
  });

  it("NO muestra el badge 'Caducado' en ítems frescos", async () => {
    vi.spyOn(apiMod.api.insumos, "listar").mockResolvedValue(INSUMOS_CON_ITEM as never);
    vi.spyOn(apiMod.api.insumos, "dias").mockResolvedValue({ dias: [] } as never);

    renderConProviders(<CajonesDia />);

    await screen.findByText("Sismo en CDMX de 5.4 grados");
    expect(screen.queryByTestId("badge-caducado")).not.toBeInTheDocument();
  });

  it("muestra el toggle 'Ocultar caducados'", async () => {
    mockApiInsumos();
    renderConProviders(<CajonesDia />);

    await screen.findByText("Portal / SMS");
    expect(screen.getByLabelText("Ocultar caducados")).toBeInTheDocument();
  });

  it("el toggle 'Ocultar caducados' está activo por defecto y llama a listar con soloFrescos=true", async () => {
    const listarMock = vi.spyOn(apiMod.api.insumos, "listar").mockResolvedValue(INSUMOS_VACIOS as never);
    vi.spyOn(apiMod.api.insumos, "dias").mockResolvedValue({ dias: [] } as never);

    renderConProviders(<CajonesDia />);

    await screen.findByText("Portal / SMS");

    // La llamada inicial debe incluir soloFrescos=true (tercer argumento)
    await waitFor(() => {
      expect(listarMock).toHaveBeenCalledWith(
        expect.any(String),
        expect.anything(),
        true,
      );
    });
  });
});
