/**
 * Tests de GaleriaPlantillas con diferenciación foto / miniatura:
 *  - Filtra por tipo al cambiar pestaña (solo se muestran las del tipo activo).
 *  - Muestra el badge de tipo en cada tarjeta.
 *  - `tipoFijo` bloquea el selector y muestra solo las del tipo indicado.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GaleriaPlantillas } from "./GaleriaPlantillas";
import type { PlantillaDiseno } from "@/lib/api";

// Plantillas de prueba
const FOTO: PlantillaDiseno = {
  id: "foto-1",
  marca: "m1",
  nombre: "Placa de marca",
  categoria: "post",
  tipo: "foto",
  documento: {},
  miniatura: "",
  miniatura_url: "",
  lineas: [],
  activo: true,
  rotar: false,
  marca_nombre: "UnoTV",
  autor_id: "u1",
  autor_nombre: "Ana",
  creado: "2026-01-01T00:00:00",
  actualizado: "2026-01-01T00:00:00",
};

const MINIATURA: PlantillaDiseno = {
  ...FOTO,
  id: "min-1",
  nombre: "Portada video",
  tipo: "miniatura",
};

const AMBAS = [FOTO, MINIATURA];

describe("GaleriaPlantillas — filtro de tipo", () => {
  it("por defecto muestra solo plantillas de tipo 'foto'", () => {
    render(
      <GaleriaPlantillas plantillas={AMBAS} onCargar={vi.fn()} onCerrar={vi.fn()} />,
    );
    // La plantilla de foto aparece; la de miniatura no.
    expect(screen.getByTitle(`Cargar «${FOTO.nombre}»`)).toBeInTheDocument();
    expect(screen.queryByTitle(`Cargar «${MINIATURA.nombre}»`)).not.toBeInTheDocument();
  });

  it("al pulsar 'Miniaturas' muestra solo las de tipo miniatura", () => {
    render(
      <GaleriaPlantillas plantillas={AMBAS} onCargar={vi.fn()} onCerrar={vi.fn()} />,
    );
    // Cambiar al filtro de miniaturas
    fireEvent.click(screen.getByText("Miniaturas"));
    expect(screen.getByTitle(`Cargar «${MINIATURA.nombre}»`)).toBeInTheDocument();
    expect(screen.queryByTitle(`Cargar «${FOTO.nombre}»`)).not.toBeInTheDocument();
  });

  it("muestra badge de tipo 'Foto' sobre cada plantilla de foto", () => {
    render(
      <GaleriaPlantillas plantillas={[FOTO]} onCargar={vi.fn()} onCerrar={vi.fn()} />,
    );
    expect(screen.getByText("Foto")).toBeInTheDocument();
  });

  it("muestra badge de tipo 'Miniatura' sobre cada plantilla de miniatura (con tipoFijo)", () => {
    render(
      <GaleriaPlantillas
        plantillas={[MINIATURA]}
        onCargar={vi.fn()}
        onCerrar={vi.fn()}
        tipoFijo="miniatura"
      />,
    );
    expect(screen.getByText("Miniatura")).toBeInTheDocument();
    // El selector de tipo NO aparece (tipoFijo lo oculta)
    expect(screen.queryByText("Fotos")).not.toBeInTheDocument();
  });

  it("tipoFijo='miniatura' filtra directamente y oculta el selector", () => {
    render(
      <GaleriaPlantillas
        plantillas={AMBAS}
        onCargar={vi.fn()}
        onCerrar={vi.fn()}
        tipoFijo="miniatura"
      />,
    );
    // Solo la miniatura aparece
    expect(screen.getByTitle(`Cargar «${MINIATURA.nombre}»`)).toBeInTheDocument();
    expect(screen.queryByTitle(`Cargar «${FOTO.nombre}»`)).not.toBeInTheDocument();
    // No hay botón de cambio de filtro
    expect(screen.queryByText("Fotos")).not.toBeInTheDocument();
  });

  it("mensaje vacío contextualizado cuando no hay plantillas del tipo activo", () => {
    render(
      <GaleriaPlantillas
        plantillas={[FOTO]}
        onCargar={vi.fn()}
        onCerrar={vi.fn()}
        tipoFijo="miniatura"
      />,
    );
    expect(screen.getByText(/miniaturas para esta marca/i)).toBeInTheDocument();
  });

  it("con onRotar: refleja el estado de rotación y lo alterna al pulsar", () => {
    const onRotar = vi.fn();
    const EN_ROTACION: PlantillaDiseno = { ...FOTO, id: "rot-1", nombre: "Azul", rotar: true };
    render(
      <GaleriaPlantillas
        plantillas={[FOTO, EN_ROTACION]}
        onCargar={vi.fn()}
        onRotar={onRotar}
        onCerrar={vi.fn()}
      />,
    );
    // FOTO no está en rotación -> "Rotación"; la otra sí -> "En rotación".
    expect(screen.getByText("Rotación")).toBeInTheDocument();
    expect(screen.getByText("En rotación")).toBeInTheDocument();
    // Pulsar la de FOTO la AÑADE a la rotación (rotar -> true).
    fireEvent.click(screen.getByText("Rotación"));
    expect(onRotar).toHaveBeenCalledWith(expect.objectContaining({ id: "foto-1" }), true);
  });

  it("sin onRotar (modo selector) no muestra el control de rotación", () => {
    render(<GaleriaPlantillas plantillas={[FOTO]} onCargar={vi.fn()} onCerrar={vi.fn()} />);
    expect(screen.queryByText("Rotación")).not.toBeInTheDocument();
  });
});
