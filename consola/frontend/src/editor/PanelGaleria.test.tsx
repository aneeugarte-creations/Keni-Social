/**
 * Tests del panel «Galería» del rail del editor (activos de marca, ya en S3):
 *  - Insertar: clic en un activo de imagen (arte) inserta una capa imagen centrada con el
 *    ASPECT-RATIO real de la foto y la SELECCIONA; clic en un logo inserta una capa logo y
 *    la selecciona. Regresión del bug del snapshot obsoleto: la selección debe leerse del
 *    estado FRESCO tras `agregar` (el documento vacío ya trae una capa, así que el snapshot
 *    viejo seleccionaría la capa equivocada).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Lee dimensiones de la foto al insertar: en jsdom las imágenes no cargan, así que se mockea
// con un 800×600 fijo (aspect 4:3) para verificar el cálculo del aspect-ratio.
vi.mock("./useImagen", () => ({
  leerDimensionesUrl: vi.fn(async () => ({ w: 800, h: 600 })),
}));

import * as apiMod from "@/lib/api";
import type { ActivoMarca } from "@/lib/api";

import { documentoVacio } from "./documento";
import { ProveedorEditor } from "./contexto";
import { PanelGaleria } from "./PanelGaleria";
import { crearStoreEditor } from "./store";

const FORMATO = { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 };

function activo(parcial: Partial<ActivoMarca>): ActivoMarca {
  return {
    id: "a1",
    marca: "m1",
    tipo: "arte",
    nombre: "Activo",
    objeto: "media/a1.png",
    metadatos: {},
    lineas: [],
    aprobado: true,
    url: "/api/media/media/a1.png",
    marca_nombre: "UnoTV",
    autor_id: "u1",
    autor_nombre: "Uno",
    creado: "2026-01-01",
    actualizado: "2026-01-01",
    ...parcial,
  };
}

const ACTIVOS: ActivoMarca[] = [
  activo({ id: "g1", tipo: "arte", nombre: "Atardecer", objeto: "media/atardecer.png" }),
  activo({ id: "l1", tipo: "logo", nombre: "Logo blanco", objeto: "media/logo-blanco.png" }),
];

function montar(marca = "m1") {
  vi.spyOn(apiMod.api, "marcaActivos").mockResolvedValue({ activos: ACTIVOS });
  const store = crearStoreEditor(documentoVacio(FORMATO, marca));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui = (
    <QueryClientProvider client={qc}>
      <ProveedorEditor store={store}>
        <PanelGaleria marca={marca} />
      </ProveedorEditor>
    </QueryClientProvider>
  );
  return { store, ...render(ui) };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("PanelGaleria — insertar activos en el lienzo", () => {
  it("clic en un arte inserta una capa imagen con el aspect-ratio real y la SELECCIONA", async () => {
    const { store } = montar();
    fireEvent.click(await screen.findByTitle(/Atardecer — clic para insertar/));
    // El documento vacío ya trae su hueco de foto (oculto): el arte se AÑADE encima.
    await waitFor(() => expect(store.getState().documento.capas).toHaveLength(2));
    const st = store.getState();
    const capa = st.documento.capas.at(-1)!;
    expect(capa.tipo).toBe("imagen");
    expect((capa as { objeto?: string }).objeto).toBe("media/atardecer.png");
    // Media anchura del lienzo (1080·0.5 = 540) con el aspect 4:3 del mock => 405 de alto.
    expect(capa.w).toBe(540);
    expect(capa.h).toBe(405);
    // La selección apunta a la capa NUEVA (estado fresco tras agregar, no el snapshot viejo).
    expect(st.seleccion).toBe(capa.id);
  });

  it("clic en un logo inserta una capa logo y la SELECCIONA", async () => {
    const { store } = montar();
    fireEvent.click(await screen.findByTitle(/Logo blanco — clic para insertar/));
    await waitFor(() => expect(store.getState().documento.capas).toHaveLength(2));
    const st = store.getState();
    const capa = st.documento.capas.at(-1)!;
    expect(capa.tipo).toBe("logo");
    expect((capa as { media_id?: string }).media_id).toBe("media/logo-blanco.png");
    expect(st.seleccion).toBe(capa.id);
  });
});
