/**
 * Tests de la página Cobertura (flujo continuo de noticias — Motor de ingesta Ola A + Ola B + Ola D).
 *
 * Cubre:
 *   1. Renderiza la barra de cobertura con los datos de salud del motor.
 *   2. Muestra la lista de noticias ingeridas (Artículos).
 *   3. Los filtros (categoría, idioma, estado, q) pasan los parámetros correctos a la API.
 *   4. El botón "Empujar ya" (override del auto-feed) llama a `api.noticias.usar`.
 *   5. El botón "Descartar" llama a `api.noticias.descartar`.
 *   6. La página es marca-aware: pasa `marcaActiva` a la query.
 *   7. Estado vacío cuando no hay ítems.
 *   8. Vista Historias (Ola B): renderiza clusters con badge "N fuentes".
 *   9. Cambiar entre modos Historias/Artículos.
 *  10. Acciones Empujar/Descartar de historias llaman a los endpoints correctos.
 *  11. Historias son marca-aware (incluye marcaActiva en query keys).
 *  12. (Ola D) Pestaña Salud: resumen, huecos y tabla de feeds.
 *  13. (Ola D) Botón Reactivar llama a fuentes.reactivar.
 *  14. (Ola D) Badges verificación y traducido en tarjetas de historias.
 *  15. Ítems en pool muestran badge "En el pool".
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
import type { Historia, ResumenCobertura, UsuarioSesion } from "@/types";

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

const RESUMEN_COBERTURA: ResumenCobertura = {
  feeds_activos: 12,
  feeds_con_error: 2,
  items_24h: 340,
  por_categoria: { mx: 120, deportes: 80, internacional: 140 },
  ultimo_sondeo: new Date(Date.now() - 3 * 60 * 1000).toISOString(),
};


// ── Fixtures: Historias (Ola B) ───────────────────────────────────────────────

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
    score: 0.85,
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
    ...overrides,
  };
}

const RESPUESTA_HISTORIAS_VACIA = { historias: [], total: 0 };
const RESPUESTA_UNA_HISTORIA = { historias: [historiaItem()], total: 1 };
const RESPUESTA_HISTORIA_USADA = {
  // Pieza REAL en el feed: el back deriva `pieza_estado='en_feed'` (pieza con copy).
  historias: [
    historiaItem({ estado: "usado", contenido_id: "c-hist-99", pieza_estado: "en_feed" }),
  ],
  total: 1,
};
const RESPUESTA_HISTORIA_EN_COLA = {
  // Promovida (cluster 'usado') pero SIN pieza en el feed todavía: el badge NO debe mentir.
  historias: [
    historiaItem({ estado: "usado", contenido_id: "c-hist-98", pieza_estado: "en_cola" }),
  ],
  total: 1,
};
const RESPUESTA_HISTORIA_GENERANDO = {
  historias: [
    historiaItem({ estado: "usado", contenido_id: "c-hist-97", pieza_estado: "generando" }),
  ],
  total: 1,
};
const RESPUESTA_HISTORIA_DESCARTADA = {
  historias: [historiaItem({ estado: "descartado", pieza_estado: "descartada" })],
  total: 1,
};
const RESPUESTA_HISTORIA_BREAKING = {
  historias: [historiaItem({ breaking: 1, n_fuentes: 6 })],
  total: 1,
};

// ── Stubs de API ──────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockHistorias: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockUsarHistoria: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockDescartarHistoria: any;
let mockDescartarLote: any;

beforeEach(() => {
  vi.spyOn(apiMod.api.noticias, "cobertura").mockResolvedValue(RESUMEN_COBERTURA);
  mockHistorias = vi
    .spyOn(apiMod.api.noticias, "historias")
    .mockResolvedValue(RESPUESTA_HISTORIAS_VACIA);
  mockUsarHistoria = vi
    .spyOn(apiMod.api.noticias, "usarHistoria")
    .mockResolvedValue({ ok: true, contenido_id: "c-hist-nuevo" });
  mockDescartarHistoria = vi
    .spyOn(apiMod.api.noticias, "descartarHistoria")
    .mockResolvedValue({ ok: true });
  mockDescartarLote = vi
    .spyOn(apiMod.api.noticias, "descartarHistoriasLote")
    .mockResolvedValue({ descartadas: 1 });
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

  it("muestra el conteo de items 24h y NO el breakdown por categoría", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByTestId("barra-cobertura")).toBeTruthy();
    });
    // El conteo de items 24h sigue (informativo); el eje pasa a marca/línea editorial.
    expect(screen.getByText(/340/)).toBeTruthy();
    // El breakdown por categoría se eliminó (ya no se filtra/desglosa por categoría).
    expect(screen.queryByText(/mx: 120/i)).toBeNull();
  });
});


describe("Cobertura · marca-aware (query keys)", () => {
  it("rerenderiza la lista de historias cuando cambia la marca activa", async () => {
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

    // La pestaña por defecto es Historias: verificamos mockHistorias
    await waitFor(() => expect(mockHistorias).toHaveBeenCalledWith(
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

    await waitFor(() => expect(mockHistorias).toHaveBeenCalledWith(
      expect.objectContaining({ marca: "claro-sports" }),
      expect.anything(),
    ));
  });
});

// ── Tests: Vista Historias (Ola B) ────────────────────────────────────────────

describe("Cobertura · Historias — vista por defecto", () => {
  it("muestra las historias directamente (sin pestañas de modo)", async () => {
    renderConProviders(<Cobertura />);
    // Ya no hay conmutador Historias/Artículos: Noticias = el pool deduplicado en historias.
    await waitFor(() => expect(mockHistorias).toHaveBeenCalled());
    expect(screen.queryByTestId("tabs-cobertura")).toBeNull();
  });

  it("llama a api.noticias.historias al cargar con la marca activa", async () => {
    renderConProviders(<Cobertura />, usuario(), "unotv");
    await waitFor(() => {
      expect(mockHistorias).toHaveBeenCalledWith(
        expect.objectContaining({ marca: "unotv" }),
        expect.anything(),
      );
    });
  });

  it("muestra estado vacío cuando no hay historias", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText(/Sin historias por ahora/i)).toBeTruthy();
    });
  });
});

describe("Cobertura · Historias — renderizado de clusters", () => {
  it("renderiza una tarjeta de historia con el título y el badge de fuentes", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_UNA_HISTORIA);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText("Historia de prueba multi-fuente")).toBeTruthy();
    });
    // Badge de fuentes prominente
    const badge = screen.getByTestId("badge-fuentes");
    expect(badge.textContent).toMatch(/3 fuentes/i);
  });

  it("muestra el badge 'Breaking' cuando breaking=1", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_HISTORIA_BREAKING);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText(/Breaking/i)).toBeTruthy();
    });
    // Badge de 6 fuentes
    const badge = screen.getByTestId("badge-fuentes");
    expect(badge.textContent).toMatch(/6 fuentes/i);
  });

  it("muestra 'En el feed' SOLO cuando hay pieza con copy (pieza_estado='en_feed')", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_HISTORIA_USADA);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText(/En el feed/i)).toBeTruthy();
    });
    // El botón "Empujar ya" no debe aparecer para historias ya en el feed
    expect(screen.queryByRole("button", { name: /Empujar ya/i })).toBeNull();
  });

  it("muestra 'En cola' (NO 'En el feed') cuando está usada pero sin pieza en el feed", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_HISTORIA_EN_COLA);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText(/En cola/i)).toBeTruthy();
    });
    // Transparencia: NO debe decir "En el feed" si la pieza no está en el feed.
    expect(screen.queryByText(/En el feed/i)).toBeNull();
    // Ya está en curso: tampoco ofrece "Empujar ya".
    expect(screen.queryByRole("button", { name: /Empujar ya/i })).toBeNull();
  });

  it("muestra 'Generando…' cuando la pieza existe pero el copy está en proceso", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_HISTORIA_GENERANDO);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText(/Generando/i)).toBeTruthy();
    });
    expect(screen.queryByText(/En el feed/i)).toBeNull();
  });

  it("muestra 'Descartada' cuando la historia está descartada", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_HISTORIA_DESCARTADA);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText(/Descartada/i)).toBeTruthy();
    });
  });

  it("expande la lista de enlaces al hacer clic en 'Ver fuentes'", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_UNA_HISTORIA);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText("Historia de prueba multi-fuente")).toBeTruthy();
    });
    const botonExpandir = screen.getByRole("button", { name: /Ver fuentes corroborantes/i });
    fireEvent.click(botonExpandir);
    await waitFor(() => {
      expect(screen.getByTestId("lista-enlaces")).toBeTruthy();
    });
    expect(screen.getByText("Fuente 1")).toBeTruthy();
    expect(screen.getByText(/Reforma/)).toBeTruthy();
  });
});

describe("Cobertura · Historias — acciones Empujar / Descartar", () => {
  it("el botón 'Empujar ya' de una historia llama a api.noticias.usarHistoria", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_UNA_HISTORIA);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText("Historia de prueba multi-fuente")).toBeTruthy();
    });
    const boton = screen.getByRole("button", { name: /Empujar ya/i });
    fireEvent.click(boton);
    await waitFor(() => {
      expect(mockUsarHistoria).toHaveBeenCalledWith("h-1", { generar: true });
    });
  });

  it("el botón 'Descartar' de una historia llama a api.noticias.descartarHistoria", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_UNA_HISTORIA);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText("Historia de prueba multi-fuente")).toBeTruthy();
    });
    const boton = screen.getByRole("button", { name: /Descartar historia/i });
    fireEvent.click(boton);
    await waitFor(() => {
      expect(mockDescartarHistoria).toHaveBeenCalledWith("h-1");
    });
  });
});

describe("Cobertura · Historias — selección múltiple (papelera estilo correo)", () => {
  it("no muestra la acción de descarte hasta que hay selección", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_UNA_HISTORIA);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText("Historia de prueba multi-fuente")).toBeTruthy();
    });
    expect(screen.queryByTestId("btn-descartar-seleccion")).toBeNull();
  });

  it("'seleccionar todo' + Descartar llama a descartarHistoriasLote con los ids", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_UNA_HISTORIA);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText("Historia de prueba multi-fuente")).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("checkbox", { name: /Seleccionar todas/i }));
    fireEvent.click(screen.getByTestId("btn-descartar-seleccion"));
    await waitFor(() => {
      expect(mockDescartarLote).toHaveBeenCalledWith(["h-1"]);
    });
  });
});

describe("Cobertura · Historias — marca-aware", () => {
  it("historias pasa la marca activa a la query", async () => {
    renderConProviders(<Cobertura />, usuario(), "unotv");
    await waitFor(() => {
      expect(mockHistorias).toHaveBeenCalledWith(
        expect.objectContaining({ marca: "unotv" }),
        expect.anything(),
      );
    });
  });

  it("historias con marcaActiva=null pasa undefined como marca", async () => {
    renderConProviders(<Cobertura />, usuario(), null);
    await waitFor(() => {
      expect(mockHistorias).toHaveBeenCalledWith(
        expect.objectContaining({ marca: undefined }),
        expect.anything(),
      );
    });
  });
});

// ── Tests: Badges de verificación y traducción (Ola D) ───────────────────────

describe("Cobertura · Historias — badge verificación", () => {
  it("muestra badge 'Corroborada' cuando verificacion='corroborada'", async () => {
    mockHistorias.mockResolvedValue({
      historias: [historiaItem({ verificacion: "corroborada" })],
      total: 1,
    });
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByTestId("badge-verificacion")).toBeTruthy();
    });
    expect(screen.getByTestId("badge-verificacion").textContent).toMatch(/Corroborada/i);
  });

  it("muestra badge 'Única fuente' cuando verificacion='unica_fuente'", async () => {
    mockHistorias.mockResolvedValue({
      historias: [historiaItem({ verificacion: "unica_fuente" })],
      total: 1,
    });
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByTestId("badge-verificacion")).toBeTruthy();
    });
    expect(screen.getByTestId("badge-verificacion").textContent).toMatch(/Única fuente/i);
  });

  it("muestra badge 'Dudosa' cuando verificacion='dudosa'", async () => {
    mockHistorias.mockResolvedValue({
      historias: [historiaItem({ verificacion: "dudosa" })],
      total: 1,
    });
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByTestId("badge-verificacion")).toBeTruthy();
    });
    expect(screen.getByTestId("badge-verificacion").textContent).toMatch(/Dudosa/i);
  });

  it("no muestra badge de verificación cuando el campo está ausente", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_UNA_HISTORIA);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText("Historia de prueba multi-fuente")).toBeTruthy();
    });
    expect(screen.queryByTestId("badge-verificacion")).toBeNull();
  });
});

describe("Cobertura · Historias — badge traducido", () => {
  it("muestra badge 'traducido de EN' cuando traducido=true e idioma='en'", async () => {
    mockHistorias.mockResolvedValue({
      historias: [
        historiaItem({
          traducido: true,
          idioma: "en",
          titulo_original: "Original English Title",
        }),
      ],
      total: 1,
    });
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByTestId("badge-traducido")).toBeTruthy();
    });
    expect(screen.getByTestId("badge-traducido").textContent).toMatch(/traducido de EN/i);
  });

  it("no muestra badge traducido cuando traducido=false o ausente", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_UNA_HISTORIA);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText("Historia de prueba multi-fuente")).toBeTruthy();
    });
    expect(screen.queryByTestId("badge-traducido")).toBeNull();
  });
});

// ── Tests: Badges de estado del pool ─────────────────────────────────────────

describe("Cobertura · badge de estado del pool", () => {
  it("historia nueva muestra badge 'En el pool'", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_UNA_HISTORIA);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText("Historia de prueba multi-fuente")).toBeTruthy();
    });
    expect(screen.getByText("En el pool")).toBeTruthy();
  });
});
