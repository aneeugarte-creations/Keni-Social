/**
 * Tests del panel «Subidas» del rail del editor (patrón Canva, SOLO mecanismos existentes):
 *  - Recientes: lista las artes catalogadas con `tipo: "subida"` de la marca (fuente de verdad
 *    del backend: GET /api/artes), no un registro local.
 *  - Insertar: clic inserta una capa imagen centrada con el ASPECT-RATIO real de la foto y la
 *    selecciona (mismo mecanismo que la Galería); arrastrar publica el payload
 *    `application/x-keni-activo` que el Lienzo ya entiende (sin tocar Lienzo).
 *  - Subir: el selector (múltiple, image/*) y la zona de arrastre suben con `api.subirMedia` y
 *    catalogan con `api.guardarArte({tipo: "subida"})`; spinner por ítem mientras sube, error
 *    visible en el propio ítem (descartable) y ficheros no-imagen rechazados.
 *  - Vacío: CTA clara para subir las primeras imágenes.
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
import type { Arte } from "@/types";

import { documentoVacio } from "./documento";
import { ProveedorEditor } from "./contexto";
import { PanelSubidas } from "./PanelSubidas";
import { crearStoreEditor } from "./store";

const FORMATO = { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 };

function arte(parcial: Partial<Arte>): Arte {
  return {
    id: "a1",
    objeto: "artes/a1.png",
    url: "/api/media/artes/a1.png",
    marca: "m1",
    marca_nombre: "UnoTV",
    tipo: "subida",
    titulo: "Subida",
    etiquetas: [],
    creado: "2026-01-01",
    ...parcial,
  };
}

const SUBIDAS: Arte[] = [
  arte({ id: "a1", objeto: "artes/atardecer.png", titulo: "Atardecer" }),
  arte({ id: "a2", objeto: "artes/equipo.png", titulo: "Equipo" }),
];

function montar(marca = "m1") {
  const store = crearStoreEditor(documentoVacio(FORMATO, marca));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui = (
    <QueryClientProvider client={qc}>
      <ProveedorEditor store={store}>
        <PanelSubidas marca={marca} />
      </ProveedorEditor>
    </QueryClientProvider>
  );
  return { store, ...render(ui) };
}

function archivo(nombre = "foto.png", tipo = "image/png") {
  return new File(["x"], nombre, { type: tipo });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("PanelSubidas — recientes reutilizables (catálogo de artes tipo «subida»)", () => {
  it("lista las subidas de la marca pidiendo SOLO el tipo «subida»", async () => {
    const listar = vi.spyOn(apiMod.api, "listarArtes").mockResolvedValue({ artes: SUBIDAS });
    montar();
    expect(await screen.findByTitle(/Atardecer — clic para insertar/)).toBeInTheDocument();
    expect(screen.getByTitle(/Equipo — clic para insertar/)).toBeInTheDocument();
    expect(listar).toHaveBeenCalledWith({ marca: "m1", tipo: "subida" }, expect.anything());
  });

  it("vacío: CTA clara para subir las primeras imágenes", async () => {
    vi.spyOn(apiMod.api, "listarArtes").mockResolvedValue({ artes: [] });
    montar();
    expect(
      await screen.findByText("Sube tus propias imágenes y reutilízalas en tus diseños."),
    ).toBeInTheDocument();
  });

  it("si el listado falla, el error se ve en el panel", async () => {
    vi.spyOn(apiMod.api, "listarArtes").mockRejectedValue(new Error("Sin conexión."));
    montar();
    expect(await screen.findByText("Sin conexión.")).toBeInTheDocument();
  });
});

describe("PanelSubidas — insertar en el lienzo (mismo mecanismo que la Galería)", () => {
  it("clic inserta una capa imagen centrada con el aspect-ratio real y la selecciona", async () => {
    vi.spyOn(apiMod.api, "listarArtes").mockResolvedValue({ artes: SUBIDAS });
    const { store } = montar();
    fireEvent.click(await screen.findByTitle(/Atardecer — clic para insertar/));
    // El documento vacío ya trae su hueco de foto (oculto): la subida se AÑADE encima.
    await waitFor(() => expect(store.getState().documento.capas).toHaveLength(2));
    const st = store.getState();
    const capa = st.documento.capas.at(-1)!;
    expect(capa.tipo).toBe("imagen");
    expect((capa as { objeto?: string }).objeto).toBe("artes/atardecer.png");
    // Media anchura del lienzo (1080·0.5 = 540) con el aspect 4:3 del mock => 405 de alto.
    expect(capa.w).toBe(540);
    expect(capa.h).toBe(405);
    expect(capa.x).toBe(Math.round((1080 - 540) / 2));
    expect(st.seleccion).toBe(capa.id);
  });

  it("arrastrar publica el payload de activo que el Lienzo ya entiende en su onDrop", async () => {
    vi.spyOn(apiMod.api, "listarArtes").mockResolvedValue({ artes: SUBIDAS });
    montar();
    const item = await screen.findByTitle(/Equipo — clic para insertar/);
    const dataTransfer = { setData: vi.fn(), effectAllowed: "" };
    fireEvent.dragStart(item, { dataTransfer });
    expect(dataTransfer.setData).toHaveBeenCalledWith(
      "application/x-keni-activo",
      JSON.stringify({ objeto: "artes/equipo.png", tipo: "subida" }),
    );
  });
});

describe("PanelSubidas — subir imágenes", () => {
  it("subir desde el selector: spinner mientras sube, catálogo como «subida» y refresco al terminar", async () => {
    const listar = vi.spyOn(apiMod.api, "listarArtes").mockResolvedValue({ artes: [] });
    let terminar!: (v: { id: string; url: string }) => void;
    vi.spyOn(apiMod.api, "subirMedia").mockReturnValue(
      new Promise((res) => {
        terminar = res;
      }),
    );
    const guardar = vi
      .spyOn(apiMod.api, "guardarArte")
      .mockResolvedValue({ arte: arte({ id: "a9", objeto: "artes/foto.png", titulo: "foto" }) });
    const { container } = montar();

    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    expect(input).toHaveAttribute("multiple");
    expect(input).toHaveAttribute("accept", "image/*");
    fireEvent.change(input, { target: { files: [archivo()] } });

    // Spinner por ítem mientras sube (el nombre del fichero queda visible).
    expect(await screen.findByTitle("Subiendo foto.png…")).toBeInTheDocument();

    terminar({ id: "media/foto.png", url: "/api/media/media/foto.png" });
    // Se cataloga como reutilizable (tipo «subida», marca y título del fichero)…
    await waitFor(() =>
      expect(guardar).toHaveBeenCalledWith({
        objeto: "media/foto.png",
        tipo: "subida",
        marca: "m1",
        titulo: "foto",
      }),
    );
    // …el ítem en curso desaparece y el catálogo se refresca (invalidación => re-fetch).
    await waitFor(() => expect(screen.queryByTitle("Subiendo foto.png…")).not.toBeInTheDocument());
    await waitFor(() => expect(listar.mock.calls.length).toBeGreaterThan(1));
  });

  it("error de subida: visible en el propio ítem y descartable", async () => {
    vi.spyOn(apiMod.api, "listarArtes").mockResolvedValue({ artes: [] });
    vi.spyOn(apiMod.api, "subirMedia").mockRejectedValue(new Error("El archivo pesa demasiado."));
    const guardar = vi.spyOn(apiMod.api, "guardarArte");
    const { container } = montar();

    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    fireEvent.change(input, { target: { files: [archivo()] } });

    expect(await screen.findByText("El archivo pesa demasiado.")).toBeInTheDocument();
    expect(screen.getByText("foto.png")).toBeInTheDocument();
    expect(guardar).not.toHaveBeenCalled();
    // El ítem fallido se descarta con su botón «Quitar».
    fireEvent.click(screen.getByTitle("Quitar"));
    expect(screen.queryByText("El archivo pesa demasiado.")).not.toBeInTheDocument();
  });

  it("soltar ficheros en la zona de arrastre los sube (y los no-imagen no llegan al backend)", async () => {
    vi.spyOn(apiMod.api, "listarArtes").mockResolvedValue({ artes: [] });
    const subir = vi
      .spyOn(apiMod.api, "subirMedia")
      .mockResolvedValue({ id: "media/foto.png", url: "/api/media/media/foto.png" });
    vi.spyOn(apiMod.api, "guardarArte").mockResolvedValue({ arte: arte({}) });
    montar();

    const zona = screen.getByTitle("Arrastra imágenes aquí para subirlas");
    fireEvent.drop(zona, { dataTransfer: { files: [archivo(), archivo("doc.txt", "text/plain")] } });
    await waitFor(() => expect(subir).toHaveBeenCalledTimes(1));

    // Una zona con solo ficheros NO-imagen no sube nada.
    fireEvent.drop(zona, { dataTransfer: { files: [archivo("doc.txt", "text/plain")] } });
    await waitFor(() => expect(subir).toHaveBeenCalledTimes(1));
  });
});
