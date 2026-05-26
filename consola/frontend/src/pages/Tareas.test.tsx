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

const TAREAS = [
  {
    id: "t1",
    proyecto: "keni-social",
    proyecto_nombre: "Keni Social",
    titulo: "Revisar copy de las 8",
    detalle: "Con la nota de portada.",
    estado: "pendiente",
    fecha: "2026-05-25T08:00:00Z",
  },
  {
    id: "t2",
    proyecto: "keni-social",
    proyecto_nombre: "Keni Social",
    titulo: "Programar reel",
    detalle: "",
    estado: "hecha",
    fecha: "2026-05-24T08:00:00Z",
  },
];

/** Stub de fetch: GET /api/tareas devuelve el payload; el resto responde {}. */
function stubFetch(tareas = TAREAS, proyectos = PROYECTOS) {
  const fn = vi.fn(async (url: string | URL, init?: RequestInit) => {
    const ruta = String(url);
    const metodo = (init?.method ?? "GET").toUpperCase();
    if (ruta.includes("/api/tareas") && metodo === "GET") {
      return new Response(JSON.stringify({ tareas, proyectos }), { status: 200 });
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

    // Barra de estatus compartida: 2 tareas, 1 pendiente, 1 hecha.
    const barra = screen.getByRole("status", { name: /resumen de tareas por estado/i });
    expect(within(barra).getByText("2 tareas")).toBeInTheDocument();
    expect(within(barra).getByText("1 pendiente")).toBeInTheDocument();
    expect(within(barra).getByText("1 hecha")).toBeInTheDocument();
  });

  it("muestra estado vacío cuando no hay tareas", async () => {
    stubFetch([]);
    renderConProviders(<Tareas />);

    expect(await screen.findByText("Sin pendientes")).toBeInTheDocument();
  });

  it("deshabilita 'Crear tarea' sin título y lo habilita al escribirlo", async () => {
    stubFetch();
    renderConProviders(<Tareas />);

    const boton = await screen.findByRole("button", { name: /crear tarea/i });
    expect(boton).toBeDisabled();

    // El primer proyecto de la allowlist se preselecciona al cargar; con título
    // y proyecto, el botón se habilita.
    fireEvent.change(screen.getByLabelText("Título"), {
      target: { value: "Nueva tarea de prueba" },
    });
    await waitFor(() => expect(boton).toBeEnabled());
  });

  it("alterna el estado de una tarea con un PATCH al backend", async () => {
    const fn = stubFetch();
    renderConProviders(<Tareas />);

    // El botón de la tarea pendiente la marca como hecha.
    const marcar = await screen.findByRole("button", { name: /marcar como hecha/i });
    fireEvent.click(marcar);

    await waitFor(() => {
      const patch = fn.mock.calls.find(
        ([url, init]) =>
          String(url).includes("/api/tareas/t1") &&
          (init?.method ?? "").toUpperCase() === "PATCH",
      );
      expect(patch).toBeTruthy();
      expect(JSON.parse(String((patch![1] as RequestInit).body))).toEqual({ estado: "hecha" });
    });
  });

  it("avisa cuando no hay proyectos configurados", async () => {
    stubFetch(TAREAS, []);
    renderConProviders(<Tareas />);

    expect(await screen.findByText(/no hay proyectos configurados/i)).toBeInTheDocument();
  });
});
