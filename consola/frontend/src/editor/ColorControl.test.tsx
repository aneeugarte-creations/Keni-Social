/**
 * Tests del ColorControl (selector de color completo, estilo Canva):
 *  - Entrada HEXADECIMAL: normaliza lo tecleado (sin `#`, forma corta), descarta lo inválido y
 *    PRESERVA el alfa del valor actual (el alfa lo gobierna el deslizador de opacidad).
 *  - Paleta de SÓLIDOS PREDETERMINADOS: un clic aplica la muestra tal cual.
 *  - OPACIDAD: el deslizador produce `#RRGGBBAA` y «Transparente» pone alfa 0.
 *  - SWATCHES GUARDADAS: «Guardar color» persiste el color actual (localStorage por marca), la
 *    muestra guardada se aplica con un clic y se puede quitar.
 *  - El espectro y la tira de tono están presentes (la geometría del arrastre no se ejercita en
 *    jsdom: no hay layout real).
 *  El control vive dentro del editor (lee el documento para «En el diseño») y consulta la marca
 *  vía react-query con contexto de marca OPCIONAL: sin provider de marca no hay sección «Marca».
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ColorControl } from "./ColorControl";
import { ProveedorEditor } from "./contexto";
import { documentoVacio } from "./documento";
import { crearStoreEditor } from "./store";
import { cargarSwatches } from "./swatches-guardados";

const FORMATO = { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 };

function montar(valor: string, onChange: (c: string) => void, titulo?: string) {
  const store = crearStoreEditor(documentoVacio(FORMATO, "m1"));
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ProveedorEditor store={store}>
        <ColorControl valor={valor} onChange={onChange} titulo={titulo} />
      </ProveedorEditor>
    </QueryClientProvider>,
  );
}

function abrir(nombre = "Color") {
  fireEvent.click(screen.getByRole("button", { name: nombre }));
}

function tecleaHex(texto: string) {
  const hex = screen.getByRole("textbox", { name: "Color en hexadecimal" });
  fireEvent.change(hex, { target: { value: texto } });
  fireEvent.keyDown(hex, { key: "Enter" });
}

describe("ColorControl — entrada hexadecimal", () => {
  it("normaliza lo tecleado (sin '#', minúsculas) y emite #RRGGBB", () => {
    const onChange = vi.fn();
    montar("#FF0000", onChange);
    abrir();
    tecleaHex("00b0f0");
    expect(onChange).toHaveBeenCalledWith("#00B0F0");
  });

  it("expande la forma corta de 3 dígitos", () => {
    const onChange = vi.fn();
    montar("#FF0000", onChange);
    abrir();
    tecleaHex("fff");
    expect(onChange).toHaveBeenCalledWith("#FFFFFF");
  });

  it("ignora lo no interpretable", () => {
    const onChange = vi.fn();
    montar("#FF0000", onChange);
    abrir();
    tecleaHex("zzz");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("PRESERVA el alfa del valor actual (#RRGGBBAA)", () => {
    const onChange = vi.fn();
    montar("#11223380", onChange);
    abrir();
    tecleaHex("ABCDEF");
    expect(onChange).toHaveBeenCalledWith("#ABCDEF80");
  });
});

describe("ColorControl — paleta de sólidos predeterminados", () => {
  it("un clic en la muestra aplica el color", () => {
    const onChange = vi.fn();
    montar("#FF0000", onChange);
    abrir();
    fireEvent.click(screen.getByTitle("#5CE1E6"));
    expect(onChange).toHaveBeenCalledWith("#5CE1E6");
  });
});

describe("ColorControl — opacidad y transparente", () => {
  it("el deslizador de opacidad produce #RRGGBBAA", () => {
    const onChange = vi.fn();
    montar("#FF0000", onChange);
    abrir();
    fireEvent.change(screen.getByRole("slider", { name: "Opacidad" }), { target: { value: "128" } });
    expect(onChange).toHaveBeenCalledWith("#FF000080");
  });

  it("«Transparente» pone alfa 0 conservando el RGB", () => {
    const onChange = vi.fn();
    montar("#FF0000", onChange);
    abrir();
    fireEvent.click(screen.getByRole("button", { name: "Transparente" }));
    expect(onChange).toHaveBeenCalledWith("#FF000000");
  });
});

describe("ColorControl — espectro completo", () => {
  it("el cuadro de saturación/brillo y la tira de tono están en el popover", () => {
    montar("#FF0000", vi.fn(), "Color del texto");
    abrir("Color del texto");
    expect(screen.getByLabelText("Espectro de color (saturación y brillo)")).toBeInTheDocument();
    expect(screen.getByLabelText("Tono")).toBeInTheDocument();
  });
});

describe("ColorControl — swatches guardadas", () => {
  // Sin provider de marca la paleta se guarda bajo la marca vacía.
  beforeEach(() => localStorage.clear());

  it("«Guardar color» persiste el color actual y lo muestra como muestra reutilizable", () => {
    montar("#123456", vi.fn());
    abrir();
    fireEvent.click(screen.getByRole("button", { name: /Guardar color/ }));
    expect(cargarSwatches("")).toEqual(["#123456"]);
    // La muestra guardada queda disponible (un swatch con su hex como título).
    expect(screen.getByTitle("#123456")).toBeInTheDocument();
  });

  it("una swatch guardada se aplica con un clic", () => {
    const onChange = vi.fn();
    localStorage.setItem("keni:swatches:_", JSON.stringify(["#123456"]));
    montar("#FF0000", onChange);
    abrir();
    fireEvent.click(screen.getByTitle("#123456"));
    expect(onChange).toHaveBeenCalledWith("#123456");
  });

  it("una swatch guardada se puede quitar", () => {
    localStorage.setItem("keni:swatches:_", JSON.stringify(["#123456"]));
    montar("#FF0000", vi.fn());
    abrir();
    fireEvent.click(screen.getByRole("button", { name: "Quitar #123456" }));
    expect(cargarSwatches("")).toEqual([]);
  });

  it("no permite guardar dos veces el mismo color (botón deshabilitado)", () => {
    montar("#00B0F0", vi.fn());
    abrir();
    fireEvent.click(screen.getByRole("button", { name: /Guardar color/ }));
    expect(screen.getByRole("button", { name: /Guardar color/ })).toBeDisabled();
    expect(cargarSwatches("")).toEqual(["#00B0F0"]);
  });
});
