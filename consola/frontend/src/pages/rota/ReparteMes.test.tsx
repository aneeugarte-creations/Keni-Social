import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { toast } from "sonner";

import { confirmar } from "@/components/comunes/confirmar";
import * as apiMod from "@/lib/api";
import type { FranjaSemana, MiembroRota, TurnoRota } from "@/types";

import { ReparteMes } from "./ReparteMes";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));
vi.mock("@/components/comunes/confirmar", () => ({ confirmar: vi.fn() }));

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

function turno(over: Partial<TurnoRota> = {}): TurnoRota {
  return {
    id: "t-1",
    semana: "2026-06-15",
    fecha: "2026-06-15",
    miembro_id: "u-luis",
    miembro_nombre: "Luis",
    franja_id: "f-m",
    franja_nombre: "Mañana",
    franja: "matutino",
    inicio: "08:00",
    fin: "16:00",
    horario_propio: false,
    estado: "aprobado",
    override: false,
    motivo: "",
    nota_relevo: "",
    es_sabado: false,
    marca: "",
    marca_nombre: "",
    ...over,
  };
}

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
        turnosExistentes={new Map()}
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

  it("marca un turno real para quitar → confirma y lo borra por lote, con Deshacer", async () => {
    vi.mocked(confirmar).mockResolvedValue(true);
    const borrar = vi.spyOn(apiMod.api, "borrarTurnosLote").mockResolvedValue({
      borrados: 1,
      no_encontrados: [],
    } as never);
    const onLimpiarDias = vi.fn();
    montar(
      <ReparteMes
        diasSel={new Set(["2026-06-15"])}
        cms={CMS}
        franjasPorSemana={FRANJAS_POR_SEMANA}
        turnosExistentes={new Map([["u-luis|2026-06-15", [turno()]]])}
        onCambio={vi.fn()}
        onCerrar={vi.fn()}
        onLimpiarDias={onLimpiarDias}
      />,
    );
    // Con Luis elegido, su celda del 15 es un TURNO REAL: no es alta, así que «Asignar» sigue inerte.
    fireEvent.click(screen.getByRole("checkbox", { name: "Luis" }));
    expect(screen.getByRole("button", { name: "Asignar" })).toBeDisabled();

    // Tocar el turno real abre su editor de hora; «Quitar turno» lo marca → «Quitar 1 turno».
    fireEvent.click(screen.getByRole("checkbox", { name: "Luis 15" }));
    fireEvent.click(screen.getByRole("button", { name: "Quitar turno" }));
    fireEvent.click(screen.getByRole("button", { name: "Quitar 1 turno" }));

    // Pasa por la confirmación destructiva y borra por lote el id del turno.
    await waitFor(() => expect(confirmar).toHaveBeenCalled());
    await waitFor(() => expect(borrar).toHaveBeenCalledWith({ ids: ["t-1"] }));
    // Avisa con un toast que ofrece Deshacer.
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringContaining("borrado"),
        expect.objectContaining({ action: expect.objectContaining({ label: "Deshacer" }) }),
      ),
    );
    await waitFor(() => expect(onLimpiarDias).toHaveBeenCalled());
  });

  it("no borra nada si se cancela la confirmación", async () => {
    vi.mocked(confirmar).mockResolvedValue(false);
    const borrar = vi.spyOn(apiMod.api, "borrarTurnosLote").mockResolvedValue({
      borrados: 0,
      no_encontrados: [],
    } as never);
    montar(
      <ReparteMes
        diasSel={new Set(["2026-06-15"])}
        cms={CMS}
        franjasPorSemana={FRANJAS_POR_SEMANA}
        turnosExistentes={new Map([["u-luis|2026-06-15", [turno()]]])}
        onCambio={vi.fn()}
        onCerrar={vi.fn()}
        onLimpiarDias={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "Luis" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Luis 15" }));
    fireEvent.click(screen.getByRole("button", { name: "Quitar turno" }));
    fireEvent.click(screen.getByRole("button", { name: "Quitar 1 turno" }));

    await waitFor(() => expect(confirmar).toHaveBeenCalled());
    expect(borrar).not.toHaveBeenCalled();
  });

  it("consulta los huecos con los ids a borrar antes de confirmar (aviso «sin cubrir»)", async () => {
    vi.mocked(confirmar).mockResolvedValue(true);
    vi.spyOn(apiMod.api, "borrarTurnosLote").mockResolvedValue({
      borrados: 1,
      no_encontrados: [],
    } as never);
    const calcularHuecos = vi.fn().mockReturnValue([{ titulo: "Partido", fecha: "2026-06-15" }]);
    montar(
      <ReparteMes
        diasSel={new Set(["2026-06-15"])}
        cms={CMS}
        franjasPorSemana={FRANJAS_POR_SEMANA}
        turnosExistentes={new Map([["u-luis|2026-06-15", [turno()]]])}
        calcularHuecos={calcularHuecos}
        onCambio={vi.fn()}
        onCerrar={vi.fn()}
        onLimpiarDias={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "Luis" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Luis 15" }));
    fireEvent.click(screen.getByRole("button", { name: "Quitar turno" }));
    fireEvent.click(screen.getByRole("button", { name: "Quitar 1 turno" }));

    // El panel pregunta por los huecos con el id del turno marcado, y la confirmación se muestra.
    await waitFor(() => expect(calcularHuecos).toHaveBeenCalledWith(["t-1"]));
    await waitFor(() => expect(confirmar).toHaveBeenCalled());
  });

  it("tocar un turno real abre su editor y «Guardar hora» cambia su horario (actualizarTurno)", async () => {
    const actualizar = vi.spyOn(apiMod.api, "actualizarTurno").mockResolvedValue({} as never);
    const onCambio = vi.fn();
    montar(
      <ReparteMes
        diasSel={new Set(["2026-06-15"])}
        cms={CMS}
        franjasPorSemana={FRANJAS_POR_SEMANA}
        turnosExistentes={new Map([["u-luis|2026-06-15", [turno()]]])}
        onCambio={onCambio}
        onCerrar={vi.fn()}
        onLimpiarDias={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "Luis" }));
    // Tocar el turno real abre el editor de hora en línea.
    fireEvent.click(screen.getByRole("checkbox", { name: "Luis 15" }));
    // Sin cambios aún, «Guardar hora» está inerte.
    expect(screen.getByRole("button", { name: "Guardar hora" })).toBeDisabled();

    // Cambiar la hora de inicio y guardar → PATCH del turno con su nuevo horario a medida.
    fireEvent.change(screen.getByLabelText("Nueva hora de inicio"), { target: { value: "09:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar hora" }));

    await waitFor(() =>
      expect(actualizar).toHaveBeenCalledWith("t-1", { inicio: "09:00", fin: "16:00" }),
    );
    await waitFor(() => expect(onCambio).toHaveBeenCalled());
  });
});
