/**
 * Tests para AyudaInfo — icono "i" que despliega una explicación al clicar.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AyudaInfo } from "./AyudaInfo";

describe("AyudaInfo", () => {
  it("no renderiza nada si no hay texto", () => {
    const { container } = render(<AyudaInfo texto="" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("el texto está oculto hasta clicar el icono", () => {
    render(<AyudaInfo texto="Explicación de la métrica" />);
    expect(screen.queryByText("Explicación de la métrica")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Explicación de la métrica")).toBeInTheDocument();
  });

  it("clicar de nuevo el icono cierra la explicación", () => {
    render(<AyudaInfo texto="Explicación de la métrica" />);
    const boton = screen.getByRole("button");
    fireEvent.click(boton);
    expect(screen.getByText("Explicación de la métrica")).toBeInTheDocument();
    fireEvent.click(boton);
    expect(screen.queryByText("Explicación de la métrica")).not.toBeInTheDocument();
  });

  it("clicar fuera cierra la explicación", () => {
    render(<AyudaInfo texto="Explicación de la métrica" />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Explicación de la métrica")).toBeInTheDocument();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByText("Explicación de la métrica")).not.toBeInTheDocument();
  });

  it("Escape cierra la explicación", () => {
    render(<AyudaInfo texto="Explicación de la métrica" />);
    fireEvent.click(screen.getByRole("button"));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByText("Explicación de la métrica")).not.toBeInTheDocument();
  });

  it("usa la etiqueta pasada como nombre accesible del botón", () => {
    render(<AyudaInfo texto="Explicación" etiqueta="Qué es Alcance" />);
    expect(screen.getByRole("button", { name: "Qué es Alcance" })).toBeInTheDocument();
  });
});
