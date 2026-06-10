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
