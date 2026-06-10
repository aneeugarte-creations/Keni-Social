import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import { FiltrosContenidoProvider } from "@/hooks/use-filtros-contenido";
import { MarcaActivaProvider } from "@/hooks/use-marca-activa";
import { formatearFechaHoraCorta } from "@/lib/fecha";
import type { UsuarioSesion } from "@/types";

import FeedIdeacion from "./FeedIdeacion";

const OPCIONES = {
  redes: [{ id: "x", nombre: "X" }],
  estados: [
    { id: "en_revision", nombre: "En revisión" },
    { id: "aprobado", nombre: "Aprobado" },
  ],
  marcas: [{ id: "unotv", nombre: "Uno TV" }],
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
  origen: "equipo",
  imagen: "",
  imagen_url: "",
  evergreen: false,
  // Etapa real del backend (Flujo C): coherente con estado 'en_revision'.
  etapa_ia: "lista_para_revisar",
};

/** Stub de fetch: enruta opciones, listado, cadenas (lote e individual) y comentarios. */
function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL) => {
      const ruta = String(url);
      if (ruta.includes("/api/publicaciones/opciones")) {
        return new Response(JSON.stringify(OPCIONES), { status: 200 });
      }
      if (ruta.includes("/api/publicaciones/cadenas")) {
        // Lote vacío: cada tarjeta cae a su query individual (/aprobacion).
        return new Response(JSON.stringify({ cadenas: {} }), { status: 200 });
      }
      if (ruta.includes("/aprobacion")) {
        // Cadena con UN nivel humano pendiente: el revisor de sesión (u1, ≠ autor u9) puede dar OK.
        return new Response(
          JSON.stringify({
            niveles: [
              {
                id: "n1",
                plataforma_id: "p1",
                contenido_id: "c1",
                nivel: 1,
                etiqueta: "Edición",
                decision: "pendiente",
                decisor_id: "",
                decisor_nombre: "",
                comentario: "",
                creado: "",
                decidido_en: "",
                cargo_requerido: "",
              },
            ],
            estado: "pendiente",
            nivel_actual: "n1",
            aprobados: 0,
            minimo_aprobaciones: 0,
            comentarios_sin_resolver: 0,
          }),
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

function renderFeed(usuario: Partial<UsuarioSesion> = {}, ruta = "/") {
  const valor: ValorSesion = {
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
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={valor}>
        <MarcaActivaProvider>
          <FiltrosContenidoProvider>
            <MemoryRouter initialEntries={[ruta]}>
              <FeedIdeacion />
            </MemoryRouter>
          </FiltrosContenidoProvider>
        </MarcaActivaProvider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("FeedIdeacion · feed de ideación interno", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("tope responsivo: en móvil (<640px) la preferencia de 5 columnas se acota a 2 efectivas", async () => {
    window.localStorage.setItem("keni_feed_columnas", "5");
    // jsdom no trae matchMedia: lo simulamos diciendo que el viewport es <640px.
    vi.stubGlobal(
      "matchMedia",
      vi.fn((query: string) => ({
        matches: true,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    );
    stubFetch();
    renderFeed();
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    // La rejilla plana usa las columnas EFECTIVAS (máx. 2 en móvil), no la preferencia (5).
    const rejilla = screen.getByRole("feed");
    expect(rejilla.className).toContain("grid-cols-2");
    expect(rejilla.className).not.toContain("grid-cols-5");
  });

  it("muestra 4 pestañas-vista del mismo feed (todo / preparación / por aprobar / aprobado)", async () => {
    stubFetch();
    renderFeed();
    // 4 vistas del mismo listado (no las bandejas viejas por estado). Es un hub: la barra
    // son las PESTAÑAS, sin título de página propio. El nombre accesible es la etiqueta
    // COMPLETA (aria-label), aunque en <sm el texto visible se acorte.
    expect(await screen.findByRole("tab", { name: "Todo el feed" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "En preparación" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Por aprobar" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Aprobado y publicado" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "En proceso" })).not.toBeInTheDocument();
  });

  it("arranca en la vista de la URL (?vista=por_aprobar) y la pestaña queda activa", async () => {
    stubFetch();
    renderFeed({}, "/?vista=por_aprobar");
    const tab = await screen.findByRole("tab", { name: /Por aprobar/ });
    expect(tab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /Todo el feed/ })).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });

  it("la pestaña filtra el feed en cliente: 'Aprobado y publicado' oculta lo que está por aprobar", async () => {
    stubFetch();
    renderFeed();
    // La única pieza (en_revision) se ve en 'Todo'.
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    // Al cambiar a 'Aprobado y publicado' desaparece (no está aprobada ni publicada). Las
    // pestañas son Radix Tabs: se activan con mouseDown (no con un click sintético en jsdom).
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Aprobado y publicado" }), { button: 0 });
    await waitFor(() =>
      expect(screen.queryByText("¡Increíble remontada!")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("Nada aprobado ni publicado")).toBeInTheDocument();
  });

  it("las 3 vistas filtradas PARTICIONAN el ciclo: el borrador completo cae en 'En preparación' y el aprobado en 'Aprobado y publicado'", async () => {
    // Tres piezas de tres ideas: borrador COMPLETO (antes invisible en toda vista filtrada),
    // en revisión y aprobada SIN hueco (antes tampoco salía en ninguna).
    const BORRADOR = {
      ...PUBLICACION,
      id: "p2",
      contenido_id: "c2",
      contenido: "Borrador completo",
      estado: "borrador",
      etapa_ia: "lista_para_revisar",
    };
    const APROBADA = {
      ...PUBLICACION,
      id: "p3",
      contenido_id: "c3",
      contenido: "Aprobada sin hueco",
      estado: "aprobado",
      etapa_ia: "aprobada",
    };
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
        if (ruta.includes("/comentarios")) {
          return new Response(JSON.stringify({ comentarios: [], total: 0 }), { status: 200 });
        }
        if (ruta.includes("/api/publicaciones")) {
          return new Response(
            JSON.stringify({
              publicaciones: [PUBLICACION, BORRADOR, APROBADA],
              paginacion: { total: 3, limite: 50, desplazamiento: 0 },
            }),
            { status: 200 },
          );
        }
        return new Response("{}", { status: 200 });
      }),
    );
    renderFeed();
    expect(await screen.findByText("Borrador completo")).toBeInTheDocument();
    // 'En preparación' = todo lo anterior a revisión (incluye el borrador completo, con su
    // badge honesto 'En borrador').
    fireEvent.mouseDown(screen.getByRole("tab", { name: "En preparación" }), { button: 0 });
    await waitFor(() => expect(screen.queryByText("Aprobada sin hueco")).not.toBeInTheDocument());
    expect(screen.getByText("Borrador completo")).toBeInTheDocument();
    expect(screen.getByText("En borrador")).toBeInTheDocument();
    // 'Aprobado y publicado' incluye lo aprobado SIN hueco todavía.
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Aprobado y publicado" }), { button: 0 });
    await waitFor(() => expect(screen.queryByText("Borrador completo")).not.toBeInTheDocument());
    expect(screen.getByText("Aprobada sin hueco")).toBeInTheDocument();
  });

  it("vista filtrada: 'Por aprobar' enseña SOLO las piezas que cumplen (sin tarjetas ajenas ni huecos)", async () => {
    // Una IDEA (c1) con dos piezas: en revisión (X) y publicada (Instagram).
    const PUB_PUBLICADA = {
      ...PUBLICACION,
      id: "p2",
      red: "instagram",
      contenido: "Ya publicada",
      estado: "publicado",
      etapa_ia: "publicada",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) => {
        const ruta = String(url);
        if (ruta.includes("/api/publicaciones/opciones")) {
          return new Response(
            JSON.stringify({
              ...OPCIONES,
              redes: [
                { id: "x", nombre: "X" },
                { id: "instagram", nombre: "Instagram" },
              ],
            }),
            { status: 200 },
          );
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
        if (ruta.includes("/comentarios")) {
          return new Response(JSON.stringify({ comentarios: [], total: 0 }), { status: 200 });
        }
        if (ruta.includes("/api/publicaciones")) {
          return new Response(
            JSON.stringify({
              publicaciones: [PUBLICACION, PUB_PUBLICADA],
              paginacion: { total: 2, limite: 50, desplazamiento: 0 },
            }),
            { status: 200 },
          );
        }
        return new Response("{}", { status: 200 });
      }),
    );
    renderFeed();
    // 'Todo el feed' (matriz por idea): ambas tarjetas.
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    expect(screen.getByText("Ya publicada")).toBeInTheDocument();
    // 'Por aprobar': solo la pieza en revisión; la publicada y los huecos no se pintan.
    fireEvent.mouseDown(screen.getByRole("tab", { name: /Por aprobar/ }), { button: 0 });
    await waitFor(() => expect(screen.queryByText("Ya publicada")).not.toBeInTheDocument());
    expect(screen.getByText("¡Increíble remontada!")).toBeInTheDocument();
    expect(screen.queryByText("No generado")).not.toBeInTheDocument();
  });

  it("vista filtrada vacía con más páginas: no afirma 'Nada por aprobar' y sigue pidiendo páginas", async () => {
    // IntersectionObserver controlable (jsdom no lo implementa): registra disparadores a mano.
    const disparadores: Array<() => void> = [];
    class IOFalso {
      cb: IntersectionObserverCallback;
      constructor(cb: IntersectionObserverCallback) {
        this.cb = cb;
        disparadores.push(() => this.cb([{ isIntersecting: true } as IntersectionObserverEntry], this));
      }
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords() {
        return [];
      }
      root = null;
      rootMargin = "";
      thresholds = [];
    }
    vi.stubGlobal("IntersectionObserver", IOFalso as unknown as typeof IntersectionObserver);

    // Página 1: SOLO una pieza publicada + cursor. Página 2: la pieza en revisión, última.
    const PUB_PUBLICADA = {
      ...PUBLICACION,
      id: "p2",
      contenido_id: "c2",
      contenido: "Ya publicada",
      estado: "publicado",
      etapa_ia: "publicada",
    };
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
          urls.push(ruta);
          if (ruta.includes("cursor=")) {
            return new Response(
              JSON.stringify({ publicaciones: [PUBLICACION], paginacion: { total: 2, limite: 1, desplazamiento: 0 } }),
              { status: 200 },
            );
          }
          return new Response(
            JSON.stringify({
              publicaciones: [PUB_PUBLICADA],
              paginacion: { total: 2, limite: 1, desplazamiento: 0, cursor_siguiente: "2026-01-01T00:00:00|p2" },
            }),
            { status: 200 },
          );
        }
        return new Response("{}", { status: 200 });
      }),
    );

    renderFeed();
    expect(await screen.findByText("Ya publicada")).toBeInTheDocument();
    // 'Por aprobar' queda vacía PERO hay más páginas: nada de "Nada por aprobar"; se busca.
    fireEvent.mouseDown(screen.getByRole("tab", { name: /Por aprobar/ }), { button: 0 });
    expect(await screen.findByText("Buscando piezas…")).toBeInTheDocument();
    expect(screen.queryByText("Nada por aprobar")).not.toBeInTheDocument();
    // El sentinel sigue montado: al intersecar pide la página siguiente (?cursor=) y la pinta.
    await waitFor(() => expect(disparadores.length).toBeGreaterThan(0));
    disparadores[disparadores.length - 1]();
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    expect(urls.some((u) => u.includes("cursor="))).toBe(true);
  });

  it("renderiza la pieza como post con etapa IA y el 'me gusta' (OK) en línea", async () => {
    stubFetch();
    renderFeed();
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    // Etapa IA en vivo: en revisión → para revisar.
    expect(screen.getByText("Para revisar")).toBeInTheDocument();
    // El OK en línea está habilitado para el revisor elegible (nombre accesible derivado del
    // estado real del toggle: "Dale tu OK"), con "No me gusta" (dislike) al lado.
    const like = await screen.findByRole("button", { name: "Dale tu OK" });
    expect(like).toBeEnabled();
    expect(screen.getByRole("button", { name: "No me gusta" })).toBeInTheDocument();
    // Panel de estado de la cadena (solo lectura): el recuento de OK (solo el conteo).
    expect(screen.getByText("0/1")).toBeInTheDocument();
  });

  it("abre el hilo de comentarios en línea al pulsar Comentar", async () => {
    stubFetch();
    renderFeed();
    const boton = await screen.findByRole("button", { name: /comentar/i });
    fireEvent.click(boton);
    await waitFor(() =>
      expect(screen.getByPlaceholderText(/comentario para el equipo/i)).toBeInTheDocument(),
    );
  });

  it("scroll infinito: la 1ª página trae cursor; al intersectar el sentinel pide la siguiente (con ?cursor=)", async () => {
    // IntersectionObserver controlable: capturamos su callback para disparar la intersección a mano
    // (jsdom no lo implementa). Cada instancia registra su disparador en `disparadores` (un holder
    // array: TS no estrecha el tipo del elemento a `null` como haría con una `let` asignada solo
    // dentro del constructor anidado).
    const disparadores: Array<() => void> = [];
    class IOFalso {
      cb: IntersectionObserverCallback;
      constructor(cb: IntersectionObserverCallback) {
        this.cb = cb;
        disparadores.push(() => this.cb([{ isIntersecting: true } as IntersectionObserverEntry], this));
      }
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords() {
        return [];
      }
      root = null;
      rootMargin = "";
      thresholds = [];
    }
    vi.stubGlobal("IntersectionObserver", IOFalso as unknown as typeof IntersectionObserver);

    const PUB2 = { ...PUBLICACION, id: "p2", contenido_id: "c2", contenido: "Segunda página" };
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) => {
        const ruta = String(url);
        if (ruta.includes("/api/publicaciones/opciones")) {
          return new Response(JSON.stringify(OPCIONES), { status: 200 });
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
          urls.push(ruta);
          // Página 1 (sin cursor): trae cursor_siguiente. Página 2 (con cursor): última, sin cursor.
          if (ruta.includes("cursor=")) {
            return new Response(
              JSON.stringify({ publicaciones: [PUB2], paginacion: { total: 2, limite: 1, desplazamiento: 0 } }),
              { status: 200 },
            );
          }
          return new Response(
            JSON.stringify({
              publicaciones: [PUBLICACION],
              paginacion: { total: 2, limite: 1, desplazamiento: 0, cursor_siguiente: "2026-01-01T00:00:00|p1" },
            }),
            { status: 200 },
          );
        }
        return new Response("{}", { status: 200 });
      }),
    );

    renderFeed();
    // Primera página pintada.
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    // Dispara la intersección del sentinel -> debe pedir la página 2 con ?cursor= y pintarla.
    await waitFor(() => expect(disparadores.length).toBeGreaterThan(0));
    disparadores[0]();
    expect(await screen.findByText("Segunda página")).toBeInTheDocument();
    expect(urls.some((u) => u.includes("cursor="))).toBe(true);
  });

  it("matriz por idea: la franja 'Falta generar' se acota a las redes del FORMATO (foto = 3 redes)", async () => {
    // Catálogo de 3 redes y una idea FOTO con pieza solo en X: falta Instagram (sí es red de
    // foto) pero NO TikTok (una foto jamás irá ahí; listarla sería trabajo pendiente falso).
    // Las redes pendientes ya no pintan placeholders gigantes: van en UNA franja compacta.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) => {
        const ruta = String(url);
        if (ruta.includes("/api/publicaciones/opciones")) {
          return new Response(
            JSON.stringify({
              ...OPCIONES,
              redes: [
                { id: "x", nombre: "X" },
                { id: "instagram", nombre: "Instagram" },
                { id: "tiktok", nombre: "TikTok" },
              ],
            }),
            { status: 200 },
          );
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
        if (ruta.includes("/comentarios")) {
          return new Response(JSON.stringify({ comentarios: [], total: 0 }), { status: 200 });
        }
        if (ruta.includes("/api/publicaciones")) {
          return new Response(
            JSON.stringify({
              publicaciones: [
                {
                  ...PUBLICACION,
                  // Nota original (pipeline): fecha de publicación en el medio + medio.
                  fecha_fuente: "2026-06-09T21:21:00Z",
                  fuente_original: "Récord",
                },
              ],
              paginacion: { total: 1, limite: 50, desplazamiento: 0 },
            }),
            { status: 200 },
          );
        }
        return new Response("{}", { status: 200 });
      }),
    );
    renderFeed();
    // El post de la red generada (X).
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    // Franja compacta con SOLO Instagram (TikTok no es red de foto); sin placeholders gigantes.
    expect(screen.getByText("Falta generar:")).toBeInTheDocument();
    expect(screen.getByText("Instagram")).toBeInTheDocument();
    expect(screen.queryByText("TikTok")).toBeNull();
    expect(screen.queryByText("No generado")).toBeNull();
    // Cabecera de la idea: sin contador "1/3 redes" ni fila de logos (la matriz ya lo cuenta);
    // título + fecha de la nota original (CDMX) + fuente.
    expect(screen.queryByText("1/3 redes")).toBeNull();
    expect(screen.queryByTestId("redes-grupo")).toBeNull();
    // La fecha de la nota se muestra en hora CDMX con el helper central (21:21 UTC -> 15:21
    // CDMX); el literal exacto depende de los datos de locale del runtime, así que se compara
    // contra el propio helper.
    expect(
      screen.getByText(formatearFechaHoraCorta("2026-06-09T21:21:00Z")),
    ).toBeInTheDocument();
    expect(screen.getByText("Récord")).toBeInTheDocument();
  });

  it("matriz por idea: una idea VIDEO va a las 5 redes (post en X + franja con las otras 4)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) => {
        const ruta = String(url);
        if (ruta.includes("/api/publicaciones/opciones")) {
          return new Response(
            JSON.stringify({
              ...OPCIONES,
              redes: [
                { id: "x", nombre: "X" },
                { id: "instagram", nombre: "Instagram" },
                { id: "facebook", nombre: "Facebook" },
                { id: "tiktok", nombre: "TikTok" },
                { id: "youtube", nombre: "YouTube" },
              ],
            }),
            { status: 200 },
          );
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
        if (ruta.includes("/comentarios")) {
          return new Response(JSON.stringify({ comentarios: [], total: 0 }), { status: 200 });
        }
        if (ruta.includes("/api/publicaciones")) {
          return new Response(
            JSON.stringify({
              publicaciones: [{ ...PUBLICACION, formato: "video" }],
              paginacion: { total: 1, limite: 50, desplazamiento: 0 },
            }),
            { status: 200 },
          );
        }
        return new Response("{}", { status: 200 });
      }),
    );
    renderFeed();
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    // El post (X) + UNA franja compacta con las 4 redes pendientes (sin placeholders gigantes).
    expect(screen.getByText("Falta generar:")).toBeInTheDocument();
    for (const red of ["Instagram", "Facebook", "TikTok", "YouTube"]) {
      expect(screen.getByText(red)).toBeInTheDocument();
    }
    expect(screen.queryByText("No generado")).toBeNull();
  });

  it("tope de búsqueda: con 5 páginas cargadas y la vista vacía aparece «Seguir buscando» y NO se pide la 6ª sola", async () => {
    // IntersectionObserver controlable que RESPETA disconnect(): un disparador de un observer
    // desconectado (sentinel apagado por el tope) no hace nada, como en el navegador.
    const observers: IOFalso[] = [];
    class IOFalso {
      activa = true;
      private cb: IntersectionObserverCallback;
      constructor(cb: IntersectionObserverCallback) {
        this.cb = cb;
        observers.push(this);
      }
      fire() {
        if (this.activa) {
          this.cb([{ isIntersecting: true } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
        }
      }
      observe() {}
      unobserve() {}
      disconnect() {
        this.activa = false;
      }
      takeRecords() {
        return [];
      }
      root = null;
      rootMargin = "";
      thresholds = [];
    }
    vi.stubGlobal("IntersectionObserver", IOFalso as unknown as typeof IntersectionObserver);

    // Todas las páginas traen UNA pieza publicada y SIEMPRE hay cursor: la vista 'Por aprobar'
    // nunca encuentra nada y el feed nunca se agota (el peor caso del rastreo encadenado).
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
          urls.push(ruta);
          const n = urls.length;
          return new Response(
            JSON.stringify({
              publicaciones: [
                {
                  ...PUBLICACION,
                  id: `p${n}`,
                  contenido_id: `c${n}`,
                  contenido: `Publicada ${n}`,
                  estado: "publicado",
                  etapa_ia: "publicada",
                },
              ],
              paginacion: { total: 99, limite: 1, desplazamiento: 0, cursor_siguiente: `cur-${n}` },
            }),
            { status: 200 },
          );
        }
        return new Response("{}", { status: 200 });
      }),
    );

    renderFeed({}, "/?vista=por_aprobar");
    // Página 1 cargada y vista vacía: se busca (no se afirma el vacío).
    expect(await screen.findByText("Buscando piezas…")).toBeInTheDocument();
    // El sentinel encadena hasta el tope del lote (5 páginas).
    for (let pagina = 2; pagina <= 5; pagina++) {
      const ultimo = observers[observers.length - 1];
      ultimo.fire();
      await waitFor(() => expect(urls.length).toBe(pagina));
    }
    // Tope alcanzado: se ofrece reanudar y el rastreo se detiene.
    expect(await screen.findByRole("button", { name: "Seguir buscando" })).toBeInTheDocument();
    expect(screen.getByText("No hay piezas de esta vista entre lo ya cargado.")).toBeInTheDocument();
    // Disparar lo que quede registrado no pide la 6ª página (los observers están apagados).
    observers.forEach((o) => o.fire());
    await waitFor(() => expect(urls.length).toBe(5));
    // "Seguir buscando" concede otro lote: el sentinel revive y pide la 6ª.
    fireEvent.click(screen.getByRole("button", { name: "Seguir buscando" }));
    await waitFor(() => {
      const ultimo = observers[observers.length - 1];
      expect(ultimo.activa).toBe(true);
    });
    observers[observers.length - 1].fire();
    await waitFor(() => expect(urls.length).toBe(6));
  });
});
