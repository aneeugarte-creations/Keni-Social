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
  origen: "equipo",
  imagen: "",
  imagen_url: "",
  evergreen: false,
  // Etapa real del backend (Flujo C): coherente con estado 'en_revision'.
  etapa_ia: "lista_para_revisar",
};

/**
 * ¿Casa la pieza con el filtro `estado=` del backend? Modela los PSEUDO-ESTADOS de la
 * partición del feed: `pendiente` = todo lo que no es `publicado`; `publicado` = solo lo
 * publicado; sin estado = todo. Cualquier otro estado va por igualdad exacta (conteos).
 */
function casaEstado(estado: string | null, piezaEstado: unknown): boolean {
  if (!estado) return true;
  if (estado === "pendiente") return piezaEstado !== "publicado";
  if (estado === "publicado") return piezaEstado === "publicado";
  return piezaEstado === estado;
}

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
      if (ruta.includes("/api/contenido/aportar")) {
        // Puerta creativa: el back devuelve el tema con una pieza-borrador por red pedida
        // (la IA redactará el copy en segundo plano; aquí solo nace el contenido).
        return new Response(
          JSON.stringify({
            contenido: { id: "t-aportado", plataformas: [{ id: "pl1", red: "x" }] },
          }),
          { status: 200 },
        );
      }
      if (ruta.includes("/api/publicaciones")) {
        const params = new URL(ruta, "http://localhost").searchParams;
        const estado = params.get("estado");
        const lista = publicaciones.filter((p) => casaEstado(estado, p.estado));
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

  it("muestra 3 pestañas-vista del mismo feed EN ORDEN (Pendientes · Publicadas · Todas), sin 'En preparación'", async () => {
    stubFetch();
    renderFeed();
    // 3 vistas-partición por estado. Es un hub: la barra son las PESTAÑAS, sin título de
    // página propio. El nombre accesible se compone del DOM (etiqueta completa + conteo en
    // piezas), no de un aria-label que pise el número: por eso se matchea por regex.
    const pestanas = await screen.findAllByRole("tab");
    expect(pestanas.map((t) => t.textContent)).toEqual([
      expect.stringContaining("Pendientes"),
      expect.stringContaining("Publicadas"),
      expect.stringContaining("Todas"),
    ]);
    // «En preparación» ya no existe: «borrador» dejó de ser un estado donde descanse una pieza
    // (el pipeline la avanza sola a revisión), así que no hay pestaña de borradores.
    expect(screen.queryByRole("tab", { name: /En preparación/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /Por aprobar/ })).not.toBeInTheDocument();
  });

  it("arranca en la vista de la URL (?vista=pendiente) y la pestaña queda activa", async () => {
    stubFetch();
    renderFeed({}, "/?vista=pendiente");
    const tab = await screen.findByRole("tab", { name: /Pendientes/ });
    expect(tab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /Todas/ })).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });

  it("«Pendientes» va con consulta DEDICADA (estado=pendiente) y pinta tarjetas reales, sin rastreo en cliente", async () => {
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

    renderFeed({}, "/?vista=pendiente");
    // El servidor filtra: la pieza en revisión (no publicada) se pinta como tarjeta REAL.
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    // La publicada queda fuera de "Pendientes".
    expect(screen.queryByText("Ya salió")).not.toBeInTheDocument();
    // Sin mecánica de rastreo en cliente: ni "Seguir buscando" ni "Buscando piezas…".
    expect(screen.queryByText("Seguir buscando")).not.toBeInTheDocument();
    expect(screen.queryByText("Buscando piezas…")).not.toBeInTheDocument();
    // La petición del feed lleva el pseudo-estado de la vista al backend.
    expect(urls.some((u) => u.includes("feed=1") && u.includes("estado=pendiente"))).toBe(true);
  });

  it("«Publicadas» (consulta DEDICADA estado=publicado) oculta lo que aún no salió", async () => {
    stubFetch();
    renderFeed();
    // La única pieza (en_revision) se ve en 'Todas'.
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    // Al cambiar a 'Publicadas' el servidor filtra por estado=publicado y no devuelve la
    // pieza en revisión. Las pestañas son Radix Tabs: se activan con mouseDown.
    fireEvent.mouseDown(screen.getByRole("tab", { name: /Publicadas/ }), { button: 0 });
    await waitFor(() =>
      expect(screen.queryByText("¡Increíble remontada!")).not.toBeInTheDocument(),
    );
    expect(await screen.findByText("Sin piezas publicadas")).toBeInTheDocument();
  });

  it("la partición es binaria por 'publicado': borrador y aprobado caen en 'Pendientes', solo lo publicado en 'Publicadas'", async () => {
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
    const PUBLICADA = {
      ...PUBLICACION,
      id: "p4",
      contenido_id: "c4",
      contenido: "Ya salió",
      estado: "publicado",
      etapa_ia: "publicada",
    };
    stubFetch([PUBLICACION, BORRADOR, APROBADA, PUBLICADA]);
    renderFeed();
    // En "Todas" se ve el borrador completo, pintado directo como "Para revisar": el
    // pipeline lo avanza solo a revisión, así que no hay badge "En borrador" intermedio.
    expect(await screen.findByText("Borrador completo")).toBeInTheDocument();
    expect(screen.getAllByText("Para revisar").length).toBeGreaterThan(0);
    expect(screen.queryByText("En borrador")).not.toBeInTheDocument();
    // 'Pendientes' = TODO lo que aún no salió: borrador y aprobado SÍ, lo publicado NO.
    fireEvent.mouseDown(screen.getByRole("tab", { name: /Pendientes/ }), { button: 0 });
    expect(await screen.findByText("Aprobada sin hueco")).toBeInTheDocument();
    expect(screen.getByText("Borrador completo")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Ya salió")).not.toBeInTheDocument());
    // 'Publicadas' = SOLO lo publicado: ni borrador ni aprobado.
    fireEvent.mouseDown(screen.getByRole("tab", { name: /Publicadas/ }), { button: 0 });
    expect(await screen.findByText("Ya salió")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Aprobada sin hueco")).not.toBeInTheDocument());
    expect(screen.queryByText("Borrador completo")).not.toBeInTheDocument();
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
            // Conteos por pseudo-estado: pendiente=6 · publicado=3 · en_revision=4 (este último
            // solo alimenta el énfasis de "Pendientes"). "Todas" = 6+3 = 9 (suma exacta).
            const total = estado === "pendiente" ? 6 : estado === "publicado" ? 3 : estado === "en_revision" ? 4 : 9;
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
    // Pendientes=6 · Publicadas=3 · Todas=6+3=9 (suma exacta de la partición binaria).
    expect(await within(screen.getByRole("tab", { name: /Pendientes/ })).findByText("6")).toBeInTheDocument();
    expect(within(screen.getByRole("tab", { name: /Publicadas/ })).getByText("3")).toBeInTheDocument();
    expect(within(screen.getByRole("tab", { name: /Todas/ })).getByText("9")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /En preparación/ })).not.toBeInTheDocument();
    // El title habla de PIEZAS (unidad canónica), pluralizado de verdad (nada de "1 ideas").
    expect(within(screen.getByRole("tab", { name: /Pendientes/ })).getByTitle("6 piezas")).toBeInTheDocument();
    // El NOMBRE ACCESIBLE incluye el conteo con su unidad ("Pendientes 6 piezas"): el
    // aria-label que lo pisaba ya no existe.
    expect(screen.getByRole("tab", { name: /Pendientes.*6 piezas/ })).toBeInTheDocument();
  });

  it("vista filtrada: 'Pendientes' enseña SOLO las piezas que cumplen (sin tarjetas ajenas ni huecos)", async () => {
    // Una IDEA (c1) con dos piezas: en revisión (X) y publicada (Instagram). El stub filtra por
    // estado= como el backend: la vista dedicada 'Pendientes' solo recibe la pieza no publicada.
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
          const lista = todas.filter((p) => casaEstado(estado, p.estado));
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
    // Arranca en 'Todas' (el default ahora es 'Pendientes', que ocultaría la publicada).
    renderFeed({}, "/?vista=todo");
    // 'Todas' (matriz por idea): ambas tarjetas.
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    expect(screen.getByText("Ya publicada")).toBeInTheDocument();
    // 'Pendientes': solo la pieza en revisión; la publicada y los huecos no se pintan.
    fireEvent.mouseDown(screen.getByRole("tab", { name: /Pendientes/ }), { button: 0 });
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Ya publicada")).not.toBeInTheDocument());
    expect(screen.queryByText("No generado")).not.toBeInTheDocument();
  });

  it("vista dedicada 'Pendientes': scroll infinito encadenando páginas del servidor por cursor", async () => {
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

    // 'Pendientes' va con consulta DEDICADA (estado=pendiente): el SERVIDOR pagina por cursor,
    // sin filtrar listas enteras en cliente. Página 1: una pieza no publicada + cursor. Página
    // 2: otra, última. Ambas deben verse al encadenar.
    const SEGUNDA = {
      ...PUBLICACION,
      id: "p2",
      contenido_id: "c2",
      contenido: "Segunda en cola",
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
              JSON.stringify({ publicaciones: [SEGUNDA], paginacion: { total: 2, limite: 1, desplazamiento: 0 } }),
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

    renderFeed({}, "/?vista=pendiente");
    // El servidor ya filtró: la primera pieza se pinta directa, sin rastreo en cliente.
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    expect(screen.queryByText("Buscando piezas…")).not.toBeInTheDocument();
    // El sentinel sigue montado: al intersecar pide la página siguiente (?cursor=) y la pinta.
    await waitFor(() => expect(disparadores.length).toBeGreaterThan(0));
    disparadores[disparadores.length - 1]();
    expect(await screen.findByText("Segunda en cola")).toBeInTheDocument();
    // Las dos peticiones del FEED (feed=1) llevaron el pseudo-estado de la vista; la 2ª, el
    // cursor. (Las consultas de conteo de badges, con limite=1, van por su lado.)
    const peticionesFeed = urls.filter((u) => u.includes("feed=1"));
    expect(peticionesFeed.length).toBeGreaterThanOrEqual(2);
    expect(peticionesFeed.every((u) => u.includes("estado=pendiente"))).toBe(true);
    expect(peticionesFeed.some((u) => u.includes("cursor="))).toBe(true);
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
      expect(screen.getByPlaceholderText(/escribe un comentario/i)).toBeInTheDocument(),
    );
  });

  it("«Crear post»: abre el diálogo y aporta el material pegado a /api/contenido/aportar (la IA redacta)", async () => {
    stubFetch();
    renderFeed();
    // El botón de alta vive en las acciones de página (en tests, render inline sin AppShell).
    fireEvent.click(await screen.findByRole("button", { name: /crear post/i }));
    const dialogo = await screen.findByRole("dialog");
    // La marca llega sola (la activa del perfil: unotv) y las redes por defecto se acotan
    // al catálogo (aquí solo "x"); el humano solo pega el material y la IA redacta el copy.
    fireEvent.change(within(dialogo).getByLabelText("Material"), {
      target: { value: "Una nota cruda del equipo desde la grada" },
    });
    fireEvent.click(within(dialogo).getByRole("button", { name: "Crear post" }));
    await waitFor(() => {
      const llamada = vi
        .mocked(globalThis.fetch)
        .mock.calls.find((c) => String(c[0]).includes("/api/contenido/aportar"));
      expect(llamada).toBeTruthy();
      const init = llamada?.[1] as RequestInit | undefined;
      expect(init?.method).toBe("POST");
      // El alta creativa va como multipart (FormData), no JSON: puede traer una imagen.
      const cuerpo = init?.body as FormData;
      expect(cuerpo).toBeInstanceOf(FormData);
      expect(cuerpo.get("material")).toBe("Una nota cruda del equipo desde la grada");
      expect(cuerpo.get("marca")).toBe("unotv");
      expect(cuerpo.get("redes")).toBe("x");
    });
    // Al crear, el diálogo se cierra (el feed se refresca por invalidación de su query).
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
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
    // La franja "Por generar" es de la matriz completa (vista "Todas"), no de las filtradas.
    renderFeed({}, "/?vista=todo");
    // El post de la red generada (X).
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    // Franja compacta con SOLO Instagram (TikTok no es red de foto); sin placeholders gigantes.
    expect(screen.getByText("Por generar:")).toBeInTheDocument();
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
    // La franja "Por generar" es de la matriz completa (vista "Todas"), no de las filtradas.
    renderFeed({}, "/?vista=todo");
    expect(await screen.findByText("¡Increíble remontada!")).toBeInTheDocument();
    // El post (X) + UNA franja compacta con las 4 redes pendientes (sin placeholders gigantes).
    expect(screen.getByText("Por generar:")).toBeInTheDocument();
    for (const red of ["Instagram", "Facebook", "TikTok", "YouTube"]) {
      expect(screen.getByText(red)).toBeInTheDocument();
    }
    expect(screen.queryByText("No generado")).toBeNull();
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
    expect(await screen.findByText("Error al cargar más")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
    expect(screen.getByText("¡Increíble remontada!")).toBeInTheDocument();
    expect(screen.queryByText("Error al cargar")).not.toBeInTheDocument();
  });
});
