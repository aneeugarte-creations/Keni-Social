/**
 * Tests para EditorCarrusel: gestión de los slides extra de un carrusel.
 *
 * - Cada fila expone su menú "⋮" SIEMPRE visible (antes estaba escondido tras click-derecho):
 *   reemplazar / reordenar / quitar son alcanzables con un clic.
 * - "Bajar"/"Quitar" llaman a onCambio con la lista reordenada / recortada.
 * - "Reemplazar media" sube un archivo y SUSTITUYE el media de ESE slide (objeto + tipo),
 *   sin moverlo de sitio.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EditorCarrusel } from "./EditorCarrusel";
import type { SlideCarrusel } from "@/lib/carrusel";

const SLIDES: SlideCarrusel[] = [
  { tipo: "imagen", objeto: "artes/a.png" },
  { tipo: "imagen", objeto: "artes/b.png" },
];

function renderEditor(overrides: Partial<React.ComponentProps<typeof EditorCarrusel>> = {}) {
  const onCambio = vi.fn();
  render(
    <EditorCarrusel slides={SLIDES} onCambio={overrides.onCambio ?? onCambio} {...overrides} />,
  );
  return { onCambio: overrides.onCambio ?? onCambio };
}

/** Abre el menú "⋮" de la fila `i` (0-based) y devuelve su contenido. */
function abrirMenu(i: number) {
  const kebabs = screen.getAllByRole("button", { name: "Más acciones" });
  fireEvent.click(kebabs[i]);
}

describe("EditorCarrusel · acciones por slide", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.unstubAllGlobals());

  it("muestra un menú de acciones VISIBLE por slide (no escondido tras click-derecho)", () => {
    renderEditor();
    // Un kebab por slide, sin hover ni click-derecho.
    expect(screen.getAllByRole("button", { name: "Más acciones" })).toHaveLength(2);
    abrirMenu(0);
    expect(screen.getByRole("menuitem", { name: "Reemplazar media" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Bajar" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Quitar" })).toBeInTheDocument();
    // "Subir" en el primer slide está deshabilitado (ya es el primero).
    expect(screen.getByRole("menuitem", { name: "Subir" })).toBeDisabled();
  });

  it("'Editar placa' solo aparece (con onEditarPlaca) en slides de imagen CON procedencia", () => {
    const onEditarPlaca = vi.fn();
    render(
      <EditorCarrusel
        slides={[
          { tipo: "imagen", objeto: "artes/a.png", titular: "Clave" }, // con procedencia
          { tipo: "imagen", objeto: "artes/b.png" }, // crudo: no editable como placa
        ]}
        onCambio={vi.fn()}
        onEditarPlaca={onEditarPlaca}
      />,
    );
    // Slide 0 (con titular): ofrece "Editar placa" y dispara el callback con su índice.
    abrirMenu(0);
    fireEvent.click(screen.getByRole("menuitem", { name: "Editar placa" }));
    expect(onEditarPlaca).toHaveBeenCalledWith(0);
    // Slide 1 (crudo): NO ofrece "Editar placa".
    abrirMenu(1);
    expect(screen.queryByRole("menuitem", { name: "Editar placa" })).toBeNull();
  });

  it("sin onEditarPlaca no se ofrece 'Editar placa' aunque haya procedencia", () => {
    render(
      <EditorCarrusel
        slides={[{ tipo: "imagen", objeto: "artes/a.png", titular: "Clave" }]}
        onCambio={vi.fn()}
      />,
    );
    abrirMenu(0);
    expect(screen.queryByRole("menuitem", { name: "Editar placa" })).toBeNull();
  });

  it("'Bajar' reordena: onCambio recibe la lista con los dos slides intercambiados", () => {
    const { onCambio } = renderEditor();
    abrirMenu(0);
    fireEvent.click(screen.getByRole("menuitem", { name: "Bajar" }));
    expect(onCambio).toHaveBeenCalledWith([
      { tipo: "imagen", objeto: "artes/b.png" },
      { tipo: "imagen", objeto: "artes/a.png" },
    ]);
  });

  it("'Quitar' elimina solo ese slide", () => {
    const { onCambio } = renderEditor();
    abrirMenu(1);
    fireEvent.click(screen.getByRole("menuitem", { name: "Quitar" }));
    expect(onCambio).toHaveBeenCalledWith([{ tipo: "imagen", objeto: "artes/a.png" }]);
  });

  it("'Reemplazar media' sube un archivo y SUSTITUYE el media del slide elegido", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ id: "fotos/nuevo.png" }), { status: 200 })),
    );
    const { onCambio } = renderEditor();
    abrirMenu(0);
    fireEvent.click(screen.getByRole("menuitem", { name: "Reemplazar media" }));
    // El menú abre el selector de archivo (input único); soltamos un archivo de imagen.
    const input = screen.getByLabelText("Reemplazar media del slide") as HTMLInputElement;
    const archivo = new File(["x"], "foto.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [archivo] } });
    await waitFor(() =>
      expect(onCambio).toHaveBeenCalledWith([
        { tipo: "imagen", objeto: "fotos/nuevo.png" },
        { tipo: "imagen", objeto: "artes/b.png" },
      ]),
    );
  });
});
