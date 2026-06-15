/**
 * Tests de la página CajonesDia.
 *
 * Cubren:
 * 1. Renderiza las 4 tarjetas de cajones.
 * 2. Permite cambiar el día (selector de fecha).
 * 3. Muestra los ítems parseados cuando la API devuelve datos.
 * 4. El botón "Empujar ya" (override del auto-feed) llama a `api.insumos.usarItem`.
 * 5. Ítems en pool muestran badge "En el pool"; ítems en feed muestran "En el feed".
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import { MarcaActivaProvider } from "@/hooks/use-marca-activa";
import * as apiMod from "@/lib/api";
import type { UsuarioSesion } from "@/types";

import CajonesDia from "./CajonesDia";

// El diálogo real de confirmación vive en main.tsx (no está montado en tests): se
// sustituye por un "sí" inmediato para poder ejercitar las acciones destructivas.
vi.mock("@/components/comunes/confirmar", () => ({
  confirmar: () => Promise.resolve(true),
}));

// Los toasts de "Empujar ya" (honesto según `copy_en_proceso`) se asertan: mockeamos sonner.
vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  }),
}));

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

/**
 * Admin sin marca de casa → marca activa "Todas" (vista agregada): ve TODOS los cajones de
 * todas las marcas. Útil para probar el cajón de Claro Sports (Eventos Claro) sin ser editor
 * de esa marca.
 */
