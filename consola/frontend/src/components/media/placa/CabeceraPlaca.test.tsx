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
