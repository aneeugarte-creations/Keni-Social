// Tests del cuerpo de TEXTO del inspector:
//  - CONTADOR de caracteres bajo el textarea (solo conteo: la placa no se ata a una red).
//  - PESO: los pesos que la familia NO embebe se ATENÚAN (option `disabled`), patrón Canva.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProveedorEditor } from "../contexto";
import { documentoVacio, nuevaCapaTexto, type Capa, type CapaTexto } from "../documento";
import { crearStoreEditor } from "../store";

import { CuerpoTexto } from "./CuerpoTexto";

const FORMATO = { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 };

// El ColorControl del cuerpo consulta la plantilla de marca vía react-query y el store del editor:
// hacen falta ambos providers.
function montar(parcial: Partial<CapaTexto> = {}, familias = ["Barlow", "Montserrat", "Anton"]) {
  const capa = nuevaCapaTexto({ id: "t1", ...parcial });
  const set = vi.fn<(cambios: Partial<Capa>) => void>();
  const store = crearStoreEditor(documentoVacio(FORMATO, "m1"));
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ProveedorEditor store={store}>
        <CuerpoTexto capa={capa} set={set} familias={familias} />
      </ProveedorEditor>
    </QueryClientProvider>,
  );
  return { set };
}

describe("CuerpoTexto — contador de caracteres", () => {
  it("cuenta los caracteres del texto de la capa (sin límite: solo el conteo)", () => {
    montar({ texto: "Hola mundo" }); // 10 caracteres
    expect(screen.getByText("10")).toBeInTheDocument();
  });

  it("un texto vacío cuenta 0", () => {
    montar({ texto: "" });
    expect(screen.getByText("0")).toBeInTheDocument();
  });
});

describe("CuerpoTexto — pesos no disponibles por familia", () => {
  it("Barlow: 300/500/800/900 salen deshabilitados; 400/600/700 no", () => {
    montar({ familia: "Barlow" });
    const opcion = (nombre: RegExp) => screen.getByRole("option", { name: nombre }) as HTMLOptionElement;
    expect(opcion(/Ligera \(300\)/).disabled).toBe(true);
    expect(opcion(/Media \(500\)/).disabled).toBe(true);
    expect(opcion(/Extranegrita \(800\)/).disabled).toBe(true);
    expect(opcion(/Black \/ Negra \(900\)/).disabled).toBe(true);
    expect(opcion(/Regular \(400\)/).disabled).toBe(false);
    expect(opcion(/Seminegrita \(600\)/).disabled).toBe(false);
    expect(opcion(/Negrita \(700\)/).disabled).toBe(false);
  });

  it("Anton: solo 400 disponible; el resto deshabilitado y marcado «no disponible»", () => {
    montar({ familia: "Anton" });
    expect((screen.getByRole("option", { name: /Regular \(400\)/ }) as HTMLOptionElement).disabled).toBe(false);
    const ligera = screen.getByRole("option", { name: /Ligera \(300\)/ }) as HTMLOptionElement;
    expect(ligera.disabled).toBe(true);
    expect(ligera.textContent).toContain("no disponible");
  });

  it("Montserrat: todos los pesos disponibles (ninguna option deshabilitada)", () => {
    montar({ familia: "Montserrat" });
    for (const p of [/Ligera \(300\)/, /Media \(500\)/, /Extranegrita \(800\)/, /Black \/ Negra \(900\)/]) {
      expect((screen.getByRole("option", { name: p }) as HTMLOptionElement).disabled).toBe(false);
    }
  });
});
