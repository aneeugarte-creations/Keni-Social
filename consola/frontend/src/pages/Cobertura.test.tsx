/**
 * Tests de la página Cobertura (flujo continuo de noticias — Motor de ingesta Ola A + Ola B + Ola D).
 *
 * Cubre:
 *   1. Renderiza la barra de cobertura con los datos de salud del motor.
 *   2. Muestra la lista de noticias ingeridas (Artículos).
 *   3. Los filtros (categoría, idioma, estado, q) pasan los parámetros correctos a la API.
 *   4. El botón "Usar" llama a `api.noticias.usar`.
 *   5. El botón "Descartar" llama a `api.noticias.descartar`.
 *   6. La página es marca-aware: pasa `marcaActiva` a la query.
 *   7. Estado vacío cuando no hay ítems.
 *   8. Vista Historias (Ola B): renderiza clusters con badge "N fuentes".
 *   9. Cambiar entre modos Historias/Artículos.
 *  10. Acciones Usar/Descartar de historias llaman a los endpoints correctos.
 *  11. Historias son marca-aware (incluye marcaActiva en query keys).
 *  12. (Ola D) Pestaña Salud: resumen, huecos y tabla de feeds.
 *  13. (Ola D) Botón Reactivar llama a fuentes.reactivar.
 *  14. (Ola D) Badges verificación y traducido en tarjetas de historias.
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
import type { Historia, NoticiaItem, ResumenCobertura, SaludCobertura, UsuarioSesion } from "@/types";

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
  historias: [historiaItem({ estado: "usado", contenido_id: "c-hist-99" })],
  total: 1,
};
const RESPUESTA_HISTORIA_DESCARTADA = {
  historias: [historiaItem({ estado: "descartado" })],
  total: 1,
};
const RESPUESTA_HISTORIA_BREAKING = {
  historias: [historiaItem({ breaking: 1, n_fuentes: 6 })],
  total: 1,
};

// ── Fixtures: Salud (Ola D) ───────────────────────────────────────────────────

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

// ── Stubs de API ──────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockListar: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockUsar: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockDescartar: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockHistorias: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockUsarHistoria: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockDescartarHistoria: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockSalud: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockReactivar: any;

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
  mockHistorias = vi
    .spyOn(apiMod.api.noticias, "historias")
    .mockResolvedValue(RESPUESTA_HISTORIAS_VACIA);
  mockUsarHistoria = vi
    .spyOn(apiMod.api.noticias, "usarHistoria")
    .mockResolvedValue({ ok: true, contenido_id: "c-hist-nuevo" });
  mockDescartarHistoria = vi
    .spyOn(apiMod.api.noticias, "descartarHistoria")
    .mockResolvedValue({ ok: true });
  mockSalud = vi
    .spyOn(apiMod.api.noticias, "salud")
    .mockResolvedValue(SALUD_VACIA);
  mockReactivar = vi
    .spyOn(apiMod.api.fuentes, "reactivar")
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

/** Helper: cambia a la pestaña Artículos (el default es Historias) y espera el contenido.
 *  Radix Tabs activa con onMouseDown (button 0), no con click. */
async function irAArticulos() {
  await waitFor(() => expect(screen.getByTestId("tab-articulos")).toBeTruthy());
  fireEvent.mouseDown(screen.getByTestId("tab-articulos"), { button: 0 });
  // Esperamos que el filtro de búsqueda libre aparezca (solo se monta en Artículos activo)
  await waitFor(() => {
    expect(screen.getByTestId("filtro-q")).toBeTruthy();
  }, { timeout: 3000 });
}

describe("Cobertura · lista de noticias", () => {
  it("muestra estado vacío cuando no hay ítems (en pestaña Artículos)", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("tabs-cobertura")).toBeTruthy());
    await irAArticulos();
    await waitFor(() => {
      expect(screen.getByText(/Sin noticias por ahora/i)).toBeTruthy();
    });
  });

  it("muestra las tarjetas cuando la API devuelve ítems", async () => {
    mockListar.mockResolvedValue(RESPUESTA_UN_ITEM);
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("tabs-cobertura")).toBeTruthy());
    await irAArticulos();
    await waitFor(() => {
      expect(screen.getByText("Título de prueba")).toBeTruthy();
    });
    expect(screen.getByText("Reforma")).toBeTruthy();
  });

  it("muestra 'En tablero' en un ítem con estado 'usado'", async () => {
    mockListar.mockResolvedValue(RESPUESTA_USADO);
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("tabs-cobertura")).toBeTruthy());
    await irAArticulos();
    await waitFor(() => {
      expect(screen.getByText(/En tablero/i)).toBeTruthy();
    });
    // El botón "Usar" no debe aparecer
    expect(screen.queryByRole("button", { name: /Usar noticia/i })).toBeNull();
  });

  it("muestra 'Descartada' en un ítem con estado 'descartado'", async () => {
    mockListar.mockResolvedValue(RESPUESTA_DESCARTADO);
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("tabs-cobertura")).toBeTruthy());
    await irAArticulos();
    await waitFor(() => {
      expect(screen.getByText(/Descartada/i)).toBeTruthy();
    });
  });
});

