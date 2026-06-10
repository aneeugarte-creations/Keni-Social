/**
 * Tests del selector de tiempo: los meses FUTUROS del año en curso no son
 * seleccionables (consultan vacío) y el corte de "hoy" es CDMX, no la zona del
 * navegador. Se fija hoy = 10 de junio de 2026 mockeando `hoyCDMX`.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { hoyCDMX } from "@/lib/fecha";

import { mesSeleccionable, SelectorTiempo } from "./Controles";

vi.mock("@/lib/fecha", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/fecha")>();
  return { ...real, hoyCDMX: vi.fn(() => "2026-06-10") };
});

beforeEach(() => {
  vi.mocked(hoyCDMX).mockReturnValue("2026-06-10");
});

const RANGOS = [
  { id: "semana", etiqueta: "Últimos 7 días" },
  { id: "mes", etiqueta: "Últimos 30 días" },
];

describe("mesSeleccionable (corte CDMX)", () => {
  it("permite el mes en curso y todos los anteriores", () => {
    expect(mesSeleccionable(2026, 6)).toBe(true); // mes en curso (datos parciales legítimos)
    expect(mesSeleccionable(2026, 5)).toBe(true);
    expect(mesSeleccionable(2026, 1)).toBe(true);
    expect(mesSeleccionable(2025, 12)).toBe(true); // cualquier mes de un año pasado
  });

  it("rechaza los meses futuros del año en curso y los años futuros", () => {
    expect(mesSeleccionable(2026, 7)).toBe(false);
    expect(mesSeleccionable(2026, 12)).toBe(false);
    expect(mesSeleccionable(2027, 1)).toBe(false);
  });

  it("usa el día CDMX, no la zona del navegador", () => {
    // En CDMX todavía es 31 de mayo (aunque en UTC ya sea 1 de junio).
    vi.mocked(hoyCDMX).mockReturnValue("2026-05-31");
    expect(mesSeleccionable(2026, 5)).toBe(true);
    expect(mesSeleccionable(2026, 6)).toBe(false);
  });
});

describe("SelectorTiempo — modo mes", () => {
  it("deshabilita los meses futuros del año en curso en el desplegable", async () => {
    render(<SelectorTiempo rangos={RANGOS} valor="mes:2026-06" onCambio={vi.fn()} />);

    // Abre el desplegable de mes con teclado (Radix abre con Enter/Espacio).
    fireEvent.keyDown(screen.getByLabelText("Mes"), { key: "Enter" });

    const julio = await screen.findByRole("option", { name: "Julio" });
    expect(julio).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("option", { name: "Diciembre" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    // Junio (mes en curso) y los anteriores siguen elegibles.
    expect(screen.getByRole("option", { name: "Junio" })).not.toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByRole("option", { name: "Enero" })).not.toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });

  it("en un año pasado ningún mes queda deshabilitado", async () => {
    render(<SelectorTiempo rangos={RANGOS} valor="mes:2025-11" onCambio={vi.fn()} />);

    fireEvent.keyDown(screen.getByLabelText("Mes"), { key: "Enter" });

    const diciembre = await screen.findByRole("option", { name: "Diciembre" });
    expect(diciembre).not.toHaveAttribute("aria-disabled", "true");
  });

  it("al cambiar al año en curso, un mes que quedaría en el futuro se recorta al mes actual", async () => {
    const onCambio = vi.fn();
    // Noviembre de 2025 elegido; al pasar a 2026 (estando en junio) nov sería futuro.
    render(<SelectorTiempo rangos={RANGOS} valor="mes:2025-11" onCambio={onCambio} />);

    fireEvent.keyDown(screen.getByLabelText("Año"), { key: "Enter" });
    const opcion2026 = await screen.findByRole("option", { name: "2026" });
    // Radix selecciona el item con Enter/Espacio (jsdom no emite pointerup reales).
    fireEvent.keyDown(opcion2026, { key: "Enter" });

    expect(onCambio).toHaveBeenCalledWith("mes:2026-06");
  });
});
