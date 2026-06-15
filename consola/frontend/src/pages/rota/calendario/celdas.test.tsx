import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";

import type {
  EventoRota,
  TurnoRota,
} from "@/types";

import {
  franjasSolapan,
  type ItemEventoCalendario,
} from "../comun";
import { CeldaDeRejilla } from "./celdas";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

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

function turno(over: Partial<TurnoRota> = {}): TurnoRota {
  return {
    id: "tr1",
    semana: "2026-06-15",
    fecha: "2026-06-15",
    miembro_id: "u-tezcu",
    miembro_nombre: "Tezcucano Pérez",
    franja_id: "f-manana",
    franja_nombre: "Mañana",
    franja: "matutino",
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

function itemEvento(
  cubridores: { id: string; nombre: string }[] = [],
  over: Partial<EventoRota> = {},
): ItemEventoCalendario {
  return { evento: evento(over), cubridores };
}

function renderCelda(
  over: { personas?: TurnoRota[]; eventos?: ItemEventoCalendario[]; editable?: boolean } = {},
) {
  return conProvider(
    <CeldaDeRejilla
      fecha="2026-06-15"
      personas={over.personas ?? []}
      eventos={over.eventos ?? []}
      equipo={[]}
      editable={over.editable ?? false}
      finde={false}
      ausenciaDe={() => undefined}
      onEditarEvento={vi.fn()}
      onCambio={vi.fn()}
    />,
  );
}

describe("CeldaDeRejilla — evento UNA vez + titularidad real (coherente con Panorama)", () => {
  it("el evento sale una sola vez con quien lo COGIÓ, no con quien está de turno", () => {
    renderCelda({
      // Roger está de TURNO (capacidad) pero NO cogió el evento; Tezcucano lo cogió.
      personas: [turno({ id: "tr-roger", miembro_id: "u-roger", miembro_nombre: "Roger" })],
      eventos: [itemEvento([{ id: "u-tezcu", nombre: "Tezcucano Pérez" }])],
    });
    // UNA vez (antes se duplicaba bajo cada persona de turno de la franja).
    expect(screen.getAllByText("España vs Cabo Verde")).toHaveLength(1);
    // En el evento, quien lo COGIÓ (su primer nombre).
    expect(screen.getByText("Tezcucano")).toBeInTheDocument();
    // Roger está en CAPACIDAD (avatar; su nombre en el `title`), pero NO figura como
    // cubridor del evento → no aparece como texto plano.
    expect(screen.getByTitle("Roger")).toBeInTheDocument();
    expect(screen.queryByText("Roger")).toBeNull();
  });

  it("un evento que nadie ha cogido sale como «Por cubrir»", () => {
    renderCelda({ eventos: [itemEvento([], { titulo: "Amistoso sin dueño" })] });
    expect(screen.getByText("Amistoso sin dueño")).toBeInTheDocument();
    expect(screen.getByText("Por cubrir")).toBeInTheDocument();
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

