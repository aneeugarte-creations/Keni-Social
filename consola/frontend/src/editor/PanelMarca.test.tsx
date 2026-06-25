/**
 * Tests del panel «Marca» (Brand Kit estilo Canva) del rail del editor:
 *  - Pinta SOLO datos de marca que ya existen: plantilla de marca (logo + colores rojo/tinta/
 *    blanco + wordmark) y activos de marca (logos, paletas, tipografías), sin duplicar colores.
 *  - Logo: clic inserta una capa logo y la selecciona (mismo mecanismo que PanelGaleria).
 *  - Color: clic lo aplica a la capa de texto seleccionada (limpiando el degradado) o, sin
 *    selección, al FONDO del documento.
 *  - Tipografía: clic aplica la familia a la capa de texto seleccionada.
 *  - Estados vacíos claros («Esta marca aún no tiene logos…», etc.).
 *  - Aviso cuando la marca del documento difiere de la marca activa global (contexto opcional:
 *    sin provider no avisa ni rompe).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  MarcaActivaContexto,
  type ValorMarcaActiva,
} from "@/hooks/marca-activa-contexto";
import * as apiMod from "@/lib/api";
import type { ActivoMarca } from "@/lib/api";
import type { PlantillaMarca } from "@/types";

import { documentoVacio, nuevaCapaTexto, type CapaTexto } from "./documento";
import { ProveedorEditor } from "./contexto";
import { PanelMarca } from "./PanelMarca";
import { crearStoreEditor } from "./store";

const FORMATO = { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 };

const PLANTILLA: PlantillaMarca = {
  marca: "m1",
  rojo: "#E10600",
  tinta: "#1A1A1A",
  blanco: "#FFFFFF",
  etiqueta_default: "ÚLTIMA HORA",
  titular_mayusculas: true,
  titular_condensada: true,
  logo: "media/logo-uno.png",
  logo_url: "/api/media/media/logo-uno.png",
  logo_posicion: "superior-derecha",
  wordmark: "UnoTV",
};

function activo(parcial: Partial<ActivoMarca>): ActivoMarca {
  return {
    id: "a1",
    marca: "m1",
    tipo: "logo",
    nombre: "Activo",
    objeto: "media/a1.png",
    metadatos: {},
    categorias: [],
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
  activo({ id: "l1", tipo: "logo", nombre: "Logo blanco", objeto: "media/logo-blanco.png" }),
  activo({
    id: "p1",
    tipo: "paleta",
    nombre: "Paleta web",
    objeto: "",
    // El primero DUPLICA el rojo de la plantilla (no debe pintarse dos veces).
    metadatos: { colores: ["#E10600", "#0057B7"] },
  }),
  activo({
    id: "t1",
    tipo: "tipografia",
    nombre: "Titular",
    objeto: "media/titular.woff2",
    metadatos: { familia: "Uno Sans" },
  }),
];

function mockApi(plantilla: PlantillaMarca | null = PLANTILLA, activos: ActivoMarca[] = ACTIVOS) {
  if (plantilla) {
    vi.spyOn(apiMod.api, "plantillaMarca").mockResolvedValue({ plantilla });
  } else {
    vi.spyOn(apiMod.api, "plantillaMarca").mockRejectedValue(new Error("Marca desconocida."));
  }
  vi.spyOn(apiMod.api, "marcaActivos").mockResolvedValue({ activos });
}

function montar({
  marca = "m1",
  contexto,
}: { marca?: string; contexto?: Partial<ValorMarcaActiva> } = {}) {
  const store = crearStoreEditor(documentoVacio(FORMATO, marca));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const panel = (
    <QueryClientProvider client={qc}>
      <ProveedorEditor store={store}>
        <PanelMarca marca={marca} />
      </ProveedorEditor>
    </QueryClientProvider>
  );
  const ui = contexto ? (
    <MarcaActivaContexto.Provider value={valorMarca(contexto)}>{panel}</MarcaActivaContexto.Provider>
  ) : (
    panel
  );
  return { store, ...render(ui) };
}

function valorMarca(parcial: Partial<ValorMarcaActiva>): ValorMarcaActiva {
  return {
    marcaActiva: "m1",
    marcaPrimaria: "m1",
    enMarcaPrimaria: true,
    esMultiMarca: true,
    puedeTodas: false,
    marcasParaSwitch: [
      { id: "m1", nombre: "UnoTV" },
      { id: "m2", nombre: "Claro Sports" },
    ],
    nombreActiva: "UnoTV",
    cambiarMarca: () => {},
    volverAPrimaria: () => {},
    ...parcial,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("PanelMarca — kit de marca con datos reales", () => {
  it("pinta logos (principal + activos), colores sin duplicar y tipografías", async () => {
    mockApi();
    montar();
    // Logo principal de la plantilla + logo de activos.
    expect(await screen.findByTitle(/Logo principal — clic para insertar/)).toBeInTheDocument();
    expect(screen.getByTitle(/Logo blanco — clic para insertar/)).toBeInTheDocument();
    // Colores: rojo/tinta/blanco de la plantilla + el azul de la paleta; el rojo duplicado de la
    // paleta NO se pinta dos veces.
    expect(screen.getByLabelText("Aplicar color Color principal #E10600")).toBeInTheDocument();
    expect(screen.getByLabelText("Aplicar color Tinta #1A1A1A")).toBeInTheDocument();
    expect(screen.getByLabelText("Aplicar color Blanco #FFFFFF")).toBeInTheDocument();
    expect(screen.getByLabelText("Aplicar color Paleta web · 2 #0057B7")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Paleta web · 1/)).not.toBeInTheDocument();
    // Tipografía de marca por su familia.
    expect(screen.getByText("Uno Sans")).toBeInTheDocument();
    // Nombre legible de la marca del documento (de los activos, sin contexto global).
    expect(screen.getByText("UnoTV")).toBeInTheDocument();
  });

  it("clic en un logo inserta una capa logo y la selecciona", async () => {
    mockApi();
    const { store } = montar();
    fireEvent.click(await screen.findByTitle(/Logo blanco — clic para insertar/));
    const st = store.getState();
    const capa = st.documento.capas.at(-1)!;
    expect(capa.tipo).toBe("logo");
    expect((capa as { media_id?: string }).media_id).toBe("media/logo-blanco.png");
    expect(st.seleccion).toBe(capa.id);
  });

  it("clic en un color SIN selección lo aplica al fondo del documento", async () => {
    mockApi();
    const { store } = montar();
    fireEvent.click(await screen.findByLabelText("Aplicar color Tinta #1A1A1A"));
    expect(store.getState().documento.fondo).toEqual({ tipo: "color", color: "#1A1A1A" });
  });

  it("clic en un color con un TEXTO seleccionado colorea la capa (y limpia su degradado)", async () => {
    mockApi();
    const { store } = montar();
    const st = store.getState();
    st.agregar(
      nuevaCapaTexto({
        texto: "Titular",
        relleno_degradado: { desde: "#000000", hasta: "#FFFFFF" },
      }),
    );
    // Estado fresco tras agregar (el set del store reemplaza `documento`).
    const capa = store.getState().documento.capas.at(-1)!;
    st.seleccionar(capa.id);
    fireEvent.click(await screen.findByLabelText("Aplicar color Color principal #E10600"));
    const trasClic = store
      .getState()
      .documento.capas.find((c) => c.id === capa.id) as CapaTexto;
    expect(trasClic.color).toBe("#E10600");
    expect(trasClic.relleno_degradado).toBeNull();
    // El fondo NO cambió (el color fue a la capa).
    expect(store.getState().documento.fondo).toEqual({ tipo: "color", color: "#00000000" });
  });

  it("clic en una tipografía aplica la familia a la capa de texto seleccionada", async () => {
    mockApi();
    const { store } = montar();
    const st = store.getState();
    st.agregar(nuevaCapaTexto({ texto: "Titular" }));
    const capa = store.getState().documento.capas.at(-1)!;
    st.seleccionar(capa.id);
    fireEvent.click(await screen.findByText("Uno Sans"));
    const trasClic = store
      .getState()
      .documento.capas.find((c) => c.id === capa.id) as CapaTexto;
    expect(trasClic.familia).toBe("Uno Sans");
  });

  it("sin logos ni tipografías muestra estados vacíos claros (con el wordmark de respaldo)", async () => {
    mockApi({ ...PLANTILLA, logo: "", logo_url: "" }, []);
    montar();
    expect(
      await screen.findByText(/Esta marca aún no tiene logos\..*wordmark «UnoTV»/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Esta marca aún no tiene tipografías propias/)).toBeInTheDocument();
  });

  it("sin plantilla (404) ni paletas muestra el vacío de colores y no rompe", async () => {
    mockApi(null, []);
    montar();
    expect(
      await screen.findByText(/Esta marca aún no tiene colores definidos/),
    ).toBeInTheDocument();
  });

  it("avisa cuando la marca del documento difiere de la marca activa global", async () => {
    mockApi();
    montar({ contexto: { marcaActiva: "m2", nombreActiva: "Claro Sports" } });
    expect(await screen.findByText(/tu marca activa es «Claro Sports»/)).toBeInTheDocument();
  });

  it("NO avisa cuando la marca activa global coincide (ni en la vista «Todas»)", async () => {
    mockApi();
    montar({ contexto: { marcaActiva: "m1", nombreActiva: "UnoTV" } });
    expect(await screen.findByTitle(/Logo principal/)).toBeInTheDocument();
    expect(screen.queryByText(/tu marca activa es/)).not.toBeInTheDocument();
  });
});
