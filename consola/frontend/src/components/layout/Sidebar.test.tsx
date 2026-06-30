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
 * `apps-scope` (paleta de comandos) que siguen consumiéndolo. Las rutas con prefijo
 * de bloque (`/operacion`, `/equipo`, `/contenido`, `/maquina`, `/datos`) reflejan la
 * correspondencia 1:1 bloque↔prefijo de la app real.
 */
const CATALOGO = {
  apps: [
    {
      id: "produccion",
      etiqueta: "Producción",
      icono: "Sparkles",
      descripcion: "Copy, clips, imágenes y verificación",
      permisos: ["editor", "admin"],
      rutas_frontend: ["/contenido/imagen", "/operacion/investigacion", "/maquina/agentes"],
      nav: [
        // Investigación es trabajo cotidiano → bloque «Operación» (es un hub: Noticias/Fuentes/…).
        { ruta: "/operacion/investigacion", etiqueta: "Investigación", icono: "Search", descripcion: "", grupo: "operacion", grupo_orden: 10, orden: 10 },
        { ruta: "/contenido/imagen", etiqueta: "Imagen", icono: "Image", descripcion: "", grupo: "contenido", grupo_orden: 20, orden: 10 },
        // Bloque «Máquina»: Contexto (página plana) + Agentes (hub: Cómputo/Economía/Actividad).
        { ruta: "/maquina/contexto", etiqueta: "Contexto", icono: "Layers", descripcion: "", grupo: "maquina", grupo_orden: 25, orden: 10 },
        { ruta: "/maquina/agentes", etiqueta: "Agentes", icono: "Bot", descripcion: "", grupo: "maquina", grupo_orden: 25, orden: 30 },
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
      rutas_frontend: ["/operacion/feed", "/operacion/programa", "/equipo/trabajo", "/equipo/calendario"],
      nav: [
        { ruta: "/operacion/feed", etiqueta: "Feed", icono: "LayoutGrid", descripcion: "", grupo: "operacion", grupo_orden: 10, orden: 20 },
        { ruta: "/operacion/programa", etiqueta: "Programa", icono: "CalendarDays", descripcion: "", grupo: "operacion", grupo_orden: 10, orden: 25 },
        { ruta: "/equipo/trabajo", etiqueta: "Trabajo", icono: "ClipboardList", descripcion: "", grupo: "equipo", grupo_orden: 15, orden: 10 },
        { ruta: "/equipo/calendario", etiqueta: "Calendario", icono: "CalendarClock", descripcion: "", grupo: "equipo", grupo_orden: 15, orden: 20 },
      ],
    },
  ],
  // Bloques de flujo tal como los entrega el backend (`entradas_nav_activas`): cada bloque vive
  // también en el path (1:1). Los hubs van como UNA entrada (su sub-nav es in-page).
  navegacion: [
    {
      etiqueta: "Operación",
      items: [
        { ruta: "/operacion/investigacion", etiqueta: "Investigación", icono: "Search", descripcion: "Pool de noticias" },
        { ruta: "/operacion/feed", etiqueta: "Feed", icono: "LayoutGrid", descripcion: "Feed del equipo" },
        { ruta: "/operacion/programa", etiqueta: "Programa", icono: "CalendarDays", descripcion: "Calendario y plan" },
      ],
    },
    {
      etiqueta: "Equipo",
      items: [
        { ruta: "/equipo/trabajo", etiqueta: "Trabajo", icono: "ClipboardList", descripcion: "Eventos y cobertura" },
        { ruta: "/equipo/calendario", etiqueta: "Calendario", icono: "CalendarClock", descripcion: "Rota de turnos" },
      ],
    },
    {
      etiqueta: "Contenido",
      items: [
        { ruta: "/contenido/imagen", etiqueta: "Imagen", icono: "Image", descripcion: "Lienzo de imagen" },
      ],
    },
    {
      etiqueta: "Máquina",
      items: [
        { ruta: "/maquina/contexto", etiqueta: "Contexto", icono: "Layers", descripcion: "La máquina como estructura" },
        { ruta: "/maquina/agentes", etiqueta: "Agentes", icono: "Bot", descripcion: "Cómputo, economía y actividad" },
      ],
    },
    {
      etiqueta: "Datos",
      items: [
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
  props: { colapsado?: boolean } = {},
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
  it("agrupa la nav en bloques rotulados para a11y (sin encabezado visible), separados por un hilo", async () => {
    const { container } = renderSidebar("editor", "/operacion/feed");
    // El nombre del bloque ya no se pinta como texto: vive como rótulo accesible de cada lista.
    expect(await screen.findByRole("list", { name: "Operación" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Equipo" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Contenido" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Máquina" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Datos" })).toBeInTheDocument();
    // Y no hay texto visible de encabezado.
    expect(screen.queryByText("Operación")).not.toBeInTheDocument();
    // Cinco bloques → cuatro hilos separadores (sin hilo antes del primero).
    expect(container.querySelectorAll("nav hr").length).toBe(4);
  });

  it("Feed y Programa se ven en cualquier marca (ambos son por marca, sin gating)", async () => {
    renderSidebar("editor", "/operacion/feed", {}, "unotv");
    expect(await screen.findByRole("link", { name: /feed/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /programa/i })).toBeInTheDocument();
  });

  it("cada entrada es un enlace; los hubs van como UNA sola entrada (sin hojas sueltas)", async () => {
    renderSidebar("editor", "/operacion/feed");
    // Bloque "Operación": Investigación (hub), Feed (hub), Programa (hub).
    expect(await screen.findByRole("link", { name: /investigación/i })).toHaveAttribute("href", "/operacion/investigacion");
    expect(screen.getByRole("link", { name: /feed/i })).toHaveAttribute("href", "/operacion/feed");
    expect(screen.getByRole("link", { name: /programa/i })).toHaveAttribute("href", "/operacion/programa");
    // Bloque "Equipo".
    expect(screen.getByRole("link", { name: /trabajo/i })).toHaveAttribute("href", "/equipo/trabajo");
    expect(screen.getByRole("link", { name: /calendario/i })).toHaveAttribute("href", "/equipo/calendario");
    // Bloque "Contenido".
    expect(screen.getByRole("link", { name: /imagen/i })).toHaveAttribute("href", "/contenido/imagen");
    // Bloque "Máquina": Contexto (página plana) + Agentes (hub).
    expect(screen.getByRole("link", { name: /contexto/i })).toHaveAttribute("href", "/maquina/contexto");
    expect(screen.getByRole("link", { name: /agentes/i })).toHaveAttribute("href", "/maquina/agentes");
    // Bloque "Datos": solo Analíticas.
    expect(screen.getByRole("link", { name: /analíticas/i })).toHaveAttribute("href", "/datos/analiticas");
    // Las pestañas internas de un hub NO viven en el sidebar (van in-page).
    expect(screen.queryByRole("link", { name: /^fuentes$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^algoritmos$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^economía$/i })).not.toBeInTheDocument();
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

describe("Sidebar · rail (colapsado)", () => {
  it("colapsado muestra solo iconos (enlaces por entrada), sin botón ni encabezados de bloque", async () => {
    renderSidebar("editor", "/operacion/feed", { colapsado: true });
    // Cada entrada sigue siendo un enlace, ahora solo-icono (nombre por aria-label).
    expect(await screen.findByRole("link", { name: /feed/i })).toHaveAttribute("href", "/operacion/feed");
    expect(screen.getByRole("link", { name: /investigación/i })).toHaveAttribute("href", "/operacion/investigacion");
    // Ya no hay botón de colapsar/expandir: la barra se expande sola al hover (lo gobierna AppShell).
    expect(screen.queryByRole("button", { name: /expandir barra|colapsar/i })).not.toBeInTheDocument();
    // En rail no se pintan los encabezados de bloque (solo iconos).
    expect(screen.queryByText("Contenido")).not.toBeInTheDocument();
  });

  it("click en el icono de una entrada (en rail) navega a su ruta", async () => {
    renderSidebar("editor", "/operacion/feed", { colapsado: true });
    fireEvent.click(await screen.findByRole("link", { name: /feed/i }));
    await waitFor(() => expect(screen.getByTestId("path")).toHaveTextContent("/operacion/feed"));
  });
});

describe("apps-scope · helpers", () => {
  const apps = CATALOGO.apps as AppCatalogo[];

  it("rutaPrimaria es la PRIMERA HOJA (aplana hubs a su 1ª sub-pestaña)", () => {
    // Producción: 1ª entrada /operacion/investigacion ES hub → resuelve a su 1ª sub-pestaña.
    expect(rutaPrimaria(apps[0])).toBe("/operacion/investigacion/noticias");
    // Métricas: 1ª entrada /datos/analiticas ES hub → resuelve a su 1ª sub-pestaña.
    expect(rutaPrimaria(apps[1])).toBe("/datos/analiticas/metricas");
    // Operación: 1ª entrada /operacion/feed ES hub → resuelve a su 1ª sub-pestaña.
    expect(rutaPrimaria(apps[2])).toBe("/operacion/feed/feed");
  });

  it("hojasDeApp aplana hubs a sub-pestañas y conserva las no-hub", () => {
    const hojas = hojasDeApp(apps[0]).map((h) => h.ruta);
    expect(hojas).toEqual([
      // /operacion/investigacion (hub) → sus 4 pestañas
      "/operacion/investigacion/noticias",
      "/operacion/investigacion/fuentes",
      "/operacion/investigacion/algoritmos",
      "/operacion/investigacion/publicaciones",
      // /contenido/imagen no es hub → se queda igual
      "/contenido/imagen",
      // /maquina/contexto no es hub → se queda igual
      "/maquina/contexto",
      // /maquina/agentes (hub) → sus pestañas (Cómputo/Economía/Actividad)
      "/maquina/agentes",
      "/maquina/economia",
      "/maquina/actividad",
    ]);
  });

  it("appDeRuta resuelve por prefijo más largo", () => {
    expect(appDeRuta(apps, "/contenido/imagen")?.id).toBe("produccion");
    expect(appDeRuta(apps, "/equipo/calendario")?.id).toBe("operacion");
    // Fuera de toda app (raíz / shell): undefined.
    expect(appDeRuta(apps, "/")).toBeUndefined();
    expect(appDeRuta(apps, "/configuracion")).toBeUndefined();
  });

  it("gruposDeApp respeta los bloques visuales por orden", () => {
    const grupos = gruposDeApp(apps[0]);
    const rutas = grupos.flatMap((g) => g.items.map((i) => i.ruta));
    // Ordenado por (grupo_orden, orden): operacion(10: /investigacion) · contenido(20: /imagen) ·
    // maquina(25: /contexto, /agentes).
    expect(rutas).toEqual([
      "/operacion/investigacion",
      "/contenido/imagen",
      "/maquina/contexto",
      "/maquina/agentes",
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
