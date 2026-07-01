/**
 * Tests de la chuleta «Atajos de teclado»: se muestra solo abierta y lista el SET INTENCIONADO
 * (coordinado con el bundle «canvas»): z-order de un paso en ⌘] / ⌘[ y frente/fondo en ⌘⇧] / ⌘⇧[.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AtajosTeclado } from "./AtajosTeclado";

describe("AtajosTeclado", () => {
  it("cerrada no pinta el diálogo", () => {
    render(<AtajosTeclado abierto={false} onCerrar={() => {}} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("abierta lista los atajos de creación, edición y ordenación", () => {
    render(<AtajosTeclado abierto onCerrar={() => {}} />);
    expect(screen.getByRole("dialog", { name: "Atajos de teclado" })).toBeInTheDocument();
    // Creación (T/R/C/L), deshacer y agrupar.
    expect(screen.getByText("Texto")).toBeInTheDocument();
    expect(screen.getByText("Deshacer")).toBeInTheDocument();
    expect(screen.getByText("Agrupar")).toBeInTheDocument();
  });

  it("lista el z-order del SET final: un paso (⌘] / ⌘[) y frente/fondo (⌘⇧] / ⌘⇧[)", () => {
    render(<AtajosTeclado abierto onCerrar={() => {}} />);
    expect(screen.getByText("Subir / bajar un paso")).toBeInTheDocument();
    expect(screen.getByText("Traer al frente / enviar al fondo")).toBeInTheDocument();
    // Las teclas del set final aparecen como <kbd> separados.
    expect(screen.getByText("⌘]")).toBeInTheDocument();
    expect(screen.getByText("⌘⇧]")).toBeInTheDocument();
    // Modificadores de redimensionar (Shift proporción, Alt centro).
    expect(screen.getByText("Bloquear proporción")).toBeInTheDocument();
    expect(screen.getByText("Escalar desde el centro")).toBeInTheDocument();
  });

  it("onCerrar se dispara al cambiar open a false", () => {
    const onCerrar = vi.fn();
    render(<AtajosTeclado abierto onCerrar={onCerrar} />);
    // El botón «Cerrar» del DialogContent (Radix) dispara onOpenChange(false).
    screen.getByRole("button", { name: "Cerrar" }).click();
    expect(onCerrar).toHaveBeenCalled();
  });
});
