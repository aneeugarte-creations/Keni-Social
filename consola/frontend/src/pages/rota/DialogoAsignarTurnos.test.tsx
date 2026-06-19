import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as apiMod from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { FranjaSemana, MiembroRota } from "@/types";

import {
  DialogoAsignarTurnos,
  asignarDiasTurno,
  asignarPersonasDiasTurno,
} from "./DialogoAsignarTurnos";

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

  it("con horario a medida envía inicio/fin; sin él los omite (hereda la franja)", async () => {
    const crear = vi.spyOn(apiMod.api, "crearTurno").mockResolvedValue({} as never);
    await asignarDiasTurno("2026-06-15", "u-luis", "f-manana", ["2026-06-15"], "07:00", "15:00");
    expect(crear).toHaveBeenLastCalledWith({
      lunes: "2026-06-15",
      fecha: "2026-06-15",
      miembro_id: "u-luis",
      franja_id: "f-manana",
      inicio: "07:00",
      fin: "15:00",
    });
    // Horas vacías ⇒ el cuerpo NO lleva inicio/fin (el turno hereda las de su franja).
    await asignarDiasTurno("2026-06-15", "u-luis", "f-manana", ["2026-06-16"]);
    expect(crear).toHaveBeenLastCalledWith({
      lunes: "2026-06-15",
      fecha: "2026-06-16",
      miembro_id: "u-luis",
      franja_id: "f-manana",
    });
  });
});

