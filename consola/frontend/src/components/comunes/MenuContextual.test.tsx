import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MenuFlotante } from "./MenuContextual";

describe("MenuFlotante", () => {
  it("su raíz lleva pointer-events-auto (clicable sobre un diálogo modal)", () => {
    // El menú se portaliza a <body>; dentro de un modal Radix, body queda en pointer-events:none.
    // Sin `pointer-events-auto` en la raíz, los ítems (p. ej. «Asignar a…» en el calendario) no
    // serían clicables. Este test fija ese requisito no obvio para que un refactor no lo borre.
    render(
      <MenuFlotante
        pos={{ x: 0, y: 0 }}
        items={[{ etiqueta: "Asignar a…", onClick: () => {} }]}
        onClose={() => {}}
      />,
    );
    expect(screen.getByRole("menu").className).toContain("pointer-events-auto");
  });

  it("un ítem dispara su onClick y cierra el menú", () => {
    const onClick = vi.fn();
    const onClose = vi.fn();
    render(
      <MenuFlotante
        pos={{ x: 0, y: 0 }}
        items={[{ etiqueta: "Asignar a…", onClick }]}
        onClose={onClose}
      />,
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "Asignar a…" }));
    expect(onClose).toHaveBeenCalled();
    expect(onClick).toHaveBeenCalled();
  });
});
