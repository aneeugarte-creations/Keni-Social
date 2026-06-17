import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import type { UsuarioSesion } from "@/types";

import MobileFeed from "./MobileFeed";

const OPCIONES = {
  redes: [{ id: "x", nombre: "X" }],
  estados: [
    { id: "en_revision", nombre: "En revisión" },
    { id: "aprobado", nombre: "Aprobado" },
  ],
  marcas: [
    { id: "unotv", nombre: "Uno TV" },
    { id: "claro-sports", nombre: "Claro Sports" },
  ],
};

const PIEZA = {
  id: "p1",
  publicacion_id: "c1",
  pipeline_id: "",
  titulo: "Gol de último minuto",
  marca: "unotv",
  marca_nombre: "Uno TV",
  red: "x",
  red_nombre: "X",
  contenido: "¡Increíble remontada!",
  copy_in: "",
  estado: "en_revision",
  revision: "",
  autor_id: "u9",
  autor_nombre: "Yustine",
  responsable_id: "",
  responsable_nombre: "",
  enviado_a_revision_en: "",
  revisor_id: "",
  revisor_nombre: "",
  revisado_en: "",
  preparado_en: "",
  id_post_metricool: "",
  tipo_contenido: "",
  formato: "foto",
  imagen_fuente: "",
  foto: "",
  falta_copy: false,
  falta_imagen: false,
  falta_revision: false,
  falta_publicar: false,
  falta_video: false,
  video: "",
  fecha_creacion: "",
  fecha_actualizacion: "",
  fecha_programada: "",
  fecha_fuente: "",
  fuente_original: "",
  origen: "",
  categoria: "",
  imagen: "",
  imagen_url: "",
  evergreen: false,
  // Etapa real del backend (Flujo C): coherente con estado 'en_revision'.
  etapa_ia: "lista_para_revisar",
};

/** Stub de fetch: enruta opciones, cadenas (lote e individual), comentarios y el listado. */
function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL) => {
      const ruta = String(url);
      if (ruta.includes("/api/piezas/opciones")) {
        return new Response(JSON.stringify(OPCIONES), { status: 200 });
      }
      if (ruta.includes("/api/piezas/cadenas")) {
        // Lote vacío: cada PostFeed cae a su query individual (/aprobacion).
        return new Response(JSON.stringify({ cadenas: {} }), { status: 200 });
      }
      if (ruta.includes("/aprobacion")) {
        return new Response(
          JSON.stringify({ niveles: [], estado: "sin_cadena", nivel_actual: "", aprobados: 0, minimo_aprobaciones: 0, comentarios_sin_resolver: 0 }),
          { status: 200 },
        );
      }
      if (ruta.includes("/comentarios")) {
        return new Response(JSON.stringify({ comentarios: [], total: 0 }), { status: 200 });
      }
      if (ruta.includes("/api/piezas")) {
        return new Response(
          JSON.stringify({
            piezas: [PIEZA],
            paginacion: { total: 1, limite: 50, desplazamiento: 0 },
          }),
          { status: 200 },
        );
      }
      return new Response("{}", { status: 200 });
    }),
  );
}

function sesion(usuario: Partial<UsuarioSesion> = {}): ValorSesion {
  return {
    usuario: {
      id: "u1",
      usuario: "revisor",
      rol: "editor",
      debe_cambiar_password: false,
      marcas: ["unotv"],
      ...usuario,
    } as UsuarioSesion,
    cargando: false,
    iniciarSesion: vi.fn(),
    verificarConPasskey: vi.fn(),
    verificarConCodigo: vi.fn(),
    cerrarSesion: vi.fn(),
    refrescar: vi.fn(),
  };
}

function arbol(valor: ValorSesion, client: QueryClient, ruta = "/") {
  return (
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={valor}>
        <MemoryRouter initialEntries={[ruta]}>
          <MobileFeed />
        </MemoryRouter>
      </SesionContexto.Provider>
    </QueryClientProvider>
  );
}

function renderFeed(usuario: Partial<UsuarioSesion> = {}, ruta = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(arbol(sesion(usuario), client, ruta));
}

