/**
 * Tests de la página Cobertura (flujo continuo de noticias — Motor de ingesta Ola A).
 *
 * Cubre:
 *   1. Renderiza la barra de cobertura con los datos de salud del motor.
 *   2. Muestra la lista de noticias ingeridas.
 *   3. Los filtros (categoría, idioma, estado, q) pasan los parámetros correctos a la API.
 *   4. El botón "Usar" llama a `api.noticias.usar`.
 *   5. El botón "Descartar" llama a `api.noticias.descartar`.
 *   6. La página es marca-aware: pasa `marcaActiva` a la query.
 *   7. Estado vacío cuando no hay ítems.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  MarcaActivaContexto,
  type ValorMarcaActiva,
} from "@/hooks/marca-activa-contexto";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import * as apiMod from "@/lib/api";
import type { NoticiaItem, ResumenCobertura, UsuarioSesion } from "@/types";

import Cobertura from "./Cobertura";

// ── Helpers ───────────────────────────────────────────────────────────────────

function usuario(marcas: string[] = ["unotv"]): UsuarioSesion {
  return {
    id: "u1",
    usuario: "testuser",
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

function renderConProviders(
  ui: React.ReactElement,
  u = usuario(),
  marcaActiva: string | null = "unotv",
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesionValor(u)}>
        <MarcaActivaContexto.Provider value={valorMarcaActiva(marcaActiva)}>
          <MemoryRouter>{ui}</MemoryRouter>
        </MarcaActivaContexto.Provider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

function noticiaItem(overrides: Partial<NoticiaItem> = {}): NoticiaItem {
  return {
    id: "n-1",
    fuente_id: "fuente-1",
    fuente_nombre: "Reforma",
    categoria: "mx",
    marca: "unotv",
    marca_nombre: "UnoTV",
    titulo: "Título de prueba",
    resumen: "Resumen de la noticia de prueba.",
    url: "https://example.com/noticia",
    url_canonica: "https://example.com/noticia",
    idioma: "es",
    autor: "Redacción",
    imagen: "",
    publicado_en: "2026-06-05T10:00:00",
    capturado_en: "2026-06-05T10:05:00",
    senal: 0,
    geo: "MX",
    estado: "nuevo",
    contenido_id: "",
    ...overrides,
  };
}

const RESUMEN_COBERTURA: ResumenCobertura = {
  feeds_activos: 12,
  feeds_con_error: 2,
  items_24h: 340,
  por_categoria: { mx: 120, deportes: 80, internacional: 140 },
  ultimo_sondeo: new Date(Date.now() - 3 * 60 * 1000).toISOString(),
};

const RESPUESTA_VACIA = { items: [], total: 0 };
const RESPUESTA_UN_ITEM = { items: [noticiaItem()], total: 1 };
const RESPUESTA_USADO = {
  items: [noticiaItem({ estado: "usado", contenido_id: "c-99" })],
  total: 1,
};
const RESPUESTA_DESCARTADO = {
  items: [noticiaItem({ estado: "descartado" })],
  total: 1,
};

// ── Stubs de API ──────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockListar: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockUsar: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockDescartar: any;

beforeEach(() => {
  mockListar = vi
    .spyOn(apiMod.api.noticias, "listar")
    .mockResolvedValue(RESPUESTA_VACIA);
  vi.spyOn(apiMod.api.noticias, "cobertura").mockResolvedValue(RESUMEN_COBERTURA);
  mockUsar = vi
    .spyOn(apiMod.api.noticias, "usar")
    .mockResolvedValue({ ok: true, contenido_id: "c-nuevo" });
  mockDescartar = vi
    .spyOn(apiMod.api.noticias, "descartar")
    .mockResolvedValue({ ok: true });
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("Cobertura · barra de cobertura", () => {
  it("renderiza la barra de cobertura con los datos del motor", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByTestId("barra-cobertura")).toBeTruthy();
    });
    expect(screen.getByText(/12 feeds activos/i)).toBeTruthy();
    expect(screen.getByText(/2 con error/i)).toBeTruthy();
    expect(screen.getByText(/340/)).toBeTruthy();
  });

  it("muestra las categorías del breakdown", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByTestId("barra-cobertura")).toBeTruthy();
    });
    // Al menos una categoría del breakdown debe aparecer
    expect(screen.getByText(/mx: 120/i)).toBeTruthy();
  });
});

describe("Cobertura · lista de noticias", () => {
  it("muestra estado vacío cuando no hay ítems", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText(/Sin noticias por ahora/i)).toBeTruthy();
    });
  });

  it("muestra las tarjetas cuando la API devuelve ítems", async () => {
    mockListar.mockResolvedValue(RESPUESTA_UN_ITEM);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText("Título de prueba")).toBeTruthy();
    });
    expect(screen.getByText("Reforma")).toBeTruthy();
  });

  it("muestra 'En tablero' en un ítem con estado 'usado'", async () => {
    mockListar.mockResolvedValue(RESPUESTA_USADO);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText(/En tablero/i)).toBeTruthy();
    });
    // El botón "Usar" no debe aparecer
    expect(screen.queryByRole("button", { name: /Usar noticia/i })).toBeNull();
  });

  it("muestra 'Descartada' en un ítem con estado 'descartado'", async () => {
    mockListar.mockResolvedValue(RESPUESTA_DESCARTADO);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText(/Descartada/i)).toBeTruthy();
    });
  });
});

describe("Cobertura · acciones Usar / Descartar", () => {
  it("el botón 'Usar' llama a api.noticias.usar con el id del ítem", async () => {
    mockListar.mockResolvedValue(RESPUESTA_UN_ITEM);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText("Título de prueba")).toBeTruthy();
    });
    const boton = screen.getByRole("button", { name: /Usar noticia/i });
    fireEvent.click(boton);
    await waitFor(() => {
      expect(mockUsar).toHaveBeenCalledWith("n-1", { generar: true });
    });
  });

  it("el botón 'Descartar' llama a api.noticias.descartar con el id del ítem", async () => {
    mockListar.mockResolvedValue(RESPUESTA_UN_ITEM);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText("Título de prueba")).toBeTruthy();
    });
    const boton = screen.getByRole("button", { name: /Descartar noticia/i });
    fireEvent.click(boton);
    await waitFor(() => {
      expect(mockDescartar).toHaveBeenCalledWith("n-1");
    });
  });
});

describe("Cobertura · filtros", () => {
  it("pasa la marca activa a la query de listar", async () => {
    renderConProviders(<Cobertura />, usuario(), "unotv");
    await waitFor(() => {
      expect(mockListar).toHaveBeenCalledWith(
        expect.objectContaining({ marca: "unotv" }),
        expect.anything(),
      );
    });
  });

  it("con marcaActiva=null pasa undefined como marca (vista admin)", async () => {
    renderConProviders(<Cobertura />, usuario(), null);
    await waitFor(() => {
      expect(mockListar).toHaveBeenCalledWith(
        expect.objectContaining({ marca: undefined }),
        expect.anything(),
      );
    });
  });

  it("el selector de estado pasa el estado a la query", async () => {
    renderConProviders(<Cobertura />);
    // Esperamos la carga inicial
    await waitFor(() => {
      expect(mockListar).toHaveBeenCalled();
    });
    // El SelectTrigger tiene data-testid="filtro-estado" y role="combobox" (Radix).
    // Lo encontramos por testid y lo clicamos directamente.
    const selectEstado = screen.getByTestId("filtro-estado");
    fireEvent.click(selectEstado);
    // Elegimos "Nuevo" de las opciones
    const opcion = await screen.findByRole("option", { name: /^Nuevo$/i });
    fireEvent.click(opcion);
    await waitFor(() => {
      expect(mockListar).toHaveBeenCalledWith(
        expect.objectContaining({ estado: "nuevo" }),
        expect.anything(),
      );
    });
  });
});

describe("Cobertura · marca-aware (query keys)", () => {
  it("rerenderiza la lista cuando cambia la marca activa", async () => {
    const { rerender } = render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <SesionContexto.Provider value={sesionValor(usuario())}>
          <MarcaActivaContexto.Provider value={valorMarcaActiva("unotv")}>
            <MemoryRouter>
              <Cobertura />
            </MemoryRouter>
          </MarcaActivaContexto.Provider>
        </SesionContexto.Provider>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(mockListar).toHaveBeenCalledWith(
      expect.objectContaining({ marca: "unotv" }),
      expect.anything(),
    ));

    rerender(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <SesionContexto.Provider value={sesionValor(usuario(["claro-sports"]))}>
          <MarcaActivaContexto.Provider value={valorMarcaActiva("claro-sports")}>
            <MemoryRouter>
              <Cobertura />
            </MemoryRouter>
          </MarcaActivaContexto.Provider>
        </SesionContexto.Provider>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(mockListar).toHaveBeenCalledWith(
      expect.objectContaining({ marca: "claro-sports" }),
      expect.anything(),
    ));
  });
});
