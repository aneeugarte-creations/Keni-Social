/**
 * Tests del inspector del LIENZO (sin capa seleccionada). El foco: elegir un PRESET de formato debe
 * REENCUADRAR el contenido (reescala + recoloca las capas con las proporciones del destino, igual que
 * «Adaptar a…» de la barra), no solo cambiar w/h dejando las capas descolocadas/estiradas.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProveedorEditor } from "../contexto";
import { documentoVacio, nuevaCapaTexto } from "../documento";
import { crearStoreEditor } from "../store";

import { CuerpoLienzo } from "./CuerpoLienzo";

// Feed vertical 4:5 -> cuadrado 1:1 (cambia el alto, así el reencuadre escala y recoloca).
const F45 = { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 };

function montar() {
  const base = documentoVacio(F45, "claro-sports");
  // Un titular NO a sangre, centrado horizontalmente, para observar el reencuadre.
  const titular = nuevaCapaTexto({ x: 240, y: 600, w: 600, h: 160, tamano: 80 });
  const store = crearStoreEditor({ ...base, capas: [...base.capas, titular] });
  render(
    <ProveedorEditor store={store}>
      <CuerpoLienzo />
    </ProveedorEditor>,
  );
  return store;
}

describe("CuerpoLienzo — preset de formato reencuadra (no deforma)", () => {
  it("al elegir 1:1 cambia el lienzo Y reescala el titular (proporción conservada)", () => {
    const store = montar();
    const antes = store.getState().documento.capas.find((c) => c.tipo === "texto");
    expect(antes?.tipo === "texto" && antes.tamano).toBe(80);

    fireEvent.click(screen.getByRole("button", { name: "1:1" }));

    const doc = store.getState().documento;
    // El lienzo adoptó el preset cuadrado.
    expect(doc.formato).toMatchObject({ w: 1080, h: 1080 });
    const despues = doc.capas.find((c) => c.tipo === "texto");
    // El titular se REESCALÓ (no quedó a tamaño 80 sobre un lienzo más bajo): con 1350 -> 1080 el
    // factor uniforme < 1, así que el tamaño de fuente encogió.
    expect(despues?.tipo === "texto" && despues.tamano).toBeLessThan(80);
    expect(despues?.tipo === "texto" && despues.tamano).toBeGreaterThan(0);
    // El hueco de foto a sangre vuelve a cubrir el lienzo nuevo (no queda a 1350 de alto).
    const hueco = doc.capas.find((c) => c.tipo === "imagen" && c.es_foto);
    expect(hueco && hueco.h).toBe(1080);
  });
});
