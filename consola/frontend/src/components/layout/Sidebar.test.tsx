import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CuentaUsuario } from "@/components/layout/CuentaUsuario";
import { Sidebar } from "@/components/layout/Sidebar";
import { appDeRuta, gruposDeApp, hojasDeApp, rutaPrimaria } from "@/components/layout/apps-scope";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import type { AppCatalogo, RolUsuario } from "@/types";

/** Catálogo de prueba: tres apps con su nav (espejo de los manifests). */
const CATALOGO = {
  apps: [
    {
      id: "produccion",
      etiqueta: "Producción",
      icono: "Sparkles",
      descripcion: "Copy, clips, skills y verificación",
      permisos: ["editor", "admin"],
      rutas_frontend: ["/generacion", "/investigacion", "/revision", "/skills", "/actividad"],
      nav: [
        { ruta: "/generacion", etiqueta: "Generación", icono: "Sparkles", descripcion: "", grupo: "dia", grupo_orden: 20, orden: 10 },
        { ruta: "/investigacion", etiqueta: "Investigación", icono: "Search", descripcion: "", grupo: "dia", grupo_orden: 20, orden: 20 },
        { ruta: "/revision", etiqueta: "Revisión", icono: "ShieldCheck", descripcion: "", grupo: "dia", grupo_orden: 20, orden: 30 },
        { ruta: "/skills", etiqueta: "Skills", icono: "Wand2", descripcion: "", grupo: "operacion", grupo_orden: 30, orden: 30 },
        { ruta: "/actividad", etiqueta: "Actividad IA", icono: "Activity", descripcion: "", grupo: "operacion", grupo_orden: 30, orden: 40 },
      ],
    },
    {
      id: "metricas",
      etiqueta: "Métricas",
      icono: "BarChart3",
      descripcion: "Analíticas y comercial",
      permisos: ["editor", "admin"],
      rutas_frontend: ["/analiticas"],
      nav: [
        { ruta: "/analiticas", etiqueta: "Analíticas", icono: "BarChart3", descripcion: "", grupo: "x", grupo_orden: 10, orden: 10 },
      ],
    },
    {
      id: "operacion",
      etiqueta: "Operación",
      icono: "Send",
      descripcion: "Rota, parrilla y publicación",
      permisos: ["editor", "admin"],
      rutas_frontend: ["/publicaciones", "/parrilla"],
      nav: [
        { ruta: "/publicaciones", etiqueta: "Publicaciones", icono: "Send", descripcion: "", grupo: "operacion", grupo_orden: 30, orden: 10 },
        { ruta: "/parrilla", etiqueta: "Parrilla", icono: "CalendarClock", descripcion: "", grupo: "operacion", grupo_orden: 30, orden: 20 },
      ],
    },
  ],
  navegacion: [],
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
 * localStorage de juguete (jsdom no siempre expone `clear`). Aísla el conjunto
 * de apps abiertas (acordeón multi-abierto, persistido) entre tests.
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
    iniciarSesion: async () => {},
    cerrarSesion: async () => {},
    refrescar: async () => {},
  };
}

/** Sonda que pinta el path actual, para verificar la navegación al hacer clic. */
function PathActual() {
  return <div data-testid="path">{useLocation().pathname}</div>;
}

/**
 * Render del sidebar con sesión simulada y en una ruta dada. El Sidebar es
 * data-driven (hidrata de `/api/catalogo`) y AHORA es un acordeón de apps: cada
 * app es un item padre colapsable; la app de la ruta actual se abre sola.
 */
