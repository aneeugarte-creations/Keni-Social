import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { datetimeLocalAIso } from "@/lib/fecha";
import type { EventoRota, FranjaSemana, Publicacion, TurnoRota } from "@/types";

import { KpiCobertura } from "./KpiCobertura";

// --- Factorías compactas (cast por brevedad: el KPI solo lee unos campos vía el selector) -----

function ev(over: Partial<EventoRota> = {}): EventoRota {
  return {
    id: "ev1",
    titulo: "Cruz Azul vs América",
    fecha: "2026-07-01",
    hora: "20:00",
    tipo_cobertura: "transmision",
    prioridad: "media",
    ...over,
  } as unknown as EventoRota;
}

function claim(over: Partial<Publicacion> = {}): Publicacion {
  return {
    id: "c1",
    clase: "tarea",
    evento_id: "ev1",
    responsable_id: "u1",
    responsable_nombre: "luis",
    titulo: "Cruz Azul vs América",
    formato: "foto",
    fecha_objetivo: "2026-07-01",
    hora_objetivo: "20:00",
    ...over,
  } as unknown as Publicacion;
}

function franja(over: Partial<FranjaSemana> = {}): FranjaSemana {
  return {
    id: "f-tarde",
    lunes: "2026-06-29",
    nombre: "Tarde",
    inicio: "14:00",
    fin: "22:00",
    orden: 1,
    es_descanso: false,
    marca: "",
    marca_nombre: "",
    ...over,
  } as unknown as FranjaSemana;
}

function turno(over: Partial<TurnoRota> = {}): TurnoRota {
  return {
    id: "t1",
    semana: "2026-06-29",
    fecha: "2026-07-01",
    miembro_id: "u9",
    miembro_nombre: "ana",
    franja_id: "f-tarde",
    franja_nombre: "Tarde",
    ...over,
  } as unknown as TurnoRota;
}

const FRANJAS: FranjaSemana[] = [franja()];

/** Fija el reloj a `min` minutos ANTES del saque del evento ancla (CDMX wall → instante real). */
function fijarAhoraAntesDelSaque(evento: EventoRota, min: number) {
  const saque = new Date(datetimeLocalAIso(`${evento.fecha}T${evento.hora}`)!);
  vi.useFakeTimers();
  vi.setSystemTime(new Date(saque.getTime() - min * 60000));
}

