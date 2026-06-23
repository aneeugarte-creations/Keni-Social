/**
 * Tests del selector de FORMATO: multi-selección dependiente de la red (Instagram →
 * Reel/Carrusel/Foto, YouTube → Vídeo), persiste en `vistaConfig.formato`, y poda los
 * formatos elegidos que dejan de aplicar al cambiar la red.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { SelectorFormato } from "./SelectorFormato";
import { useVistaConfig } from "./vistaConfig";

beforeEach(() => {
  localStorage.clear();
  useVistaConfig.getState().reset();
});

describe("SelectorFormato", () => {
  it("ofrece los formatos de la red en foco (Instagram → Reel/Carrusel/Foto)", () => {
    useVistaConfig.getState().setRed("instagram");
    render(<SelectorFormato />);
    fireEvent.click(screen.getByRole("button", { name: "Formatos" }));

    expect(screen.getByRole("menuitemcheckbox", { name: /Reel/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitemcheckbox", { name: /Carrusel/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitemcheckbox", { name: /Foto/ })).toBeInTheDocument();
    // Instagram no ofrece "Enlace".
    expect(screen.queryByRole("menuitemcheckbox", { name: /Enlace/ })).not.toBeInTheDocument();
  });

  it("toggla un formato y lo persiste; 'Todos' lo limpia", () => {
    useVistaConfig.getState().setRed("instagram");
    render(<SelectorFormato />);
    fireEvent.click(screen.getByRole("button", { name: "Formatos" }));

    fireEvent.click(screen.getByRole("menuitemcheckbox", { name: /Reel/ }));
    expect(useVistaConfig.getState().formato).toBe("reel");

    fireEvent.click(screen.getByRole("menuitemradio", { name: /Todos los formatos/ }));
    expect(useVistaConfig.getState().formato).toBeNull();
  });

  it("poda los formatos que dejan de aplicar al cambiar la red", () => {
    useVistaConfig.getState().setRed("instagram");
    useVistaConfig.getState().setFormatos(["reel", "carrusel"]);
    const { rerender } = render(<SelectorFormato />);

    // Cambia el foco a YouTube (solo vídeo): reel/carrusel ya no aplican → se podan a null.
    useVistaConfig.getState().setRed("youtube");
    rerender(<SelectorFormato />);
    expect(useVistaConfig.getState().formato).toBeNull();
  });
});
