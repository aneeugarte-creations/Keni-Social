import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as apiMod from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { FranjaSemana, MiembroRota } from "@/types";

import { DialogoAsignarTurnos, asignarDiasTurno } from "./DialogoAsignarTurnos";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

// El reparto día-a-día es la lógica clave; se prueba aparte de los Select de Radix (que dentro
// de un Dialog se cuelgan en jsdom), por eso `asignarDiasTurno` está extraído del componente.
describe("asignarDiasTurno — reparte un turno por día y clasifica el resultado", () => {
  it("crea / ya-estaba (409) / sábado-override (409) / fallo, en ese orden", async () => {
    const crear = vi
      .spyOn(apiMod.api, "crearTurno")
      .mockResolvedValueOnce({} as never) // creado
      .mockRejectedValueOnce(new ApiError("dup", 409, { id: "x" })) // ya estaba
      .mockRejectedValueOnce(new ApiError("sáb", 409, { requiere_override: true })) // sábado
      .mockRejectedValueOnce(new Error("red")); // fallo
    const r = await asignarDiasTurno("2026-06-15", "u-luis", "f-manana", [
      "2026-06-15",
      "2026-06-16",
      "2026-06-20",
      "2026-06-17",
    ]);
    expect(crear).toHaveBeenCalledTimes(4);
    expect(r).toEqual({ creados: 1, yaEstaba: 1, sabados: 1, fallos: 1 });
    expect(crear).toHaveBeenCalledWith({
      lunes: "2026-06-15",
      fecha: "2026-06-15",
      miembro_id: "u-luis",
      franja_id: "f-manana",
    });
  });

  it("sin fechas seleccionadas no llama a la API", async () => {
    const crear = vi.spyOn(apiMod.api, "crearTurno").mockResolvedValue({} as never);
    const r = await asignarDiasTurno("2026-06-15", "u-luis", "f-manana", []);
    expect(crear).not.toHaveBeenCalled();
    expect(r).toEqual({ creados: 0, yaEstaba: 0, sabados: 0, fallos: 0 });
  });
});

const FRANJAS: FranjaSemana[] = [
  {
    id: "f-manana",
    lunes: "2026-06-15",
    nombre: "Mañana",
    inicio: "08:00",
    fin: "14:00",
    orden: 0,
    es_descanso: false,
    marca: "",
    marca_nombre: "",
  },
];
const CMS: MiembroRota[] = [{ id: "u-luis", nombre: "Luis" }];
const DIAS = ["2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18", "2026-06-19", "2026-06-20", "2026-06-21"];

describe("DialogoAsignarTurnos (render)", () => {
  it("«Asignar» está deshabilitado hasta elegir persona y franja; ofrece import automático", () => {
    // El diálogo embebe «Importar documento» (su badge sondea propuestas pendientes).
    vi.spyOn(apiMod.api, "propuestasParrilla").mockResolvedValue({ propuestas: [] } as never);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <DialogoAsignarTurnos
          abierto
          onOpenChange={vi.fn()}
          lunes="2026-06-15"
          dias={DIAS}
          franjas={FRANJAS}
          cms={CMS}
          onCambio={vi.fn()}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByText("Asignar turnos")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Asignar" })).toBeDisabled();
    // La vía automática (import) está disponible dentro del mismo diálogo.
    expect(screen.getByRole("button", { name: /Importar documento/ })).toBeInTheDocument();
  });
});
