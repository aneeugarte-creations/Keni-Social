import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import type { UsuarioSesion } from "@/types";

import Tablero from "./Tareas";

const CATALOGOS = {
  usuarios: [
    { id: "u1", usuario: "ana" },
    { id: "u2", usuario: "luis" },
  ],
  marcas: [
    { id: "unotv", nombre: "UnoTV" },
    { id: "claro-sports", nombre: "Claro Sports" },
  ],
  redes: [
    { id: "x", nombre: "X", limite: 280 },
    { id: "instagram", nombre: "Instagram", limite: 2200 },
    { id: "web", nombre: "Web", limite: null },
  ],
  flujos: ["importante", "evergreen", "evento"],
  prioridades: ["alta", "media", "baja"],
  estados_contenido: ["pendiente", "en_curso", "hecha"],
  estados_plataforma: ["pendiente", "en_curso", "en_revision", "aprobado", "programado", "publicado"],
  eventos: [],
};

function contenido(over: Record<string, unknown> = {}) {
  return {
    id: "c1",
    clase: "contenido",
    flujo: "importante",
    titulo: "Sismo CDMX",
    descripcion: "",
    marca: "unotv",
    marca_nombre: "UnoTV",
    evento_id: "",
    programa: "",
    prioridad: "alta",
    estado: "pendiente",
    fecha_objetivo: "",
    hora_objetivo: "",
    fecha_entrega: "",
    responsable_id: "",
    responsable_nombre: "",
    autor_nombre: "ana",
    origen: "manual",
    notas: "",
    tipo_contenido: "ia",
    vencido: false,
    plataformas: [
      {
        id: "p1",
        contenido_id: "c1",
        red: "x",
        red_nombre: "X",
        estado: "pendiente",
        falta_copy: true,
        falta_imagen: true,
        falta_revision: true,
        falta_publicar: true,
        copy: "",
        imagen: "",
        imagen_fuente: "",
        foto: "",
        imagen_url: "",
        veredicto: "",
        fecha_programada: "",
        hora_post: "",
        enlace: "",
        evergreen: false,
      },
    ],
    ...over,
  };
}

// Estados que devuelve `/api/publicaciones/opciones` (los que espera el editor unificado).
const ESTADOS_PUB = [
  { id: "borrador", nombre: "Borrador" },
  { id: "en_revision", nombre: "En revisión" },
  { id: "aprobado", nombre: "Aprobado" },
  { id: "programado", nombre: "Programado" },
  { id: "publicado", nombre: "Publicado" },
];

// Forma `Publicacion` que devuelve `GET /api/publicaciones/{id}` (id = id de la plataforma,
// p.ej. "p1"). El editor rico (`DialogoEditar`) la carga al abrirse desde el feed. Por
// defecto la pieza tiene TODO en falta (falta_copy/imagen/revision/publicar = true), de modo
// que marcar un check del checklist lo pone a `false`.
function publicacion(over: Record<string, unknown> = {}) {
  return {
    id: "p1",
    contenido_id: "c1",
    titulo: "Sismo CDMX",
    marca: "unotv",
    marca_nombre: "UnoTV",
    red: "x",
    red_nombre: "X",
    contenido: "",
    copy_in: "",
    estado: "borrador",
    veredicto: "",
    autor_id: "",
    autor_nombre: "ana",
    enviado_a_revision_en: "",
    revisor_id: "",
    revisor_nombre: "",
    revisado_en: "",
    preparado_en: "",
    id_post_metricool: "",
    falta_copy: true,
    falta_imagen: true,
    falta_revision: true,
    falta_publicar: true,
    fecha_creacion: "",
    fecha_actualizacion: "",
    fecha_programada: "",
    origen: "manual",
    imagen: "",
    imagen_url: "",
    evergreen: false,
    // Etapa real del backend (Flujo C): borrador sin copy -> generando_copy.
    etapa_ia: "generando_copy",
    ...over,
  };
}

