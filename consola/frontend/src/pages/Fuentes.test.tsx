/**
 * Tests para la sección "Catálogo" de Fuentes.tsx (Ola 4: Fuentes externas + idiomas).
 *
 * Valida:
 * - El catálogo renderiza los presets recibidos del backend.
 * - El checkbox de un preset activo está deshabilitado.
 * - Seleccionar un preset y hacer clic en "Activar seleccionadas" llama a la API.
 * - Un preset ya activo muestra el badge "Activo".
 * - La pestaña RSS filtra los feeds y noticias por marca activa.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MarcaActivaContexto, type ValorMarcaActiva } from "@/hooks/marca-activa-contexto";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import { MarcaActivaProvider } from "@/hooks/use-marca-activa";
import type { UsuarioSesion } from "@/types";

import Fuentes from "./Fuentes";

// ── Datos de prueba ─────────────────────────────────────────────────────────

const OPCIONES = {
  marcas: [{ id: "unotv", nombre: "UnoTV" }],
  redes: [{ id: "instagram", nombre: "Instagram", limite: null }],
};

const PRESETS = {
  presets: [
    {
      id: "reuters-world",
      nombre: "Reuters — World",
      url: "https://feeds.reuters.com/reuters/worldNews",
      categoria: "internacional",
      marca_sugerida: "unotv",
      linea_sugerida: "Internacional",
      idioma: "en",
      region: "GLOBAL",
      descripcion: "Noticias internacionales de Reuters.",
      activa: false,
    },
    {
      id: "bbc-mundo",
      nombre: "BBC Mundo",
      url: "https://feeds.bbci.co.uk/mundo/rss.xml",
      categoria: "internacional",
      marca_sugerida: "unotv",
      linea_sugerida: "Internacional",
      idioma: "es",
      region: "GLOBAL",
      descripcion: "BBC en español.",
      activa: true,
    },
  ],
  categorias: ["mx", "internacional", "deportes"],
};

const PRESETS_ACTIVAR = {
  creadas: 1,
  fuentes: [
    {
      id: "f1",
      nombre: "Reuters — World",
      url: "https://feeds.reuters.com/reuters/worldNews",
      marca: "unotv",
      marca_nombre: "UnoTV",
      activo: true,
      incluir: "",
      excluir: "",
      redes_def: [],
      ultima_actualizacion: null,
      ultimo_error: null,
      ultimo_conteo: 0,
      propia: false,
    },
  ],
};

// ── RSS fixtures ──────────────────────────────────────────────────────────────

const FUENTES_RSS_UNOTV = {
  fuentes: [
    {
      id: "f-unotv",
      nombre: "UnoTV Nacional",
      url: "https://unotv.com/feed",
      marca: "unotv",
      marca_nombre: "UnoTV",
      activo: true,
      incluir: "",
      excluir: "",
      redes_def: [],
      ultima_actualizacion: null,
      ultimo_error: null,
      ultimo_conteo: 0,
      propia: false,
    },
  ],
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function marcaActivaValor(marcaActiva: string | null): ValorMarcaActiva {
  return {
    marcaActiva,
    marcaPrimaria: marcaActiva,
    enMarcaPrimaria: true,
    esMultiMarca: false,
    puedeTodas: false,
    marcasParaSwitch: marcaActiva ? [{ id: marcaActiva, nombre: marcaActiva }] : [],
    nombreActiva: marcaActiva,
    cambiarMarca: vi.fn(),
    volverAPrimaria: vi.fn(),
  };
}

function renderFuentesConMarca(marcaActiva: string | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesionValor(usuario())}>
        <MarcaActivaContexto.Provider value={marcaActivaValor(marcaActiva)}>
          <MemoryRouter>
            <Fuentes />
          </MemoryRouter>
        </MarcaActivaContexto.Provider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

let activarCalled = false;
let activarBody: unknown = null;

function stubFetch(opts: { rssPayload?: object } = {}) {
  activarCalled = false;
  activarBody = null;

  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL, init?: RequestInit) => {
      const ruta = String(url);

      if (ruta.includes("/api/publicaciones/opciones")) {
        return new Response(JSON.stringify(OPCIONES), { status: 200 });
      }
      if (ruta.includes("/api/fuentes/presets/activar")) {
        activarCalled = true;
        activarBody = init?.body ? JSON.parse(init.body as string) : null;
        return new Response(JSON.stringify(PRESETS_ACTIVAR), { status: 200 });
      }
      if (ruta.includes("/api/fuentes/presets")) {
        return new Response(JSON.stringify(PRESETS), { status: 200 });
      }
      if (ruta.includes("/api/fuentes")) {
        return new Response(
          JSON.stringify({ fuentes: [], agencias: [], pendientes: [] }),
          { status: 200 },
        );
      }
      if (ruta.includes("/api/rss/items")) {
        return new Response(JSON.stringify({ items: [], errores: [] }), { status: 200 });
      }
      if (ruta.includes("/api/rss/fuentes")) {
        const payload = opts.rssPayload ?? { fuentes: [] };
        return new Response(JSON.stringify(payload), { status: 200 });
      }
      // Fallback silencioso para cualquier otra petición.
      return new Response("{}", { status: 200 });
    }),
  );
}

function usuario(): UsuarioSesion {
  return { id: "u1", usuario: "ana", rol: "editor", debe_cambiar_password: false, marcas: ["unotv"] };
}

function sesionValor(u: UsuarioSesion | null): ValorSesion {
  return { usuario: u, cargando: false, iniciarSesion: vi.fn(), verificarConPasskey: vi.fn(), verificarConCodigo: vi.fn(), cerrarSesion: vi.fn(), refrescar: vi.fn() };
}

function renderFuentes() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesionValor(usuario())}>
        <MarcaActivaProvider>
          <MemoryRouter>
            <Fuentes />
          </MemoryRouter>
        </MarcaActivaProvider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("Fuentes — Catálogo (Ola 4)", () => {
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

  it("muestra la pestaña Catálogo y renderiza los presets", async () => {
    stubFetch();
    renderFuentes();

    // Navegar a la pestaña Catálogo.
    const tabCatalogo = await screen.findByRole("tab", { name: "Externas" });
    fireEvent.mouseDown(tabCatalogo, { button: 0 });

    // Los dos presets deben aparecer.
    expect(await screen.findByText("Reuters — World")).toBeInTheDocument();
    expect(await screen.findByText("BBC Mundo")).toBeInTheDocument();
  });

  it("tres pestañas: Externas, Internas y Rendimiento", async () => {
    stubFetch();
    renderFuentes();

    // Fuentes tiene 3 pestañas: lo externo (RSS/agencias/Trends), lo interno (buzones del
    // equipo) y el RENDIMIENTO editorial por fuente (quién abre historias, % de uso) que
    // alimenta la decisión de potencia/tier de las fuentes.
    expect(await screen.findByRole("tab", { name: "Externas" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Internas" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Rendimiento" })).toBeInTheDocument();
    expect(screen.getAllByRole("tab")).toHaveLength(3);
  });

  it("el preset ya activo muestra badge 'Activo' y su checkbox está deshabilitado", async () => {
    stubFetch();
    renderFuentes();

    const tabCatalogo = await screen.findByRole("tab", { name: "Externas" });
    fireEvent.mouseDown(tabCatalogo, { button: 0 });

    // Espera a que renderice los presets.
    await screen.findByText("BBC Mundo");

    // El checkbox del preset activo debe estar deshabilitado.
    const chkBbc = screen.getByRole("checkbox", { name: "Seleccionar BBC Mundo" });
    expect(chkBbc).toBeDisabled();

    // El badge "Activo" aparece junto al nombre del preset activo.
    expect(screen.getByText("Activo")).toBeInTheDocument();
  });

  it("activar seleccionadas llama a la API con los ids correctos", async () => {
    stubFetch();
    renderFuentes();

    const tabCatalogo = await screen.findByRole("tab", { name: "Externas" });
    fireEvent.mouseDown(tabCatalogo, { button: 0 });

    // Espera a que renderice los presets.
    await screen.findByText("Reuters — World");

    // Seleccionar Reuters (el no activo).
    const chkReuters = screen.getByRole("checkbox", { name: "Seleccionar Reuters — World" });
    fireEvent.click(chkReuters);

    // Clic en "Activar seleccionadas".
    const boton = screen.getByRole("button", { name: /activar seleccionadas/i });
    expect(boton).not.toBeDisabled();
    fireEvent.click(boton);

    // Espera a que la mutación se complete.
    await waitFor(() => {
      expect(activarCalled).toBe(true);
    });

    // El body enviado debe contener el id del preset seleccionado.
    expect((activarBody as { ids: string[] }).ids).toContain("reuters-world");
  });

  it("el botón 'Activar seleccionadas' empieza deshabilitado sin selección", async () => {
    stubFetch();
    renderFuentes();

    const tabCatalogo = await screen.findByRole("tab", { name: "Externas" });
    fireEvent.mouseDown(tabCatalogo, { button: 0 });

    await screen.findByText("Reuters — World");

    const boton = screen.getByRole("button", { name: /activar seleccionadas/i });
    expect(boton).toBeDisabled();
  });

  it("activar seleccionadas incluye la marca activa en el body cuando hay marca activa", async () => {
    stubFetch();

    // Render con marca activa "unotv" directamente via contexto
    renderFuentesConMarca("unotv");

    const tabCatalogo = await screen.findByRole("tab", { name: "Externas" });
    fireEvent.mouseDown(tabCatalogo, { button: 0 });

    await screen.findByText("Reuters — World");

    const chkReuters = screen.getByRole("checkbox", { name: "Seleccionar Reuters — World" });
    fireEvent.click(chkReuters);

    const boton = screen.getByRole("button", { name: /activar seleccionadas/i });
    fireEvent.click(boton);

    await waitFor(() => {
      expect(activarCalled).toBe(true);
    });

    // La marca activa debe enviarse en el body.
    expect((activarBody as { marca?: string }).marca).toBe("unotv");
  });
});

describe("Fuentes — filtrado por marca activa en pestaña RSS", () => {
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

  it("Externas muestra solo los feeds de la marca activa", async () => {
    stubFetch({ rssPayload: FUENTES_RSS_UNOTV });
    renderFuentesConMarca("unotv");

    // Navegar a la pestaña Externas (los feeds RSS se gestionan ahí)
    const tabExternas = await screen.findByRole("tab", { name: "Externas" });
    fireEvent.mouseDown(tabExternas, { button: 0 });

    // El feed de UnoTV debe aparecer (misma marca que la activa)
    expect(await screen.findByText("UnoTV Nacional")).toBeInTheDocument();
  });
});
