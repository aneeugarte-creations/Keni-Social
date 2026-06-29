import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IndicadorUso } from "@/components/layout/IndicadorUso";
import type { UsoCuenta } from "@/hooks/use-uso-cuenta";

// Aislamos la red y el selector: el componente lee el RESULTADO del hook de uso (`use-uso-cuenta`)
// y la marca activa (`useMarcaActiva`). Mockear ambos nos deja conducir cada estado (cargando /
// una cuenta / dos cuentas / sin cuentas / rojo) y cada modo del selector (Todas / marca concreta).
const usoMock = vi.fn();
const marcaActivaMock = vi.fn();
vi.mock("@/hooks/use-uso-cuenta", () => ({
  useUsoCuenta: () => usoMock(),
}));
vi.mock("@/hooks/marca-activa-contexto", () => ({
  useMarcaActiva: () => marcaActivaMock(),
}));

afterEach(() => {
  vi.clearAllMocks();
});

function cuenta(parcial: Partial<UsoCuenta>): UsoCuenta {
  return {
    cuenta: "a",
    etiqueta: "Claro Sports",
    marcas: ["claro-sports"],
    conectada: true,
    semana_pct: 42,
    sesion_5h_pct: 18,
    sonnet_pct: null,
    reset_semana_iso: "2026-07-01T00:00:00Z",
    reset_semana_txt: "Jul 1 at 12:00am (UTC)",
    actualizado_ts: 1_700_000_000,
    al_100: false,
    alerta_roja: false,
    ...parcial,
  };
}

const CUENTA_B = cuenta({
  cuenta: "b",
  etiqueta: "UnoTV · Nación Gamer · Fundación",
  marcas: ["unotv", "nacion-gamer", "fundacion"],
  semana_pct: 70,
  sesion_5h_pct: 30,
});

/** Renderiza con la respuesta del hook y la marca activa dadas. */
function renderIndicador(
  resultadoUso: unknown,
  marcaActiva: string | null = null,
  colapsado = false,
) {
  usoMock.mockReturnValue(resultadoUso);
  marcaActivaMock.mockReturnValue({ marcaActiva });
  return render(<IndicadorUso colapsado={colapsado} />);
}

describe("IndicadorUso", () => {
  it("estado de carga (sin dato) es NEUTRO, no rojo: muestra «—» y los medidores", () => {
    renderIndicador({ data: undefined });
    expect(screen.getByText("Semana")).toBeInTheDocument();
    expect(screen.getByText("5h")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.queryByText(/Sin cuenta|100%/)).not.toBeInTheDocument();
  });

  it("una cuenta (marca concreta): pinta sus porcentajes, sin etiqueta de marca", () => {
    renderIndicador({ data: { cuentas: [cuenta({})] } }, "claro-sports");
    expect(screen.getByText("42%")).toBeInTheDocument();
    expect(screen.getByText("18%")).toBeInTheDocument();
    // Con UNA cuenta no se rotula la etiqueta de marca (igual que antes).
    expect(screen.queryByText("Claro Sports")).not.toBeInTheDocument();
  });

  it("dos cuentas (Todas): pinta AMBAS, cada una etiquetada por sus marcas", () => {
    renderIndicador({ data: { cuentas: [cuenta({}), CUENTA_B] } }, null);
    expect(screen.getByText("Claro Sports")).toBeInTheDocument();
    expect(screen.getByText("UnoTV · Nación Gamer · Fundación")).toBeInTheDocument();
    expect(screen.getByText("42%")).toBeInTheDocument();
    expect(screen.getByText("70%")).toBeInTheDocument();
  });

  it("marca concreta filtra a la cuenta de esa marca aunque el back devuelva ambas", () => {
    renderIndicador({ data: { cuentas: [cuenta({}), CUENTA_B] } }, "unotv");
    // Solo la cuenta B (la de unotv): sus porcentajes presentes; los de A ausentes.
    expect(screen.getByText("70%")).toBeInTheDocument();
    expect(screen.getByText("30%")).toBeInTheDocument();
    expect(screen.queryByText("42%")).not.toBeInTheDocument();
    // Una sola cuenta tras el filtro: no se rotula la etiqueta de marca (igual que antes).
    expect(screen.queryByText("UnoTV · Nación Gamer · Fundación")).not.toBeInTheDocument();
  });

  it("sin cuentas (editor sin marcas): no renderiza nada", () => {
    const { container } = renderIndicador({ data: { cuentas: [] } }, null);
    expect(container).toBeEmptyDOMElement();
  });

  it("marca activa que no es de ninguna cuenta permitida: no renderiza nada", () => {
    const { container } = renderIndicador({ data: { cuentas: [cuenta({})] } }, "unotv");
    expect(container).toBeEmptyDOMElement();
  });

  it("rojo sin cuenta: mensaje «Sin cuenta» en clase destructiva", () => {
    renderIndicador(
      {
        data: {
          cuentas: [cuenta({ conectada: false, semana_pct: null, sesion_5h_pct: null, alerta_roja: true })],
        },
      },
      "claro-sports",
    );
    const aviso = screen.getByText("Sin cuenta");
    expect(aviso).toBeInTheDocument();
    expect(aviso.className).toContain("text-destructive");
  });

  it("rojo al 100%: mensaje «Límite semanal al 100%»", () => {
    renderIndicador(
      { data: { cuentas: [cuenta({ semana_pct: 100, sesion_5h_pct: 60, al_100: true, alerta_roja: true })] } },
      "claro-sports",
    );
    expect(screen.getByText("Límite semanal al 100%")).toBeInTheDocument();
  });

  it("colapsado: pinta un círculo (svg) con el número semanal, sin barras", () => {
    const { container } = renderIndicador({ data: { cuentas: [cuenta({ semana_pct: 42 })] } }, "claro-sports", true);
    expect(container.querySelector("svg")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.queryByText("Semana")).not.toBeInTheDocument();
  });

  it("colapsado dos cuentas: un círculo por cuenta", () => {
    const { container } = renderIndicador({ data: { cuentas: [cuenta({}), CUENTA_B] } }, null, true);
    expect(container.querySelectorAll("svg").length).toBe(2);
  });

  it("colapsado rojo: el tooltip/etiqueta lleva el aviso «Sin cuenta»", () => {
    renderIndicador(
      {
        data: {
          cuentas: [cuenta({ conectada: false, semana_pct: null, sesion_5h_pct: null, alerta_roja: true })],
        },
      },
      "claro-sports",
      true,
    );
    expect(screen.getByLabelText(/Sin cuenta/)).toBeInTheDocument();
  });
});
