import { describe, expect, it } from "vitest";

import type { MiembroRota } from "@/types";

import { cmsDeMarca } from "./utils";

function miembro(over: Partial<MiembroRota> & Pick<MiembroRota, "id" | "nombre">): MiembroRota {
  return { marcas: ["clarosports"], cargo: "community_manager", cobertura: true, ...over };
}

describe("cmsDeMarca", () => {
  it("incluye a los coordinadores que cubren (paridad con los carriles del Panorama)", () => {
    // Regresión: antes el dropdown «Añadir turno» filtraba por cargo y dejaba al
    // coordinador (p.ej. Elías) fuera, aunque sí aparecía como responsable en el Panorama.
    const equipo = [
      miembro({ id: "u-luis", nombre: "Luis" }),
      miembro({ id: "u-roger", nombre: "Roger" }),
      miembro({ id: "u-tezcu", nombre: "Tezcucano" }),
      miembro({ id: "u-elias", nombre: "Elías", cargo: "coordinador" }),
    ];
    const ids = cmsDeMarca(equipo, "clarosports").map((m) => m.id);
    expect(ids).toContain("u-elias");
    expect(ids).toHaveLength(4);
  });

  it("excluye a quien no tiene cobertura", () => {
    const equipo = [
      miembro({ id: "u-cm", nombre: "Activo" }),
      miembro({ id: "u-off", nombre: "Sin cobertura", cobertura: false }),
    ];
    const ids = cmsDeMarca(equipo, "clarosports").map((m) => m.id);
    expect(ids).toEqual(["u-cm"]);
  });

  it("acota por la marca activa y no filtra en «Todas» (null)", () => {
    const equipo = [
      miembro({ id: "u-cs", nombre: "Claro", marcas: ["clarosports"] }),
      miembro({ id: "u-ng", nombre: "Gamer", marcas: ["naciongamer"] }),
    ];
    expect(cmsDeMarca(equipo, "clarosports").map((m) => m.id)).toEqual(["u-cs"]);
    expect(cmsDeMarca(equipo, null).map((m) => m.id)).toEqual(["u-cs", "u-ng"]);
  });
});