describe("Cobertura · acciones Usar / Descartar", () => {
  it("el botón 'Usar' llama a api.noticias.usar con el id del ítem", async () => {
    mockListar.mockResolvedValue(RESPUESTA_UN_ITEM);
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("tabs-cobertura")).toBeTruthy());
    await irAArticulos();
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
    await waitFor(() => expect(screen.getByTestId("tabs-cobertura")).toBeTruthy());
    await irAArticulos();
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
  it("pasa la marca activa a la query de listar (pestaña Artículos)", async () => {
    renderConProviders(<Cobertura />, usuario(), "unotv");
    await waitFor(() => expect(screen.getByTestId("tabs-cobertura")).toBeTruthy());
    await irAArticulos();
    await waitFor(() => {
      expect(mockListar).toHaveBeenCalledWith(
        expect.objectContaining({ marca: "unotv" }),
        expect.anything(),
      );
    });
  });

  it("con marcaActiva=null pasa undefined como marca (vista admin)", async () => {
    renderConProviders(<Cobertura />, usuario(), null);
    await waitFor(() => expect(screen.getByTestId("tabs-cobertura")).toBeTruthy());
    await irAArticulos();
    await waitFor(() => {
      expect(mockListar).toHaveBeenCalledWith(
        expect.objectContaining({ marca: undefined }),
        expect.anything(),
      );
    });
  });

  it("el selector de estado pasa el estado a la query", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => expect(screen.getByTestId("tabs-cobertura")).toBeTruthy());
    await irAArticulos();
    // Esperamos la carga inicial
    await waitFor(() => {
      expect(mockListar).toHaveBeenCalled();
    });
    // El SelectTrigger tiene data-testid="filtro-estado" y role="combobox" (Radix).
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
  it("muestra la pestaña Historias activa por defecto", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByTestId("tabs-cobertura")).toBeTruthy();
    });
    const tabHistorias = screen.getByTestId("tab-historias");
    expect(tabHistorias).toBeTruthy();
    // La pestaña Historias está activa (Radix pone data-state=active)
    expect(tabHistorias.getAttribute("data-state")).toBe("active");
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

  it("muestra 'En tablero' cuando la historia está usada", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_HISTORIA_USADA);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText(/En tablero/i)).toBeTruthy();
    });
    expect(screen.queryByRole("button", { name: /Usar historia/i })).toBeNull();
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

describe("Cobertura · Historias — acciones Usar / Descartar", () => {
  it("el botón 'Usar' de una historia llama a api.noticias.usarHistoria", async () => {
    mockHistorias.mockResolvedValue(RESPUESTA_UNA_HISTORIA);
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByText("Historia de prueba multi-fuente")).toBeTruthy();
    });
    const boton = screen.getByRole("button", { name: /Usar historia/i });
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

describe("Cobertura · cambio de modo Historias / Artículos", () => {
  it("al activar la pestaña Artículos se muestran los filtros de artículos", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByTestId("tabs-cobertura")).toBeTruthy();
    });
    fireEvent.mouseDown(screen.getByTestId("tab-articulos"), { button: 0 });
    // El filtro de búsqueda libre solo existe en la vista de Artículos
    await waitFor(() => {
      expect(screen.getByTestId("filtro-q")).toBeTruthy();
    });
  });

  it("en la pestaña Artículos se llama a api.noticias.listar con la marca activa", async () => {
    renderConProviders(<Cobertura />, usuario(), "claro-sports");
    await waitFor(() => {
      expect(screen.getByTestId("tabs-cobertura")).toBeTruthy();
    });
    fireEvent.mouseDown(screen.getByTestId("tab-articulos"), { button: 0 });
    await waitFor(() => {
      expect(mockListar).toHaveBeenCalledWith(
        expect.objectContaining({ marca: "claro-sports" }),
        expect.anything(),
      );
    });
  });
});