describe("MobileFeed · feed móvil de revisión", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("muestra la cabecera compacta, las MISMAS 3 vistas del escritorio y el botón de crear", async () => {
    stubFetch();
    renderFeed();
    // El título queda solo para lectores de pantalla (sr-only): la cabecera no gasta una fila.
    expect(await screen.findByText("Feed de revisión")).toBeInTheDocument();
    // La partición compartida (vistas.tsx): el móvil ya no es una superficie capada con 2
    // bandejas; mismo vocabulario y ORDEN que el escritorio (Pendientes · Publicadas · Todas).
    // Por defecto manda "Pendientes". «Portal» no es vista del feed (es un clon, solo escritorio).
    const pestanas = screen.getAllByRole("tab");
    expect(pestanas).toHaveLength(3);
    expect(pestanas.map((t) => t.textContent)).toEqual([
      expect.stringContaining("Pendientes"),
      expect.stringContaining("Publicadas"),
      expect.stringContaining("Todas"),
    ]);
    expect(screen.queryByRole("tab", { name: /Portal/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /En preparación/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /Por aprobar/ })).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Pendientes/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    // El feed se auto-refresca (refetchInterval de la vista): ya no hay botón manual de recarga.
    expect(screen.queryByRole("button", { name: "Actualizar" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /crear pieza/i })).toBeInTheDocument();
    // Con UNA sola marca asignada el selector de marca no es una decisión: no se pinta.
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("con varias marcas asignadas SÍ muestra el selector de marca", async () => {
    stubFetch();
    renderFeed({ marcas: ["unotv", "claro-sports"] });
    await screen.findByText("Feed de revisión");
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });

  it("renderiza la pieza como PostFeed (mismas acciones que el feed de escritorio)", async () => {
    stubFetch();
    renderFeed();
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    // La tarjeta es el MISMO PostFeed del escritorio: like/dislike (la pieza está en revisión)
    // y comentar; nada de los botones planos Aprobar/Rechazar sin gates. El nombre accesible
    // del like deriva del estado real (aquí la cadena no da turno: "no disponible").
    expect(screen.getByRole("button", { name: "Me gusta: no disponible" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "No me gusta" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Comentar" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^aprobar$/i })).not.toBeInTheDocument();
  });

  it("el imán Reels vive en el SCROLLER propio de la pantalla, con geometría MEDIDA", async () => {
    // El CSS global bloquea el scroll de html/body (anti rubber-band iOS): un snap puesto
    // en el documento es INERTE (así se perdió el imán del feed). Contrato: el div raíz
    // del feed es el scroller (un viewport de alto, scroll interno) y lleva el snap
    // obligatorio + scroll-padding con la altura REAL de la cabecera (variable CSS escrita
    // por ResizeObserver; aquí en jsdom valen los fallbacks del style).
    stubFetch();
    renderFeed();
    const titulo = await screen.findByText("Feed de revisión");
    const raiz = titulo.closest(".snap-y") as HTMLElement | null;
    expect(raiz).not.toBeNull();
    expect(raiz!.className).toContain("snap-mandatory");
    expect(raiz!.className).toContain("h-dvh");
    expect(raiz!.className).toContain("overflow-y-auto");
    expect(raiz!.style.scrollPaddingTop).toBe("var(--feed-top)");
    expect(raiz!.style.getPropertyValue("--feed-top")).toBe("6rem");
    expect(raiz!.style.getPropertyValue("--feed-bottom")).toBe("4.5rem");
    // El documento queda intacto (ya no hay estilos que poner/revertir ahí).
    expect(document.documentElement.style.scrollSnapType).toBe("");
  });

  it("cada pieza vive en un slot de un viewport MEDIDO (sin franja ocluida) y operable por teclado", async () => {
    stubFetch();
    renderFeed();
    const post = await screen.findByText("¡Increíble remontada!");
    const slot = post.closest(".snap-start");
    expect(slot).not.toBeNull();
    expect(slot!.className).toContain("snap-always");
    // Alto = viewport menos cabecera y barra inferior REALES (variables medidas): la fila de
    // acciones nunca scrollea hacia la zona tapada por la barra fija "Crear pieza".
    expect(slot!.className).toContain("h-[calc(100dvh-var(--feed-top)-var(--feed-bottom))]");
    expect(slot!.className).toContain("overflow-y-auto");
    // El scroll INTERNO del slot es operable por teclado (WCAG 2.1.1) y se anuncia con nombre.
    expect(slot).toHaveAttribute("tabindex", "0");
    expect(slot).toHaveAttribute("role", "group");
    expect(slot).toHaveAttribute("aria-label", "Gol de último minuto");
  });

  it("feed agotado con piezas: pinta el fin del feed", async () => {
    stubFetch(); // 1 pieza, sin cursor_siguiente -> no hay más páginas
    renderFeed();
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    expect(screen.getByText("Fin del feed")).toBeInTheDocument();
  });

  it("vacío HONESTO: con la página llena de otras marcas y más por traer, busca en vez de afirmar 'Nada pendiente'", async () => {
    // Usuario multi-marca (filtro en 'todas'): la página 1 trae solo piezas de una marca AJENA
    // (el filtro en cliente las descarta) y hay cursor: el feed debe seguir buscando.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) => {
        const ruta = String(url);
        if (ruta.includes("/api/piezas/opciones")) {
          return new Response(JSON.stringify(OPCIONES), { status: 200 });
        }
        if (ruta.includes("/api/piezas/cadenas")) {
          return new Response(JSON.stringify({ cadenas: {} }), { status: 200 });
        }
        if (ruta.includes("/aprobacion")) {
          return new Response(
            JSON.stringify({ niveles: [], estado: "sin_cadena", nivel_actual: "", aprobados: 0, minimo_aprobaciones: 0, comentarios_sin_resolver: 0 }),
            { status: 200 },
          );
        }
        if (ruta.includes("/api/piezas")) {
          return new Response(
            JSON.stringify({
              piezas: [{ ...PIEZA, marca: "otra-marca" }],
              paginacion: { total: 9, limite: 1, desplazamiento: 0, cursor_siguiente: "2026-01-01T00:00:00|p1" },
            }),
            { status: 200 },
          );
        }
        return new Response("{}", { status: 200 });
      }),
    );
    renderFeed({ marcas: ["unotv", "claro-sports"] });
    expect(await screen.findByText("Buscando piezas…")).toBeInTheDocument();
    expect(screen.queryByText("Nada pendiente")).not.toBeInTheDocument();
  });

  it("el alta rápida se envía con Enter (form de verdad) y el botón Crear es submit", async () => {
    const creadas: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL, init?: RequestInit) => {
        const ruta = String(url);
        if (ruta.includes("/api/publicaciones") && init?.method === "POST") {
          creadas.push(String(init.body));
          return new Response(JSON.stringify({ id: "c9" }), { status: 200 });
        }
        if (ruta.includes("/api/piezas/opciones")) {
          return new Response(JSON.stringify(OPCIONES), { status: 200 });
        }
        if (ruta.includes("/api/piezas/cadenas")) {
          return new Response(JSON.stringify({ cadenas: {} }), { status: 200 });
        }
        if (ruta.includes("/api/piezas")) {
          return new Response(
            JSON.stringify({ piezas: [], paginacion: { total: 0, limite: 50, desplazamiento: 0 } }),
            { status: 200 },
          );
        }
        return new Response("{}", { status: 200 });
      }),
    );
    renderFeed();
    fireEvent.click(await screen.findByRole("button", { name: /crear pieza/i }));
    const input = await screen.findByLabelText("Título");
    fireEvent.change(input, { target: { value: "Idea desde el móvil" } });
    // Enter/«ir» del teclado móvil = submit del form (no hace falta alcanzar el botón).
    expect(screen.getByRole("button", { name: "Crear" })).toHaveAttribute("type", "submit");
    fireEvent.submit(input.closest("form") as HTMLFormElement);
    await waitFor(() => expect(creadas.length).toBe(1));
    expect(creadas[0]).toContain("Idea desde el móvil");
  });

  it("preselecciona la única marca del usuario aunque la sesión llegue DESPUÉS del mount", async () => {
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) => {
        const ruta = String(url);
        if (ruta.includes("/api/piezas/opciones")) {
          return new Response(JSON.stringify(OPCIONES), { status: 200 });
        }
        if (ruta.includes("/api/piezas/cadenas")) {
          return new Response(JSON.stringify({ cadenas: {} }), { status: 200 });
        }
        if (ruta.includes("/api/piezas")) {
          urls.push(ruta);
          return new Response(
            JSON.stringify({ piezas: [], paginacion: { total: 0, limite: 50, desplazamiento: 0 } }),
            { status: 200 },
          );
        }
        return new Response("{}", { status: 200 });
      }),
    );
    // Mount en carga fría: la sesión aún no trae marcas -> el filtro arranca en "todas".
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(arbol(sesion({ marcas: [] }), client));
    await screen.findByText("Feed de revisión");
    // La sesión aterriza con UNA marca: el filtro se preselecciona solo (sin tocar el selector),
    // y el listado pasa a pedirse acotado a esa marca (las altas rápidas ya no nacen sueltas).
    rerender(arbol(sesion({ marcas: ["unotv"] }), client));
    await waitFor(() => expect(urls.some((u) => u.includes("marca=unotv"))).toBe(true));
  });

  it("deep-link ?vista= y ?marca=: arranca en la vista y marca de la URL", async () => {
    stubFetch();
    const base = globalThis.fetch as (url: string | URL) => Promise<Response>;
    const urls: string[] = [];
    vi.stubGlobal("fetch", async (url: string | URL) => {
      urls.push(String(url));
      return base(url);
    });
    // Deep-link a una vista NO por defecto ("Publicadas") para probar que la URL manda.
    renderFeed({ marcas: ["unotv", "claro-sports"] }, "/?vista=publicado&marca=claro-sports");
    await screen.findByText("Feed de revisión");
    expect(screen.getByRole("tab", { name: /Publicadas/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    // La consulta dedicada va al servidor con el pseudo-estado de la vista Y la marca de la URL.
    await waitFor(() =>
      expect(
        urls.some((u) => u.includes("estado=publicado") && u.includes("marca=claro-sports")),
      ).toBe(true),
    );
  });

  it("el parámetro LEGADO ?bandeja=aprobado mapea a la vista 'Publicadas'", async () => {
    stubFetch();
    renderFeed({}, "/?bandeja=aprobado");
    await screen.findByText("Feed de revisión");
    // Los deep-links compartidos antes de unificar las superficies siguen aterrizando bien.
    expect(screen.getByRole("tab", { name: /Publicadas/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    // La única pieza del stub está en revisión y el feed está agotado: vacío honesto de la
    // vista, con el MISMO vocabulario que el escritorio.
    expect(await screen.findByText("Sin piezas publicadas")).toBeInTheDocument();
  });
});
