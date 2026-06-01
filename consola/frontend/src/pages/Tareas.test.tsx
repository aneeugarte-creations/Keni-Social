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

function stubFetch(contenidos = [contenido()]) {
  const fn = vi.fn(async (url: string | URL, init?: RequestInit) => {
    const ruta = String(url);
    const metodo = (init?.method ?? "GET").toUpperCase();
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

  it("muestra las secciones por flujo y la tarjeta con su plataforma", async () => {
    stubFetch();
    renderConProviders(<Tablero />);

    expect(await screen.findByRole("heading", { name: "Tablero de contenido" })).toBeInTheDocument();
    // Espera a que cargue el tablero (las secciones solo aparecen con datos).
    expect(await screen.findByText("Sismo CDMX")).toBeInTheDocument();
    expect(screen.getByText("Importante del día")).toBeInTheDocument();
    expect(screen.getByText("Evergreen")).toBeInTheDocument();
    expect(screen.getByText("Eventos previstos")).toBeInTheDocument();
    // La fila por plataforma muestra la red y su checklist.
    expect(screen.getByText("X")).toBeInTheDocument();
    expect(screen.getByLabelText("Copy")).toBeInTheDocument();
  });

  it("muestra estado vacío cuando el tablero no tiene contenido", async () => {
    stubFetch([]);
    renderConProviders(<Tablero />);
    expect(await screen.findByText("Tablero vacío")).toBeInTheDocument();
  });

  it("marca un check del checklist con un PATCH a la plataforma", async () => {
    const fn = stubFetch();
    renderConProviders(<Tablero />);

    const check = await screen.findByLabelText("Copy");
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

  it("vencido resalta el deadline", async () => {
    stubFetch([contenido({ fecha_entrega: "2000-01-01", vencido: true })]);
    renderConProviders(<Tablero />);
    expect(await screen.findByText(/venció/i)).toBeInTheDocument();
  });

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
    await screen.findByText("Sismo CDMX");

    // Cambia a la vista Feed.
    fireEvent.click(screen.getByRole("button", { name: "Feed" }));

    // Una preview por red: aparecen los iconos de X e Instagram (etiqueta accesible).
    expect(await screen.findByLabelText("Instagram")).toBeInTheDocument();
    expect(screen.getByLabelText("X")).toBeInTheDocument();
    // Y el copy de cada red.
    expect(screen.getByText(/Hola X/)).toBeInTheDocument();
    expect(screen.getByText(/Hola IG/)).toBeInTheDocument();
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
