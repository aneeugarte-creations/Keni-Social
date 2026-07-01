// Tests del PanelCapas: la barra de alinear/ordenar aparece con selección y cablea las acciones del
// store, y el ojo/candado actúa sobre TODA la multi-selección cuando la fila está en ella.

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProveedorEditor } from "../contexto";
import { documentoVacio, nuevaCapaMarco, nuevaCapaTexto } from "../documento";
import { crearStoreEditor, type StoreEditor } from "../store";

import { PanelCapas } from "./PanelCapas";

const FORMATO = { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 };

function montar(seleccionar: (store: StoreEditor) => void) {
  const store = crearStoreEditor(documentoVacio(FORMATO, "m1"));
  const a = nuevaCapaMarco({ id: "a", nombre: "A", forma: "rect", x: 0, y: 0, w: 100, h: 100, z: 1 });
  const b = nuevaCapaMarco({ id: "b", nombre: "B", forma: "rect", x: 400, y: 400, w: 100, h: 100, z: 2 });
  const c = nuevaCapaTexto({ id: "c", nombre: "C", x: 800, y: 800, z: 3 });
  store.getState().agregar(a);
  store.getState().agregar(b);
  store.getState().agregar(c);
  seleccionar(store);
  render(
    <ProveedorEditor store={store}>
      <PanelCapas />
    </ProveedorEditor>,
  );
  return store;
}

describe("PanelCapas — barra de alinear/ordenar", () => {
  it("no aparece sin selección", () => {
    montar(() => {});
    expect(screen.queryByRole("toolbar", { name: "Alinear y ordenar" })).not.toBeInTheDocument();
  });

  it("con selección única ofrece alinear + traer al frente / enviar al fondo, sin distribuir", () => {
    montar((s) => s.getState().seleccionar("a"));
    const barra = screen.getByRole("toolbar", { name: "Alinear y ordenar" });
    expect(within(barra).getByLabelText("Traer al frente")).toBeInTheDocument();
    expect(within(barra).getByLabelText("Enviar al fondo")).toBeInTheDocument();
    expect(within(barra).queryByLabelText("Distribuir horizontal")).not.toBeInTheDocument();
  });

  it("«Traer al frente» cablea la acción del store (sube la z de la capa al tope)", () => {
    const store = montar((s) => s.getState().seleccionar("a"));
    fireEvent.click(within(screen.getByRole("toolbar", { name: "Alinear y ordenar" })).getByLabelText("Traer al frente"));
    const capas = store.getState().documento.capas;
    const a = capas.find((c) => c.id === "a")!;
    expect(a.z).toBeGreaterThan(Math.max(...capas.filter((c) => c.id !== "a").map((c) => c.z)));
  });

  it("«Alinear izquierda» centra la capa contra el borde seguro izquierdo del lienzo", () => {
    const store = montar((s) => s.getState().seleccionar("b"));
    fireEvent.click(within(screen.getByRole("toolbar", { name: "Alinear y ordenar" })).getByLabelText("Alinear izquierda"));
    expect(store.getState().documento.capas.find((c) => c.id === "b")!.x).toBe(0);
  });

  it("con ≥3 capas seleccionadas aparecen distribuir y ordenar", () => {
    montar((s) => {
      s.getState().seleccionar("a");
      s.getState().alternar("b");
      s.getState().alternar("c");
    });
    const barra = screen.getByRole("toolbar", { name: "Alinear y ordenar" });
    expect(within(barra).getByLabelText("Distribuir horizontal")).toBeInTheDocument();
    expect(within(barra).getByLabelText("Distribuir vertical")).toBeInTheDocument();
    expect(within(barra).getByLabelText("Ordenar")).toBeInTheDocument();
  });
});

// La fila cuyo nombre visible es `nombre` (rango por su span de texto). Devuelve el contenedor de
// fila para consultar sus botones (ojo/candado/papelera) sin depender del orden global.
function filaDe(nombre: string): HTMLElement {
  const etiqueta = screen.getByText(nombre);
  const fila = etiqueta.closest("div.flex");
  if (!fila) throw new Error(`sin fila para ${nombre}`);
  return fila as HTMLElement;
}

describe("PanelCapas — ojo/candado sobre la multi-selección", () => {
  it("ocultar desde una fila de la multi-selección oculta TODAS las seleccionadas", () => {
    const store = montar((s) => {
      s.getState().seleccionar("a");
      s.getState().alternar("b");
    });
    // La fila de A ofrece «Ocultar»; al pulsarla, A y B deben quedar ocultas (C no).
    fireEvent.click(within(filaDe("A")).getByTitle("Ocultar"));
    const capas = store.getState().documento.capas;
    expect(capas.find((c) => c.id === "a")!.visible).toBe(false);
    expect(capas.find((c) => c.id === "b")!.visible).toBe(false);
    expect(capas.find((c) => c.id === "c")!.visible).toBe(true);
  });

  it("bloquear en lote no toca los huecos de foto (siempre bloqueados)", () => {
    const store = montar((s) => {
      // Incluye el hueco de foto «foto» en la multi-selección junto con A.
      s.getState().seleccionar("a");
      s.getState().alternar("foto");
    });
    const foto = () => store.getState().documento.capas.find((c) => c.id === "foto")!;
    expect(foto().bloqueada).toBe(true);
    fireEvent.click(within(filaDe("A")).getByTitle("Bloquear"));
    expect(store.getState().documento.capas.find((c) => c.id === "a")!.bloqueada).toBe(true);
    expect(foto().bloqueada).toBe(true);
  });

  it("con selección única el ojo afecta SOLO a esa capa", () => {
    const store = montar((s) => s.getState().seleccionar("a"));
    fireEvent.click(within(filaDe("A")).getByTitle("Ocultar"));
    const capas = store.getState().documento.capas;
    expect(capas.find((c) => c.id === "a")!.visible).toBe(false);
    expect(capas.find((c) => c.id === "b")!.visible).toBe(true);
  });
});
