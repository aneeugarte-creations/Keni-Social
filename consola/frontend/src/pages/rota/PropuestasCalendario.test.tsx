import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as apiMod from "@/lib/api";
import type { Contenido } from "@/types";

import { PropuestasCalendario } from "./PropuestasCalendario";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

function tarea(over: Partial<Contenido> = {}): Contenido {
  return {
    id: "t1",
    clase: "tarea",
    flujo: "",
    titulo: "La Velada del Año VI",
    descripcion: "Estadio Santiago Bernabéu",
    marca: "claro-sports",
    marca_nombre: "Claro Sports",
    evento_id: "",
    programa: "",
    prioridad: "media",
    estado: "pendiente",
    fecha_objetivo: "2026-07-26",
    hora_objetivo: "20:00",
    fecha_entrega: "",
    responsable_id: "",
    responsable_nombre: "",
    autor_nombre: "",
    origen: "manual",
    notas: "",
    tipo_contenido: "ia",
    formato: "foto",
    vencido: false,
    plataformas: [],
    etiquetas: [],
    ...over,
  };
}

function montar(propuestas: Contenido[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PropuestasCalendario propuestas={propuestas} />
    </QueryClientProvider>,
  );
}

describe("PropuestasCalendario — bandeja de propuestas del calendario", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sin propuestas no pinta el icono (nada que notificar)", () => {
    montar([]);
    expect(screen.queryByRole("button", { name: /Propuestas de calendario/ })).toBeNull();
  });

  it("muestra el badge con el número y abre el cajón con título y fecha", async () => {
    montar([tarea(), tarea({ id: "t2", titulo: "Otra gala", fecha_objetivo: "2026-08-01" })]);
    const boton = screen.getByRole("button", { name: "Propuestas de calendario (2)" });
    fireEvent.click(boton);
    expect(await screen.findByText("La Velada del Año VI")).toBeTruthy();
    expect(screen.getByText(/2026-07-26/)).toBeTruthy();
    expect(screen.getByText("Otra gala")).toBeTruthy();
  });

  it("«Aceptar» promueve la propuesta (llama a aceptarContenido con su id)", async () => {
    const aceptar = vi
      .spyOn(apiMod.api, "aceptarContenido")
      .mockResolvedValue({ aceptada: true, evento: { id: "ev1" } } as never);
    montar([tarea({ id: "t-aceptar" })]);
    fireEvent.click(screen.getByRole("button", { name: /Propuestas de calendario/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Aceptar/ }));
    await waitFor(() => expect(aceptar).toHaveBeenCalledTimes(1));
    expect(aceptar).toHaveBeenCalledWith("t-aceptar");
  });

  it("«Descartar» borra la propuesta (llama a eliminarContenido con su id)", async () => {
    const eliminar = vi
      .spyOn(apiMod.api, "eliminarContenido")
      .mockResolvedValue({ mensaje: "ok" } as never);
    montar([tarea({ id: "t-descartar" })]);
    fireEvent.click(screen.getByRole("button", { name: /Propuestas de calendario/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Descartar/ }));
    await waitFor(() => expect(eliminar).toHaveBeenCalledTimes(1));
    expect(eliminar).toHaveBeenCalledWith("t-descartar");
  });
});
