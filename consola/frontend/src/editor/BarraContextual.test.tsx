/**
 * Tests de la barra CONTEXTUAL de texto (patrón Canva):
 *  - Interlineado: select de presets (1.0/1.15/1.3/1.5/2.0) + el valor actual si no es preset
 *    (p. ej. el 1.14 por defecto de las plantillas). Cambiarlo actualiza la capa.
 *  - Espaciado entre letras (tracking): stepper en px que actualiza `interletra`.
 *  Ambos campos viajan en el documento y los respeta el export del servidor (`dibujar.mjs`):
 *  nada de propiedades que el editor muestre y el export ignore.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BarraContextual } from "./BarraContextual";
import { ProveedorEditor } from "./contexto";
import { documentoVacio, nuevaCapaTexto, type CapaTexto } from "./documento";
import { crearStoreEditor } from "./store";

const FORMATO = { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 };

function montarConTexto(parcial: Partial<CapaTexto> = {}) {
  const doc = documentoVacio(FORMATO, "m1");
  doc.capas.push(nuevaCapaTexto({ id: "t1", ...parcial }));
  const store = crearStoreEditor(doc);
  store.getState().seleccionar("t1");
  render(
    <ProveedorEditor store={store}>
      <BarraContextual onAbrirAjustes={vi.fn()} onReencuadrar={vi.fn()} onReemplazar={vi.fn()} />
    </ProveedorEditor>,
  );
  return store;
}

function capaTexto(store: ReturnType<typeof crearStoreEditor>): CapaTexto {
  return store.getState().documento.capas.find((c) => c.id === "t1") as CapaTexto;
}

describe("BarraContextual — interlineado", () => {
  it("ofrece los presets y cambiarlo actualiza la capa", () => {
    const store = montarConTexto({ interlineado: 1.15 });
    const select = screen.getByLabelText("Interlineado");
    // Presets estilo Canva presentes.
    for (const etiqueta of ["1.0", "1.15", "1.3", "1.5", "2.0"]) {
      expect(screen.getByRole("option", { name: etiqueta })).toBeInTheDocument();
    }
    fireEvent.change(select, { target: { value: "1.5" } });
    expect(capaTexto(store).interlineado).toBe(1.5);
  });

  it("un valor NO preset (1.14 por defecto) aparece como opción y queda seleccionado", () => {
    montarConTexto(); // default de fábrica: 1.14
    const select = screen.getByLabelText("Interlineado") as HTMLSelectElement;
    expect(select.value).toBe("1.14");
    expect(screen.getByRole("option", { name: "1.14" })).toBeInTheDocument();
  });
});

describe("BarraContextual — espaciado entre letras (tracking)", () => {
  it("el stepper actualiza `interletra` en px", () => {
    const store = montarConTexto({ interletra: 0 });
    const input = screen.getByLabelText("Espaciado entre letras");
    fireEvent.change(input, { target: { value: "8" } });
    fireEvent.blur(input);
    expect(capaTexto(store).interletra).toBe(8);
  });

  it("los botones −/+ ajustan el tracking de 1 en 1", () => {
    const store = montarConTexto({ interletra: 2 });
    fireEvent.click(screen.getByTitle("Espaciado entre letras: más"));
    expect(capaTexto(store).interletra).toBe(3);
    fireEvent.click(screen.getByTitle("Espaciado entre letras: menos"));
    expect(capaTexto(store).interletra).toBe(2);
  });

  it("admite tracking negativo hasta el mínimo (−20)", () => {
    const store = montarConTexto({ interletra: 0 });
    const input = screen.getByLabelText("Espaciado entre letras");
    fireEvent.change(input, { target: { value: "-99" } });
    fireEvent.blur(input);
    expect(capaTexto(store).interletra).toBe(-20);
  });
});

describe("BarraContextual — tamaño de letra (regresión)", () => {
  it("el stepper de tamaño sigue editando `tamano`", () => {
    const store = montarConTexto({ tamano: 64 });
    const input = screen.getByLabelText("Tamaño de letra");
    fireEvent.change(input, { target: { value: "72" } });
    fireEvent.blur(input);
    expect(capaTexto(store).tamano).toBe(72);
  });
});

describe("BarraContextual — cursiva (I) y subrayado (U)", () => {
  it("I conmuta `cursiva` en una familia CON itálica (Barlow)", () => {
    const store = montarConTexto(); // familia por defecto: Barlow
    const btn = screen.getByRole("button", { name: "Cursiva" });
    expect(btn).not.toBeDisabled();
    expect(btn).toHaveAttribute("title", "Cursiva");
    fireEvent.click(btn);
    expect(capaTexto(store).cursiva).toBe(true);
    fireEvent.click(btn);
    expect(capaTexto(store).cursiva).toBe(false);
  });

  it("I queda DESHABILITADO (con tooltip) si la familia no tiene itálica (Anton)", () => {
    const store = montarConTexto({ familia: "Anton" });
    const btn = screen.getByRole("button", { name: "Cursiva" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", "Esta fuente no tiene cursiva");
    fireEvent.click(btn);
    expect(capaTexto(store).cursiva).toBeUndefined(); // el clic no hace nada
  });

  it("las familias lógicas legadas ('sans'/'condensada') resuelven a Barlow: I habilitado", () => {
    montarConTexto({ familia: "condensada" });
    expect(screen.getByRole("button", { name: "Cursiva" })).not.toBeDisabled();
  });

  it("U conmuta `subrayado`", () => {
    const store = montarConTexto();
    const btn = screen.getByRole("button", { name: "Subrayado" });
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);
    expect(capaTexto(store).subrayado).toBe(true);
    fireEvent.click(btn);
    expect(capaTexto(store).subrayado).toBe(false);
  });

  it("U queda DESHABILITADO para el texto en arco (curva), con tooltip", () => {
    const store = montarConTexto({ curva: { radio: 600 } });
    const btn = screen.getByRole("button", { name: "Subrayado" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", "El texto en arco no admite subrayado");
    fireEvent.click(btn);
    expect(capaTexto(store).subrayado).toBeUndefined();
  });
});

describe("BarraContextual — tachado (S)", () => {
  it("S conmuta `tachado` (combinable con el subrayado)", () => {
    const store = montarConTexto({ subrayado: true });
    const btn = screen.getByRole("button", { name: "Tachado" });
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);
    expect(capaTexto(store).tachado).toBe(true);
    expect(capaTexto(store).subrayado).toBe(true); // no se pisan
    fireEvent.click(btn);
    expect(capaTexto(store).tachado).toBe(false);
  });

  it("S queda DESHABILITADO para el texto en arco (curva), con tooltip (mismo trato que U)", () => {
    const store = montarConTexto({ curva: { radio: 600 } });
    const btn = screen.getByRole("button", { name: "Tachado" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", "El texto en arco no admite tachado");
    fireEvent.click(btn);
    expect(capaTexto(store).tachado).toBeUndefined();
  });
});
