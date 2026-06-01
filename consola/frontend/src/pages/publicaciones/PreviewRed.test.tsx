import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PreviewRed } from "./PreviewRed";

describe("PreviewRed (vista previa por red)", () => {
  it("muestra la marca, su handle y el nombre de la red", () => {
    render(<PreviewRed red="instagram" marcaNombre="Uno TV" copy="Hola mundo" />);
    expect(screen.getByText("Uno TV")).toBeInTheDocument();
    // El handle aproximado: @marcasinespacios (en cabecera y como prefijo del copy).
    expect(screen.getAllByText("@unotv").length).toBeGreaterThanOrEqual(1);
    // El icono de la red lleva su nombre como etiqueta accesible.
    expect(screen.getByLabelText("Instagram")).toBeInTheDocument();
  });

  it("recorta el copy al tope de caracteres de la red (X = 280)", () => {
    const largo = "a".repeat(300);
    render(<PreviewRed red="x" marcaNombre="Claro Sports" copy={largo} />);
    // Contador en rojo: 300 / 280.
    expect(screen.getByText("300 / 280")).toBeInTheDocument();
    // El texto mostrado va recortado (no aparece la cadena completa de 300).
    expect(screen.queryByText(largo)).not.toBeInTheDocument();
  });

  it("no muestra contador para redes sin tope (Facebook)", () => {
    render(<PreviewRed red="facebook" marcaNombre="Marca" copy="texto" />);
    expect(screen.queryByText(/\/\s*\d/)).not.toBeInTheDocument();
  });

  it("renderiza la imagen cuando hay imagen_url", () => {
    render(
      <PreviewRed red="instagram" marcaNombre="Marca" copy="x" imagenUrl="/api/media/foto.png" titulo="Nota" />,
    );
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("src", "/api/media/foto.png");
  });

  it("muestra un aviso de copy vacío por red", () => {
    render(<PreviewRed red="x" marcaNombre="Marca" copy="" />);
    expect(screen.getByText(/Sin copy para X/i)).toBeInTheDocument();
  });
});
