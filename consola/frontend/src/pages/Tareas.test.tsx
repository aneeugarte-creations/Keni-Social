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

/** Stub de fetch: GET /api/tareas devuelve el payload; el resto responde {}. */
function stubFetch(tareas = TAREAS, proyectos = PROYECTOS, usuarios = USUARIOS) {
  const fn = vi.fn(async (url: string | URL, init?: RequestInit) => {
    const ruta = String(url);
    const metodo = (init?.method ?? "GET").toUpperCase();
    if (ruta.includes("/api/tareas") && metodo === "GET") {
      return new Response(JSON.stringify({ tareas, proyectos, usuarios }), { status: 200 });
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

    // El primer proyecto de la allowlist se preselecciona al cargar; con título
    // y proyecto, el botón se habilita.
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

  it("avisa cuando no hay proyectos configurados", async () => {
    stubFetch(TAREAS, []);
    renderConProviders(<Tareas />);

    expect(await screen.findByText(/no hay proyectos configurados/i)).toBeInTheDocument();
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
