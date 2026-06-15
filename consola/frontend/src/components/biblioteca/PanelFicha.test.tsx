import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PanelFicha } from "./PanelFicha";
import type { DocumentoTexto } from "@/types";

function doc(parcial: Partial<DocumentoTexto> = {}): DocumentoTexto {
  return {
    id: "doc-1",
    titulo: "Voz de marca",
    tipo: "voz",
    carpeta: "marcas",
    cuerpo: "",
    creado: "2026-01-01T00:00:00",
    actualizado: "2026-01-01T00:00:00",
    clase: "voz",
    marcas: ["unotv"],
    etiquetas: ["breaking"],
    prioridad: 10,
    ...parcial,
  };
}

const MARCAS = [
  { id: "unotv", nombre: "UnoTV" },
  { id: "claro", nombre: "Claro Sports" },
];

describe("PanelFicha", () => {
  it("guarda la descripción al teclear", () => {
    const onEditar = vi.fn();
    render(<PanelFicha borrador={doc()} marcas={MARCAS} onEditar={onEditar} />);
    fireEvent.change(screen.getByLabelText("Descripción"), { target: { value: "Hola" } });
    expect(onEditar).toHaveBeenCalledWith({ descripcion: "Hola" });
  });

  it("parsea las etiquetas por comas al salir del campo", () => {
    const onEditar = vi.fn();
    render(<PanelFicha borrador={doc()} marcas={MARCAS} onEditar={onEditar} />);
    const campo = screen.getByLabelText("Etiquetas");
    fireEvent.change(campo, { target: { value: " a, b ,, c " } });
    fireEvent.blur(campo);
    expect(onEditar).toHaveBeenCalledWith({ etiquetas: ["a", "b", "c"] });
  });

  it("alterna una marca con el checkbox", () => {
    const onEditar = vi.fn();
    render(<PanelFicha borrador={doc()} marcas={MARCAS} onEditar={onEditar} />);
    fireEvent.click(screen.getByLabelText("Claro Sports"));
    expect(onEditar).toHaveBeenCalledWith({ marcas: ["unotv", "claro"] });
  });

  it("oculta los campos editoriales para documentos de tipo prompt", () => {
    const onEditar = vi.fn();
    render(<PanelFicha borrador={doc({ tipo: "prompt" })} marcas={MARCAS} onEditar={onEditar} />);
    expect(screen.queryByText("Marcas a las que aplica")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Clase")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Prioridad de ensamblaje")).not.toBeInTheDocument();
    // Los campos comunes siguen presentes.
    expect(screen.getByLabelText("Descripción")).toBeInTheDocument();
  });
});