function usuarioAdmin(): UsuarioSesion {
  return {
    id: "uA",
    usuario: "admin",
    rol: "admin",
    debe_cambiar_password: false,
    marcas: [],
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

function renderConProviders(ui: React.ReactElement, u: UsuarioSesion = usuario()) {
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

// Ítem del cajón Eventos Claro (tipo='evento'): se convierte en EVENTO de la rota,
// no en pieza del feed. Debe ofrecer "Crear evento" en vez de "Enviar al feed".
const ITEM_EVENTO = {
  ...ITEM_PARSED,
  id: "item-ev",
  cajon: "eventos_claro" as const,
  tipo: "evento" as const,
  titulo: "Cruz Azul vs América",
  resumen: "Clip del gol y resumen 1 min",
  marca: "claro-sports",
  marca_nombre: "Claro Sports",
};

const INSUMOS_CON_EVENTO = {
  fecha: "2026-06-05",
  cajones: [
    { cajon: "portal", lotes: [], items: [] },
    { cajon: "corresponsales", lotes: [], items: [] },
    { cajon: "reporteros", lotes: [], items: [] },
    {
      cajon: "eventos_claro",
      lotes: [{ ...LOTE_PORTAL, cajon: "eventos_claro" }],
      items: [ITEM_EVENTO],
    },
  ],
};

// Ítem del cajón Indicaciones (tipo='contexto'): guía editorial, nunca pieza. Muestra el
// badge "Guía" (sin "Empujar ya"); la generación de copy lee esas indicaciones hacia adentro.
const ITEM_CONTEXTO = {
  ...ITEM_PARSED,
  id: "item-ctx",
  cajon: "contexto" as const,
  tipo: "contexto" as const,
  titulo: "No llamar 'Tri' a la selección",
  marca: "claro-sports",
  marca_nombre: "Claro Sports",
};

const INSUMOS_CON_CONTEXTO = {
  fecha: "2026-06-05",
  cajones: [
    { cajon: "portal", lotes: [], items: [] },
    { cajon: "corresponsales", lotes: [], items: [] },
    { cajon: "reporteros", lotes: [], items: [] },
    { cajon: "eventos_claro", lotes: [], items: [] },
    {
      cajon: "contexto",
      lotes: [{ ...LOTE_PORTAL, cajon: "contexto" }],
      items: [ITEM_CONTEXTO],
    },
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

// Lote en estado `parseando`: el worker aún corre Haiku (flujo asíncrono). El cajón debe
// mostrar el indicador "Procesando…" y los ítems aún no aparecen.
const LOTE_PARSEANDO = {
  ...LOTE_PORTAL,
  id: "lote-p",
  estado: "parseando",
  total_items: 0,
};

const INSUMOS_PARSEANDO = {
  fecha: "2026-06-05",
  cajones: [
    { cajon: "portal", lotes: [LOTE_PARSEANDO], items: [] },
    { cajon: "corresponsales", lotes: [], items: [] },
    { cajon: "reporteros", lotes: [], items: [] },
    { cajon: "eventos_claro", lotes: [], items: [] },
  ],
};

const GENERACION_INSUMOS = {
  id: "gen-1",
  tipo: "insumos",
  marca: "",
  etiqueta: "Cajón portal · 2026-06-05",
  estado: "ejecutando",
  fase: "",
  motivo: "",
  salida: "",
  error: "",
  metricas: null,
  resultado: null,
  autor_id: "",
  autor_nombre: "",
  fecha_inicio: "2026-06-05T06:00:00",
  fecha_fin: "",
};

const DIAS_HISTORIAL = {
  dias: [
    { fecha: "2026-06-05", total: 1, por_cajon: { portal: 1, corresponsales: 0, reporteros: 0, eventos_claro: 0, notas: 0, contexto: 0 } },
    { fecha: "2026-06-04", total: 5, por_cajon: { portal: 2, corresponsales: 2, reporteros: 1, eventos_claro: 0, notas: 0, contexto: 0 } },
  ],
};

// ── Setup y teardown ──────────────────────────────────────────────────────────

beforeEach(() => {
  vi.restoreAllMocks();
  // El mock de sonner es un vi.fn() persistente (no un spyOn): restoreAllMocks no borra su
  // historial, así que lo limpiamos a mano para que los toasts de un test no contaminen al otro.
  vi.clearAllMocks();
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
  it("un editor de UnoTV solo ve sus cajones (sin los de Claro Sports)", async () => {
    mockApiInsumos();
    renderConProviders(<CajonesDia />);

    expect(await screen.findByText("Portal / SMS")).toBeInTheDocument();
    expect(screen.getByText("Corresponsales")).toBeInTheDocument();
    expect(screen.getByText("Reporteros (agenda PDF)")).toBeInTheDocument();
    // Eventos Claro, Notas e Indicaciones son de Claro Sports: NO para un editor de UnoTV.
    expect(screen.queryByText("Eventos Claro (Excel/CSV)")).not.toBeInTheDocument();
    expect(screen.queryByText("Notas y links")).not.toBeInTheDocument();
    expect(screen.queryByText("Indicaciones")).not.toBeInTheDocument();
  });

  it("en 'Todas' (admin) se ven los cajones de todas las marcas", async () => {
    mockApiInsumos();
    renderConProviders(<CajonesDia />, usuarioAdmin());

    expect(await screen.findByText("Portal / SMS")).toBeInTheDocument();
    expect(screen.getByText("Corresponsales")).toBeInTheDocument();
    expect(screen.getByText("Reporteros (agenda PDF)")).toBeInTheDocument();
    expect(screen.getByText("Eventos Claro (Excel/CSV)")).toBeInTheDocument();
    // Cajones de Claro Sports para que el coordinador de redes vuelque su material de WhatsApp.
    expect(screen.getByText("Notas y links")).toBeInTheDocument();
    expect(screen.getByText("Indicaciones")).toBeInTheDocument();
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
        expect.anything(), // marca param
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

  it("el botón 'Empujar ya' llama a api.insumos.usarItem", async () => {
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

    // Ahora encontrar y hacer clic en el botón "Empujar ya" (override del auto-feed)
    const boton = screen.getByRole("button", { name: "Empujar ya (fuerza al feed)" });
    fireEvent.click(boton);

    await waitFor(() => {
      expect(usarMock).toHaveBeenCalledWith("item-1", { generar: true });
    });
  });

  it("«Empujar ya» con copy_en_proceso=false AVISA (no miente con 'Copy en marcha')", async () => {
    vi.spyOn(apiMod.api.insumos, "usarItem").mockResolvedValue({
      item: { ...ITEM_PARSED, usado: true },
      contenido_id: "c-nuevo",
      copy_en_proceso: false,
    } as never);
    vi.spyOn(apiMod.api.insumos, "listar").mockResolvedValue(INSUMOS_CON_ITEM as never);
    vi.spyOn(apiMod.api.insumos, "dias").mockResolvedValue({ dias: [] } as never);

    renderConProviders(<CajonesDia />);

    await screen.findByText("Sismo en CDMX de 5.4 grados");
    fireEvent.click(screen.getByRole("button", { name: "Empujar ya (fuerza al feed)" }));

    await waitFor(() => {
      expect(toast.warning).toHaveBeenCalledWith(
        expect.stringMatching(/el copy no arrancó/i),
      );
    });
    expect(toast.success).not.toHaveBeenCalledWith("Copy en marcha");
  });

  it("«Empujar ya» con copy_en_proceso=true confirma 'Copy en marcha'", async () => {
    vi.spyOn(apiMod.api.insumos, "usarItem").mockResolvedValue({
      item: { ...ITEM_PARSED, usado: true },
      contenido_id: "c-nuevo",
      copy_en_proceso: true,
    } as never);
    vi.spyOn(apiMod.api.insumos, "listar").mockResolvedValue(INSUMOS_CON_ITEM as never);
    vi.spyOn(apiMod.api.insumos, "dias").mockResolvedValue({ dias: [] } as never);

    renderConProviders(<CajonesDia />);

    await screen.findByText("Sismo en CDMX de 5.4 grados");
    fireEvent.click(screen.getByRole("button", { name: "Empujar ya (fuerza al feed)" }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith("Copy en marcha");
    });
    expect(toast.warning).not.toHaveBeenCalled();
  });

  it("el botón 'Descartar' llama a api.insumos.descartarItem tras confirmar", async () => {
    const descartarMock = vi
      .spyOn(apiMod.api.insumos, "descartarItem")
      .mockResolvedValue({ ok: true } as never);
    vi.spyOn(apiMod.api.insumos, "listar").mockResolvedValue(INSUMOS_CON_ITEM as never);
    vi.spyOn(apiMod.api.insumos, "dias").mockResolvedValue({ dias: [] } as never);

    renderConProviders(<CajonesDia />);

    await screen.findByText("Sismo en CDMX de 5.4 grados");
    fireEvent.click(screen.getByRole("button", { name: "Descartar ítem" }));

    await waitFor(() => {
      expect(descartarMock).toHaveBeenCalledWith("item-1");
    });
  });

  it("un ítem usado NO ofrece 'Descartar' (su pieza ya vive en el tablero)", async () => {
    const itemUsado = { ...ITEM_PARSED, usado: true, contenido_id: "c-99" };
    vi.spyOn(apiMod.api.insumos, "listar").mockResolvedValue({
      ...INSUMOS_CON_ITEM,
      cajones: [
        { cajon: "portal", lotes: [LOTE_PORTAL], items: [itemUsado] },
        { cajon: "corresponsales", lotes: [], items: [] },
        { cajon: "reporteros", lotes: [], items: [] },
        { cajon: "eventos_claro", lotes: [], items: [] },
      ],
    } as never);
    vi.spyOn(apiMod.api.insumos, "dias").mockResolvedValue({ dias: [] } as never);

    renderConProviders(<CajonesDia />);

    await screen.findByText("Sismo en CDMX de 5.4 grados");
    expect(screen.queryByRole("button", { name: "Descartar ítem" })).not.toBeInTheDocument();
  });

  it("ítem en pool muestra badge 'En el pool'", async () => {
    vi.spyOn(apiMod.api.insumos, "listar").mockResolvedValue(INSUMOS_CON_ITEM as never);
    vi.spyOn(apiMod.api.insumos, "dias").mockResolvedValue({ dias: [] } as never);

    renderConProviders(<CajonesDia />);

    await screen.findByText("Sismo en CDMX de 5.4 grados");
    expect(screen.getByText("En el pool")).toBeInTheDocument();
  });

  it("ítem ya usado muestra badge 'En el feed' (sin 'Empujar ya')", async () => {
    const itemUsado = { ...ITEM_PARSED, usado: true, contenido_id: "c-99" };
    vi.spyOn(apiMod.api.insumos, "listar").mockResolvedValue({
      ...INSUMOS_CON_ITEM,
      cajones: [
        { cajon: "portal", lotes: [LOTE_PORTAL], items: [itemUsado] },
        { cajon: "corresponsales", lotes: [], items: [] },
        { cajon: "reporteros", lotes: [], items: [] },
        { cajon: "eventos_claro", lotes: [], items: [] },
      ],
    } as never);
    vi.spyOn(apiMod.api.insumos, "dias").mockResolvedValue({ dias: [] } as never);

    renderConProviders(<CajonesDia />);

    await screen.findByText("Sismo en CDMX de 5.4 grados");
    expect(screen.getByText("En el feed")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Empujar ya (fuerza al feed)" })).not.toBeInTheDocument();
  });

  it("un ítem de Eventos Claro ofrece 'Crear evento' (no 'Empujar ya')", async () => {
    vi.spyOn(apiMod.api.insumos, "listar").mockResolvedValue(INSUMOS_CON_EVENTO as never);
    vi.spyOn(apiMod.api.insumos, "dias").mockResolvedValue({ dias: [] } as never);

    // El cajón Eventos Claro es de Claro Sports; lo ve un admin en "Todas".
    renderConProviders(<CajonesDia />, usuarioAdmin());

    await screen.findByText("Cruz Azul vs América");
    expect(screen.getByRole("button", { name: "Crear evento" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Empujar ya (fuerza al feed)" }),
    ).not.toBeInTheDocument();
  });

  it("el botón 'Crear evento' llama a api.insumos.crearEvento", async () => {
    const crearMock = vi.spyOn(apiMod.api.insumos, "crearEvento").mockResolvedValue({
      item: { ...ITEM_EVENTO, usado: true, contenido_id: "ev-nuevo" },
      evento: { id: "ev-nuevo" },
      evento_id: "ev-nuevo",
    } as never);
    vi.spyOn(apiMod.api.insumos, "listar").mockResolvedValue(INSUMOS_CON_EVENTO as never);
    vi.spyOn(apiMod.api.insumos, "dias").mockResolvedValue({ dias: [] } as never);

    // El cajón Eventos Claro es de Claro Sports; lo ve un admin en "Todas".
    renderConProviders(<CajonesDia />, usuarioAdmin());

    await screen.findByText("Cruz Azul vs América");
    fireEvent.click(screen.getByRole("button", { name: "Crear evento" }));

    await waitFor(() => {
      expect(crearMock).toHaveBeenCalledWith("item-ev", {});
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
        expect.anything(), // marca param
      );
    });
  });

  it("muestra el indicador 'Procesando con Haiku…' cuando un lote está parseando sin generación activa", async () => {
    mockApiInsumos(INSUMOS_PARSEANDO, { dias: [] });
    renderConProviders(<CajonesDia />);

    // Sin generación activa: muestra el spinner de texto "Procesando con Haiku…".
    expect(await screen.findByTestId("lote-parseando")).toBeInTheDocument();
    expect(screen.getByText("Procesando con Haiku…")).toBeInTheDocument();
  });

  it("NO muestra 'Procesando con Haiku…' si el lote parseando YA tiene ítems (zombi: worker muerto a medias)", async () => {
    // Lote atascado en `parseando` pero con ítems ya insertados: el parseo SÍ terminó.
    // El spinner NO debe quedarse atascado (regresión: antes se mostraba para siempre).
    const itemDelLote = { ...ITEM_PARSED, id: "item-z", lote_id: LOTE_PARSEANDO.id };
    const insumosZombi = {
      fecha: "2026-06-05",
      cajones: [
        { cajon: "portal", lotes: [LOTE_PARSEANDO], items: [itemDelLote] },
        { cajon: "corresponsales", lotes: [], items: [] },
        { cajon: "reporteros", lotes: [], items: [] },
        { cajon: "eventos_claro", lotes: [], items: [] },
      ],
    };
    mockApiInsumos(insumosZombi, { dias: [] });
    renderConProviders(<CajonesDia />);

    // El ítem del lote aparece…
    expect(await screen.findByText("Sismo en CDMX de 5.4 grados")).toBeInTheDocument();
    // …y NO se muestra el spinner "Procesando con Haiku…" (el parseo ya produjo ítems).
    expect(screen.queryByTestId("lote-parseando")).not.toBeInTheDocument();
    expect(screen.queryByText("Procesando con Haiku…")).not.toBeInTheDocument();
  });

  it("muestra el visor de streaming cuando hay lote parseando con generación en ejecución", async () => {
    // Simula aportar devolviendo una generación en ejecución.
    const genEjecutando = { ...GENERACION_INSUMOS, estado: "ejecutando" };
    vi.spyOn(apiMod.api.insumos, "aportar").mockResolvedValue({
      lote: LOTE_PARSEANDO,
      generacion: genEjecutando,
    } as never);
    // Después del aportar, el listar devuelve el lote parseando.
    vi.spyOn(apiMod.api.insumos, "listar")
      .mockResolvedValueOnce(INSUMOS_VACIOS as never)
      .mockResolvedValue(INSUMOS_PARSEANDO as never);
    vi.spyOn(apiMod.api.insumos, "dias").mockResolvedValue({ dias: [] } as never);
    // El sondeo de useGeneracion llama a api.generacion; devolvemos la misma gen ejecutando.
    vi.spyOn(apiMod.api, "generacion").mockResolvedValue({
      generacion: genEjecutando,
    } as never);

    renderConProviders(<CajonesDia />);
    await screen.findByText("Portal / SMS");

    // Enviar material para arrancar el flujo.
    const textarea = screen.getByLabelText("Texto para Portal / SMS");
    fireEvent.change(textarea, { target: { value: "1.- Sismo" } });
    fireEvent.click(screen.getByRole("button", { name: "Procesar Portal / SMS" }));

    await waitFor(() => {
      expect(screen.getByTestId("lote-parseando")).toBeInTheDocument();
    });
    // Con la generación en ejecución debe mostrar "Procesando con IA…" (no "Haiku").
    await waitFor(() => {
      expect(screen.getByText("Procesando con IA…")).toBeInTheDocument();
    });
  });

  it("aportar encola el job (devuelve {lote, generacion}) y refresca el cajón", async () => {
    const aportarMock = vi
      .spyOn(apiMod.api.insumos, "aportar")
      .mockResolvedValue({ lote: LOTE_PARSEANDO, generacion: GENERACION_INSUMOS } as never);
    // 1ª carga: lote en proceso. 2ª (tras invalidar): ya listo con el ítem.
    const listarMock = vi
      .spyOn(apiMod.api.insumos, "listar")
      .mockResolvedValueOnce(INSUMOS_VACIOS as never)
      .mockResolvedValue(INSUMOS_CON_ITEM as never);
    vi.spyOn(apiMod.api.insumos, "dias").mockResolvedValue({ dias: [] } as never);

    renderConProviders(<CajonesDia />);

    await screen.findByText("Portal / SMS");

    // Escribe texto en el cajón Portal y pulsa "Procesar".
    const textarea = screen.getByLabelText("Texto para Portal / SMS");
    fireEvent.change(textarea, { target: { value: "1.- Sismo" } });
    fireEvent.click(screen.getByRole("button", { name: "Procesar Portal / SMS" }));

    await waitFor(() => {
      expect(aportarMock).toHaveBeenCalled();
    });
    // El lote se estampa con la marca activa del usuario ("unotv"): así los ítems que la
    // IA no clasifique heredan esa marca y el filtro por marca del cajón los encuentra.
    const form = aportarMock.mock.calls[0][0] as FormData;
    expect(form.get("marca")).toBe("unotv");
    // Tras encolar, se invalida la query y aparece el ítem ya parseado (segundo listar).
    expect(await screen.findByText("Sismo en CDMX de 5.4 grados")).toBeInTheDocument();
    expect(listarMock.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("en 'Todas' (admin) el lote hereda la marca DUEÑA del cajón, no queda sin marca", async () => {
    const aportarMock = vi
      .spyOn(apiMod.api.insumos, "aportar")
      .mockResolvedValue({ lote: LOTE_PORTAL, generacion: null } as never);
    mockApiInsumos();

    renderConProviders(<CajonesDia />, usuarioAdmin());

    await screen.findByText("Portal / SMS");
    fireEvent.change(screen.getByLabelText("Texto para Portal / SMS"), {
      target: { value: "1.- Nota" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Procesar Portal / SMS" }));

    await waitFor(() => {
      expect(aportarMock).toHaveBeenCalled();
    });
    // Sin marca activa (vista "Todas") el lote cae a la marca del cajón (Portal → unotv):
    // sus ítems no quedan huérfanos del filtro por marca.
    const form = aportarMock.mock.calls[0][0] as FormData;
    expect(form.get("marca")).toBe("unotv");
  });

  it("una indicación muestra el badge 'Guía' (tooltip honesto) y no ofrece 'Empujar ya'", async () => {
    vi.spyOn(apiMod.api.insumos, "listar").mockResolvedValue(INSUMOS_CON_CONTEXTO as never);
    vi.spyOn(apiMod.api.insumos, "dias").mockResolvedValue({ dias: [] } as never);

    // El cajón Indicaciones es de Claro Sports; lo ve un admin en "Todas".
    renderConProviders(<CajonesDia />, usuarioAdmin());

    await screen.findByText("No llamar 'Tri' a la selección");
    const badge = screen.getByText("Guía");
    expect(badge).toHaveAttribute(
      "title",
      "Guía al equipo y a la IA al redactar (no se publica). Caduca a los 7 días.",
    );
    expect(
      screen.queryByRole("button", { name: "Empujar ya (fuerza al feed)" }),
    ).not.toBeInTheDocument();
  });

  it("una indicación CADUCADA (indicacion_vigente=false) muestra 'Caducada', no 'Guía'", async () => {
    const ctxCaducada = { ...ITEM_CONTEXTO, indicacion_vigente: false };
    vi.spyOn(apiMod.api.insumos, "listar").mockResolvedValue({
      fecha: "2026-06-05",
      cajones: [
        { cajon: "portal", lotes: [], items: [] },
        { cajon: "corresponsales", lotes: [], items: [] },
        { cajon: "reporteros", lotes: [], items: [] },
        { cajon: "eventos_claro", lotes: [], items: [] },
        {
          cajon: "contexto",
          lotes: [{ ...LOTE_PORTAL, cajon: "contexto" }],
          items: [ctxCaducada],
        },
      ],
    } as never);
    vi.spyOn(apiMod.api.insumos, "dias").mockResolvedValue({ dias: [] } as never);

    renderConProviders(<CajonesDia />, usuarioAdmin());

    await screen.findByText("No llamar 'Tri' a la selección");
    const badge = screen.getByText("Caducada");
    expect(badge).toHaveAttribute(
      "title",
      "Ya no guía el copy: vuelve a pegarla para reactivarla.",
    );
    expect(screen.queryByText("Guía")).not.toBeInTheDocument();
  });

  it("una indicación VIGENTE (indicacion_vigente=true) sigue mostrando 'Guía'", async () => {
    const ctxVigente = { ...ITEM_CONTEXTO, indicacion_vigente: true };
    vi.spyOn(apiMod.api.insumos, "listar").mockResolvedValue({
      fecha: "2026-06-05",
      cajones: [
        { cajon: "portal", lotes: [], items: [] },
        { cajon: "corresponsales", lotes: [], items: [] },
        { cajon: "reporteros", lotes: [], items: [] },
        { cajon: "eventos_claro", lotes: [], items: [] },
        {
          cajon: "contexto",
          lotes: [{ ...LOTE_PORTAL, cajon: "contexto" }],
          items: [ctxVigente],
        },
      ],
    } as never);
    vi.spyOn(apiMod.api.insumos, "dias").mockResolvedValue({ dias: [] } as never);

    renderConProviders(<CajonesDia />, usuarioAdmin());

    await screen.findByText("No llamar 'Tri' a la selección");
    expect(screen.getByText("Guía")).toBeInTheDocument();
    expect(screen.queryByText("Caducada")).not.toBeInTheDocument();
  });

  it("pasa la marca activa del usuario a api.insumos.listar", async () => {
    const listarMock = vi.spyOn(apiMod.api.insumos, "listar").mockResolvedValue(INSUMOS_VACIOS as never);
    vi.spyOn(apiMod.api.insumos, "dias").mockResolvedValue({ dias: [] } as never);

    renderConProviders(<CajonesDia />);

    await screen.findByText("Portal / SMS");

    // El usuario del helper tiene marcas: ["unotv"], así que marcaActiva = "unotv"
    await waitFor(() => {
      expect(listarMock).toHaveBeenCalledWith(
        expect.any(String),
        expect.anything(),
        expect.any(Boolean),
        "unotv",
      );
    });
  });
});