// ── Tests: Vista Salud (Ola D) ────────────────────────────────────────────────

/** Helper: activa la pestaña Salud. */
async function irASalud() {
  await waitFor(() => expect(screen.getByTestId("tab-salud")).toBeTruthy());
  fireEvent.mouseDown(screen.getByTestId("tab-salud"), { button: 0 });
  await waitFor(() => {
    expect(screen.getByTestId("tabs-cobertura")).toBeTruthy();
  }, { timeout: 3000 });
}

describe("Cobertura · Salud — pestaña existe y es accesible", () => {
  it("muestra la pestaña Salud en el selector de tabs", async () => {
    renderConProviders(<Cobertura />);
    await waitFor(() => {
      expect(screen.getByTestId("tab-salud")).toBeTruthy();
    });
  });

  it("al activar la pestaña Salud llama a api.noticias.salud con la marca activa", async () => {
    renderConProviders(<Cobertura />, usuario(), "unotv");
    await irASalud();
    await waitFor(() => {
      expect(mockSalud).toHaveBeenCalledWith("unotv", expect.anything());
    });
  });

  it("con marcaActiva=null pasa undefined a api.noticias.salud", async () => {
    renderConProviders(<Cobertura />, usuario(), null);
    await irASalud();
    await waitFor(() => {
      expect(mockSalud).toHaveBeenCalledWith(undefined, expect.anything());
    });
  });
});

describe("Cobertura · Salud — resumen y huecos", () => {
  it("muestra el resumen con chips de estado", async () => {
    mockSalud.mockResolvedValue(SALUD_COBERTURA);
    renderConProviders(<Cobertura />);
    await irASalud();
    await waitFor(() => {
      expect(screen.getByTestId("salud-resumen")).toBeTruthy();
    });
    // Chips de feeds activos, auto-desactivados, items 24h
    expect(screen.getByText(/15 activos/i)).toBeTruthy();
    expect(screen.getByText(/2 auto-desactivados/i)).toBeTruthy();
    expect(screen.getByText(/420/)).toBeTruthy();
  });

  it("muestra la lista de huecos de cobertura cuando los hay", async () => {
    mockSalud.mockResolvedValue(SALUD_COBERTURA);
    renderConProviders(<Cobertura />);
    await irASalud();
    await waitFor(() => {
      expect(screen.getByTestId("salud-huecos-lista")).toBeTruthy();
    });
    expect(screen.getByText(/gaming/i)).toBeTruthy();
    expect(screen.getByText(/ciencia-tech/i)).toBeTruthy();
  });

  it("no muestra el bloque de huecos cuando no hay ninguno", async () => {
    mockSalud.mockResolvedValue(SALUD_VACIA);
    renderConProviders(<Cobertura />);
    await irASalud();
    // Esperamos que la vista cargue (estado vacío de feeds)
    await waitFor(() => {
      expect(screen.getByText(/Sin feeds registrados/i)).toBeTruthy();
    });
    expect(screen.queryByTestId("salud-huecos-lista")).toBeNull();
  });
});

describe("Cobertura · Salud — tabla de feeds", () => {
  it("muestra la tabla de feeds con nombre y estado", async () => {
    mockSalud.mockResolvedValue(SALUD_COBERTURA);
    renderConProviders(<Cobertura />);
    await irASalud();
    await waitFor(() => {
      expect(screen.getByTestId("salud-tabla-feeds")).toBeTruthy();
    });
    expect(screen.getByText("Reforma RSS")).toBeTruthy();
    expect(screen.getByText("Feed caído")).toBeTruthy();
  });

  it("muestra el botón Reactivar solo para feeds auto-desactivados", async () => {
    mockSalud.mockResolvedValue(SALUD_COBERTURA);
    renderConProviders(<Cobertura />);
    await irASalud();
    await waitFor(() => {
      expect(screen.getByTestId("btn-reactivar-feed-2")).toBeTruthy();
    });
    // El feed activo no tiene botón Reactivar
    expect(screen.queryByTestId("btn-reactivar-feed-1")).toBeNull();
  });

  it("el botón Reactivar llama a api.fuentes.reactivar con el id del feed", async () => {
    mockSalud.mockResolvedValue(SALUD_COBERTURA);
    renderConProviders(<Cobertura />);
    await irASalud();
    await waitFor(() => {
      expect(screen.getByTestId("btn-reactivar-feed-2")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("btn-reactivar-feed-2"));
    await waitFor(() => {
      expect(mockReactivar).toHaveBeenCalledWith("feed-2");
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
