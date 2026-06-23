import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as apiMod from "@/lib/api";
import type { FranjaSemana, MiembroRota } from "@/types";

import { ReparteMes } from "./ReparteMes";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

// 2026-06-15 es lunes; las dos fechas caen en la MISMA semana (un solo grupo de franjas).
const FRANJA: FranjaSemana = {
  id: "f-m",
  lunes: "2026-06-15",
  nombre: "Mañana",
  inicio: "08:00",
  fin: "16:00",
  orden: 0,
  es_descanso: false,
  marca: "",
  marca_nombre: "",
};
const CMS: MiembroRota[] = [
  { id: "u-luis", nombre: "Luis" },
  { id: "u-ana", nombre: "Ana" },
];
const FRANJAS_POR_SEMANA = new Map([["2026-06-15", [FRANJA]]]);

function montar(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("ReparteMes — matriz editable por persona", () => {
  it("crea un turno por cada celda encendida (días marcados × persona), apagable por celda", async () => {
    const crear = vi.spyOn(apiMod.api, "crearTurno").mockResolvedValue({} as never);
    const onLimpiarDias = vi.fn();
    montar(
      <ReparteMes
        diasSel={new Set(["2026-06-15", "2026-06-16"])}
        cms={CMS}
        franjasPorSemana={FRANJAS_POR_SEMANA}
        onCambio={vi.fn()}
        onCerrar={vi.fn()}
        onLimpiarDias={onLimpiarDias}
      />,
    );
    // Sin persona elegida, «Asignar» está deshabilitado.
    expect(screen.getByRole("button", { name: "Asignar" })).toBeDisabled();

    // Elegir Luis: 2 días marcados × 1 persona = 2 turnos (todas las celdas ON por defecto).
    fireEvent.click(screen.getByRole("checkbox", { name: "Luis" }));
    expect(screen.getByRole("button", { name: "Asignar 2 turnos" })).toBeEnabled();

    // Apagar la celda de Luis del día 16 → su patrón baja a 1 día.
    fireEvent.click(screen.getByRole("checkbox", { name: "Luis 16" }));
    fireEvent.click(screen.getByRole("button", { name: "Asignar 1 turno" }));

    await waitFor(() => expect(crear).toHaveBeenCalledTimes(1));
    // La franja se resolvió por la semana de la fecha; horario = el de la franja ⇒ sin horas a medida.
    expect(crear).toHaveBeenCalledWith({
      lunes: "2026-06-15",
      fecha: "2026-06-15",
      miembro_id: "u-luis",
      franja_id: "f-m",
    });
    // Tras crear, limpia la selección de días para encadenar otra tanda.
    await waitFor(() => expect(onLimpiarDias).toHaveBeenCalled());
  });
});
