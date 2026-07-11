import { describe, expect, it } from "vitest";

import type { EstadoCobertura, Semaforo } from "@/lib/cobertura";

import { COBERTURA_BADGE, COBERTURA_TEXTO, SEMAFORO_ESTILO } from "./estado-color";

/**
 * Fija la taxonomía CENTRAL de color: cada fase del semáforo y cada estado de cobertura mapea a sus
 * clases Tailwind EXACTAS (incluido `dark:`). El tinte es la receta única de badge de estado del
 * sistema de diseño (`bg-<c>-500/15 text-<c>-700 dark:text-<c>-300`, docs/sistema-diseno.md); el
 * test la congela para que los futuros estados no deriven los existentes sin querer.
 */
describe("SEMAFORO_ESTILO — color por fase temporal", () => {
  it("verde para en-vivo (badge + punto verde)", () => {
    expect(SEMAFORO_ESTILO["en-vivo"]).toEqual({
      badge: "border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
      dot: "bg-emerald-500",
      icon: "text-emerald-600 dark:text-emerald-400",
    });
  });

  it("ámbar para empieza-en (PRE-LIVE)", () => {
    expect(SEMAFORO_ESTILO["empieza-en"]).toEqual({
      badge: "border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-300",
      dot: "bg-amber-500",
      icon: "text-amber-600 dark:text-amber-400",
    });
  });

  it("verde para terminado (resuelto, comparte el verde de en-vivo)", () => {
    expect(SEMAFORO_ESTILO.terminado).toEqual({
      badge: "border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
      dot: "bg-emerald-500",
      icon: "text-emerald-600 dark:text-emerald-400",
    });
  });

  it("gris/muted para programado (neutro, punto slate)", () => {
    expect(SEMAFORO_ESTILO.programado).toEqual({
      badge: "text-muted-foreground",
      dot: "bg-slate-400 dark:bg-slate-500",
      icon: "text-muted-foreground",
    });
  });

  it("cubre las cuatro fases del semáforo", () => {
    const fases: Semaforo[] = ["programado", "empieza-en", "en-vivo", "terminado"];
    for (const f of fases) expect(SEMAFORO_ESTILO[f]).toBeDefined();
    expect(Object.keys(SEMAFORO_ESTILO).sort()).toEqual([...fases].sort());
  });
});

describe("COBERTURA_TEXTO — color del corte del KPI por estado de cobertura", () => {
  it("amarillo para sin-cubrir (hueco que pide decisión)", () => {
    expect(COBERTURA_TEXTO["sin-cubrir"]).toBe("text-yellow-700 dark:text-yellow-300");
  });

  it("verde para cubierto-turno y cogido (resuelto / en marcha)", () => {
    expect(COBERTURA_TEXTO["cubierto-turno"]).toBe("text-emerald-700 dark:text-emerald-300");
    expect(COBERTURA_TEXTO.cogido).toBe("text-emerald-700 dark:text-emerald-300");
  });

  it("cubre los tres estados de cobertura", () => {
    const estados: EstadoCobertura[] = ["sin-cubrir", "cubierto-turno", "cogido"];
    for (const e of estados) expect(COBERTURA_TEXTO[e]).toBeTruthy();
    expect(Object.keys(COBERTURA_TEXTO).sort()).toEqual([...estados].sort());
  });
});

describe("COBERTURA_BADGE — píldora de tinte de cobertura del chip del calendario", () => {
  it("verde para cubierto-turno («Cubierto · <nombres>»)", () => {
    expect(COBERTURA_BADGE["cubierto-turno"]).toBe(
      "border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
    );
  });

  it("cogido comparte el verde de cubierto-turno", () => {
    expect(COBERTURA_BADGE.cogido).toBe(COBERTURA_BADGE["cubierto-turno"]);
  });

  it("amarillo para sin-cubrir (mismo amarillo que el KPI: «sin cubrir» es UN color)", () => {
    expect(COBERTURA_BADGE["sin-cubrir"]).toBe(
      "border-transparent bg-yellow-500/15 text-yellow-700 dark:text-yellow-300",
    );
  });

  it("cubre los tres estados de cobertura", () => {
    const estados: EstadoCobertura[] = ["sin-cubrir", "cubierto-turno", "cogido"];
    for (const e of estados) expect(COBERTURA_BADGE[e]).toBeTruthy();
    expect(Object.keys(COBERTURA_BADGE).sort()).toEqual([...estados].sort());
  });
});
