import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Tareas from "./Tareas";

const PROYECTOS = [
  { id: "keni-social", nombre: "Keni Social", existe: true },
  { id: "viejo", nombre: "Proyecto viejo", existe: false },
];

const USUARIOS = [
  { id: "u1", usuario: "ana" },
  { id: "u2", usuario: "luis" },
];

const TAREAS = [
  {
    id: "t1",
    proyecto: "keni-social",
    proyecto_nombre: "Keni Social",
    proyecto_existe: true,
    titulo: "Revisar copy de las 8",
    detalle: "Con la nota de portada.",
    estado: "pendiente",
    fecha: "2026-05-25T08:00:00Z",
    autor_id: "u1",
    autor_nombre: "ana",
    responsable_id: "u2",
    responsable_nombre: "luis",
    enlace: "/asistente?skill=copy",
  },
  {
    id: "t2",
    proyecto: "keni-social",
    proyecto_nombre: "Keni Social",
    proyecto_existe: true,
    titulo: "Programar reel",
    detalle: "",
    estado: "hecha",
    fecha: "2026-05-24T08:00:00Z",
    autor_id: "u1",
    autor_nombre: "ana",
    responsable_id: "",
    responsable_nombre: "",
    enlace: "",
  },
];

const EVENTOS_SIN_CUBRIR: {
  id: string;
  titulo: string;
  fecha: string;
  hora: string;
  contenido: string;
  tipo_cobertura: "transmision" | "imagenes" | "no_cubrir";
  prioridad: "alta" | "media" | "baja";
}[] = [];

