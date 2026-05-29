import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CuentaUsuario } from "@/components/layout/CuentaUsuario";
import { Sidebar } from "@/components/layout/Sidebar";
import { appDeRuta, gruposDeApp, rutaPrimaria } from "@/components/layout/apps-scope";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import type { AppCatalogo, RolUsuario } from "@/types";

/** Catálogo de prueba: dos apps con su nav (espejo de los manifests). */
const CATALOGO = {
  apps: [
    {
      id: "produccion",
      etiqueta: "Producción",
      icono: "Sparkles",
      descripcion: "Copy, clips, skills y verificación",
      permisos: ["editor", "admin"],
      rutas_frontend: ["/generacion", "/investigacion", "/revision", "/skills", "/agentes"],
      nav: [
        { ruta: "/generacion", etiqueta: "Generación", icono: "Sparkles", descripcion: "", grupo: "dia", grupo_orden: 20, orden: 10 },
        { ruta: "/investigacion", etiqueta: "Investigación", icono: "Search", descripcion: "", grupo: "dia", grupo_orden: 20, orden: 20 },
        { ruta: "/revision", etiqueta: "Revisión", icono: "ShieldCheck", descripcion: "", grupo: "dia", grupo_orden: 20, orden: 30 },
        { ruta: "/skills", etiqueta: "Skills", icono: "Wand2", descripcion: "", grupo: "operacion", grupo_orden: 30, orden: 30 },
        { ruta: "/agentes", etiqueta: "Agentes", icono: "Bot", descripcion: "", grupo: "operacion", grupo_orden: 30, orden: 40 },
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

/**
 * Render del sidebar con sesión simulada y en una ruta dada. El Sidebar es
 * data-driven (hidrata de `/api/catalogo`) y AHORA con scope por app: muestra solo
 * la nav de la app de la ruta actual, más el control "Apps" para volver al launcher.
 */
function renderSidebar(rol: RolUsuario, ruta = "/generacion") {
  stubCatalogo();
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <SesionContexto.Provider value={valorSesion(rol)}>
        <MemoryRouter initialEntries={[ruta]}>
          <Sidebar />
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

describe("Sidebar · scope por app", () => {
  it("dentro de una app muestra SOLO las secciones de esa app + 'Apps'", async () => {
    renderSidebar("editor", "/generacion");
    // Control para volver al launcher.
    expect(await screen.findByRole("link", { name: /apps/i })).toBeInTheDocument();
    // Secciones de Producción.
    expect(await screen.findByRole("link", { name: /generación/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /investigación/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /skills/i })).toBeInTheDocument();
    // NO se ven las secciones de otra app (Operación).
    expect(screen.queryByRole("link", { name: /publicaciones/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /parrilla/i })).not.toBeInTheDocument();
  });

  it("en otra app muestra solo la nav de ESA app", async () => {
    renderSidebar("editor", "/parrilla/calendario");
    expect(await screen.findByRole("link", { name: /publicaciones/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /parrilla/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /generación/i })).not.toBeInTheDocument();
  });

  it("en el launcher ('/') no muestra nav de ninguna app", async () => {
    renderSidebar("editor", "/");
    // El control "Apps" sigue (volver al inicio), pero no hay secciones de app.
    expect(await screen.findByRole("link", { name: /apps/i })).toBeInTheDocument();
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

describe("apps-scope · helpers", () => {
  const apps = CATALOGO.apps as AppCatalogo[];

  it("rutaPrimaria es el primer item de nav", () => {
    expect(rutaPrimaria(apps[0])).toBe("/generacion");
    expect(rutaPrimaria(apps[1])).toBe("/publicaciones");
  });

  it("appDeRuta resuelve por prefijo más largo", () => {
    expect(appDeRuta(apps, "/generacion")?.id).toBe("produccion");
    expect(appDeRuta(apps, "/parrilla/calendario")?.id).toBe("operacion");
    // Fuera de toda app (launcher / shell): undefined.
    expect(appDeRuta(apps, "/")).toBeUndefined();
    expect(appDeRuta(apps, "/panel")).toBeUndefined();
  });

  it("gruposDeApp respeta los bloques visuales por orden", () => {
    const grupos = gruposDeApp(apps[0]);
    const rutas = grupos.flatMap((g) => g.items.map((i) => i.ruta));
    expect(rutas).toEqual(["/generacion", "/investigacion", "/revision", "/skills", "/agentes"]);
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
