import { beforeEach, describe, expect, it } from "vitest";

import {
  columnasVisibles,
  useVistaConfig,
  VISTA_POR_DEFECTO,
} from "./vistaConfig";

beforeEach(() => {
  localStorage.clear();
  useVistaConfig.getState().reset();
});

describe("columnasVisibles", () => {
  const todas = ["a", "b", "c", "d"];

  it("sin config respeta el orden base completo", () => {
    expect(columnasVisibles(todas, { orden: [], ocultas: [] })).toEqual(todas);
  });

  it("reordena y manda al final las no listadas", () => {
    expect(columnasVisibles(todas, { orden: ["c", "a"], ocultas: [] })).toEqual([
      "c", "a", "b", "d",
    ]);
  });

  it("descarta las columnas ocultas", () => {
    expect(columnasVisibles(todas, { orden: ["d", "a"], ocultas: ["a"] })).toEqual([
      "d", "b", "c",
    ]);
  });
});

describe("useVistaConfig", () => {
  it("seccionVisible: ausente = visible; false = oculta", () => {
    const s = useVistaConfig.getState();
    expect(s.seccionVisible("piezas")).toBe(true);
    s.setSeccionVisible("piezas", false);
    expect(useVistaConfig.getState().seccionVisible("piezas")).toBe(false);
  });

  it("exportar/aplicar redondean la configuración", () => {
    const s = useVistaConfig.getState();
    s.setRed("instagram");
    s.setColumnas("piezas", { orden: ["titulo"], ocultas: ["clics"] });
    const cfg = useVistaConfig.getState().exportar();
    expect(cfg.red).toBe("instagram");

    useVistaConfig.getState().reset();
    expect(useVistaConfig.getState().red).toBe(null);

    useVistaConfig.getState().aplicar(cfg);
    expect(useVistaConfig.getState().red).toBe("instagram");
    expect(useVistaConfig.getState().columnasDe("piezas", []).ocultas).toEqual(["clics"]);
  });

  it("reset vuelve al estado por defecto", () => {
    const s = useVistaConfig.getState();
    s.setRed("youtube");
    s.reset();
    expect(useVistaConfig.getState().red).toBe(VISTA_POR_DEFECTO.red);
  });
});
