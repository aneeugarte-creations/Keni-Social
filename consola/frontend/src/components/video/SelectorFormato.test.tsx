/**
 * Tests del SelectorFormato: selector de aspecto con icono SVG proporcional por opción.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SelectorFormato } from "./SelectorFormato";

describe("SelectorFormato", () => {
  it("pinta un icono SVG por cada opción de aspecto (9:16, 1:1, 16:9)", () => {
    const { container } = render(<SelectorFormato aspecto="9:16" onCambio={vi.fn()} />);
    // Un SVG (aria-hidden) por botón de aspecto.
    expect(container.querySelectorAll("svg")).toHaveLength(3);
  });

  it("muestra los tres botones de aspecto con su etiqueta", () => {
    render(<SelectorFormato aspecto="9:16" onCambio={vi.fn()} />);
    expect(screen.getByRole("radio", { name: /9:16/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /1:1/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /16:9/ })).toBeInTheDocument();
  });

  it("marca el aspecto activo como aria-checked=true y los demás como false", () => {
    render(<SelectorFormato aspecto="1:1" onCambio={vi.fn()} />);
    expect(screen.getByRole("radio", { name: /1:1/ })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: /9:16/ })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByRole("radio", { name: /16:9/ })).toHaveAttribute("aria-checked", "false");
  });

  it("llama a onCambio con el aspecto seleccionado al hacer clic", () => {
    const onCambio = vi.fn();
    render(<SelectorFormato aspecto="9:16" onCambio={onCambio} />);
    fireEvent.click(screen.getByRole("radio", { name: /16:9/ }));
    expect(onCambio).toHaveBeenCalledWith("16:9");
  });

  it("muestra el párrafo de ayuda por defecto", () => {
    render(<SelectorFormato aspecto="9:16" onCambio={vi.fn()} />);
    expect(screen.getByText(/márgenes punteados/i)).toBeInTheDocument();
  });

  it("oculta el párrafo de ayuda cuando mostrarAyuda={false}", () => {
    render(<SelectorFormato aspecto="9:16" onCambio={vi.fn()} mostrarAyuda={false} />);
    expect(screen.queryByText(/márgenes punteados/i)).not.toBeInTheDocument();
  });
});
