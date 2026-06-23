import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CabeceraPlaca } from "@/components/media/placa/CabeceraPlaca";

/**
 * El botón de descarga del render solo aparece cuando se pasa `onDescargar`, y al pulsarlo invoca
 * ese callback (la composición foto+plantilla+texto y la oferta de copiar el copy las hace el
 * editor; aquí solo se verifica el cableado del botón junto al selector de plantilla).
 */
describe("CabeceraPlaca · botón de descarga", () => {
  it("no muestra el botón de descarga sin `onDescargar`", () => {
    render(
      <CabeceraPlaca
        sinPlantilla={false}
        onAlternarSinPlantilla={() => {}}
        onAbrirGaleria={() => {}}
      />,
    );
    expect(screen.queryByTitle("Descargar imagen para postear")).toBeNull();
  });

  it("muestra el botón y lo invoca al pulsarlo cuando hay `onDescargar`", () => {
    const onDescargar = vi.fn();
    render(
      <CabeceraPlaca
        sinPlantilla={false}
        onAlternarSinPlantilla={() => {}}
        onAbrirGaleria={() => {}}
        onDescargar={onDescargar}
      />,
    );
    fireEvent.click(screen.getByTitle("Descargar imagen para postear"));
    expect(onDescargar).toHaveBeenCalledTimes(1);
  });
});

/**
 * El control de MODO es un toggle ghost cuyo glifo refleja el estado (con plantilla ↔ solo foto),
 * sin tachado rojo. El sufijo "· solo foto" del título reafirma el modo cuando la plantilla está
 * apagada. Pulsarlo invoca `onAlternarSinPlantilla`.
 */
describe("CabeceraPlaca · modo plantilla", () => {
  it("con plantilla: el toggle invita a quitarla y no hay sufijo «solo foto»", () => {
    const onAlternar = vi.fn();
    render(
      <CabeceraPlaca sinPlantilla={false} onAlternarSinPlantilla={onAlternar} />,
    );
    expect(screen.queryByText("· solo foto")).toBeNull();
    fireEvent.click(screen.getByTitle("Con plantilla. Toca para publicar solo la foto"));
    expect(onAlternar).toHaveBeenCalledTimes(1);
  });

  it("solo foto: aparece el sufijo y el toggle invita a poner la plantilla", () => {
    const onAlternar = vi.fn();
    render(
      <CabeceraPlaca sinPlantilla={true} onAlternarSinPlantilla={onAlternar} />,
    );
    expect(screen.getByText("· solo foto")).toBeInTheDocument();
    const toggle = screen.getByTitle("Solo foto. Toca para poner la plantilla");
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(toggle);
    expect(onAlternar).toHaveBeenCalledTimes(1);
  });
});
