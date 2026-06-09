import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DistintivoRed } from "./DistintivoRed";

/**
 * El distintivo unifica logo de red + icono de formato en UNA píldora, SIN el nombre de la red
 * (solo iconos) y sin partirse en dos burbujas. El nombre va al `title` (tooltip), no como texto.
 */
describe("DistintivoRed", () => {
  it("no muestra el NOMBRE de la red como texto (solo iconos); el nombre vive en el tooltip", () => {
    const { container } = render(<DistintivoRed red="instagram" formato="foto" />);
    expect(screen.queryByText("Instagram")).toBeNull();
    // Una sola píldora (un único <span> contenedor), no dos burbujas separadas.
    const pildora = container.querySelector("span");
    expect(pildora).not.toBeNull();
    expect(pildora).toHaveAttribute("title", "Instagram · Foto");
    // Red + formato => dos iconos (SVG) dentro de la misma píldora.
    expect(pildora!.querySelectorAll("svg")).toHaveLength(2);
  });

  it("sin formato pinta solo el logo de la red (un icono)", () => {
    const { container } = render(<DistintivoRed red="tiktok" />);
    const pildora = container.querySelector("span");
    expect(pildora).toHaveAttribute("title", "TikTok");
    expect(pildora!.querySelectorAll("svg")).toHaveLength(1);
  });
});