function renderSidebar(
  rol: RolUsuario,
  ruta = "/generacion",
  props: { colapsado?: boolean; onToggleColapsar?: () => void } = {},
) {
  stubCatalogo();
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <SesionContexto.Provider value={valorSesion(rol)}>
        <MemoryRouter initialEntries={[ruta]}>
          <Routes>
            <Route path="*" element={<Sidebar {...props} />} />
          </Routes>
          <PathActual />
        </MemoryRouter>
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

describe("Sidebar · acordeón de apps", () => {
  it("muestra Panel global (arriba) y las 3 apps como padres colapsables, sin ⊞ Apps", async () => {
    renderSidebar("editor", "/generacion");
    // Panel: entrada global fija, lleva a /panel.
    const panel = await screen.findByRole("link", { name: /^panel$/i });
    expect(panel).toHaveAttribute("href", "/panel");
    // Las 3 apps como BOTONES padres (no enlaces): colapsables.
    expect(await screen.findByRole("button", { name: /producción/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /métricas/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /operación/i })).toBeInTheDocument();
    // Ya NO hay control "⊞ Apps" (no hay launcher al que volver).
    expect(screen.queryByRole("link", { name: /^apps$/i })).not.toBeInTheDocument();
  });

  it("la app de la ruta actual se abre automáticamente y expande sus HOJAS planas (sin nivel-hub)", async () => {
    renderSidebar("editor", "/generacion");
    // Producción está abierta: se ven sus hojas planas (nivel 2 directo).
    expect(await screen.findByRole("link", { name: /generación/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /skills/i })).toBeInTheDocument();
    // NO hay nivel-hub: "Investigación" y "Revisión" desaparecen como entrada;
    // se aplanan a sus sub-pestañas como hojas directas.
    expect(screen.queryByRole("link", { name: /^investigación$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^revisión$/i })).not.toBeInTheDocument();
    // Las sub-pestañas del hub Investigación son ahora hojas directas.
    expect(screen.getByRole("link", { name: /fuentes/i })).toHaveAttribute("href", "/investigacion/fuentes");
    expect(screen.getByRole("link", { name: /termómetro/i })).toBeInTheDocument();
    // Las del hub Revisión también (Editorial, Verificación).
    expect(screen.getByRole("link", { name: /editorial/i })).toHaveAttribute("href", "/revision/editorial");
    expect(screen.getByRole("link", { name: /verificación/i })).toHaveAttribute("href", "/revision/verificacion");
    // Actividad IA es una hoja directa (ya no es un hub con sub-pestañas).
    expect(screen.getByRole("link", { name: /actividad ia/i })).toHaveAttribute("href", "/actividad");
    // Las OTRAS apps están cerradas: no se ven sus hojas.
    expect(screen.queryByRole("link", { name: /publicaciones/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^métricas$/i })).not.toBeInTheDocument();
  });

  it("acordeón PERMISIVO: al abrir otra app NO se cierra la actual (multi-abierto)", async () => {
    renderSidebar("editor", "/generacion");
    // Producción abierta de inicio (app de la ruta actual).
    await screen.findByRole("link", { name: /generación/i });
    // Abre Operación: se ven SUS hojas y SIGUEN viéndose las de Producción.
    fireEvent.click(screen.getByRole("button", { name: /operación/i }));
    expect(await screen.findByRole("link", { name: /publicaciones/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /generación/i })).toBeInTheDocument();
  });

  it("alterna el padre: un 2º clic en una app abierta la cierra (sin tocar las demás)", async () => {
    renderSidebar("editor", "/generacion");
    fireEvent.click(await screen.findByRole("button", { name: /operación/i }));
    expect(await screen.findByRole("link", { name: /publicaciones/i })).toBeInTheDocument();
    // Cierra Operación: desaparecen sus hojas; Producción sigue abierta.
    fireEvent.click(screen.getByRole("button", { name: /operación/i }));
    expect(screen.queryByRole("link", { name: /publicaciones/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /generación/i })).toBeInTheDocument();
  });

  it("persiste el conjunto de apps abiertas en localStorage", async () => {
    renderSidebar("editor", "/generacion");
    fireEvent.click(await screen.findByRole("button", { name: /operación/i }));
    await screen.findByRole("link", { name: /publicaciones/i });
    await waitFor(() => {
      const guardado = JSON.parse(localStorage.getItem("keni:sidebar-apps-abiertas") ?? "[]");
      expect(guardado).toEqual(expect.arrayContaining(["produccion", "operacion"]));
    });
  });

  it("rehidrata el conjunto de apps abiertas desde localStorage", async () => {
    // Operación quedó abierta de una sesión previa, aunque la ruta sea /panel.
    localStorage.setItem("keni:sidebar-apps-abiertas", JSON.stringify(["operacion"]));
    renderSidebar("editor", "/panel");
    expect(await screen.findByRole("link", { name: /publicaciones/i })).toBeInTheDocument();
  });

  it("las HOJAS van en TEXTO (sin icono) y la activa marca acento a la izquierda", async () => {
    renderSidebar("editor", "/generacion");
    const hoja = await screen.findByRole("link", { name: /generación/i });
    // La hoja activa lleva la barra/acento de marca a la izquierda (border-l-2 + border-keni).
    expect(hoja.className).toContain("border-l-2");
    expect(hoja.className).toContain("border-keni");
    // Sin icono en la hoja: ningún <svg> dentro del enlace.
    expect(hoja.querySelector("svg")).toBeNull();
    // Una hoja inactiva tampoco lleva icono.
    const inactiva = screen.getByRole("link", { name: /skills/i });
    expect(inactiva.querySelector("svg")).toBeNull();
  });

  it("muestra un trigger de paleta (Buscar… + ⌘K) en vez del input falso 'F'", async () => {
    renderSidebar("editor", "/generacion");
    // Es un BOTÓN que abre la paleta, no un input de texto muerto.
    const trigger = await screen.findByRole("button", { name: /buscar páginas/i });
    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveTextContent("⌘K");
    // Ya no hay input de búsqueda ni el atajo "F".
    expect(screen.queryByRole("textbox", { name: /buscar/i })).not.toBeInTheDocument();
  });

  it("el título de la app NO es click muerto: navega a su 1ª hoja y abre su acordeón", async () => {
    renderSidebar("editor", "/panel");
    // Desde /panel, click en Métricas debe navegar a su 1ª HOJA aplanada
    // (Analíticas es un hub → /analiticas/metricas, NO /analiticas).
    fireEvent.click(await screen.findByRole("button", { name: /métricas/i }));
    await waitFor(() => expect(screen.getByTestId("path")).toHaveTextContent("/analiticas/metricas"));
    // Y su acordeón queda abierto: se ven sus hojas (Métricas, Comercial…).
    expect(screen.getByRole("link", { name: /comercial/i })).toHaveAttribute("href", "/analiticas/comercial");
  });

  it("no pone encabezados de sección: el nombre de la app ya nombra el grupo", async () => {
    const { container } = renderSidebar("editor", "/generacion");
    await screen.findByRole("link", { name: /generación/i });
    // El nombre del bloque del manifest ("dia", "operacion") NO se pinta como
    // encabezado de sección; el único agrupador es el botón padre de la app.
    expect(screen.queryByText(/^dia$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^operacion$/i)).not.toBeInTheDocument();
    // No hay <p> con estilo de encabezado de sección (uppercase tracking-wider).
    expect(container.querySelector("p.uppercase")).toBeNull();
  });

  it("en `/panel` ninguna app se abre sola (Panel global activo)", async () => {
    renderSidebar("editor", "/panel");
    const panel = await screen.findByRole("link", { name: /^panel$/i });
    expect(panel).toHaveAttribute("href", "/panel");
    // Apps presentes como padres, pero cerradas: sin secciones visibles.
    expect(await screen.findByRole("button", { name: /producción/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /generación/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /publicaciones/i })).not.toBeInTheDocument();
  });

  it("no muestra los ajustes en el sidebar (cuelgan del avatar)", async () => {
    renderSidebar("admin", "/generacion");
    await screen.findByRole("link", { name: /generación/i });
    expect(screen.queryByRole("link", { name: /^configuración$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^usuarios$/i })).not.toBeInTheDocument();
  });
});

describe("Sidebar · rail colapsable", () => {
  it("colapsado muestra solo iconos (Panel + apps) y un botón para expandir", async () => {
    renderSidebar("editor", "/generacion", { colapsado: true, onToggleColapsar: () => {} });
    // Panel sigue accesible como enlace de icono.
    expect(await screen.findByRole("link", { name: /^panel$/i })).toHaveAttribute("href", "/panel");
    // Las apps son botones de icono (tooltip = aria-label con el nombre).
    expect(await screen.findByRole("button", { name: /producción/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /métricas/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /operación/i })).toBeInTheDocument();
    // Botón para volver a expandir la barra.
    expect(screen.getByRole("button", { name: /expandir barra/i })).toBeInTheDocument();
    // En rail no hay secciones expandidas (solo iconos).
    expect(screen.queryByRole("link", { name: /generación/i })).not.toBeInTheDocument();
  });

  it("el toggle (« colapsar / » expandir) invoca onToggleColapsar", async () => {
    const onToggle = vi.fn();
    // Expandida: botón "Colapsar".
    const { unmount } = renderSidebar("editor", "/generacion", {
      colapsado: false,
      onToggleColapsar: onToggle,
    });
    fireEvent.click(await screen.findByRole("button", { name: /colapsar/i }));
    expect(onToggle).toHaveBeenCalledTimes(1);
    unmount();
    // Colapsada: botón "Expandir barra".
    renderSidebar("editor", "/generacion", { colapsado: true, onToggleColapsar: onToggle });
    fireEvent.click(await screen.findByRole("button", { name: /expandir barra/i }));
    expect(onToggle).toHaveBeenCalledTimes(2);
  });

  it("click en el icono de una app (en rail) expande la barra y navega a su ruta primaria", async () => {
    const onToggle = vi.fn();
    renderSidebar("editor", "/panel", { colapsado: true, onToggleColapsar: onToggle });
    fireEvent.click(await screen.findByRole("button", { name: /operación/i }));
    // Re-expande la barra…
    expect(onToggle).toHaveBeenCalledTimes(1);
    // …y navega a la ruta primaria de Operación.
    await waitFor(() => expect(screen.getByTestId("path")).toHaveTextContent("/publicaciones"));
  });
});

describe("apps-scope · helpers", () => {
  const apps = CATALOGO.apps as AppCatalogo[];

  it("rutaPrimaria es la PRIMERA HOJA (aplana hubs a su 1ª sub-pestaña)", () => {
    // Producción: 1ª entrada /generacion no es hub → se queda igual.
    expect(rutaPrimaria(apps[0])).toBe("/generacion");
    // Métricas: 1ª entrada /analiticas ES hub → resuelve a su 1ª sub-pestaña.
    expect(rutaPrimaria(apps[1])).toBe("/analiticas/metricas");
    // Operación: 1ª entrada /publicaciones no es hub → se queda igual.
    expect(rutaPrimaria(apps[2])).toBe("/publicaciones");
  });

  it("hojasDeApp aplana hubs a sub-pestañas y conserva las no-hub", () => {
    const hojas = hojasDeApp(apps[0]).map((h) => h.ruta);
    expect(hojas).toEqual([
      "/generacion",
      // /investigacion (hub) → sus 4 sub-pestañas
      "/investigacion/fuentes",
      "/investigacion/termometro",
      "/investigacion/radar",
      "/investigacion/algoritmos",
      // /revision (hub) → sus 2 sub-pestañas
      "/revision/editorial",
      "/revision/verificacion",
      "/skills",
      // /actividad NO es hub: queda como hoja directa.
      "/actividad",
    ]);
  });

  it("appDeRuta resuelve por prefijo más largo", () => {
    expect(appDeRuta(apps, "/generacion")?.id).toBe("produccion");
    expect(appDeRuta(apps, "/parrilla/calendario")?.id).toBe("operacion");
    // Fuera de toda app (raíz / shell): undefined.
    expect(appDeRuta(apps, "/")).toBeUndefined();
    expect(appDeRuta(apps, "/panel")).toBeUndefined();
  });

  it("gruposDeApp respeta los bloques visuales por orden", () => {
    const grupos = gruposDeApp(apps[0]);
    const rutas = grupos.flatMap((g) => g.items.map((i) => i.ruta));
    expect(rutas).toEqual(["/generacion", "/investigacion", "/revision", "/skills", "/actividad"]);
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
