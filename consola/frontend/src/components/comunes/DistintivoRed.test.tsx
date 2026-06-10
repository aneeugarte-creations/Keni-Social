import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DistintivoRed } from "./DistintivoRed";

/**
 * El distintivo unifica icono de formato + logo de red en un solo contenedor (logos pelados, sin
 * píldora), SIN el nombre de la red (solo iconos) ni dos burbujas. El nombre va al `title`, no
 * como texto. Orden del rediseño aprobado: FORMATO delante de la RED.
 */
describe("DistintivoRed", () => {
  it("no muestra el NOMBRE de la red como texto (solo iconos); el nombre vive en el tooltip", () => {
    const { container } = render(<DistintivoRed red="instagram" formato="foto" />);
    expect(screen.queryByText("Instagram")).toBeNull();
    // Un solo contenedor (un único <span>), no dos burbujas separadas.
    const distintivo = container.querySelector("span");
    expect(distintivo).not.toBeNull();
    expect(distintivo).toHaveAttribute("title", "Instagram · Foto");
    // Formato + red => dos iconos (SVG) dentro del mismo contenedor, el FORMATO primero.
    const iconos = distintivo!.querySelectorAll("svg");
    expect(iconos).toHaveLength(2);
    expect(iconos[0].classList.contains("lucide-camera")).toBe(true);
  });

  it("sin formato pinta solo el logo de la red (un icono)", () => {
    const { container } = render(<DistintivoRed red="tiktok" />);
    const distintivo = container.querySelector("span");
    expect(distintivo).toHaveAttribute("title", "TikTok");
    expect(distintivo!.querySelectorAll("svg")).toHaveLength(1);
  });

  it("carrusel pinta su propio icono (capas) y la etiqueta en el tooltip", () => {
    const { container } = render(<DistintivoRed red="instagram" formato="carrusel" />);
    const distintivo = container.querySelector("span");
    expect(distintivo).toHaveAttribute("title", "Instagram · Carrusel");
    const iconos = distintivo!.querySelectorAll("svg");
    expect(iconos).toHaveLength(2);
    expect(iconos[0].classList.contains("lucide-layers")).toBe(true);
  });
});