// Multi-persona: el mismo horario+días se aplica a varias personas. Como `asignarDiasTurno`, se
// prueba aparte del componente (los chips de persona ya no son Selects de Radix, pero la
// agregación es la lógica clave a fijar: que un choque de una persona NO arrastre a las demás).
describe("asignarPersonasDiasTurno — aplica a varias personas y agrega el resultado", () => {
  it("suma creados/yaEstaba/sábados/fallos de cada persona; cuenta las que recibieron creados", async () => {
    // Luis: 2 fechas → ambas creadas. Ana: 2 fechas → 1 ya estaba (409) + 1 sábado (409, override).
    const crear = vi
      .spyOn(apiMod.api, "crearTurno")
      .mockResolvedValueOnce({} as never) // Luis · día 1 creado
      .mockResolvedValueOnce({} as never) // Luis · día 2 creado
      .mockRejectedValueOnce(new ApiError("dup", 409, { id: "x" })) // Ana · día 1 ya estaba
      .mockRejectedValueOnce(new ApiError("sáb", 409, { requiere_override: true })); // Ana · día 2 sábado
    const r = await asignarPersonasDiasTurno(
      "2026-06-15",
      ["u-luis", "u-ana"],
      "f-manana",
      ["2026-06-15", "2026-06-16"],
    );
    expect(crear).toHaveBeenCalledTimes(4);
    // Solo Luis recibió creados ⇒ personasConCreados = 1, aunque se procesaron 2 personas.
    expect(r).toEqual({
      creados: 2,
      yaEstaba: 1,
      sabados: 1,
      fallos: 0,
      personasConCreados: 1,
    });
  });

  it("propaga el horario a medida a cada persona; sin personas no llama a la API", async () => {
    const crear = vi.spyOn(apiMod.api, "crearTurno").mockResolvedValue({} as never);
    await asignarPersonasDiasTurno(
      "2026-06-15",
      ["u-luis", "u-ana"],
      "f-manana",
      ["2026-06-15"],
      "07:00",
      "15:00",
    );
    expect(crear).toHaveBeenCalledTimes(2);
    expect(crear).toHaveBeenNthCalledWith(1, {
      lunes: "2026-06-15",
      fecha: "2026-06-15",
      miembro_id: "u-luis",
      franja_id: "f-manana",
      inicio: "07:00",
      fin: "15:00",
    });
    expect(crear).toHaveBeenNthCalledWith(2, {
      lunes: "2026-06-15",
      fecha: "2026-06-15",
      miembro_id: "u-ana",
      franja_id: "f-manana",
      inicio: "07:00",
      fin: "15:00",
    });

    crear.mockClear();
    const vacio = await asignarPersonasDiasTurno("2026-06-15", [], "f-manana", ["2026-06-15"]);
    expect(crear).not.toHaveBeenCalled();
    expect(vacio).toEqual({
      creados: 0,
      yaEstaba: 0,
      sabados: 0,
      fallos: 0,
      personasConCreados: 0,
    });
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
const CMS: MiembroRota[] = [
  { id: "u-luis", nombre: "Luis" },
  { id: "u-ana", nombre: "Ana" },
];
const DIAS = ["2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18", "2026-06-19", "2026-06-20", "2026-06-21"];

describe("DialogoAsignarTurnos (render)", () => {
  it("pide personas + horario (sin selector de franja) y ofrece import automático", () => {
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
          marca="claro-sports"
          onCambio={vi.fn()}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByText("Asignar turnos")).toBeInTheDocument();
    // Persona pasó de Select a pastillas multi-selección: hay «Personas» y un chip por CM.
    expect(screen.getByText("Personas")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Luis" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Ana" })).toBeInTheDocument();
    // El horario sustituye al selector de franja: hay «Horario», ya no «Franja».
    expect(screen.getByText("Horario")).toBeInTheDocument();
    expect(screen.queryByText("Franja")).not.toBeInTheDocument();
    // Sin persona ni días elegidos, «Asignar» está deshabilitado.
    expect(screen.getByRole("button", { name: "Asignar" })).toBeDisabled();
    // La vía automática (import) está disponible dentro del mismo diálogo.
    expect(screen.getByRole("button", { name: /Importar documento/ })).toBeInTheDocument();
  });

  it("arranca vacío; personas × días mueven el conteo de turnos del botón", () => {
    // Los chips de persona/día y los atajos son <button> planos (no Selects de Radix), así que
    // sí se pueden ejercitar en jsdom. El botón «Asignar» lleva el conteo de turnos
    // (personas × días): el aviso para que «elijo 2 personas y 3 días» se vea como 6 turnos.
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
          marca="claro-sports"
          onCambio={vi.fn()}
        />
      </QueryClientProvider>,
    );
    // Arranca vacío: 2 personas + 7 días = 9 chips, ninguno marcado, y el botón sin conteo.
    const chips = screen.getAllByRole("checkbox");
    expect(chips).toHaveLength(9);
    chips.forEach((c) => expect(c).toHaveAttribute("aria-checked", "false"));
    expect(screen.getByRole("button", { name: "Asignar" })).toBeInTheDocument();

    // Solo días (sin persona) NO produce conteo: hace falta al menos una persona.
    fireEvent.click(screen.getByRole("button", { name: "Toda la semana" }));
    expect(screen.getByRole("button", { name: "Asignar" })).toBeDisabled();

    // 1 persona × 7 días = 7 turnos.
    fireEvent.click(screen.getByRole("checkbox", { name: "Luis" }));
    expect(screen.getByRole("button", { name: "Asignar 7 turnos" })).toBeEnabled();

    // 2 personas × 7 días = 14 turnos.
    fireEvent.click(screen.getByRole("checkbox", { name: "Ana" }));
    expect(screen.getByRole("button", { name: "Asignar 14 turnos" })).toBeInTheDocument();

    // «L–V» deja 5 días → 2 × 5 = 10 turnos.
    fireEvent.click(screen.getByRole("button", { name: "L–V" }));
    expect(screen.getByRole("button", { name: "Asignar 10 turnos" })).toBeInTheDocument();

    // «Todas» de personas no cambia nada (ya están las 2). «Ninguno» de días limpia el conteo.
    fireEvent.click(screen.getByRole("button", { name: "Ninguno" }));
    expect(screen.getByRole("button", { name: "Asignar" })).toBeDisabled();

    // Una persona × un día = 1 turno (singular correcto).
    fireEvent.click(screen.getByRole("checkbox", { name: "Ana" })); // deja solo a Luis
    fireEvent.click(screen.getByRole("checkbox", { name: /15$/ })); // un día
    expect(screen.getByRole("button", { name: "Asignar 1 turno" })).toBeInTheDocument();
  });

  it("incrustado: columna lateral (aside), no modal; cerrado no pinta nada", () => {
    // En «Gestión» el reparto va junto a la rejilla viva: un <aside> (rol complementary), NO un
    // modal que la tape. Cerrado no renderiza nada para que la rejilla recupere el ancho.
    vi.spyOn(apiMod.api, "propuestasParrilla").mockResolvedValue({ propuestas: [] } as never);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const onOpenChange = vi.fn();
    const props = {
      incrustado: true as const,
      onOpenChange,
      lunes: "2026-06-15",
      dias: DIAS,
      franjas: FRANJAS,
      cms: CMS,
      marca: "claro-sports",
      onCambio: vi.fn(),
    };
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <DialogoAsignarTurnos abierto={false} {...props} />
      </QueryClientProvider>,
    );
    expect(screen.queryByText("Personas")).not.toBeInTheDocument();

    rerender(
      <QueryClientProvider client={client}>
        <DialogoAsignarTurnos abierto {...props} />
      </QueryClientProvider>,
    );
    const panel = screen.getByRole("complementary", { name: "Asignar turnos" });
    expect(within(panel).getByText("Personas")).toBeInTheDocument();
    expect(within(panel).getByText("Horario")).toBeInTheDocument();
    // No es un modal: nada de role=dialog que cubra la rejilla.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    // Su propio botón de cerrar devuelve el ancho a la rejilla.
    fireEvent.click(within(panel).getByRole("button", { name: "Cerrar" }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
