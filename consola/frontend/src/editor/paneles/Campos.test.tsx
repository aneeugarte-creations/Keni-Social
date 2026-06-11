/**
 * Tests del control numérico `Num` del inspector:
 *  - los estados PARCIALES ("", "-" inicial) NO emiten — antes el input era 100% controlado y
 *    `Number("") === 0` escribía 0 al documento al vaciar el campo (la capa saltaba al origen) y
 *    el value redondeado machacaba el texto a medio teclear.
 *  - el texto válido se emite EN VIVO y SIN redondear (el redondeo a 2 decimales es presentación).
 *  - Escape restaura el valor con el que se entró al campo.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Num } from "./Campos";

function montar(valor: number) {
  const onChange = vi.fn();
  render(<Num valor={valor} onChange={onChange} />);
  return { input: screen.getByRole("spinbutton") as HTMLInputElement, onChange };
}

describe("Num — borrador local del inspector", () => {
  it("vaciar el campo NO emite 0 (la capa no salta al origen)", () => {
    const { input, onChange } = montar(-700);
    fireEvent.change(input, { target: { value: "" } });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("teclear un número válido emite en vivo y sin redondear", () => {
    const { input, onChange } = montar(0);
    fireEvent.change(input, { target: { value: "12.345" } });
    expect(onChange).toHaveBeenCalledWith(12.345);
  });

  it("emite negativos completos (p. ej. reponer una Y=-700 desde el inspector)", () => {
    const { input, onChange } = montar(0);
    fireEvent.change(input, { target: { value: "-700" } });
    expect(onChange).toHaveBeenCalledWith(-700);
  });

  it("Escape restaura el valor de entrada del campo", () => {
    const { input, onChange } = montar(42);
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "9" } });
    expect(onChange).toHaveBeenLastCalledWith(9);
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onChange).toHaveBeenLastCalledWith(42);
  });

  it("sin foco, el display muestra el valor del store redondeado a 2 decimales", () => {
    const { input } = montar(12.3456);
    expect(input.value).toBe("12.35");
  });
});
