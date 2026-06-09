import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DistintivoRed } from "./DistintivoRed";

/**
 * El distintivo unifica logo de red + icono de formato en un solo contenedor (logos pelados, sin
 * píldora), SIN el nombre de la red (solo iconos) ni dos burbujas. El nombre va al `title`, no como texto.
 */
describe("DistintivoRed", () => {
  it("no muestra el NOMBRE de la red como texto (solo iconos); el nombre vive en el tooltip", () => {
    const { container } = render(<DistintivoRed red="instagram" formato="foto" />);
    expect(screen.queryByText("Instagram")).toBeNull();
    // Un solo contenedor (un único <span>), no dos burbujas separadas.
    const distintivo = container.querySelector("span");
    expect(distintivo).not.toBeNull();
    expect(distintivo).toHaveAttribute("title", "Instagram · Foto");
    // Red + formato => dos iconos (SVG) dentro del mismo contenedor.
    expect(distintivo!.querySelectorAll("svg")).toHaveLength(2);
  });

  it("sin formato pinta solo el logo de la red (un icono)", () => {
    const { container } = render(<DistintivoRed red="tiktok" />);
    const distintivo = container.querySelector("span");
    expect(distintivo).toHaveAttribute("title", "TikTok");
    expect(distintivo!.querySelectorAll("svg")).toHaveLength(1);
  });
});
