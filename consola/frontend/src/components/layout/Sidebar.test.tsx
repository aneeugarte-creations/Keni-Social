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
 * `apps-scope` (paleta de comandos) que siguen consumiéndolo.
 */
const CATALOGO = {
  apps: [
    {
      id: "produccion",
      etiqueta: "Producción",
      icono: "Sparkles",
      descripcion: "Copy, clips, imágenes y verificación",
      permisos: ["editor", "admin"],
      rutas_frontend: ["/publicaciones/imagen", "/maquina/investigacion", "/maquina/computo"],
      nav: [
        { ruta: "/publicaciones/imagen", etiqueta: "Imagen", icono: "Palette", descripcion: "", grupo: "contenido", grupo_orden: 20, orden: 10 },
        { ruta: "/publicaciones/texto", etiqueta: "Texto", icono: "Library", descripcion: "", grupo: "contenido", grupo_orden: 20, orden: 20 },
        // Bloque «Máquina»: dos cockpits (los agentes IA) + el hub de la sala de máquinas («Agentes»).
        { ruta: "/maquina/investigacion", etiqueta: "Investigación", icono: "Search", descripcion: "", grupo: "maquina", grupo_orden: 25, orden: 10 },
        { ruta: "/maquina/produccion", etiqueta: "Producción", icono: "Wand2", descripcion: "", grupo: "maquina", grupo_orden: 25, orden: 20 },
        { ruta: "/maquina/computo", etiqueta: "Agentes", icono: "Bot", descripcion: "", grupo: "maquina", grupo_orden: 25, orden: 30 },
      ],
    },
    {
      id: "metricas",
      etiqueta: "Analíticas",
      icono: "BarChart3",
      descripcion: "Métricas, campañas y reportes",
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
      rutas_frontend: ["/operacion/feed", "/operacion/programacion", "/operacion/turnos"],
      nav: [
        { ruta: "/operacion/feed", etiqueta: "Feed", icono: "LayoutGrid", descripcion: "", grupo: "operacion", grupo_orden: 10, orden: 20 },
        { ruta: "/operacion/programacion", etiqueta: "Programación", icono: "CalendarDays", descripcion: "", grupo: "operacion", grupo_orden: 10, orden: 25 },
        { ruta: "/operacion/turnos", etiqueta: "Turnos", icono: "CalendarClock", descripcion: "", grupo: "operacion", grupo_orden: 10, orden: 28 },
      ],
    },
  ],
  // Bloques de flujo tal como los entrega el backend (`entradas_nav_activas`):
  // Feed (red social interna) encabeza "Operación", seguido de Programación y Turnos (páginas
  // planas). Los hubs que quedan van como UNA entrada (su sub-nav es in-page). El bloque vive
  // también en el path.
  navegacion: [
    {
      etiqueta: "Operación",
      items: [
        { ruta: "/operacion/feed", etiqueta: "Feed", icono: "LayoutGrid", descripcion: "Feed del equipo" },
        { ruta: "/operacion/programacion", etiqueta: "Programación", icono: "CalendarDays", descripcion: "Calendario de piezas" },
        { ruta: "/operacion/turnos", etiqueta: "Turnos", icono: "CalendarClock", descripcion: "Rota de cobertura" },
      ],
    },
    {
      etiqueta: "Publicacion",
      items: [
        { ruta: "/publicaciones/imagen", etiqueta: "Imagen", icono: "Palette", descripcion: "Lienzo de imagen" },
        { ruta: "/publicaciones/texto", etiqueta: "Texto", icono: "Library", descripcion: "Prompts, editorial y plantillas" },
      ],
    },
    {
      etiqueta: "Máquina",
      items: [
        { ruta: "/maquina/investigacion", etiqueta: "Investigación", icono: "Search", descripcion: "Cockpit de investigación" },
        { ruta: "/maquina/produccion", etiqueta: "Producción", icono: "Wand2", descripcion: "Cockpit de producción" },
        { ruta: "/maquina/computo", etiqueta: "Agentes", icono: "Bot", descripcion: "Cómputo, economía y actividad" },
      ],
    },
    {
      etiqueta: "Datos",
      items: [
        // Tras la consolidación de nav, «Datos» queda solo con Analíticas (la medición que cierra
        // el loop). Investigación vive en su cockpit y el feed de Producción, en Agentes.
        { ruta: "/datos/analiticas", etiqueta: "Analíticas", icono: "BarChart3", descripcion: "Medición" },
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

function valorSesion(rol: RolUsuario, esSuperadmin = false): ValorSesion {
  return {
    usuario: { id: "u1", usuario: "x", rol, debe_cambiar_password: false, es_superadmin: esSuperadmin },
    cargando: false,
    errorConexion: false,
    iniciarSesion: async () => ({ mfaRequerido: false }),
    verificarConPasskey: async () => {},
  entrarConPasskey: async () => {},
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
function renderAvatarMenu(rol: RolUsuario, esSuperadmin = false) {
  return render(
    <SesionContexto.Provider value={valorSesion(rol, esSuperadmin)}>
      <MemoryRouter>
        <CuentaUsuario />
      </MemoryRouter>
    </SesionContexto.Provider>,
  );
}

describe("Sidebar · bloques de flujo", () => {
  it("pinta los bloques de flujo con su encabezado", async () => {
    renderSidebar("editor", "/operacion/feed");
    expect(await screen.findByText("Operación")).toBeInTheDocument();
    expect(screen.getByText("Publicacion")).toBeInTheDocument();
    expect(screen.getByText("Máquina")).toBeInTheDocument();
    expect(screen.getByText("Datos")).toBeInTheDocument();
  });

  it("Programación y Turnos se ven en cualquier marca (ambas son por marca, sin gating)", async () => {
    // Ambas son por marca: cada marca ve su Programación y sus Turnos.
    renderSidebar("editor", "/operacion/feed", {}, "unotv");
    expect(await screen.findByRole("link", { name: /programación/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /turnos/i })).toBeInTheDocument();
  });

  it("cada entrada es un enlace; los hubs van como UNA sola entrada (sin hojas sueltas)", async () => {
    renderSidebar("editor", "/operacion/feed");
    // Bloque "Operación": Feed, Programación y Turnos, los checkpoints diarios.
    expect(await screen.findByRole("link", { name: /feed/i })).toHaveAttribute("href", "/operacion/feed");
    expect(screen.getByRole("link", { name: /programación/i })).toHaveAttribute("href", "/operacion/programacion");
    expect(screen.getByRole("link", { name: /turnos/i })).toHaveAttribute("href", "/operacion/turnos");
    // Bloque "Publicacion".
    expect(screen.getByRole("link", { name: /imagen/i })).toHaveAttribute("href", "/publicaciones/imagen");
    expect(screen.getByRole("link", { name: /texto/i })).toHaveAttribute("href", "/publicaciones/texto");
    // Bloque "Máquina": dos cockpits (los agentes IA) + el hub de la sala de máquinas («Agentes»).
    expect(screen.getByRole("link", { name: /investigación/i })).toHaveAttribute("href", "/maquina/investigacion");
    expect(screen.getByRole("link", { name: /producción/i })).toHaveAttribute("href", "/maquina/produccion");
    expect(screen.getByRole("link", { name: /agentes/i })).toHaveAttribute("href", "/maquina/computo");
    // Bloque "Datos": solo Analíticas.
    expect(screen.getByRole("link", { name: /analíticas/i })).toHaveAttribute("href", "/datos/analiticas");
    // Las pestañas internas de un hub NO viven en el sidebar (van in-page).
    expect(screen.queryByRole("link", { name: /^fuentes$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^termómetro$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^editorial$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^comercial$/i })).not.toBeInTheDocument();
  });

  it("marca activa la entrada del hub aun estando en una de sus sub-rutas", async () => {
    // Analíticas sigue siendo un hub del bloque «Datos» (Métricas/Campañas como sub-rutas).
    renderSidebar("editor", "/datos/analiticas/metricas");
    const analiticas = await screen.findByRole("link", { name: /analíticas/i });
    // NavLink marca `aria-current=page` por prefijo (/datos/analiticas ⊇ …/metricas).
    expect(analiticas).toHaveAttribute("aria-current", "page");
    // Y una entrada de otro bloque NO está activa.
    expect(screen.getByRole("link", { name: /imagen/i })).not.toHaveAttribute("aria-current");
  });

  it("las entradas llevan icono (no son texto plano)", async () => {
    renderSidebar("editor", "/operacion/feed");
    const feed = await screen.findByRole("link", { name: /feed/i });
    expect(feed.querySelector("svg")).not.toBeNull();
  });

  it("no muestra un buscador en el sidebar", async () => {
    renderSidebar("editor", "/operacion/feed");
    await screen.findByRole("link", { name: /feed/i });
    expect(screen.queryByRole("button", { name: /buscar páginas/i })).not.toBeInTheDocument();
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
    expect(screen.getByRole("link", { name: /investigación/i })).toHaveAttribute("href", "/maquina/investigacion");
    // Botón para volver a expandir la barra.
    expect(screen.getByRole("button", { name: /expandir barra/i })).toBeInTheDocument();
    // En rail no se pintan los encabezados de bloque (solo iconos).
    expect(screen.queryByText("Publicacion")).not.toBeInTheDocument();
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
    // Producción: 1ª entrada /contenido/imagen no es hub → se queda igual.
    expect(rutaPrimaria(apps[0])).toBe("/publicaciones/imagen");
    // Métricas: 1ª entrada /datos/analiticas ES hub → resuelve a su 1ª sub-pestaña.
    expect(rutaPrimaria(apps[1])).toBe("/datos/analiticas/metricas");
    // Operación: 1ª entrada /operacion/feed ES hub → resuelve a su 1ª sub-pestaña.
    expect(rutaPrimaria(apps[2])).toBe("/operacion/feed/feed");
  });

  it("hojasDeApp aplana hubs a sub-pestañas y conserva las no-hub", () => {
    const hojas = hojasDeApp(apps[0]).map((h) => h.ruta);
    expect(hojas).toEqual([
      "/publicaciones/imagen",
      // /contenido/texto (hub) → sus sub-pestañas
      "/publicaciones/texto/documentos",
      "/publicaciones/texto/estrategia",
      // Bloque «Máquina»: los cockpits Investigación/Producción son páginas planas; Cómputo es la
      // entrada del hub «sala de máquinas» → se aplana a sus pestañas (Cómputo/Economía/Actividad).
      "/maquina/investigacion",
      "/maquina/produccion",
      "/maquina/computo",
      "/maquina/economia",
      "/maquina/actividad",
    ]);
  });

  it("appDeRuta resuelve por prefijo más largo", () => {
    expect(appDeRuta(apps, "/publicaciones/imagen")?.id).toBe("produccion");
    expect(appDeRuta(apps, "/operacion/turnos")?.id).toBe("operacion");
    // Fuera de toda app (raíz / shell): undefined.
    expect(appDeRuta(apps, "/")).toBeUndefined();
    expect(appDeRuta(apps, "/configuracion")).toBeUndefined();
  });

  it("gruposDeApp respeta los bloques visuales por orden", () => {
    const grupos = gruposDeApp(apps[0]);
    const rutas = grupos.flatMap((g) => g.items.map((i) => i.ruta));
    // Ordenado por (grupo_orden, orden): contenido(20: /imagen,/texto) · maquina(25: /investigacion,
    // /produccion, /computo). Producción ya no aporta entradas a "operacion" ni a "datos".
    expect(rutas).toEqual([
      "/publicaciones/imagen",
      "/publicaciones/texto",
      "/maquina/investigacion",
      "/maquina/produccion",
      "/maquina/computo",
    ]);
  });
});

describe("Avatar · visibilidad de Usuarios por rol", () => {
  it("muestra 'Usuarios' al abrir el menú cuando es superadmin", () => {
    renderAvatarMenu("admin", true);
    fireEvent.click(screen.getByRole("button", { name: /x.*administrador/i }));
    expect(screen.getByRole("menuitem", { name: /usuarios/i })).toBeInTheDocument();
  });

  it("oculta 'Usuarios' del menú a un admin normal (sin superadmin)", () => {
    renderAvatarMenu("admin");
    fireEvent.click(screen.getByRole("button", { name: /x.*administrador/i }));
    expect(screen.queryByRole("menuitem", { name: /usuarios/i })).not.toBeInTheDocument();
  });

  it("oculta 'Usuarios' del menú cuando el rol es editor", () => {
    renderAvatarMenu("editor");
    fireEvent.click(screen.getByRole("button", { name: /x.*editor/i }));
    expect(screen.queryByRole("menuitem", { name: /usuarios/i })).not.toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /mi cuenta/i })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /configuración/i })).not.toBeInTheDocument();
  });
});
