/**
 * Tests de la página Cobertura — la MESA DE REDACCIÓN de Noticias.
 *
 * Cubre:
 *   1. Con marca activa, la vista ÚNICA es la MESA (GET /api/noticias/mesa): chips de
 *      navegación por línea (última hora primero) y tarjetas editoriales LIMPIAS
 *      (titular/hora/fuente/score), cuya única acción es abrir la subpágina de detalle.
 *      Ya NO hay pestañas «En marcha»/«Descartadas» ni acciones de empujar/descartar en la
 *      tarjeta (viven en la subpágina).
 *   2. «Fuera del plan» es un chip que filtra sus candidatas.
 *   3. AvisoSalud: una línea ámbar SOLO si hay fuentes con error (el detalle vive en Fuentes).
 *   4. Vista «Todas» (sin marca): lista plana clásica con filtros + selección múltiple +
 *      borrado hard; la tarjeta dice la verdad de la pieza sin desplegar (en_feed/en_cola).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  MarcaActivaContexto,
  type ValorMarcaActiva,
} from "@/hooks/marca-activa-contexto";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import { confirmar } from "@/components/comunes/confirmar";
import * as apiMod from "@/lib/api";
import type { Historia, RespuestaMesa, ResumenCobertura, UsuarioSesion } from "@/types";

import Cobertura from "./Cobertura";

// La app NO usa el confirm del navegador: borrar/vaciar pasa por `confirmar()`
// (Promise<boolean>). Lo mockeamos para controlar la respuesta del usuario.
vi.mock("@/components/comunes/confirmar", () => ({
  confirmar: vi.fn(),
}));

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
    errorConexion: false,
    iniciarSesion: vi.fn(),
    verificarConPasskey: vi.fn(),
    entrarConPasskey: vi.fn(),
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
    nombreActiva: marcaActiva === "unotv" ? "UnoTV" : marcaActiva,
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

const RESUMEN_COBERTURA: ResumenCobertura = {
  feeds_activos: 12,
  feeds_con_error: 2,
  items_24h: 340,
  ultimo_sondeo: new Date(Date.now() - 3 * 60 * 1000).toISOString(),
};

const RESUMEN_COBERTURA_SANO: ResumenCobertura = {
  ...RESUMEN_COBERTURA,
  feeds_con_error: 0,
};

function historiaItem(overrides: Partial<Historia> = {}): Historia {
  return {
    id: "h-1",
    titulo: "Historia de prueba multi-fuente",
    resumen: "Resumen del cluster de noticias.",
    marca: "unotv",
    marca_nombre: "UnoTV",
    categoria: "mx",
    geo: "MX",
    n_items: 5,
    n_fuentes: 3,
    idiomas: ["es"],
    senal: 150,
    score: 0.55,
    breaking: 0,
    primer_visto: "2026-06-05T09:00:00",
    ultimo_visto: "2026-06-05T10:30:00",
    estado: "nuevo",
    publicacion_id: "",
    enlaces: [
      { titulo: "Fuente 1", url: "https://example.com/1", fuente: "Reforma" },
      { titulo: "Fuente 2", url: "https://example.com/2", fuente: "El Universal" },
      { titulo: "Fuente 3", url: "https://example.com/3", fuente: "Milenio" },
    ],
    fuentes: [
      { fuente: "Reforma", fuente_id: "f1", peso: 1, tier: "normal", primer_visto: "2026-06-05T09:00:00", n_items: 2 },
      { fuente: "El Universal", fuente_id: "f2", peso: 1, tier: "normal", primer_visto: "2026-06-05T09:40:00", n_items: 2 },
      { fuente: "Milenio", fuente_id: "f3", peso: 1, tier: "normal", primer_visto: "2026-06-05T10:30:00", n_items: 1 },
    ],
    primera_fuente_nombre: "Reforma",
    peso_fuentes: 3,
    ...overrides,
  };
}

const HISTORIA_BREAKING = historiaItem({
  id: "h-br",
  titulo: "Sismo de 6.2 con epicentro en Guerrero",
  breaking: 1,
  categoria: "mx",
  score: 0.72,
  verificacion: "corroborada",
  fuentes: [
    { fuente: "Reuters", fuente_id: "fa", peso: 2, tier: "potente", primer_visto: "2026-06-05T10:00:00", n_items: 1 },
    { fuente: "AP", fuente_id: "fb", peso: 2, tier: "potente", primer_visto: "2026-06-05T10:10:00", n_items: 1 },
  ],
  primera_fuente_nombre: "Reuters",
  peso_fuentes: 4,
});

function mesaFixture(overrides: Partial<RespuestaMesa> = {}): RespuestaMesa {
  return {
    marca: "unotv",
    plan: true,
    lineas: [
      {
        linea: "breaking", cupo: 1, generados: 0, publicados: 0, restante: 1,
        en_pool: 1, historias: [HISTORIA_BREAKING],
      },
      {
        linea: "mx", cupo: 2, generados: 1, publicados: 1, restante: 1,
        en_pool: 1, historias: [historiaItem()],
      },
      {
        linea: "internacional", cupo: 1, generados: 1, publicados: 0, restante: 0,
        en_pool: 0, historias: [],
      },
    ],
    fuera_de_plan: {
      en_pool: 1,
      historias: [historiaItem({ id: "h-fuera", titulo: "Gaming sin línea", categoria: "gaming" })],
    },
    total_objetivo: 4,
    total_generados: 2,
    ...overrides,
  };
}

const RESPUESTA_HISTORIAS_VACIA = { historias: [], total: 0 };
const RESPUESTA_UNA_HISTORIA = { historias: [historiaItem()], total: 1 };

// ── Stubs de API ──────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockCobertura: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockMesa: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockMesaLinea: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockHistorias: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockDescartarLote: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockBorrarLote: any;

beforeEach(() => {
  mockCobertura = vi
    .spyOn(apiMod.api.noticias, "cobertura")
    .mockResolvedValue(RESUMEN_COBERTURA);
  mockMesa = vi.spyOn(apiMod.api.noticias, "mesa").mockResolvedValue(mesaFixture());
  // Pulsar un chip/línea recorre TODO el pool de esa línea (lista paginada). Por defecto
  // devuelve una candidata; los tests que afinan la línea sobreescriben este stub.
  mockMesaLinea = vi
    .spyOn(apiMod.api.noticias, "mesaLinea")
    .mockResolvedValue({ historias: [historiaItem()], total: 1 });
  mockHistorias = vi
    .spyOn(apiMod.api.noticias, "historias")
    .mockResolvedValue(RESPUESTA_HISTORIAS_VACIA);
  mockDescartarLote = vi
    .spyOn(apiMod.api.noticias, "descartarHistoriasLote")
    .mockResolvedValue({ descartadas: 1 });
  mockBorrarLote = vi
    .spyOn(apiMod.api.noticias, "borrarHistoriasLote")
    .mockResolvedValue({ borradas: 1 });
  vi.spyOn(apiMod.api.noticias, "borrarTodasHistorias").mockResolvedValue({ borradas: 3 });
  vi.mocked(confirmar).mockResolvedValue(true);
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ── Tests: la Mesa (vista única con marca activa) ─────────────────────────────

describe("Cobertura · Mesa", () => {
  it("pide la mesa de la marca activa y muestra los chips de navegación por línea", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() =>
      expect(mockMesa).toHaveBeenCalledWith(
        expect.objectContaining({ marca: "unotv" }),
        expect.anything(),
      ),
    );
    // La mesa segmenta por líneas con chips de navegación (sin barra de progreso).
    await waitFor(() => expect(screen.getByTestId("chip-grupo-Nacional")).toBeTruthy());
    expect(screen.getByTestId("chip-grupo-Internacional")).toBeTruthy();
    // Ya no hay pestañas de flujo.
    expect(screen.queryByTestId("tab-en_marcha")).toBeNull();
    expect(screen.queryByTestId("tab-descartadas")).toBeNull();
  });

  it("última hora va primero y su tarjeta lleva el rayito de ÚLTIMA HORA", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("badge-ultima-hora")).toBeTruthy());
    // Última hora abre la lista (orden de ranking): la primera tarjeta es la breaking.
    const cards = screen.getAllByTestId("historia-item");
    const breaking = within(cards[0]);
    expect(breaking.getByTestId("badge-ultima-hora")).toBeTruthy();
  });

  it("la tarjeta limpia muestra el score como pastilla, sin desplegar", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("chip-grupo-Nacional")).toBeTruthy());
    fireEvent.click(screen.getByTestId("chip-grupo-Nacional"));
    const card = within(await screen.findByTestId("historia-item"));
    expect(card.getByTestId("punto-prioridad").textContent).toMatch(/Score 55/);
    // La tarjeta ya no expande inline: nada de chevron ni desglose.
    expect(card.queryByTestId("btn-expandir")).toBeNull();
  });

  it("la tarjeta navega a la subpágina de detalle al pulsar el titular", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("chip-grupo-Nacional")).toBeTruthy());
    fireEvent.click(screen.getByTestId("chip-grupo-Nacional"));
    const card = await screen.findByTestId("historia-item");
    // El botón del titular es la única acción de la tarjeta (abre la subpágina).
    expect(within(card).getByTestId("btn-detalle")).toBeTruthy();
  });

  it("una promovible muestra el indicador «Sale sola al feed» en la tarjeta", async () => {
    mockMesa.mockResolvedValue(
      mesaFixture({
        lineas: [
          {
            linea: "mx", cupo: 2, generados: 0, publicados: 0, restante: 2, en_pool: 1,
            historias: [historiaItem({ promovible: true, promovible_motivo: "score 0.55 ≥ 0.35" })],
          },
        ],
        fuera_de_plan: { en_pool: 0, historias: [] },
      }),
    );
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("historia-item")).toBeTruthy());
    expect(screen.getByTestId("badge-sale-sola")).toBeTruthy();
  });

  it("«Fuera del plan» es un chip que recorre su pool paginado (todo, no solo el top-N)", async () => {
    // El chip de una línea abre su lista PAGINADA (GET mesa/linea con la clave de reparto): para
    // «Fuera del plan» eso es la clave '__fuera__'. El back devuelve el pool entero de la línea.
    mockMesaLinea.mockResolvedValue({
      historias: [historiaItem({ id: "h-fuera", titulo: "Gaming sin línea", categoria: "gaming" })],
      total: 1,
    });
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("chip-grupo-Fuera del plan")).toBeTruthy());
    fireEvent.click(screen.getByTestId("chip-grupo-Fuera del plan"));
    await waitFor(() => expect(screen.getByText("Gaming sin línea")).toBeTruthy());
    expect(mockMesaLinea).toHaveBeenCalledWith(
      expect.objectContaining({ marca: "unotv", linea: "__fuera__" }),
      expect.anything(),
    );
  });

  it("pulsar un chip de línea abre su lista PAGINADA (recorre TODO el pool, no solo el top-N)", async () => {
    mockMesaLinea.mockResolvedValue({
      historias: [historiaItem(), historiaItem({ id: "h-2", titulo: "Otra nacional" })],
      total: 42,
    });
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("chip-grupo-Nacional")).toBeTruthy());
    fireEvent.click(screen.getByTestId("chip-grupo-Nacional"));
    // Pide el pool de la línea 'mx' (Nacional) y muestra su lista + el total real.
    await waitFor(() =>
      expect(mockMesaLinea).toHaveBeenCalledWith(
        expect.objectContaining({ marca: "unotv", linea: "mx" }),
        expect.anything(),
      ),
    );
    expect(await screen.findByText(/de 42/)).toBeTruthy();
  });
});

// ── Tests: AvisoSalud ─────────────────────────────────────────────────────────

describe("Cobertura · aviso de salud (mínimo y condicional)", () => {
  it("muestra UNA línea ámbar con link a Fuentes cuando hay errores", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("aviso-salud")).toBeTruthy());
    expect(screen.getByTestId("aviso-salud").textContent).toMatch(/2 fuentes con fallas/);
    expect(screen.getByRole("link", { name: /revisar en Fuentes/i })).toBeTruthy();
    // Los chips operacionales viejos ya no existen.
    expect(screen.queryByText(/feeds activos/i)).toBeNull();
    expect(screen.queryByText(/en 24 h/i)).toBeNull();
  });

  it("no muestra nada cuando todo está bien", async () => {
    mockCobertura.mockResolvedValue(RESUMEN_COBERTURA_SANO);
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(mockMesa).toHaveBeenCalled());
    expect(screen.queryByTestId("aviso-salud")).toBeNull();
  });
});

// ── Tests: vista «Todas» (sin marca activa) ───────────────────────────────────

describe("Cobertura · vista Todas (lista plana clásica)", () => {
  it("sin marca activa no hay mesa: lista plana con filtro de estado", async () => {
    renderConProviders(<Cobertura />, usuario(), null);
    await waitFor(() =>
      expect(mockHistorias).toHaveBeenCalledWith(
        expect.objectContaining({ marca: undefined }),
        expect.anything(),
      ),
    );
    expect(mockMesa).not.toHaveBeenCalled();
    expect(screen.getByTestId("filtro-estado-historias")).toBeTruthy();
  });

  it("muestra estado vacío cuando no hay historias", async () => {
    renderConProviders(<Cobertura />, usuario(), null);
    await waitFor(() => expect(screen.getByText(/Sin historias por ahora/i)).toBeTruthy());
  });

  it("'seleccionar todo' + Descartar llama a descartarHistoriasLote con los ids", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_UNA_HISTORIA);
    renderConProviders(<Cobertura />, usuario(), null);
    await waitFor(() => expect(screen.getByTestId("barra-seleccion-historias")).toBeTruthy());
    const barra = within(screen.getByTestId("barra-seleccion-historias"));
    fireEvent.click(barra.getByRole("checkbox"));
    fireEvent.click(await screen.findByTestId("btn-descartar-seleccion"));
    await waitFor(() => expect(mockDescartarLote).toHaveBeenCalledWith(["h-1"]));
  });

  it("'Borrar' seleccionadas pide confirmación y llama a borrarHistoriasLote", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_UNA_HISTORIA);
    vi.mocked(confirmar).mockResolvedValue(true);
    renderConProviders(<Cobertura />, usuario(), null);
    await waitFor(() => expect(screen.getByTestId("barra-seleccion-historias")).toBeTruthy());
    const barra = within(screen.getByTestId("barra-seleccion-historias"));
    fireEvent.click(barra.getByRole("checkbox"));
    fireEvent.click(await screen.findByTestId("btn-borrar-seleccion"));
    await waitFor(() => expect(mockBorrarLote).toHaveBeenCalledWith(["h-1"]));
  });

  it("'Borrar' cancelado en el confirm NO llama a la API", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_UNA_HISTORIA);
    vi.mocked(confirmar).mockResolvedValue(false);
    renderConProviders(<Cobertura />, usuario(), null);
    await waitFor(() => expect(screen.getByTestId("barra-seleccion-historias")).toBeTruthy());
    const barra = within(screen.getByTestId("barra-seleccion-historias"));
    fireEvent.click(barra.getByRole("checkbox"));
    fireEvent.click(await screen.findByTestId("btn-borrar-seleccion"));
    await waitFor(() => expect(confirmar).toHaveBeenCalled());
    expect(mockBorrarLote).not.toHaveBeenCalled();
  });

  it("la tarjeta dice la verdad de la pieza SIN desplegar: 'En cola'", async () => {
    mockHistorias.mockResolvedValue({
      historias: [
        historiaItem({ estado: "usado", publicacion_id: "c-98", pieza_estado: "en_cola" }),
      ],
      total: 1,
    });
    renderConProviders(<Cobertura />, usuario(), null);
    // El estado de la pieza es visible directamente en la tarjeta limpia.
    await screen.findByTestId("historia-item");
    expect(screen.getByText(/En cola/i)).toBeTruthy();
    expect(screen.queryByText(/En el feed/i)).toBeNull();
  });
});
