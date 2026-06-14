import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { EstadoSwap, SwapTurno } from "@/types";

import { ETIQUETA_ESTADO_SWAP, pasosSwap, TarjetaSwap } from "./CambiosYAusencias";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

function swap(over: Partial<SwapTurno> = {}): SwapTurno {
  return {
    id: "s1",
    solicitante_id: "u1",
    solicitante_nombre: "Ana",
    destinatario_id: "u2",
    destinatario_nombre: "Bruno",
    // `franja_a`/`franja_b` son `franja_id` reales (uuid, no literales legacy): el backend
    // emite el nombre legible aparte, en `franja_a_nombre`/`franja_b_nombre`.
    fecha_a: "2026-06-15",
    franja_a: "a1b2c3d4e5f6",
    franja_a_nombre: "Mañana",
    fecha_b: "2026-06-16",
    franja_b: "0f1e2d3c4b5a",
    franja_b_nombre: "Tarde",
    motivo: "",
    estado: "propuesto",
    respuesta_destinatario: "",
    respuesta_admin: "",
    creado: "2026-06-10T12:00:00",
    actualizado: "2026-06-10T12:00:00",
    decidido_destinatario: "",
    decidido_admin: "",
    aplicado: "",
    marca: "",
    marca_nombre: "",
    ...over,
  };
}

function renderTarjeta(s: SwapTurno, miId: string, esAdmin = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TarjetaSwap swap={s} miId={miId} esAdmin={esAdmin} />
    </QueryClientProvider>,
  );
}

describe("pasosSwap — máquina de estados como recorrido", () => {
  const fase = (e: EstadoSwap) => pasosSwap(swap({ estado: e })).map((p) => p.estado);

  it("propuesto: en el compañero (pendiente de Elías)", () => {
    expect(fase("propuesto")).toEqual(["hecho", "actual", "pendiente"]);
  });
  it("aceptado: el compañero aceptó, ahora pende de Elías", () => {
    expect(fase("aceptado")).toEqual(["hecho", "hecho", "actual"]);
  });
  it("aprobado/aplicado: Elías cerró la cadena", () => {
    expect(fase("aprobado")).toEqual(["hecho", "hecho", "hecho"]);
    expect(fase("aplicado")).toEqual(["hecho", "hecho", "hecho"]);
  });
  it("rechazado: se detuvo en el compañero", () => {
    expect(fase("rechazado")).toEqual(["hecho", "rechazado", "pendiente"]);
  });
  it("rechazado_admin: el compañero aceptó pero Elías rechazó", () => {
    expect(fase("rechazado_admin")).toEqual(["hecho", "hecho", "rechazado"]);
  });
  it("cancelado (compañero sin responder): la cadena queda detenida", () => {
    expect(fase("cancelado")).toEqual(["hecho", "pendiente", "pendiente"]);
  });
  it("cancelado tras aceptar el compañero: detenido antes de Elías", () => {
    expect(
      pasosSwap(swap({ estado: "cancelado", decidido_destinatario: "2026-06-12T10:00:00" })).map(
        (p) => p.estado,
      ),
    ).toEqual(["hecho", "hecho", "pendiente"]);
  });
});

describe("TarjetaSwap — progreso visible y «sigue siendo tuyo»", () => {
  it("muestra el progreso (solicitante → compañero → Elías) y el badge de estado", () => {
    renderTarjeta(swap(), "u1");
    const progreso = screen.getByLabelText("Progreso de la solicitud");
    // Elías solo aparece en el progreso (no en la cabecera): identifica el indicador.
    expect(within(progreso).getByText("Elías")).toBeInTheDocument();
    expect(within(progreso).getByText("Ana")).toBeInTheDocument();
    expect(within(progreso).getByText("Bruno")).toBeInTheDocument();
    // Reusa la etiqueta de estado existente.
    expect(screen.getByText(ETIQUETA_ESTADO_SWAP.propuesto)).toBeInTheDocument();
  });

  it("renderiza el NOMBRE de la franja del swap (no el franja_id en blanco)", () => {
    // `franja_a`/`franja_b` son `franja_id` (uuid); el nombre legible viene en
    // `franja_a_nombre`/`franja_b_nombre`. Antes se indexaba `ETIQUETA_FRANJA[franja_id]`
    // → `undefined` → franja en blanco; esto lo bloquea.
    renderTarjeta(swap(), "u1");
    expect(screen.getByText(/Mañana/)).toBeInTheDocument();
    expect(screen.getByText(/Tarde/)).toBeInTheDocument();
  });

  it("cae al literal legacy (ETIQUETA_FRANJA) si el swap no trae nombre de franja", () => {
    // Swap antiguo: sin `franja_*_nombre`, con literal en `franja_a`/`franja_b`.
    renderTarjeta(
      swap({
        franja_a: "matutino",
        franja_a_nombre: undefined,
        franja_b: "vespertino",
        franja_b_nombre: undefined,
      }),
      "u1",
    );
    expect(screen.getByText(/Mañana/)).toBeInTheDocument();
    expect(screen.getByText(/Tarde/)).toBeInTheDocument();
  });

  it("mientras está abierto, avisa que el turno sigue siendo tuyo (solicitante)", () => {
    renderTarjeta(swap(), "u1");
    expect(
      screen.getByText("Este turno sigue siendo tuyo hasta que se aplique el cambio."),
    ).toBeInTheDocument();
  });

  it("para un tercero (admin), el aviso es neutro", () => {
    renderTarjeta(swap({ estado: "aceptado" }), "otro", true);
    expect(
      screen.getByText("Cada quien conserva su turno hasta que se aplique el cambio."),
    ).toBeInTheDocument();
  });

  it("en un estado terminal NO muestra el aviso de «sigue siendo tuyo»", () => {
    renderTarjeta(swap({ estado: "aplicado", aplicado: "2026-06-12T10:00:00" }), "u1");
    expect(screen.queryByText(/sigue siendo tuyo/)).toBeNull();
    expect(screen.queryByText(/conserva su turno/)).toBeNull();
    expect(screen.getByText(ETIQUETA_ESTADO_SWAP.aplicado)).toBeInTheDocument();
  });
});
