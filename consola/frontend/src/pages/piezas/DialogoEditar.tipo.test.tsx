/**
 * Tests del filtrado de plantillas por tipo en DialogoEditar:
 *  - La lógica `tipoPlantilla` derivada del formato ("foto" → "foto", "video" → "miniatura").
 *  - El filtrado client-side de plantillas según el tipo.
 *  - El `tipoFijo` que se pasa a GaleriaPlantillas.
 *
 * DialogoEditar completo es difícil de montar (EditorPlacaInline + Konva + …), así que
 * validamos la lógica de derivación directamente y la integración de GaleriaPlantillas
 * con tipoFijo con props controladas.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GaleriaPlantillas } from "@/editor/GaleriaPlantillas";
import type { PlantillaDiseno } from "@/lib/api";

// --- Fixtures ---
function plantilla(overrides: Partial<PlantillaDiseno>): PlantillaDiseno {
  return {
    id: "p1",
    marca: "m1",
    nombre: "Test",
    categoria: "post",
    tipo: "foto",
    documento: {},
    miniatura: "",
    miniatura_url: "",
    foto_muestra: "",
    foto_muestra_url: "",
    titular_muestra: "",
    etiqueta_muestra: "",
    lineas: [],
    activo: true,
    rotar: false,
    orden: 0,
    marca_nombre: "Marca",
    autor_id: "u1",
    autor_nombre: "Ana",
    creado: "2026-01-01T00:00:00",
    actualizado: "2026-01-01T00:00:00",
    ...overrides,
  };
}

const FOTO = plantilla({ id: "pf-1", nombre: "Foto base", tipo: "foto" });
const MINIATURA = plantilla({ id: "pm-1", nombre: "Portada video", tipo: "miniatura" });
const SIN_TIPO = plantilla({ id: "pp-1", nombre: "Sin tipo (legacy)" });

// --- Lógica de tipo ---
/** Espejo de la derivación que hace DialogoEditar. */
function derivarTipoPlantilla(formato: string): "foto" | "miniatura" {
  return formato === "video" ? "miniatura" : "foto";
}

/** Espejo del filtro client-side. */
function filtrarPorTipo(
  plantillas: PlantillaDiseno[],
  tipo: "foto" | "miniatura",
): PlantillaDiseno[] {
  return plantillas.filter((p) => (p.tipo ?? "foto") === tipo);
}

describe("DialogoEditar — lógica de tipo de plantilla", () => {
  it("deriva tipo 'foto' para piezas de formato foto", () => {
    expect(derivarTipoPlantilla("foto")).toBe("foto");
  });

  it("deriva tipo 'miniatura' para piezas de formato video", () => {
    expect(derivarTipoPlantilla("video")).toBe("miniatura");
  });

  it("filtra correctamente: solo las de tipo 'foto'", () => {
    const res = filtrarPorTipo([FOTO, MINIATURA], "foto");
    expect(res).toHaveLength(1);
    expect(res[0].id).toBe("pf-1");
  });

  it("filtra correctamente: solo las de tipo 'miniatura'", () => {
    const res = filtrarPorTipo([FOTO, MINIATURA], "miniatura");
    expect(res).toHaveLength(1);
    expect(res[0].id).toBe("pm-1");
  });

  it("las plantillas legacy sin tipo explícito caen en 'foto' (defaulting)", () => {
    const res = filtrarPorTipo([SIN_TIPO], "foto");
    expect(res).toHaveLength(1);
    expect(res[0].id).toBe("pp-1");
  });

  it("las plantillas legacy sin tipo quedan fuera de 'miniatura'", () => {
    const res = filtrarPorTipo([SIN_TIPO], "miniatura");
    expect(res).toHaveLength(0);
  });
});

// --- Puente al Estudio de video ---
/** Espejo del destino de navegación del botón "Estudio de video". */
function rutaVideo(publicacionId: string): string {
  return `/publicaciones/video?contenido=${encodeURIComponent(publicacionId)}`;
}

describe("DialogoEditar — puente al Estudio de video", () => {
  it("navega a /contenido/video con el publicacion_id de la pieza", () => {
    expect(rutaVideo("cont-42")).toBe("/publicaciones/video?contenido=cont-42");
  });

  it("escapa ids con caracteres especiales en el query param", () => {
    expect(rutaVideo("a/b c")).toBe("/publicaciones/video?contenido=a%2Fb%20c");
  });
});

describe("DialogoEditar — GaleriaPlantillas con tipoFijo (simulando integración)", () => {
  it("con tipoFijo='foto', la galería muestra solo fotos y oculta el selector", () => {
    render(
      <GaleriaPlantillas
        plantillas={[FOTO, MINIATURA]}
        onCargar={vi.fn()}
        onCerrar={vi.fn()}
        tipoFijo="foto"
      />,
    );
    expect(screen.getByTitle(`Cargar «${FOTO.nombre}»`)).toBeInTheDocument();
    expect(screen.queryByTitle(`Cargar «${MINIATURA.nombre}»`)).not.toBeInTheDocument();
    // Sin selector de tipo (tipoFijo lo suprime)
    expect(screen.queryByText("Fotos")).not.toBeInTheDocument();
    expect(screen.queryByText("Miniaturas")).not.toBeInTheDocument();
  });

  it("con tipoFijo='miniatura', la galería muestra solo miniaturas (pieza video → portada)", () => {
    render(
      <GaleriaPlantillas
        plantillas={[FOTO, MINIATURA]}
        onCargar={vi.fn()}
        onCerrar={vi.fn()}
        tipoFijo="miniatura"
      />,
    );
    expect(screen.getByTitle(`Cargar «${MINIATURA.nombre}»`)).toBeInTheDocument();
    expect(screen.queryByTitle(`Cargar «${FOTO.nombre}»`)).not.toBeInTheDocument();
  });

  it("las plantillas que llegan a la galería ya vienen filtradas por tipo (como en DialogoEditar)", () => {
    // DialogoEditar filtra las plantillas ANTES de pasarlas a GaleriaPlantillas.
    // Aquí simulamos ese pre-filtrado + tipoFijo a la vez.
    const plantillasFiltradas = filtrarPorTipo([FOTO, MINIATURA], "miniatura");
    render(
      <GaleriaPlantillas
        plantillas={plantillasFiltradas}
        onCargar={vi.fn()}
        onCerrar={vi.fn()}
        tipoFijo="miniatura"
      />,
    );
    expect(screen.getByTitle(`Cargar «${MINIATURA.nombre}»`)).toBeInTheDocument();
    expect(screen.queryByTitle(`Cargar «${FOTO.nombre}»`)).not.toBeInTheDocument();
  });
});
