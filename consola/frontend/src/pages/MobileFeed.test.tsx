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

const PUBLICACION = {
  id: "p1",
  contenido_id: "c1",
  pipeline_id: "",
  titulo: "Gol de último minuto",
  marca: "unotv",
  marca_nombre: "Uno TV",
  red: "x",
  red_nombre: "X",
  contenido: "¡Increíble remontada!",
  copy_in: "",
  estado: "en_revision",
  veredicto: "",
  autor_id: "u9",
  autor_nombre: "Yustine",
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
      if (ruta.includes("/api/publicaciones/opciones")) {
        return new Response(JSON.stringify(OPCIONES), { status: 200 });
      }
      if (ruta.includes("/api/publicaciones/cadenas")) {
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
      if (ruta.includes("/api/publicaciones")) {
        return new Response(
          JSON.stringify({
            publicaciones: [PUBLICACION],
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

function arbol(valor: ValorSesion, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={valor}>
        <MemoryRouter>
          <MobileFeed />
        </MemoryRouter>
      </SesionContexto.Provider>
    </QueryClientProvider>
  );
}

function renderFeed(usuario: Partial<UsuarioSesion> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(arbol(sesion(usuario), client));
}

describe("MobileFeed · feed móvil de revisión", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("muestra la cabecera compacta, las bandejas y el botón de crear", async () => {
    stubFetch();
    renderFeed();
    // El título queda solo para lectores de pantalla (sr-only): la cabecera no gasta una fila.
    expect(await screen.findByText("Feed de revisión")).toBeInTheDocument();
    // Mismo vocabulario que el feed de escritorio: "Por aprobar" (el OK), no "Por revisar".
    expect(screen.getByRole("tab", { name: "Por aprobar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Actualizar" })).toBeInTheDocument();
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

  it("activa el scroll magnético por pieza mientras está montado y lo revierte al salir", async () => {
    stubFetch();
    const { unmount } = renderFeed();
    await screen.findByText("Feed de revisión");
    // Estilo Reels/Shorts: snap OBLIGATORIO (una pieza por pantalla, el scroll aterriza
    // encuadrado en la siguiente). Viable porque cada pieza vive en un slot de un viewport
    // (las tarjetas largas scrollean por dentro del slot).
    expect(document.documentElement.style.scrollSnapType).toBe("y mandatory");
    unmount();
    expect(document.documentElement.style.scrollSnapType).toBe("");
  });

  it("cada pieza vive en un slot de un viewport con snap obligatorio (estilo Reels)", async () => {
    stubFetch();
    renderFeed();
    const post = await screen.findByText("¡Increíble remontada!");
    const slot = post.closest(".snap-start");
    expect(slot).not.toBeNull();
    expect(slot!.className).toContain("snap-always");
    expect(slot!.className).toContain("h-[calc(100dvh-7rem)]");
    expect(slot!.className).toContain("overflow-y-auto");
  });

  it("feed agotado con piezas: pinta el fin del feed", async () => {
    stubFetch(); // 1 pieza, sin cursor_siguiente -> no hay más páginas
    renderFeed();
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    expect(screen.getByText("Has llegado al final del feed.")).toBeInTheDocument();
  });

  it("vacío HONESTO: con la página llena de otras marcas y más por traer, busca en vez de afirmar 'Nada por aprobar'", async () => {
    // Usuario multi-marca (filtro en 'todas'): la página 1 trae solo piezas de una marca AJENA
    // (el filtro en cliente las descarta) y hay cursor: el feed debe seguir buscando.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) => {
        const ruta = String(url);
        if (ruta.includes("/api/publicaciones/opciones")) {
          return new Response(JSON.stringify(OPCIONES), { status: 200 });
        }
        if (ruta.includes("/api/publicaciones/cadenas")) {
          return new Response(JSON.stringify({ cadenas: {} }), { status: 200 });
        }
        if (ruta.includes("/aprobacion")) {
          return new Response(
            JSON.stringify({ niveles: [], estado: "sin_cadena", nivel_actual: "", aprobados: 0, minimo_aprobaciones: 0, comentarios_sin_resolver: 0 }),
            { status: 200 },
          );
        }
        if (ruta.includes("/api/publicaciones")) {
          return new Response(
            JSON.stringify({
              publicaciones: [{ ...PUBLICACION, marca: "otra-marca" }],
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
    expect(screen.queryByText("Nada por aprobar")).not.toBeInTheDocument();
  });

  it("el alta rápida se envía con Enter (form de verdad) y el botón Crear es submit", async () => {
    const creadas: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL, init?: RequestInit) => {
        const ruta = String(url);
        if (ruta.includes("/api/contenido") && init?.method === "POST") {
          creadas.push(String(init.body));
          return new Response(JSON.stringify({ id: "c9" }), { status: 200 });
        }
        if (ruta.includes("/api/publicaciones/opciones")) {
          return new Response(JSON.stringify(OPCIONES), { status: 200 });
        }
        if (ruta.includes("/api/publicaciones/cadenas")) {
          return new Response(JSON.stringify({ cadenas: {} }), { status: 200 });
        }
        if (ruta.includes("/api/publicaciones")) {
          return new Response(
            JSON.stringify({ publicaciones: [], paginacion: { total: 0, limite: 50, desplazamiento: 0 } }),
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
        if (ruta.includes("/api/publicaciones/opciones")) {
          return new Response(JSON.stringify(OPCIONES), { status: 200 });
        }
        if (ruta.includes("/api/publicaciones/cadenas")) {
          return new Response(JSON.stringify({ cadenas: {} }), { status: 200 });
        }
        if (ruta.includes("/api/publicaciones")) {
          urls.push(ruta);
          return new Response(
            JSON.stringify({ publicaciones: [], paginacion: { total: 0, limite: 50, desplazamiento: 0 } }),
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
    // y el listado pasa a pedirse acotado a esa marca (las altas rápidas ya no nacen huérfanas).
    rerender(arbol(sesion({ marcas: ["unotv"] }), client));
    await waitFor(() => expect(urls.some((u) => u.includes("marca=unotv"))).toBe(true));
  });
});
