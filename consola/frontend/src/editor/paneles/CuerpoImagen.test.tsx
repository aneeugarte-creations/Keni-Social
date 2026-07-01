// Presets de filtro de un clic del inspector de imagen: cada chip fija un `filtros` completo. "B&N"
// desatura del todo (saturación 0 = gris en previa y export); "Quitar" vuelve a neutro conservando
// el duotono si lo hubiera. El `set` del inspector recibe el `filtros` resultante.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";

import { type CapaImagen, documentoVacio, nuevaCapaImagen } from "../documento";
import { crearStoreEditor } from "../store";
import { CtxEditor } from "../usarEditor";
import { CuerpoImagen } from "./CuerpoImagen";

// El cuerpo monta ColorControl (Sombra/Luz del duotono) que consulta la paleta de marca con
// react-query; un cliente vacío basta (los presets no dependen de datos remotos).
function montar(capaParcial: Partial<CapaImagen> = {}) {
  const doc = documentoVacio({ w: 1080, h: 1350, safe_top: 0, safe_bottom: 0 }, "m1");
  const capa = nuevaCapaImagen("obj-1", { id: "img1", ...capaParcial });
  doc.capas.push(capa);
  const store = crearStoreEditor(doc);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const set = vi.fn();
  render(
    createElement(
      QueryClientProvider,
      { client: qc },
      createElement(CtxEditor.Provider, { value: store }, createElement(CuerpoImagen, { capa, set, familias: [] })),
    ),
  );
  return { set, capa };
}

describe("CuerpoImagen — presets de filtro de un clic", () => {
  it("ofrece los cinco chips de preset", () => {
    montar();
    for (const etiqueta of ["B&N", "Cálido", "Dramático", "Desaturado marca", "Quitar"]) {
      expect(screen.getByRole("button", { name: etiqueta })).toBeInTheDocument();
    }
  });

  it("«B&N» desatura del todo (saturación 0)", () => {
    const { set } = montar();
    fireEvent.click(screen.getByRole("button", { name: "B&N" }));
    expect(set).toHaveBeenCalledTimes(1);
    const { filtros } = set.mock.calls[0][0] as { filtros: NonNullable<CapaImagen["filtros"]> };
    expect(filtros.saturacion).toBe(0);
  });

  it("«Quitar» vuelve a null cuando no hay duotono", () => {
    const { set } = montar({ filtros: { brillo: 0.8, contraste: 1.4, saturacion: 1.2, desenfoque: 0 } });
    fireEvent.click(screen.getByRole("button", { name: "Quitar" }));
    expect(set).toHaveBeenCalledWith({ filtros: null });
  });

  it("«Quitar» conserva el duotono si estaba activo", () => {
    const duotono = { sombra: "#111315", luz: "#E30613" };
    const { set } = montar({ filtros: { brillo: 0.8, contraste: 1.4, saturacion: 1.2, desenfoque: 0, duotono } });
    fireEvent.click(screen.getByRole("button", { name: "Quitar" }));
    const { filtros } = set.mock.calls[0][0] as { filtros: NonNullable<CapaImagen["filtros"]> };
    expect(filtros.duotono).toEqual(duotono);
    expect(filtros.saturacion).toBe(1);
  });

  it("un preset de color conserva el duotono existente", () => {
    const duotono = { sombra: "#111315", luz: "#E30613" };
    const { set } = montar({ filtros: { brillo: 1, contraste: 1, saturacion: 1, desenfoque: 0, duotono } });
    fireEvent.click(screen.getByRole("button", { name: "Cálido" }));
    const { filtros } = set.mock.calls[0][0] as { filtros: NonNullable<CapaImagen["filtros"]> };
    expect(filtros.duotono).toEqual(duotono);
    expect(filtros.saturacion).toBeCloseTo(1.35);
  });
});