/** Stub de fetch: GET /api/tareas devuelve el payload; el resto responde {}. */
function stubFetch(
  tareas = TAREAS,
  proyectos = PROYECTOS,
  usuarios = USUARIOS,
  eventos_sin_cubrir = EVENTOS_SIN_CUBRIR,
) {
  const fn = vi.fn(async (url: string | URL, init?: RequestInit) => {
    const ruta = String(url);
    const metodo = (init?.method ?? "GET").toUpperCase();
    if (ruta.includes("/api/tareas") && metodo === "GET") {
      return new Response(
        JSON.stringify({ tareas, proyectos, usuarios, eventos_sin_cubrir }),
        { status: 200 },
      );
    }
    if (ruta.includes("/api/tareas") && metodo === "POST") {
      return new Response(JSON.stringify({ tarea: tareas[0] }), { status: 200 });
    }
    if (ruta.includes("/api/tareas") && metodo === "PATCH") {
      return new Response(JSON.stringify({ tarea: tareas[0] }), { status: 200 });
    }
    return new Response("{}", { status: 200 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Tareas (vista de pendientes)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lista las tareas y muestra la barra de estatus con el recuento por estado", async () => {
    stubFetch();
    renderConProviders(<Tareas />);

    expect(await screen.findByRole("heading", { name: "Pendientes" })).toBeInTheDocument();
    expect(await screen.findByText("Revisar copy de las 8")).toBeInTheDocument();
    expect(screen.getByText("Programar reel")).toBeInTheDocument();

    // Barra de estatus compartida: 2 pendientes, 1 pendiente, 0 en curso, 1 hecha.
    const barra = screen.getByRole("status", { name: /resumen de tareas por estado/i });
    expect(within(barra).getByText("2 pendientes")).toBeInTheDocument();
    expect(within(barra).getByText("1 pendiente")).toBeInTheDocument();
    expect(within(barra).getByText("0 en curso")).toBeInTheDocument();
    expect(within(barra).getByText("1 hecha")).toBeInTheDocument();
  });

  it("muestra el responsable y el enlace de acción de un pendiente", async () => {
    stubFetch();
    renderConProviders(<Tareas />);

    // La tarjeta de t1 lleva responsable "luis" (en su selector) y un enlace de acción.
    await screen.findByText("Revisar copy de las 8");
    expect(screen.getByRole("link", { name: /abrir enlace de acción/i })).toHaveAttribute(
      "href",
      "/asistente?skill=copy",
    );
    // El selector de responsable de t1 muestra a luis (el asignado).
    expect(screen.getAllByText("luis").length).toBeGreaterThan(0);
  });

  it("muestra estado vacío cuando no hay tareas", async () => {
    stubFetch([]);
    renderConProviders(<Tareas />);

    expect(await screen.findByText("Sin pendientes")).toBeInTheDocument();
  });

  it("deshabilita 'Crear pendiente' sin título y lo habilita al escribirlo", async () => {
    stubFetch();
    renderConProviders(<Tareas />);

    const boton = await screen.findByRole("button", { name: /crear pendiente/i });
    expect(boton).toBeDisabled();

    // Proyecto es OPCIONAL: basta con escribir un título para habilitar el botón.
    fireEvent.change(screen.getByLabelText("Título"), {
      target: { value: "Nueva tarea de prueba" },
    });
    await waitFor(() => expect(boton).toBeEnabled());
  });

  it("avanza el estado de un pendiente con un PATCH al backend (pendiente -> en curso)", async () => {
    const fn = stubFetch();
    renderConProviders(<Tareas />);

    // El pendiente t1 (pendiente) avanza a "en curso" al pulsar su botón de ciclo.
    const avanzar = await screen.findByRole("button", { name: /pasar a en curso/i });
    fireEvent.click(avanzar);

    await waitFor(() => {
      const patch = fn.mock.calls.find(
        ([url, init]) =>
          String(url).includes("/api/tareas/t1") &&
          (init?.method ?? "").toUpperCase() === "PATCH",
      );
      expect(patch).toBeTruthy();
      expect(JSON.parse(String((patch![1] as RequestInit).body))).toEqual({ estado: "en_curso" });
    });
  });

  it("permite crear un pendiente sin proyecto cuando la allowlist está vacía", async () => {
    const fn = stubFetch(TAREAS, []);
    renderConProviders(<Tareas />);

    // Sin proyectos: el formulario sigue disponible y el campo Proyecto queda
    // en "(sin proyecto)". Con título basta para habilitar "Crear pendiente".
    const titulo = await screen.findByLabelText("Título");
    fireEvent.change(titulo, { target: { value: "Pendiente libre" } });
    const boton = screen.getByRole("button", { name: /crear pendiente/i });
    await waitFor(() => expect(boton).toBeEnabled());
    fireEvent.click(boton);

    await waitFor(() => {
      const post = fn.mock.calls.find(
        ([url, init]) =>
          String(url).includes("/api/tareas") &&
          (init?.method ?? "").toUpperCase() === "POST",
      );
      expect(post).toBeTruthy();
      const cuerpo = JSON.parse(String((post![1] as RequestInit).body));
      expect(cuerpo.titulo).toBe("Pendiente libre");
      expect(cuerpo.proyecto).toBe("");
      expect(cuerpo.evento_id).toBeUndefined();
    });
  });

  it("muestra eventos sin cubrir y, al hacer clic, prepopula el formulario", async () => {
    const eventos = [
      {
        id: "ev1",
        titulo: "Cruz Azul vs Tigres",
        fecha: "2026-05-29",
        hora: "21:00",
        contenido: "Partido amistoso",
        tipo_cobertura: "transmision" as const,
        prioridad: "alta" as const,
      },
    ];
    stubFetch(TAREAS, PROYECTOS, USUARIOS, eventos);
    renderConProviders(<Tareas />);

    // Sección "Eventos sin cubrir" aparece arriba con el chip del evento.
    expect(
      await screen.findByText(/eventos sin cubrir esta semana y la siguiente/i),
    ).toBeInTheDocument();
    const chip = screen.getByRole("button", { name: /cruz azul vs tigres/i });
    fireEvent.click(chip);

    // El título del formulario se rellena con "Cubrir: ...".
    const titulo = screen.getByLabelText("Título") as HTMLInputElement;
    await waitFor(() => {
      expect(titulo.value).toContain("Cruz Azul vs Tigres");
      expect(titulo.value).toContain("2026-05-29");
    });
  });

  it("filtra los pendientes por proyecto", async () => {
    // Dos proyectos, una tarea en cada uno.
    const proyectos = [
      { id: "p-a", nombre: "Proyecto A", existe: true },
      { id: "p-b", nombre: "Proyecto B", existe: true },
    ];
    const tareas = [
      { ...TAREAS[0], id: "ta", proyecto: "p-a", titulo: "De A", estado: "pendiente" },
      { ...TAREAS[0], id: "tb", proyecto: "p-b", titulo: "De B", estado: "pendiente" },
    ];
    stubFetch(tareas, proyectos);
    renderConProviders(<Tareas />);

    // Sin filtro se ven ambas.
    expect(await screen.findByText("De A")).toBeInTheDocument();
    expect(screen.getByText("De B")).toBeInTheDocument();

    // Filtrar a "Proyecto A" deja solo su pendiente.
    fireEvent.click(screen.getByRole("combobox", { name: /filtrar por proyecto/i }));
    fireEvent.click(await screen.findByRole("option", { name: "Proyecto A" }));
    await waitFor(() => expect(screen.queryByText("De B")).not.toBeInTheDocument());
    expect(screen.getByText("De A")).toBeInTheDocument();
  });
});