describe("KpiCobertura — cabecera de cobertura", () => {
  afterEach(() => vi.useRealTimers());

  it("sin eventos no pinta nada (total 0)", () => {
    const { container } = render(
      <KpiCobertura eventos={[]} claims={[]} turnos={[]} franjas={FRANJAS} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("resume cubiertos/total y los huecos en rojo", () => {
    fijarAhoraAntesDelSaque(ev(), 300); // lejos del saque → ni pronto ni en vivo
    const cubierto = ev({ id: "e-cog" });
    const hueco = ev({ id: "e-hueco" });
    render(
      <KpiCobertura
        eventos={[cubierto, hueco]}
        claims={[claim({ id: "cc", evento_id: "e-cog" })]}
        turnos={[]}
        franjas={FRANJAS}
      />,
    );
    // 1 de 2 cubiertos.
    const kpi = screen.getByRole("status");
    expect(kpi).toHaveTextContent("1");
    expect(kpi).toHaveTextContent("/2");
    // El hueco se anuncia (accesible) y se ve con texto + color de significado.
    expect(kpi).toHaveAttribute(
      "aria-label",
      expect.stringContaining("1 sin cubrir"),
    );
    expect(screen.getAllByText(/1 sin cubrir/).length).toBeGreaterThan(0);
  });

  it("«en vivo» se cuenta y se muestra (color verde con texto, como el semáforo)", () => {
    const ancla = ev({ id: "base" });
    fijarAhoraAntesDelSaque(ancla, -30); // 30 min DESPUÉS del saque → en vivo
    const enVivo = ev({ id: "e-vivo" });
    render(
      <KpiCobertura
        eventos={[enVivo]}
        claims={[claim({ id: "cc", evento_id: "e-vivo" })]}
        turnos={[turno({ id: "tt" })]}
        franjas={FRANJAS}
      />,
    );
    // El corte «en vivo» habla el mismo lenguaje que el semáforo de las tarjetas: VERDE, no ámbar.
    const corteEnVivo = screen.getByText(/1 en vivo/);
    expect(corteEnVivo).toHaveClass("text-emerald-700");
    expect(corteEnVivo).not.toHaveClass("text-amber-700");
  });

  it("todo cubierto y sin huecos → «Todo cubierto» (desktop y móvil), sin rojo", () => {
    fijarAhoraAntesDelSaque(ev(), 300);
    render(
      <KpiCobertura
        eventos={[ev()]}
        claims={[claim()]}
        turnos={[]}
        franjas={FRANJAS}
      />,
    );
    // Sale en las DOS variantes (la desktop sm:flex y la móvil sm:hidden): ambas con «Todo cubierto».
    expect(screen.getAllByText("Todo cubierto").length).toBe(2);
    expect(screen.queryByText(/sin cubrir/)).toBeNull();
    // La móvil ya no muestra la palabra suelta «cubiertos».
    expect(screen.queryByText("cubiertos")).toBeNull();
  });

  it("«N sin cubrir» es un botón que filtra el Panorama a «Por cubrir»", () => {
    fijarAhoraAntesDelSaque(ev(), 300);
    const irASinCubrir = vi.fn();
    render(
      <KpiCobertura
        eventos={[ev({ id: "e-cog" }), ev({ id: "e-hueco" })]}
        claims={[claim({ id: "cc", evento_id: "e-cog" })]}
        turnos={[]}
        franjas={FRANJAS}
        onIrASinCubrir={irASinCubrir}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /1 sin cubrir/ }));
    expect(irASinCubrir).toHaveBeenCalledTimes(1);
  });

  it("«N hechas» se muestra como dato NEUTRO (gris, sin barra ni naranja) al final de la línea", () => {
    fijarAhoraAntesDelSaque(ev(), 300);
    const { container } = render(
      <KpiCobertura eventos={[ev()]} claims={[claim()]} turnos={[]} franjas={FRANJAS} hechas={3} />,
    );
    // El conteo va en el aria-label del recuadro (accesible) y como texto gris en la línea.
    const kpi = screen.getByRole("status");
    expect(kpi).toHaveAttribute("aria-label", expect.stringContaining("3 hechas"));
    const hechasEl = screen.getByText(/·\s*3\s*hechas/);
    expect(hechasEl).toHaveClass("text-muted-foreground");
    // Es texto, no una barra de progreso de marca: nada de naranja `keni-*`.
    expect(container.querySelector(".bg-keni-500")).toBeNull();
  });

  it("sin `hechas` (o 0) NO aparece el dato «hechas»", () => {
    fijarAhoraAntesDelSaque(ev(), 300);
    render(<KpiCobertura eventos={[ev()]} claims={[claim()]} turnos={[]} franjas={FRANJAS} />);
    expect(screen.queryByText(/hechas/)).toBeNull();
    expect(screen.getByRole("status").getAttribute("aria-label")).not.toContain("hechas");
  });

  it("sin `onIrASinCubrir` el corte «N sin cubrir» NO es un botón", () => {
    fijarAhoraAntesDelSaque(ev(), 300);
    render(
      <KpiCobertura
        eventos={[ev({ id: "e-cog" }), ev({ id: "e-hueco" })]}
        claims={[claim({ id: "cc", evento_id: "e-cog" })]}
        turnos={[]}
        franjas={FRANJAS}
      />,
    );
    expect(screen.queryByRole("button", { name: /sin cubrir/ })).toBeNull();
  });
});
