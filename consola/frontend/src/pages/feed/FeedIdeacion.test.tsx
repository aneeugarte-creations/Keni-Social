import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

/**
 * Stub de fetch: enruta opciones, cadenas (lote e individual), comentarios y el listado.
 * El listado FILTRA por `estado=` como el backend (consultas dedicadas de las vistas y
 * conteos con `limite=1`, que devuelven `paginacion.total` exacto del filtro).
 */
function stubFetch(publicaciones: Array<Record<string, unknown>> = [PUBLICACION]) {
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
        const params = new URL(ruta, "http://localhost").searchParams;
        const estado = params.get("estado");
        const lista = estado
          ? publicaciones.filter((p) => p.estado === estado)
          : publicaciones;
        return new Response(
          JSON.stringify({
            publicaciones: params.get("limite") === "1" ? lista.slice(0, 1) : lista,
            paginacion: { total: lista.length, limite: 50, desplazamiento: 0 },
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

  it("tope por ancho real: con ~500px de contenedor la preferencia de 5 columnas se acota a 2 efectivas", async () => {
    window.localStorage.setItem("keni_feed_columnas", "5");
    // jsdom no calcula layout: simulamos que todo contenedor mide 500px de ancho. La medición
    // inicial del layout-effect (la que vale en tests) acota 5 → floor(500/240) = 2.
    const orig = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientWidth");
    Object.defineProperty(HTMLElement.prototype, "clientWidth", {
      configurable: true,
      get: () => 500,
    });
    try {
      stubFetch();
      renderFeed();
      expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
      // La rejilla plana usa las columnas EFECTIVAS (las que caben), no la preferencia (5).
      const rejilla = screen.getByRole("feed");
      expect(rejilla.className).toContain("grid-cols-2");
      expect(rejilla.className).not.toContain("grid-cols-5");
      // El stepper "por fila" vive directo en la barra (control de vista tipo zoom, no un
      // ajuste) y enseña la PREFERENCIA a secas ("5"); el acote por ancho va en title/sr-only.
      const grupo = screen.getByRole("group", { name: "Piezas por fila" });
      expect(within(grupo).getByText("5")).toBeInTheDocument();
      expect(within(grupo).queryByText("2/5")).not.toBeInTheDocument();
    } finally {
      if (orig) Object.defineProperty(HTMLElement.prototype, "clientWidth", orig);
      else delete (HTMLElement.prototype as { clientWidth?: unknown }).clientWidth;
    }
  });

  it("muestra 3 pestañas-vista del mismo feed (todo / por aprobar / publicadas), sin 'En preparación'", async () => {
    stubFetch();
    renderFeed();
    // 3 vistas-partición por estado. Es un hub: la barra son las PESTAÑAS, sin título de
    // página propio. El nombre accesible se compone del DOM (etiqueta completa + conteo en
    // piezas), no de un aria-label que pise el número: por eso se matchea por regex.
    expect(await screen.findByRole("tab", { name: /Todo el feed/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Por aprobar/ })).toBeInTheDocument();
    // Vocabulario en femenino (la unidad es LA pieza): "Aprobadas y publicadas".
    expect(screen.getByRole("tab", { name: /Aprobadas y publicadas/ })).toBeInTheDocument();
    // «En preparación» ya no existe: «borrador» dejó de ser un estado donde descanse una pieza
    // (el pipeline la avanza sola a revisión), así que no hay pestaña de borradores.
    expect(screen.queryByRole("tab", { name: /En preparación/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /En proceso/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /Aprobado y publicado(?!s)/ })).not.toBeInTheDocument();
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

  it("«Por aprobar» va con consulta DEDICADA (estado=en_revision) y pinta tarjetas reales, sin rastreo en cliente", async () => {
    // El stub base enruta y filtra por estado; este wrapper solo captura las URLs pedidas.
    stubFetch([
      PUBLICACION,
      { ...PUBLICACION, id: "p2", contenido_id: "c2", contenido: "Ya salió", estado: "publicado", etapa_ia: "publicada" },
    ]);
    const base = globalThis.fetch as (url: string | URL) => Promise<Response>;
    const urls: string[] = [];
    vi.stubGlobal("fetch", async (url: string | URL) => {
      urls.push(String(url));
      return base(url);
    });

    renderFeed({}, "/?vista=por_aprobar");
    // El servidor filtra: la pieza en revisión se pinta como tarjeta REAL directamente.
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    expect(screen.queryByText("Ya salió")).not.toBeInTheDocument();
    // Sin mecánica de rastreo en cliente: ni "Seguir buscando" ni "Buscando piezas…".
    expect(screen.queryByText("Seguir buscando")).not.toBeInTheDocument();
    expect(screen.queryByText("Buscando piezas…")).not.toBeInTheDocument();
    // La petición del feed lleva el filtro de estado al backend.
    expect(urls.some((u) => u.includes("feed=1") && u.includes("estado=en_revision"))).toBe(true);
  });

  it("la pestaña filtra el feed en cliente: 'Aprobadas y publicadas' oculta lo que está por aprobar", async () => {
    stubFetch();
    renderFeed();
    // La única pieza (en_revision) se ve en 'Todo'.
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    // Al cambiar a 'Aprobadas y publicadas' desaparece (no está aprobada ni publicada). Las
    // pestañas son Radix Tabs: se activan con mouseDown (no con un click sintético en jsdom).
    fireEvent.mouseDown(screen.getByRole("tab", { name: /Aprobadas y publicadas/ }), { button: 0 });
    await waitFor(() =>
      expect(screen.queryByText("¡Increíble remontada!")).not.toBeInTheDocument(),
    );
    expect(await screen.findByText("Sin piezas aprobadas ni publicadas")).toBeInTheDocument();
  });

  it("un borrador COMPLETO cae en 'Todo el feed' con badge 'Para revisar' (sin etapa intermedia) y queda fuera de 'Aprobadas y publicadas'", async () => {
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
    stubFetch([PUBLICACION, BORRADOR, APROBADA]);
    renderFeed();
    // En "Todo el feed" se ve el borrador completo, pintado directo como "Para revisar": el
    // pipeline lo avanza solo a revisión, así que no hay badge "En borrador" intermedio.
    expect(await screen.findByText("Borrador completo")).toBeInTheDocument();
    expect(screen.getAllByText("Para revisar").length).toBeGreaterThan(0);
    expect(screen.queryByText("En borrador")).not.toBeInTheDocument();
    // 'Aprobadas y publicadas' (filtro en cliente sobre el listado base) incluye lo aprobado
    // SIN hueco todavía, pero NO el borrador (no es un estado final).
    fireEvent.mouseDown(screen.getByRole("tab", { name: /Aprobadas y publicadas/ }), { button: 0 });
    expect(await screen.findByText("Aprobada sin hueco")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Borrador completo")).not.toBeInTheDocument());
  });

  it("badges de pestañas: el total EXACTO del servidor (piezas), sin esperar a agotar el feed", async () => {
    // El feed deja páginas pendientes (cursor_siguiente presente): antes los badges no se
    // pintaban nunca; ahora salen de `paginacion.total` (limite=1) por estado.
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
          const params = new URL(ruta, "http://localhost").searchParams;
          if (params.get("limite") === "1") {
            const estado = params.get("estado");
            const total = estado === "borrador" ? 2 : estado === "en_revision" ? 4 : 9;
            return new Response(
              JSON.stringify({
                publicaciones: [PUBLICACION],
                paginacion: { total, limite: 1, desplazamiento: 0 },
              }),
              { status: 200 },
            );
          }
          return new Response(
            JSON.stringify({
              publicaciones: [PUBLICACION],
              paginacion: { total: 9, limite: 1, desplazamiento: 0, cursor_siguiente: "2026-01-01T00:00:00|p1" },
            }),
            { status: 200 },
          );
        }
        return new Response("{}", { status: 200 });
      }),
    );
    renderFeed();
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    // Todo=9 · Por aprobar=4 · Aprobadas y publicadas=9−2−4=3 (los 2 borradores se restan aunque
    // ya no tengan pestaña propia, para que "Aprobadas y publicadas" no los cuente).
    expect(await within(screen.getByRole("tab", { name: /Todo el feed/ })).findByText("9")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /En preparación/ })).not.toBeInTheDocument();
    expect(within(screen.getByRole("tab", { name: /Por aprobar/ })).getByText("4")).toBeInTheDocument();
    expect(within(screen.getByRole("tab", { name: /Aprobadas y publicadas/ })).getByText("3")).toBeInTheDocument();
    // El title habla de PIEZAS (unidad canónica), pluralizado de verdad (nada de "1 ideas").
    expect(within(screen.getByRole("tab", { name: /Por aprobar/ })).getByTitle("4 piezas")).toBeInTheDocument();
    // El NOMBRE ACCESIBLE incluye el conteo con su unidad ("Por aprobar 4 piezas"): el
    // aria-label que lo pisaba ya no existe.
    expect(screen.getByRole("tab", { name: /Por aprobar.*4 piezas/ })).toBeInTheDocument();
  });

  it("vista filtrada: 'Por aprobar' enseña SOLO las piezas que cumplen (sin tarjetas ajenas ni huecos)", async () => {
    // Una IDEA (c1) con dos piezas: en revisión (X) y publicada (Instagram). El stub filtra por
    // estado= como el backend: la vista dedicada solo recibe la pieza en revisión.
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
          const params = new URL(ruta, "http://localhost").searchParams;
          const estado = params.get("estado");
          const todas = [PUBLICACION, PUB_PUBLICADA];
          const lista = estado ? todas.filter((p) => p.estado === estado) : todas;
          return new Response(
            JSON.stringify({
              publicaciones: lista,
              paginacion: { total: lista.length, limite: 50, desplazamiento: 0 },
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
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Ya publicada")).not.toBeInTheDocument());
    expect(screen.queryByText("No generado")).not.toBeInTheDocument();
  });

  it("vista filtrada EN CLIENTE vacía con más páginas: no afirma el vacío y sigue pidiendo páginas", async () => {
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

    // 'Aprobadas y publicadas' filtra el listado base EN CLIENTE. Página 1: SOLO una pieza en
    // revisión + cursor. Página 2: la aprobada, última.
    const APROBADA = {
      ...PUBLICACION,
      id: "p2",
      contenido_id: "c2",
      contenido: "Aprobada sin hueco",
      estado: "aprobado",
      etapa_ia: "aprobada",
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
              JSON.stringify({ publicaciones: [APROBADA], paginacion: { total: 2, limite: 1, desplazamiento: 0 } }),
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
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    // 'Aprobadas y publicadas' queda vacía PERO hay más páginas: nada de afirmar el vacío; se busca.
    fireEvent.mouseDown(screen.getByRole("tab", { name: /Aprobadas y publicadas/ }), { button: 0 });
    expect(await screen.findByText("Buscando piezas…")).toBeInTheDocument();
    expect(screen.queryByText("Sin piezas aprobadas ni publicadas")).not.toBeInTheDocument();
    // El sentinel sigue montado: al intersecar pide la página siguiente (?cursor=) y la pinta.
    await waitFor(() => expect(disparadores.length).toBeGreaterThan(0));
    disparadores[disparadores.length - 1]();
    expect(await screen.findByText("Aprobada sin hueco")).toBeInTheDocument();
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

  it("/opciones caído (500): el feed degrada al catálogo estático y pinta tarjetas reales, no «No generado»", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) => {
        const ruta = String(url);
        if (ruta.includes("/api/publicaciones/opciones")) {
          return new Response(JSON.stringify({ error: "boom" }), { status: 500 });
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
              publicaciones: [PUBLICACION],
              paginacion: { total: 1, limite: 50, desplazamiento: 0 },
            }),
            { status: 200 },
          );
        }
        return new Response("{}", { status: 200 });
      }),
    );
    renderFeed();
    // La tarjeta REAL (article de PostFeed) se pinta con el catálogo de respaldo…
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    expect(screen.getByRole("article")).toBeInTheDocument();
    // …y nada se disfraza de hueco "No generado" (el bug que mentía con catálogo vacío).
    expect(screen.queryByText("No generado")).not.toBeInTheDocument();
  });

  it("mientras /opciones está en vuelo se ve skeleton, no placeholders falsos", async () => {
    let feedServido = false;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string | URL) => {
        const ruta = String(url);
        if (ruta.includes("/api/publicaciones/opciones")) {
          return new Promise<Response>(() => {}); // /opciones nunca aterriza
        }
        if (ruta.includes("/api/publicaciones/cadenas")) {
          return Promise.resolve(new Response(JSON.stringify({ cadenas: {} }), { status: 200 }));
        }
        if (ruta.includes("/api/publicaciones")) {
          feedServido = true;
          return Promise.resolve(
            new Response(
              JSON.stringify({
                publicaciones: [PUBLICACION],
                paginacion: { total: 1, limite: 50, desplazamiento: 0 },
              }),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(new Response("{}", { status: 200 }));
      }),
    );
    renderFeed();
    await waitFor(() => expect(feedServido).toBe(true));
    // El feed YA llegó pero el catálogo no: gate de skeleton (sin tarjetas ni huecos falsos).
    await waitFor(() =>
      expect(document.querySelector('[class*="animate-pulse"]')).not.toBeNull(),
    );
    expect(screen.queryByText("No generado")).not.toBeInTheDocument();
    expect(screen.queryByText("¡Increíble remontada!")).not.toBeInTheDocument();
  });

  it("scroll infinito: la 1ª página trae cursor; al intersectar el sentinel pide la siguiente (con ?cursor=)", async () => {
    // IntersectionObserver controlable: capturamos su callback para disparar la intersección a
    // mano (jsdom no lo implementa).
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

  it("tope de búsqueda (vista en cliente): con 5 páginas y la vista vacía aparece «Seguir buscando» y NO se pide la 6ª sola", async () => {
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

    // Todas las páginas del feed traen UNA pieza en revisión y SIEMPRE hay cursor: la vista
    // 'Aprobadas y publicadas' (filtro EN CLIENTE) nunca encuentra nada y el feed nunca se agota
    // (el peor caso del rastreo encadenado). Solo cuentan las peticiones del FEED (feed=1):
    // los conteos de los badges (limite=1) van aparte.
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
          if (!ruta.includes("feed=1")) {
            // Conteos de badges: total fijo, sin cursor.
            return new Response(
              JSON.stringify({ publicaciones: [PUBLICACION], paginacion: { total: 99, limite: 1, desplazamiento: 0 } }),
              { status: 200 },
            );
          }
          urls.push(ruta);
          const n = urls.length;
          return new Response(
            JSON.stringify({
              publicaciones: [
                {
                  ...PUBLICACION,
                  id: `p${n}`,
                  contenido_id: `c${n}`,
                  contenido: `En revisión ${n}`,
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

    renderFeed({}, "/?vista=publicado");
    // Página 1 cargada y vista vacía: se busca (no se afirma el vacío).
    expect(await screen.findByText("Buscando piezas…")).toBeInTheDocument();
    // El sentinel encadena hasta el tope del lote (5 páginas).
    for (let pagina = 2; pagina <= 5; pagina++) {
      const ultimo = observers[observers.length - 1];
      ultimo.fire();
      await waitFor(() => expect(urls.length).toBe(pagina));
    }
    // Tope alcanzado: el vacío de la casa (EstadoVacio) ofrece reanudar y el rastreo se detiene.
    expect(await screen.findByRole("button", { name: "Seguir buscando" })).toBeInTheDocument();
    expect(screen.getByText("Sin piezas aprobadas ni publicadas")).toBeInTheDocument();
    expect(screen.getByText("Puede haber piezas más antiguas aún sin cargar.")).toBeInTheDocument();
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

  it("un fallo al cargar MÁS no tira el feed: las piezas cargadas siguen y el pie ofrece Reintentar", async () => {
    // IntersectionObserver controlable (jsdom no lo implementa).
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

    // Página 1 OK (con cursor); la página 2 (con cursor=) REVIENTA con 500.
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
          if (ruta.includes("cursor=")) {
            return new Response(JSON.stringify({ error: "boom" }), { status: 500 });
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
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    // El sentinel pide la página 2, que falla: la query pasa a error PERO conserva los datos.
    await waitFor(() => expect(disparadores.length).toBeGreaterThan(0));
    disparadores[0]();
    // El pie inline con Reintentar (reintenta SOLO la página fallida), no el BloqueError a
    // página completa que descartaba el feed visible y la posición de scroll.
    expect(await screen.findByText("No se pudo cargar más.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
    expect(screen.getByText("¡Increíble remontada!")).toBeInTheDocument();
    expect(screen.queryByText("No se pudo cargar el feed")).not.toBeInTheDocument();
  });
});
