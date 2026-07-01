import { act, fireEvent, render, screen, within } from "@testing-library/react";
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
    reset_semana_iso: "2026-07-01T00:00:00Z",
    reset_semana_txt: "Jul 1 at 12:00am (UTC)",
    reset_sesion_iso: null,
    actualizado_ts: 1_700_000_000,
    al_100: false,
    alerta_roja: false,
    dia: { consumo_pct: 5, umbral_pct: 14.3, limite: "semanal", pausado: false },
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
  it("estado de carga (sin dato) es NEUTRO, no rojo: muestra «—»", () => {
    renderIndicador({ data: undefined });
    expect(screen.getByText("Uso")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText(/Sin cuenta|100%/)).not.toBeInTheDocument();
  });

  it("sin burn rate activo (reset semanal ya pasado en el fixture): cae al % semanal", () => {
    renderIndicador({ data: { cuentas: [cuenta({ semana_pct: 40 })] } }, "claro-sports");
    expect(screen.getByText("40%")).toBeInTheDocument();
  });

  it("burn rate activo: si el 5h va a bloquear antes que la semana, «Uso» muestra el 5h (no el semanal)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-15T10:00:00Z"));
    try {
      renderIndicador(
        {
          data: {
            cuentas: [
              cuenta({
                semana_pct: 30,
                // Ventana de 5h que empezó hace 3h (resetea en 2h): a ritmo de 80/3 %/h llega al
                // 100% en ~45 min, mucho antes que la semana (cuyo reset cae fuera de la ventana
                // "iniciada" a esta hora simulada, así que ni compite).
                sesion_5h_pct: 80,
                reset_sesion_iso: "2026-06-15T12:00:00Z",
              }),
            ],
          },
        },
        "claro-sports",
      );
      expect(screen.getByText("80%")).toBeInTheDocument();
      expect(screen.queryByText("30%")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("barra «24h»: el cupo del día (consumo/umbral del límite semanal) va en el tooltip", () => {
    renderIndicador(
      {
        data: {
          cuentas: [cuenta({ dia: { consumo_pct: 10, umbral_pct: 14.3, limite: "semanal", pausado: false } })],
        },
      },
      "claro-sports",
    );
    expect(screen.getByLabelText(/24h 70%/)).toBeInTheDocument(); // 10 / 14.3 ≈ 70 %
  });

  it("una cuenta (marca concreta): SIN cabecera (es su cuenta siempre); un solo número (Semana), el resto al tooltip", () => {
    renderIndicador({ data: { cuentas: [cuenta({})] } }, "claro-sports");
    expect(screen.getByText("42%")).toBeInTheDocument();
    expect(screen.getByLabelText(/5h 18%/)).toBeInTheDocument();
    // Con una sola cuenta no se rotula cabecera: ni "Cuenta A" ni la lista de marcas.
    expect(screen.queryByText("Cuenta A")).not.toBeInTheDocument();
    expect(screen.queryByText("Claro Sports")).not.toBeInTheDocument();
  });

  it("dos cuentas (Todas): pinta AMBAS con cabecera «Cuenta A» / «Cuenta B»", () => {
    renderIndicador({ data: { cuentas: [cuenta({}), CUENTA_B] } }, null);
    expect(screen.getByText("Cuenta A")).toBeInTheDocument();
    expect(screen.getByText("Cuenta B")).toBeInTheDocument();
    expect(screen.queryByText("UnoTV · Nación Gamer · Fundación")).not.toBeInTheDocument();
    expect(screen.getByText("42%")).toBeInTheDocument();
    expect(screen.getByText("70%")).toBeInTheDocument();
  });

  it("marca concreta filtra a la cuenta de esa marca aunque el back devuelva ambas", () => {
    renderIndicador({ data: { cuentas: [cuenta({}), CUENTA_B] } }, "unotv");
    // Solo la cuenta B (la de unotv): su número está presente; el de A ausente.
    expect(screen.getByText("70%")).toBeInTheDocument();
    expect(screen.getByLabelText(/5h 30%/)).toBeInTheDocument();
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

  it("al 100% NO repite el texto «Límite … al 100%»: ya se ve en la barra roja al tope", () => {
    renderIndicador(
      { data: { cuentas: [cuenta({ semana_pct: 100, sesion_5h_pct: 60, al_100: true, alerta_roja: true })] } },
      "claro-sports",
    );
    expect(screen.getByText("100%")).toBeInTheDocument(); // el % sigue
    expect(screen.queryByText(/Límite.*100%/)).not.toBeInTheDocument(); // sin el texto redundante
  });

  it("colapsado: anillo (svg) con el % del que antes bloqueará (sin resets útiles, cae al semanal)", () => {
    // Sin reset de sesión y con el semanal que resetea antes de llenarse, el burn rate no predice y
    // el anillo cae al % semanal (42).
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

  it("hover en «Uso» despliega el desglose (Semana/24h/5h); al salir el ratón se cierra tras un instante", () => {
    vi.useFakeTimers();
    try {
      renderIndicador({ data: { cuentas: [cuenta({ semana_pct: 42, sesion_5h_pct: 18 })] } }, "claro-sports");
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

      const boton = screen.getByRole("button", { name: /Semana 42%/ });
      fireEvent.mouseEnter(boton);
      const panel = screen.getByRole("dialog", { name: "Desglose de uso" });
      expect(within(panel).getByText("Semana")).toBeInTheDocument();
      expect(within(panel).getByText("24h")).toBeInTheDocument();
      expect(within(panel).getByText("5h")).toBeInTheDocument();
      expect(boton).toHaveAttribute("aria-expanded", "true");

      fireEvent.mouseLeave(boton);
      expect(screen.getByRole("dialog")).toBeInTheDocument(); // el retardo aún no venció
      act(() => vi.runAllTimers()); // el cierre lo dispara un setTimeout, fuera de un evento React
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(boton).toHaveAttribute("aria-expanded", "false");
    } finally {
      vi.useRealTimers();
    }
  });

  it("mover el ratón del botón al panel (que vive fuera, portado) no lo cierra", () => {
    vi.useFakeTimers();
    try {
      renderIndicador({ data: { cuentas: [cuenta({})] } }, "claro-sports");
      const boton = screen.getByRole("button", { name: /Semana/ });
      fireEvent.mouseEnter(boton);
      const panel = screen.getByRole("dialog");
      fireEvent.mouseLeave(boton);
      fireEvent.mouseEnter(panel);
      act(() => vi.runAllTimers()); // el cierre lo dispara un setTimeout, fuera de un evento React
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("Escape cierra el desglose abierto", () => {
    renderIndicador({ data: { cuentas: [cuenta({})] } }, "claro-sports");
    fireEvent.mouseEnter(screen.getByRole("button", { name: /Semana/ }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("click fuera cierra el desglose abierto", () => {
    renderIndicador({ data: { cuentas: [cuenta({})] } }, "claro-sports");
    fireEvent.mouseEnter(screen.getByRole("button", { name: /Semana/ }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("el click sigue alternando el desglose (fallback táctil/accesible)", () => {
    renderIndicador({ data: { cuentas: [cuenta({ semana_pct: 42 })] } }, "claro-sports");
    const boton = screen.getByRole("button", { name: /Semana 42%/ });
    fireEvent.click(boton);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.click(boton);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("dos cuentas: pasar el ratón de una a otra cierra la primera y abre la segunda", () => {
    renderIndicador({ data: { cuentas: [cuenta({}), CUENTA_B] } }, null);
    const [botonA, botonB] = screen.getAllByRole("button");
    fireEvent.mouseEnter(botonA);
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    fireEvent.mouseEnter(botonB);
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
  });
});
