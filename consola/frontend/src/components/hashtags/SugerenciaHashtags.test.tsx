import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Pieza } from "@/types";

import { SugerenciaHashtags } from "./SugerenciaHashtags";

/** Pieza mínima para el componente (solo usa estado + hashtags_sugeridos). */
function pieza(extra: Partial<Pieza> = {}): Pieza {
  return {
    estado: "en_revision",
    hashtags_sugeridos: ["#futbol", "#ligamx"],
    ...extra,
  } as Pieza;
}

describe("SugerenciaHashtags", () => {
  it("muestra los hashtags sugeridos y los controles cuando al copy le faltan", () => {
    render(
      <SugerenciaHashtags contenido="Gran partido hoy" pieza={pieza()} onAceptar={vi.fn()} />,
    );
    expect(screen.getByText("#futbol #ligamx")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /aceptar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /rechazar/i })).toBeInTheDocument();
  });

  it("no sugiere si el copy YA lleva un hashtag", () => {
    const { container } = render(
      <SugerenciaHashtags contenido="Gran partido #futbol" pieza={pieza()} onAceptar={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("no sugiere si no hay hashtags_sugeridos", () => {
    const { container } = render(
      <SugerenciaHashtags
        contenido="Gran partido"
        pieza={pieza({ hashtags_sugeridos: [] })}
        onAceptar={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("no sugiere en piezas publicadas", () => {
    const { container } = render(
      <SugerenciaHashtags
        contenido="Gran partido"
        pieza={pieza({ estado: "publicado" })}
        onAceptar={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("aceptar llama onAceptar con los hashtags sugeridos", () => {
    const onAceptar = vi.fn();
    render(<SugerenciaHashtags contenido="Gran partido" pieza={pieza()} onAceptar={onAceptar} />);
    fireEvent.click(screen.getByRole("button", { name: /aceptar/i }));
    expect(onAceptar).toHaveBeenCalledWith(["#futbol", "#ligamx"]);
  });

  it("rechazar oculta la sugerencia", () => {
    const { container } = render(
      <SugerenciaHashtags contenido="Gran partido" pieza={pieza()} onAceptar={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /rechazar/i }));
    expect(container).toBeEmptyDOMElement();
  });
});
