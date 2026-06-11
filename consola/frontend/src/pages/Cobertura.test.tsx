/**
 * Tests de la página Cobertura — la MESA DE REDACCIÓN de Noticias.
 *
 * Cubre:
 *   1. Con marca activa, la vista por defecto es la MESA (GET /api/noticias/mesa):
 *      plan del día (chips + progreso), secciones por línea (última hora primero),
 *      tarjetas editoriales (frase de corroboración, ÚLTIMA HORA, prioridad).
 *   2. Acciones de la tarjeta: Empujar/Adelantar → usarHistoria; Descartar → descartarHistoria.
 *   3. Pestañas: «En marcha» (estado=usado) y «Descartadas» (estado=descartado + Devolver
 *      al pool → restaurarHistoria).
 *   4. «Fuera del plan» plegado por defecto; se expande al clic.
 *   5. AvisoSalud: una línea ámbar SOLO si hay fuentes con error (el detalle vive en Fuentes).
 *   6. Vista «Todas» (sin marca): lista plana clásica con filtros + selección múltiple +
 *      borrado hard + pieza_estado sin mentir (en_feed / en_cola / generando).
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
import * as apiMod from "@/lib/api";
import type { Historia, RespuestaMesa, ResumenCobertura, UsuarioSesion } from "@/types";

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
    contenido_id: "",
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
let mockHistorias: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockUsarHistoria: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockDescartarHistoria: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockRestaurarHistoria: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockDescartarLote: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockBorrarLote: any;

beforeEach(() => {
  mockCobertura = vi
    .spyOn(apiMod.api.noticias, "cobertura")
    .mockResolvedValue(RESUMEN_COBERTURA);
  mockMesa = vi.spyOn(apiMod.api.noticias, "mesa").mockResolvedValue(mesaFixture());
  mockHistorias = vi
    .spyOn(apiMod.api.noticias, "historias")
    .mockResolvedValue(RESPUESTA_HISTORIAS_VACIA);
  mockUsarHistoria = vi
    .spyOn(apiMod.api.noticias, "usarHistoria")
    .mockResolvedValue({ ok: true, contenido_id: "c-hist-nuevo" });
  mockDescartarHistoria = vi
    .spyOn(apiMod.api.noticias, "descartarHistoria")
    .mockResolvedValue({ ok: true });
  mockRestaurarHistoria = vi
    .spyOn(apiMod.api.noticias, "restaurarHistoria")
    .mockResolvedValue({ historia: historiaItem() });
  mockDescartarLote = vi
    .spyOn(apiMod.api.noticias, "descartarHistoriasLote")
    .mockResolvedValue({ descartadas: 1 });
  mockBorrarLote = vi
    .spyOn(apiMod.api.noticias, "borrarHistoriasLote")
    .mockResolvedValue({ borradas: 1 });
  vi.spyOn(apiMod.api.noticias, "borrarTodasHistorias").mockResolvedValue({ borradas: 3 });
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ── Tests: la Mesa (vista por defecto con marca activa) ───────────────────────

describe("Cobertura · Mesa — plan del día", () => {
  it("pide la mesa de la marca activa y pinta el plan del día con sus chips", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() =>
      expect(mockMesa).toHaveBeenCalledWith(
        expect.objectContaining({ marca: "unotv" }),
        expect.anything(),
      ),
    );
    await waitFor(() => expect(screen.getByTestId("barra-plan-dia")).toBeTruthy());
    expect(screen.getByTestId("barra-plan-dia").textContent).toMatch(/Plan de hoy — UnoTV/);
    expect(screen.getByTestId("barra-plan-dia").textContent).toMatch(/2 de 4/);
    expect(screen.getByTestId("chip-linea-mx").textContent).toMatch(/Nacional 1\/2/);
    // Línea completa: lleva check.
    expect(screen.getByTestId("chip-linea-internacional").textContent).toMatch(/1\/1 ✓/);
  });

  it("última hora va primero y su tarjeta lleva el tratamiento ÚLTIMA HORA", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("seccion-breaking")).toBeTruthy());
    const secciones = screen.getAllByTestId(/^seccion-/);
    expect(secciones[0].getAttribute("data-testid")).toBe("seccion-breaking");
    const breaking = within(screen.getByTestId("seccion-breaking"));
    expect(breaking.getByTestId("badge-ultima-hora")).toBeTruthy();
    // Frase editorial de última hora: la confirmaron casi a la vez.
    expect(breaking.getByTestId("frase-corroboracion").textContent).toMatch(
      /Reuters y AP la confirmaron casi a la vez/,
    );
  });

  it("la tarjeta normal cuenta la corroboración como frase (quién la abrió)", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("seccion-mx")).toBeTruthy());
    const mx = within(screen.getByTestId("seccion-mx"));
    const frase = mx.getByTestId("frase-corroboracion").textContent ?? "";
    expect(frase).toMatch(/Confirmada por Reforma, El Universal y Milenio/);
    expect(frase).toMatch(/la abrió Reforma/);
    // El SCORE es visible; el cálculo completo vive en su pop-up (clic), no en un tooltip.
    expect(mx.getByTestId("punto-prioridad").textContent).toMatch(/Score 55/);
    fireEvent.click(mx.getByTestId("punto-prioridad"));
    await waitFor(() => expect(screen.getByTestId("popup-calculo")).toBeTruthy());
    expect(screen.getByTestId("calculo-score")).toBeTruthy();
  });

  it("una línea con cupo pendiente y sin candidatas no muestra el aviso redundante", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("seccion-internacional")).toBeTruthy());
    // internacional: cupo 1, generados 1 → sin hueco pendiente, no avisa.
    mockMesa.mockResolvedValue(
      mesaFixture({
        lineas: [
          {
            linea: "internacional", cupo: 2, generados: 0, publicados: 0, restante: 2,
            en_pool: 0, historias: [],
          },
        ],
      }),
    );
    renderConProviders(<Cobertura />);
    // El aviso redundante fue eliminado; el KPI visual ya lo indica.
    expect(screen.queryByText(/sin candidatas en el pool/)).toBeNull();
  });

  it("«Fuera del plan» está plegado por defecto y se expande al clic", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("seccion-fuera-de-plan")).toBeTruthy());
    expect(screen.queryByText("Gaming sin línea")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Fuera del plan/i }));
    await waitFor(() => expect(screen.getByText("Gaming sin línea")).toBeTruthy());
  });
});

describe("Cobertura · Mesa — acciones de la tarjeta", () => {
  it("Empujar/Adelantar llama a usarHistoria", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("seccion-mx")).toBeTruthy());
    const mx = within(screen.getByTestId("seccion-mx"));
    fireEvent.click(mx.getByTestId("btn-empujar"));
    await waitFor(() =>
      expect(mockUsarHistoria).toHaveBeenCalledWith("h-1", { generar: true }),
    );
  });

  it("Descartar llama a descartarHistoria", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("seccion-mx")).toBeTruthy());
    const mx = within(screen.getByTestId("seccion-mx"));
    fireEvent.click(mx.getByTestId("btn-descartar"));
    await waitFor(() => expect(mockDescartarHistoria).toHaveBeenCalledWith("h-1"));
  });

  it("una promovible anuncia que sale sola al feed y el botón pasa a «Adelantar»", async () => {
    mockMesa.mockResolvedValue(
      mesaFixture({
        lineas: [
          {
            linea: "mx", cupo: 2, generados: 0, publicados: 0, restante: 2, en_pool: 1,
            historias: [historiaItem({ promovible: true, promovible_motivo: "score 0.55 ≥ 0.35" })],
          },
        ],
      }),
    );
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("badge-sale-sola")).toBeTruthy());
    expect(screen.getByTestId("btn-empujar").textContent).toMatch(/Adelantar/);
  });
});

// ── Tests: pestañas En marcha / Descartadas ───────────────────────────────────

describe("Cobertura · pestañas de flujo", () => {
  it("«En marcha» lista las usadas (estado=usado) con su pieza_estado", async () => {
    mockHistorias.mockResolvedValue({
      historias: [
        historiaItem({ estado: "usado", contenido_id: "c-1", pieza_estado: "en_feed" }),
      ],
      total: 1,
    });
    renderConProviders(<Cobertura />);
    fireEvent.click(screen.getByTestId("tab-en_marcha"));
    await waitFor(() =>
      expect(mockHistorias).toHaveBeenCalledWith(
        expect.objectContaining({ marca: "unotv", estado: "usado" }),
        expect.anything(),
      ),
    );
    await waitFor(() => expect(screen.getByText(/En el feed/i)).toBeTruthy());
    // Ya en marcha: no ofrece Empujar.
    expect(screen.queryByTestId("btn-empujar")).toBeNull();
  });

  it("«Descartadas» ofrece «Devolver al pool» y llama a restaurarHistoria", async () => {
    mockHistorias.mockResolvedValue({
      historias: [
        historiaItem({ id: "h-desc", estado: "descartado", pieza_estado: "descartada" }),
      ],
      total: 1,
    });
    renderConProviders(<Cobertura />);
    fireEvent.click(screen.getByTestId("tab-descartadas"));
    await waitFor(() =>
      expect(mockHistorias).toHaveBeenCalledWith(
        expect.objectContaining({ estado: "descartado" }),
        expect.anything(),
      ),
    );
    const boton = await screen.findByTestId("btn-restaurar");
    fireEvent.click(boton);
    await waitFor(() => expect(mockRestaurarHistoria).toHaveBeenCalledWith("h-desc"));
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
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderConProviders(<Cobertura />, usuario(), null);
    await waitFor(() => expect(screen.getByTestId("barra-seleccion-historias")).toBeTruthy());
    const barra = within(screen.getByTestId("barra-seleccion-historias"));
    fireEvent.click(barra.getByRole("checkbox"));
    fireEvent.click(await screen.findByTestId("btn-borrar-seleccion"));
    await waitFor(() => expect(mockBorrarLote).toHaveBeenCalledWith(["h-1"]));
    confirmSpy.mockRestore();
  });

  it("'Borrar' cancelado en el confirm NO llama a la API", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_UNA_HISTORIA);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderConProviders(<Cobertura />, usuario(), null);
    await waitFor(() => expect(screen.getByTestId("barra-seleccion-historias")).toBeTruthy());
    const barra = within(screen.getByTestId("barra-seleccion-historias"));
    fireEvent.click(barra.getByRole("checkbox"));
    fireEvent.click(await screen.findByTestId("btn-borrar-seleccion"));
    expect(mockBorrarLote).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("la tarjeta dice la verdad de la pieza: 'En cola' cuando aún no hay pieza en el feed", async () => {
    mockHistorias.mockResolvedValue({
      historias: [
        historiaItem({ estado: "usado", contenido_id: "c-98", pieza_estado: "en_cola" }),
      ],
      total: 1,
    });
    renderConProviders(<Cobertura />, usuario(), null);
    await waitFor(() => expect(screen.getByText(/En cola/i)).toBeTruthy());
    expect(screen.queryByText(/En el feed/i)).toBeNull();
  });

  it("expande la lista de enlaces al hacer clic en 'Ver fuentes'", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_UNA_HISTORIA);
    renderConProviders(<Cobertura />, usuario(), null);
    await waitFor(() => expect(screen.getByText("Historia de prueba multi-fuente")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /Ver fuentes corroborantes/i }));
    await waitFor(() => expect(screen.getByTestId("lista-enlaces")).toBeTruthy());
    const lista = within(screen.getByTestId("lista-enlaces"));
    expect(lista.getByText("Fuente 1")).toBeTruthy();
    expect(lista.getByText(/Reforma/)).toBeTruthy();
  });
});
