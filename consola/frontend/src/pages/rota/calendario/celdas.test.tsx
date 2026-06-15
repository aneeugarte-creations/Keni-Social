import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";

import type {
  AusenciaRota,
  EventoRota,
  FranjaSemana,
  MiembroRota,
  TurnoCobertura,
} from "@/types";

import { franjasSolapan, type ConflictoCandidato } from "../comun";
import { DropdownAnadirPersona, RecuadroPersonaCalendario } from "./celdas";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

function franja(over: Partial<FranjaSemana> = {}): FranjaSemana {
  return {
    id: "f-manana",
    lunes: "2026-06-15",
    nombre: "Mañana",
    inicio: "08:00",
    fin: "14:00",
    orden: 0,
    es_descanso: false,
    marca: "",
    marca_nombre: "",
    ...over,
  };
}

function conProvider(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function evento(over: Partial<EventoRota> = {}): EventoRota {
  return {
    id: "ev1",
    titulo: "España vs Cabo Verde",
    fecha: "2026-06-15",
    hora: "10:00",
    contenido: "",
    nota: "",
    tipo_cobertura: "transmision",
    prioridad: "media",
    cambiado: false,
    actualizado: "",
    es_sabado: false,
    marca: "",
    marca_nombre: "",
    ...over,
  };
}

function cubridor(over: Partial<TurnoCobertura> = {}): TurnoCobertura {
  return {
    turno_id: "t1",
    miembro_id: "u1",
    miembro_nombre: "Persona",
    franja_id: "f-manana",
    franja_nombre: "Mañana",
    override: false,
    ...over,
  };
}

describe("RecuadroPersonaCalendario — copy «Sin turno a esa hora»", () => {
  it("etiqueta el recuadro sin turno de forma inequívoca (no «Sin cubrir»)", () => {
    render(
      <RecuadroPersonaCalendario
        recuadro={{
          miembro_id: "",
          miembro_nombre: "Sin turno a esa hora",
          turno: null,
          sinCubrir: true,
          eventos: [],
        }}
        franja={franja()}
        equipo={[]}
        editable={false}
        onEditarEvento={vi.fn()}
        onCambio={vi.fn()}
      />,
    );
    expect(screen.getByText("Sin turno a esa hora")).toBeInTheDocument();
    // «Por cubrir»/«Sin cubrir» quedan reservados a otros planos; aquí NO deben aparecer.
    expect(screen.queryByText("Sin cubrir")).toBeNull();
    expect(screen.queryByText("Por cubrir")).toBeNull();
  });

  it("cuando es asignable, el header es un botón con la misma etiqueta", () => {
    const onClick = vi.fn();
    render(
      <RecuadroPersonaCalendario
        recuadro={{
          miembro_id: "",
          miembro_nombre: "Sin turno a esa hora",
          turno: null,
          sinCubrir: true,
          eventos: [],
        }}
        franja={franja()}
        equipo={[]}
        editable
        onEditarEvento={vi.fn()}
        onCambio={vi.fn()}
        onClickHeaderSinCubrir={onClick}
      />,
    );
    const boton = screen.getByRole("button", { name: "Sin turno a esa hora" });
    fireEvent.click(boton);
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

describe("ChipEventoCalendario — cubridores en el evento del calendario", () => {
  it("muestra el avatar + PRIMER nombre de cada cubridor (como en el tablero)", () => {
    render(
      <RecuadroPersonaCalendario
        recuadro={{
          miembro_id: "u-elias",
          miembro_nombre: "Elias",
          turno: null,
          sinCubrir: false,
          eventos: [
            {
              evento: evento(),
              cobertura: [
                cubridor({ turno_id: "t-elias", miembro_id: "u-elias", miembro_nombre: "Elias" }),
                cubridor({ turno_id: "t-rami", miembro_id: "u-rami", miembro_nombre: "Ramiro Soto" }),
              ],
            },
          ],
        }}
        franja={franja()}
        equipo={[]}
        editable={false}
        onEditarEvento={vi.fn()}
        onCambio={vi.fn()}
      />,
    );
    expect(screen.getByText("España vs Cabo Verde")).toBeInTheDocument();
    // Cada cubridor sale por su PRIMER nombre, no el nombre completo.
    expect(screen.getByText("Ramiro")).toBeInTheDocument();
    expect(screen.queryByText("Ramiro Soto")).toBeNull();
    // El otro cubridor también figura (al menos en el chip).
    expect(screen.getAllByText("Elias").length).toBeGreaterThanOrEqual(1);
  });

  it("no muestra cubridores cuando el evento no tiene cobertura («Sin turno a esa hora»)", () => {
    render(
      <RecuadroPersonaCalendario
        recuadro={{
          miembro_id: "",
          miembro_nombre: "Sin turno a esa hora",
          turno: null,
          sinCubrir: true,
          eventos: [{ evento: evento({ titulo: "Amistoso sin señal" }), cobertura: [] }],
        }}
        franja={franja()}
        equipo={[]}
        editable={false}
        onEditarEvento={vi.fn()}
        onCambio={vi.fn()}
      />,
    );
    expect(screen.getByText("Amistoso sin señal")).toBeInTheDocument();
    expect(screen.queryByText("Ramiro")).toBeNull();
  });
});

describe("franjasSolapan — detección de solape horario", () => {
  it("dos franjas que comparten minutos solapan", () => {
    expect(franjasSolapan({ inicio: "08:00", fin: "14:00" }, { inicio: "13:00", fin: "20:00" })).toBe(
      true,
    );
  });
  it("franjas contiguas (fin == inicio) no solapan", () => {
    expect(franjasSolapan({ inicio: "08:00", fin: "14:00" }, { inicio: "14:00", fin: "20:00" })).toBe(
      false,
    );
  });
  it("una franja degenerada (inicio == fin) no solapa con nada", () => {
    expect(franjasSolapan({ inicio: "00:00", fin: "00:00" }, { inicio: "08:00", fin: "14:00" })).toBe(
      false,
    );
  });
  it("soporta franjas que cruzan medianoche", () => {
    // 22:00→02:00 solapa con 01:00→05:00 (comparten 01:00–02:00).
    expect(franjasSolapan({ inicio: "22:00", fin: "02:00" }, { inicio: "01:00", fin: "05:00" })).toBe(
      true,
    );
    // 22:00→02:00 NO solapa con 03:00→06:00.
    expect(franjasSolapan({ inicio: "22:00", fin: "02:00" }, { inicio: "03:00", fin: "06:00" })).toBe(
      false,
    );
  });
});

describe("DropdownAnadirPersona — avisos inline de conflicto", () => {
  const cms: MiembroRota[] = [
    { id: "m1", nombre: "Ana" },
    { id: "m2", nombre: "Bruno" },
  ];
  const ausencia: AusenciaRota = {
    id: "a1",
    miembro_id: "m1",
    miembro_nombre: "Ana",
    tipo: "vacaciones",
    desde: "2026-06-15",
    hasta: "2026-06-20",
    motivo: "",
  };
  const conflictoCandidato = (miembroId: string): ConflictoCandidato => {
    if (miembroId === "m1") return { ausencia, solapa: false };
    if (miembroId === "m2") return { ausencia: undefined, solapa: true };
    return { solapa: false };
  };

  it("muestra «De ausencia ese día» y «Ya tiene turno» en las opciones", async () => {
    conProvider(
      <DropdownAnadirPersona
        lunes="2026-06-15"
        fecha="2026-06-15"
        franja={franja()}
        cmsDisponibles={cms}
        conflictoCandidato={conflictoCandidato}
        onCambio={vi.fn()}
      />,
    );
    // Radix abre el Select con Enter (jsdom no emite pointerup reales); patrón de la suite.
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Enter" });
    await screen.findByRole("option", { name: /Ana/ });
    expect(screen.getByText("De ausencia ese día")).toBeInTheDocument();
    expect(screen.getByText("Ya tiene turno")).toBeInTheDocument();
  });
});
