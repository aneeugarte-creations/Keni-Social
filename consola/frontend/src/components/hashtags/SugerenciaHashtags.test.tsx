import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Pieza } from "@/types";

import { SugerenciaHashtags } from "./SugerenciaHashtags";

/** Pieza mínima para el componente (estado + hashtags_sugeridos + hashtags_linea). */
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
    expect(screen.getByRole("button", { name: /aceptar hashtags sugeridos/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /rechazar/i })).toBeInTheDocument();
  });

  it("sigue sugiriendo SOLO lo que falta aunque el copy lleve otros hashtags distintos", () => {
    render(
      <SugerenciaHashtags contenido="Gran partido #futbol" pieza={pieza()} onAceptar={vi.fn()} />,
    );
    // #futbol ya está; se sigue ofreciendo el que falta (#ligamx), no se oculta del todo.
    expect(screen.getByText("#ligamx")).toBeInTheDocument();
  });

  it("no sugiere si el copy YA lleva todos los sugeridos (y no hay línea)", () => {
    const { container } = render(
      <SugerenciaHashtags
        contenido="Gran partido #futbol #ligamx"
        pieza={pieza()}
        onAceptar={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("no sugiere si no hay sugeridos ni línea", () => {
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
        pieza={pieza({ estado: "publicado", hashtags_linea: ["#nacional"] })}
        onAceptar={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("aceptar gris llama onAceptar solo con lo que falta", () => {
    const onAceptar = vi.fn();
    render(
      <SugerenciaHashtags contenido="Gran partido #futbol" pieza={pieza()} onAceptar={onAceptar} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /aceptar hashtags sugeridos/i }));
    expect(onAceptar).toHaveBeenCalledWith(["#ligamx"]);
  });

  it("rechazar oculta los sugeridos (pero no la línea)", () => {
    const { container } = render(
      <SugerenciaHashtags contenido="Gran partido" pieza={pieza()} onAceptar={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /rechazar/i }));
    expect(container).toBeEmptyDOMElement();
  });

  it("avisa en rojo del hashtag de la línea cuando falta, con su advertencia", () => {
    render(
      <SugerenciaHashtags
        contenido="Gran partido #futbol #ligamx"
        pieza={pieza({ hashtags_linea: ["#cienciatech"] })}
        onAceptar={vi.fn()}
      />,
    );
    expect(screen.getByText("#cienciatech")).toBeInTheDocument();
    expect(screen.getByText(/no pueden trackear bien/i)).toBeInTheDocument();
  });

  it("aceptar la línea llama onAceptar con su hashtag", () => {
    const onAceptar = vi.fn();
    render(
      <SugerenciaHashtags
        contenido="Gran partido #futbol #ligamx"
        pieza={pieza({ hashtags_linea: ["#cienciatech"] })}
        onAceptar={onAceptar}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /aceptar hashtag de la línea/i }));
    expect(onAceptar).toHaveBeenCalledWith(["#cienciatech"]);
  });

  it("no avisa de la línea si el copy ya la lleva (insensible a mayúsculas)", () => {
    const { container } = render(
      <SugerenciaHashtags
        contenido="Gran partido #CienciaTech #futbol #ligamx"
        pieza={pieza({ hashtags_linea: ["#cienciatech"] })}
        onAceptar={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
