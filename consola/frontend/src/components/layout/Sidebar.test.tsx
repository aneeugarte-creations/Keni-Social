import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CuentaUsuario } from "@/components/layout/CuentaUsuario";
import { Sidebar } from "@/components/layout/Sidebar";
import { appDeRuta, gruposDeApp, hojasDeApp, rutaPrimaria } from "@/components/layout/apps-scope";
import {
  MarcaActivaContexto,
  type ValorMarcaActiva,
} from "@/hooks/marca-activa-contexto";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import type { AppCatalogo, RolUsuario } from "@/types";

/**
 * Catálogo de prueba. `navegacion` es lo que pinta el sidebar (bloques de flujo ya
 * agrupados y etiquetados por el backend); `apps` se conserva para los helpers de
 * `apps-scope` (breadcrumb, paleta) que siguen consumiéndolo.
 */
const CATALOGO = {
  apps: [
    {
      id: "produccion",
      etiqueta: "Producción",
      icono: "Sparkles",
      descripcion: "Copy, clips, skills y verificación",
      permisos: ["editor", "admin"],
      rutas_frontend: ["/contenido/estudio", "/datos/investigacion", "/operacion/revision", "/datos/actividad"],
      nav: [
        { ruta: "/contenido/estudio", etiqueta: "Estudio", icono: "Palette", descripcion: "", grupo: "contenido", grupo_orden: 20, orden: 10 },
        { ruta: "/contenido/biblioteca", etiqueta: "Biblioteca", icono: "Library", descripcion: "", grupo: "contenido", grupo_orden: 20, orden: 20 },
        { ruta: "/datos/investigacion", etiqueta: "Investigación", icono: "Search", descripcion: "", grupo: "datos", grupo_orden: 30, orden: 10 },
        { ruta: "/operacion/revision", etiqueta: "Revisión", icono: "ShieldCheck", descripcion: "", grupo: "operacion", grupo_orden: 10, orden: 30 },
        { ruta: "/datos/actividad", etiqueta: "Actividad IA", icono: "Activity", descripcion: "", grupo: "datos", grupo_orden: 30, orden: 30 },
      ],
    },
    {
      id: "metricas",
      etiqueta: "Analíticas",
      icono: "BarChart3",
      descripcion: "Métricas, comercial y reportes",
      permisos: ["editor", "admin"],
      rutas_frontend: ["/datos/analiticas"],
      nav: [
        { ruta: "/datos/analiticas", etiqueta: "Analíticas", icono: "BarChart3", descripcion: "", grupo: "datos", grupo_orden: 30, orden: 20 },
      ],
    },
    {
      id: "operacion",
      etiqueta: "Operación",
      icono: "Send",
      descripcion: "Rota, parrilla y publicación",
      permisos: ["editor", "admin"],
      rutas_frontend: ["/operacion/feed", "/operacion/calendario"],
      nav: [
        { ruta: "/operacion/feed", etiqueta: "Feed", icono: "LayoutGrid", descripcion: "", grupo: "operacion", grupo_orden: 10, orden: 20 },
        { ruta: "/operacion/calendario", etiqueta: "Calendario", icono: "CalendarDays", descripcion: "", grupo: "operacion", grupo_orden: 10, orden: 25 },
      ],
    },
  ],
  // Bloques de flujo tal como los entrega el backend (`entradas_nav_activas`):
  // Feed (red social interna) encabeza "Operación", seguido de Calendario y Revisión; los
  // hubs van como UNA entrada (su sub-nav es in-page). El bloque vive también en el path.
  navegacion: [
    {
      etiqueta: "Operación",
      items: [
        { ruta: "/operacion/feed", etiqueta: "Feed", icono: "LayoutGrid", descripcion: "Feed del equipo" },
        { ruta: "/operacion/calendario", etiqueta: "Calendario", icono: "CalendarDays", descripcion: "Turnos y calendario" },
        { ruta: "/operacion/revision", etiqueta: "Revisión", icono: "ShieldCheck", descripcion: "Cola de aprobación" },
      ],
    },
    {
      etiqueta: "Contenido",
      items: [
        { ruta: "/contenido/estudio", etiqueta: "Estudio", icono: "Palette", descripcion: "Lienzo de imagen" },
        { ruta: "/contenido/biblioteca", etiqueta: "Biblioteca", icono: "Library", descripcion: "Prompts, editorial y plantillas" },
      ],
    },
    {
      etiqueta: "Datos",
      items: [
        { ruta: "/datos/investigacion", etiqueta: "Investigación", icono: "Search", descripcion: "Fuentes y radar" },
        { ruta: "/datos/analiticas", etiqueta: "Analíticas", icono: "BarChart3", descripcion: "Medición" },
        { ruta: "/datos/actividad", etiqueta: "Actividad IA", icono: "Activity", descripcion: "Qué hizo la IA" },
      ],
    },
  ],
};

