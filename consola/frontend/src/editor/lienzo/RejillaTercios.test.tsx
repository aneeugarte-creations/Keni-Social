// Rejilla de tercios: 4 líneas (2 verticales + 2 horizontales) a 1/3 y 2/3 dentro del marco, solo
// cuando `visible`. Es pura guía visual (aria-hidden, sin eventos).

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RejillaTercios } from "./RejillaTercios";

describe("RejillaTercios", () => {
  it("no pinta nada cuando no es visible", () => {
    const { container } = render(<RejillaTercios visible={false} />);
    expect(container.firstChild).toBeNull();
  });

  it("pinta 4 líneas a 1/3 y 2/3 cuando es visible", () => {
    const { container } = render(<RejillaTercios visible />);
    const marco = container.firstChild as HTMLElement;
    const lineas = Array.from(marco.children) as HTMLElement[];
    expect(lineas).toHaveLength(4);
    const posiciones = lineas.map((l) => l.style.left || l.style.top);
    expect(posiciones.filter((p) => p.startsWith("33"))).toHaveLength(2);
    expect(posiciones.filter((p) => p.startsWith("66"))).toHaveLength(2);
  });
});