// `pubs` mapea id de plataforma → la `Publicacion` que servirá `GET /api/publicaciones/{id}`.
function stubFetch(contenidos = [contenido()], pubs: Record<string, ReturnType<typeof publicacion>> = {}) {
  const fn = vi.fn(async (url: string | URL, init?: RequestInit) => {
    const ruta = String(url);
    const metodo = (init?.method ?? "GET").toUpperCase();
    // El editor unificado pide opciones + la publicación por id; estas rutas son MÁS
    // específicas que `/api/contenido`, así que se chequean ANTES para no colisionar.
    if (ruta.includes("/api/publicaciones/opciones") && metodo === "GET") {
      return new Response(
        JSON.stringify({ estados: ESTADOS_PUB, marcas: CATALOGOS.marcas, redes: CATALOGOS.redes }),
        { status: 200 },
      );
    }
    const matchPub = ruta.match(/\/api\/publicaciones\/([^/?]+)/);
    if (matchPub && metodo === "GET") {
      const id = decodeURIComponent(matchPub[1]);
      return new Response(JSON.stringify({ publicacion: pubs[id] ?? publicacion({ id }) }), {
        status: 200,
      });
    }
    if (ruta.includes("/api/contenido") && metodo === "GET") {
      return new Response(JSON.stringify({ contenidos, catalogos: CATALOGOS }), { status: 200 });
    }
    if (ruta.includes("/api/contenido") && metodo === "POST") {
      return new Response(JSON.stringify({ contenido: contenido() }), { status: 200 });
    }
    if (ruta.includes("/api/contenido") && metodo === "PATCH") {
      return new Response(JSON.stringify({ plataforma: contenido().plataformas[0] }), { status: 200 });
    }
    return new Response("{}", { status: 200 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function usuarioConMarcas(marcas: string[]): UsuarioSesion {
  return {
    id: "u1",
    usuario: "ana",
    rol: "editor",
    debe_cambiar_password: false,
    marcas,
  };
}

function sesionValor(usuario: UsuarioSesion | null): ValorSesion {
  return {
    usuario,
    cargando: false,
    iniciarSesion: vi.fn(),
    cerrarSesion: vi.fn(),
    refrescar: vi.fn(),
  };
}

// Por defecto, usuario MULTIMARCA => el workspace arranca en "Todas" (comportamiento
// histórico de estos tests). Los casos de marca por defecto pasan un usuario monomarca.
function renderConProviders(
  ui: React.ReactElement,
  { usuario = usuarioConMarcas(["unotv", "claro-sports"]) }: { usuario?: UsuarioSesion | null } = {},
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesionValor(usuario)}>
        <MemoryRouter>{ui}</MemoryRouter>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("Tablero de contenido", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    // El workspace se persiste en localStorage; un stub en memoria por test lo aísla
    // (jsdom no expone un localStorage completo aquí).
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("muestra el feed por red y el filtro de flujo", async () => {
    stubFetch();
    renderConProviders(<Tablero />);

    expect(await screen.findByRole("heading", { name: "Tablero de contenido" })).toBeInTheDocument();
    // La vista por defecto es el FEED: la pieza se ve a través de su preview por red. Con el
    // copy vacío, la preview cae al título del contenido ("Sismo CDMX").
    expect(await screen.findByText("Sismo CDMX")).toBeInTheDocument();
    // El flujo ya no son secciones (Importante/Evergreen/Eventos): es un FILTRO (#fusion).
    expect(screen.getByLabelText("Filtrar por flujo")).toBeInTheDocument();
  });

  it("muestra estado vacío cuando el tablero no tiene contenido", async () => {
    stubFetch([]);
    renderConProviders(<Tablero />);
    expect(await screen.findByText("Tablero vacío")).toBeInTheDocument();
  });

  it("marca un check del checklist con un PATCH a la plataforma", async () => {
    // El checklist por red ya no vive en la tarjeta de lista: está en el editor unificado
    // (`DialogoEditar`), que se abre al hacer click en la preview del feed.
    const fn = stubFetch();
    renderConProviders(<Tablero />);

    // Abre el editor desde la preview del feed (un <button> con el texto de la pieza).
    const preview = (await screen.findByText("Sismo CDMX")).closest("button");
    expect(preview).not.toBeNull();
    fireEvent.click(preview!);

    // El editor carga la publicación; el checklist está en la pestaña "Editar".
    // Radix Tabs activa con `mousedown` (botón 0), no con `click`.
    const dialogo = await screen.findByRole("dialog");
    fireEvent.mouseDown(within(dialogo).getByRole("tab", { name: "Editar" }), { button: 0 });
    const check = await within(dialogo).findByLabelText("Copy");
    fireEvent.click(check);

    await waitFor(() => {
      const patch = fn.mock.calls.find(
        ([url, init]) =>
          String(url).includes("/api/contenido/c1/plataformas/p1") &&
          (init?.method ?? "").toUpperCase() === "PATCH",
      );
      expect(patch).toBeTruthy();
      // Marcar "Copy" como hecho => falta_copy false.
      expect(JSON.parse(String((patch![1] as RequestInit).body))).toEqual({ falta_copy: false });
    });
  });

  it("abre el diálogo de nuevo contenido y crea con POST", async () => {
    const fn = stubFetch();
    renderConProviders(<Tablero />);

    // El botón se habilita al cargar el tablero (y el diálogo necesita catálogos).
    await screen.findByText("Sismo CDMX");
    fireEvent.click(screen.getByRole("button", { name: /nuevo contenido/i }));
    const dialogo = await screen.findByRole("dialog");
    fireEvent.change(within(dialogo).getByLabelText("Título"), {
      target: { value: "Nueva nota" },
    });
    fireEvent.click(within(dialogo).getByRole("button", { name: /^crear$/i }));

    await waitFor(() => {
      const post = fn.mock.calls.find(
        ([url, init]) =>
          String(url).includes("/api/contenido") &&
          (init?.method ?? "").toUpperCase() === "POST",
      );
      expect(post).toBeTruthy();
      expect(JSON.parse(String((post![1] as RequestInit).body)).titulo).toBe("Nueva nota");
    });
  });

  // NOTA: el test "vencido resalta el deadline" se ELIMINÓ (pérdida aceptada). El display de
  // vencido ("Venció …") vivía en la tarjeta de lista del tablero (TarjetaContenido), que ya
  // NO se renderiza en la superficie única: el feed muestra previews por red (VistaPreviaRed),
  // sin badge de deadline. No hay equivalente en esta superficie, así que no se reescribe.

  it("usuario MONOMARCA: el workspace arranca aislado en su marca y filtra el resto", async () => {
    stubFetch([
      contenido(),
      contenido({ id: "c2", titulo: "Final Champions", marca: "claro-sports", marca_nombre: "Claro Sports" }),
    ]);
    renderConProviders(<Tablero />, { usuario: usuarioConMarcas(["unotv"]) });

    // Su marca (unotv) se ve; la otra marca queda fuera del workspace por defecto.
    expect(await screen.findByText("Sismo CDMX")).toBeInTheDocument();
    expect(screen.queryByText("Final Champions")).not.toBeInTheDocument();
  });

  it("permite editar la IMAGEN por plataforma (generar IA / adjuntar)", async () => {
    // La edición de imagen vive ahora en el editor unificado (`DialogoEditar` → pestaña
    // "Editar"), no en la tarjeta de lista. Se abre con click en la preview del feed.
    stubFetch();
    renderConProviders(<Tablero />);

    const preview = (await screen.findByText("Sismo CDMX")).closest("button");
    fireEvent.click(preview!);

    // Radix Tabs activa con `mousedown` (botón 0), no con `click`.
    const dialogo = await screen.findByRole("dialog");
    fireEvent.mouseDown(within(dialogo).getByRole("tab", { name: "Editar" }), { button: 0 });
    // Sin imagen aún (falta_imagen): el editor ofrece generar con IA o adjuntar.
    expect(await within(dialogo).findByRole("button", { name: /Generar con IA/i })).toBeInTheDocument();
    expect(within(dialogo).getByLabelText("Adjuntar imagen")).toBeInTheDocument();
  });

  // NOTA: el test "tipo 'fuente': el editor de imagen pide la URL de la fuente original" se
  // ELIMINÓ (pérdida aceptada). Ese flujo (pegar la URL `imagen_fuente` del artículo original,
  // placeholder `https://…/imagen-del-articulo.jpg`) vivía en el editor de imagen POR PLATAFORMA
  // de la tarjeta de lista, que ya no se renderiza. El editor de imagen del `DialogoEditar`
  // unificado (`EditorImagen`) NO depende de `tipo_contenido` ni tiene modo 'fuente': solo
  // adjunta archivo o genera con IA. No hay equivalente, así que no se reescribe.

  it("modo Feed: una vista previa POR RED (no una por pieza)", async () => {
    stubFetch([
      contenido({
        plataformas: [
          { ...contenido().plataformas[0], id: "p1", red: "x", red_nombre: "X", copy: "Hola X" },
          {
            ...contenido().plataformas[0],
            id: "p2",
            red: "instagram",
            red_nombre: "Instagram",
            copy: "Hola IG",
          },
        ],
      }),
    ]);
    renderConProviders(<Tablero />);

    // El feed es la vista por defecto: una columna por red (X e Instagram), cada una con el
    // copy de esa red en su mockup fiel de plataforma. Con copy definido, NO se muestra el
    // título ("Sismo CDMX") sino el copy de cada red.
    expect(await screen.findByText(/Hola X/)).toBeInTheDocument();
    expect(screen.getByText(/Hola IG/)).toBeInTheDocument();
    // Cada preview es un botón clicable que abre el detalle de la pieza.
    expect(screen.getByText(/Hola X/).closest("button")).not.toBeNull();
  });

  it("usuario MULTIMARCA: el workspace arranca en Todas (ve ambas marcas)", async () => {
    stubFetch([
      contenido(),
      contenido({ id: "c2", titulo: "Final Champions", marca: "claro-sports", marca_nombre: "Claro Sports" }),
    ]);
    renderConProviders(<Tablero />, { usuario: usuarioConMarcas(["unotv", "claro-sports"]) });

    expect(await screen.findByText("Sismo CDMX")).toBeInTheDocument();
    expect(screen.getByText("Final Champions")).toBeInTheDocument();
  });
});