function stubCatalogo() {
  const fn = vi.fn(async (url: string | URL) => {
    if (String(url).includes("/api/catalogo")) {
      return new Response(JSON.stringify(CATALOGO), { status: 200 });
    }
    return new Response("{}", { status: 200 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

/**
 * localStorage de juguete (jsdom no siempre expone `clear`). Aísla cualquier
 * estado persistido entre tests (p. ej. el colapsado del sidebar lo guarda el
 * AppShell, no el Sidebar, pero CuentaUsuario y otros podrían tocarlo).
 */
function instalarLocalStorage() {
  let store: Record<string, string> = {};
  const mock: Storage = {
    get length() {
      return Object.keys(store).length;
    },
    clear: () => {
      store = {};
    },
    getItem: (k: string) => (k in store ? store[k] : null),
    key: (i: number) => Object.keys(store)[i] ?? null,
    removeItem: (k: string) => {
      delete store[k];
    },
    setItem: (k: string, v: string) => {
      store[k] = String(v);
    },
  };
  vi.stubGlobal("localStorage", mock);
}

beforeEach(() => {
  instalarLocalStorage();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function valorSesion(rol: RolUsuario): ValorSesion {
  return {
    usuario: { id: "u1", usuario: "x", rol, debe_cambiar_password: false },
    cargando: false,
    iniciarSesion: async () => ({ mfaRequerido: false }),
    verificarMfa: async () => {},
    cerrarSesion: async () => {},
    refrescar: async () => {},
  };
}

/** Sonda que pinta el path actual, para verificar la navegación al hacer clic. */
function PathActual() {
  return <div data-testid="path">{useLocation().pathname}</div>;
}

/** Valor mínimo del contexto de marca activa (el Sidebar solo lee `marcaActiva`). */
function valorMarcaActiva(marcaActiva: string | null): ValorMarcaActiva {
  return {
    marcaActiva,
    marcaPrimaria: marcaActiva,
    enMarcaPrimaria: true,
    esMultiMarca: true,
    puedeTodas: true,
    marcasParaSwitch: [],
    nombreActiva: null,
    cambiarMarca: () => {},
    volverAPrimaria: () => {},
  };
}

/**
 * Render del sidebar con sesión simulada y en una ruta dada. El Sidebar es
 * data-driven (hidrata de `/api/catalogo`) y agrupa la nav por bloques de flujo.
 * `marcaActiva` (default `null` = "Todas") alimenta el gating por marca del nav.
 */
function renderSidebar(
  rol: RolUsuario,
  ruta = "/operacion/feed",
  props: { colapsado?: boolean; onToggleColapsar?: () => void } = {},
  marcaActiva: string | null = null,
) {
  stubCatalogo();
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <SesionContexto.Provider value={valorSesion(rol)}>
        <MarcaActivaContexto.Provider value={valorMarcaActiva(marcaActiva)}>
          <MemoryRouter initialEntries={[ruta]}>
            <Routes>
              <Route path="*" element={<Sidebar {...props} />} />
            </Routes>
            <PathActual />
          </MemoryRouter>
        </MarcaActivaContexto.Provider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

/** Render del menú del avatar (donde ahora viven los ajustes). */
function renderAvatarMenu(rol: RolUsuario) {
  return render(
    <SesionContexto.Provider value={valorSesion(rol)}>
      <MemoryRouter>
        <CuentaUsuario />
      </MemoryRouter>
    </SesionContexto.Provider>,
  );
}

describe("Sidebar · bloques de flujo", () => {
  it("pinta los 3 bloques de flujo con su encabezado", async () => {
    renderSidebar("editor", "/operacion/feed");
    expect(await screen.findByText("Operación")).toBeInTheDocument();
    expect(screen.getByText("Contenido")).toBeInTheDocument();
    expect(screen.getByText("Datos")).toBeInTheDocument();
  });

  it("el hub Calendario se ve en cualquier marca (su gating es por pestaña, no por hub)", async () => {
    // La Programación (calendario de publicaciones) es para todas las marcas; lo único de
    // Claro Sports es la pestaña Turnos, que se filtra dentro del hub (ver SubnavHub), no aquí.
    renderSidebar("editor", "/operacion/feed", {}, "unotv");
    expect(await screen.findByRole("link", { name: /calendario/i })).toBeInTheDocument();
  });

  it("cada entrada es un enlace; los hubs van como UNA sola entrada (sin hojas sueltas)", async () => {
    renderSidebar("editor", "/operacion/feed");
    // Bloque "Operación": tablero + revisión, los checkpoints diarios.
    expect(await screen.findByRole("link", { name: /feed/i })).toHaveAttribute("href", "/operacion/feed");
    expect(screen.getByRole("link", { name: /revisión/i })).toHaveAttribute("href", "/operacion/revision");
    // Bloque "Contenido".
    expect(screen.getByRole("link", { name: /estudio/i })).toHaveAttribute("href", "/contenido/estudio");
    expect(screen.getByRole("link", { name: /biblioteca/i })).toHaveAttribute("href", "/contenido/biblioteca");
    // Bloque "Datos": los hubs son una entrada, no sus pestañas.
    expect(screen.getByRole("link", { name: /investigación/i })).toHaveAttribute("href", "/datos/investigacion");
    expect(screen.getByRole("link", { name: /actividad ia/i })).toHaveAttribute("href", "/datos/actividad");
    // Las pestañas internas de un hub NO viven en el sidebar (van in-page).
    expect(screen.queryByRole("link", { name: /^fuentes$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^termómetro$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^editorial$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^comercial$/i })).not.toBeInTheDocument();
  });

  it("marca activa la entrada del hub aun estando en una de sus sub-rutas", async () => {
    renderSidebar("editor", "/datos/investigacion/fuentes");
    const investigacion = await screen.findByRole("link", { name: /investigación/i });
    // NavLink marca `aria-current=page` por prefijo (/datos/investigacion ⊇ …/fuentes).
    expect(investigacion).toHaveAttribute("aria-current", "page");
    // Y una entrada de otro bloque NO está activa.
    expect(screen.getByRole("link", { name: /estudio/i })).not.toHaveAttribute("aria-current");
  });

  it("las entradas llevan icono (no son texto plano)", async () => {
    renderSidebar("editor", "/operacion/feed");
    const feed = await screen.findByRole("link", { name: /feed/i });
    expect(feed.querySelector("svg")).not.toBeNull();
  });

  it("muestra un trigger de paleta (Buscar… + ⌘K) en vez del input falso 'F'", async () => {
    renderSidebar("editor", "/operacion/feed");
    const trigger = await screen.findByRole("button", { name: /buscar páginas/i });
    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveTextContent("⌘K");
    expect(screen.queryByRole("textbox", { name: /buscar/i })).not.toBeInTheDocument();
  });

  it("no muestra los ajustes en el sidebar (cuelgan del avatar)", async () => {
    renderSidebar("admin", "/operacion/feed");
    await screen.findByRole("link", { name: /feed/i });
    expect(screen.queryByRole("link", { name: /^configuración$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^usuarios$/i })).not.toBeInTheDocument();
  });
});

describe("Sidebar · rail colapsable", () => {
  it("colapsado muestra solo iconos (enlaces por entrada) y un botón para expandir", async () => {
    renderSidebar("editor", "/operacion/feed", { colapsado: true, onToggleColapsar: () => {} });
    // Cada entrada sigue siendo un enlace, ahora solo-icono (nombre por aria-label).
    expect(await screen.findByRole("link", { name: /feed/i })).toHaveAttribute("href", "/operacion/feed");
    expect(screen.getByRole("link", { name: /investigación/i })).toHaveAttribute("href", "/datos/investigacion");
    // Botón para volver a expandir la barra.
    expect(screen.getByRole("button", { name: /expandir barra/i })).toBeInTheDocument();
    // En rail no se pintan los encabezados de bloque (solo iconos).
    expect(screen.queryByText("Contenido")).not.toBeInTheDocument();
  });

  it("el toggle (colapsar / expandir) invoca onToggleColapsar", async () => {
    const onToggle = vi.fn();
    const { unmount } = renderSidebar("editor", "/operacion/feed", {
      colapsado: false,
      onToggleColapsar: onToggle,
    });
    fireEvent.click(await screen.findByRole("button", { name: /colapsar/i }));
    expect(onToggle).toHaveBeenCalledTimes(1);
    unmount();
    renderSidebar("editor", "/operacion/feed", { colapsado: true, onToggleColapsar: onToggle });
    fireEvent.click(await screen.findByRole("button", { name: /expandir barra/i }));
    expect(onToggle).toHaveBeenCalledTimes(2);
  });

  it("click en el icono de una entrada (en rail) navega a su ruta", async () => {
    renderSidebar("editor", "/operacion/feed", { colapsado: true, onToggleColapsar: () => {} });
    fireEvent.click(await screen.findByRole("link", { name: /feed/i }));
    await waitFor(() => expect(screen.getByTestId("path")).toHaveTextContent("/operacion/feed"));
  });
});

describe("apps-scope · helpers", () => {
  const apps = CATALOGO.apps as AppCatalogo[];

  it("rutaPrimaria es la PRIMERA HOJA (aplana hubs a su 1ª sub-pestaña)", () => {
    // Producción: 1ª entrada /contenido/estudio no es hub → se queda igual.
    expect(rutaPrimaria(apps[0])).toBe("/contenido/estudio");
    // Métricas: 1ª entrada /datos/analiticas ES hub → resuelve a su 1ª sub-pestaña.
    expect(rutaPrimaria(apps[1])).toBe("/datos/analiticas/metricas");
    // Operación: 1ª entrada /operacion/feed ES hub → resuelve a su 1ª sub-pestaña.
    expect(rutaPrimaria(apps[2])).toBe("/operacion/feed/feed");
  });

  it("hojasDeApp aplana hubs a sub-pestañas y conserva las no-hub", () => {
    const hojas = hojasDeApp(apps[0]).map((h) => h.ruta);
    expect(hojas).toEqual([
      "/contenido/estudio",
      // /contenido/biblioteca (hub) → sus sub-pestañas (Algoritmos se mudó aquí)
      "/contenido/biblioteca/documentos",
      "/contenido/biblioteca/estrategia",
      "/contenido/biblioteca/algoritmos",
      // /datos/investigacion (hub) → sus 2 sub-pestañas (Investigador = índice + Fuentes)
      "/datos/investigacion",
      "/datos/investigacion/fuentes",
      // /operacion/revision (hub) → sus 2 sub-pestañas
      "/operacion/revision/editorial",
      "/operacion/revision/verificacion",
      // /datos/actividad NO es hub: queda como hoja directa.
      "/datos/actividad",
    ]);
  });

  it("appDeRuta resuelve por prefijo más largo", () => {
    expect(appDeRuta(apps, "/contenido/estudio")?.id).toBe("produccion");
    expect(appDeRuta(apps, "/operacion/calendario/turnos")?.id).toBe("operacion");
    // Fuera de toda app (raíz / shell): undefined.
    expect(appDeRuta(apps, "/")).toBeUndefined();
    expect(appDeRuta(apps, "/configuracion")).toBeUndefined();
  });

  it("gruposDeApp respeta los bloques visuales por orden", () => {
    const grupos = gruposDeApp(apps[0]);
    const rutas = grupos.flatMap((g) => g.items.map((i) => i.ruta));
    // Ordenado por (grupo_orden, orden): operacion(/revision) · contenido(/estudio,/biblioteca) · datos(/investigacion,/actividad).
    expect(rutas).toEqual([
      "/operacion/revision",
      "/contenido/estudio",
      "/contenido/biblioteca",
      "/datos/investigacion",
      "/datos/actividad",
    ]);
  });
});

describe("Avatar · visibilidad de Usuarios por rol", () => {
  it("muestra 'Usuarios' al abrir el menú cuando el rol es admin", () => {
    renderAvatarMenu("admin");
    fireEvent.click(screen.getByRole("button", { name: /x.*administrador/i }));
    expect(screen.getByRole("menuitem", { name: /usuarios/i })).toBeInTheDocument();
  });

  it("oculta 'Usuarios' del menú cuando el rol es editor", () => {
    renderAvatarMenu("editor");
    fireEvent.click(screen.getByRole("button", { name: /x.*editor/i }));
    expect(screen.queryByRole("menuitem", { name: /usuarios/i })).not.toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /mi cuenta/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /configuración/i })).toBeInTheDocument();
  });
});
