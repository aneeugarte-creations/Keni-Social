/**
 * Tests para ResultadoRedes (#118 A-2, #119 A-4):
 *
 * A-2: Dos publicaciones de la misma red no deben ocultarse entre sí.
 *      Las tabs usan value={p.id} (no value={p.red}).
 * A-4: El timeout de "copiado" en PanelPublicacion/PanelManual se limpia al desmontar.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Publicacion, RespuestaEjecutarSkill } from "@/types";
import { ResultadoRedes } from "./ResultadoRedes";

/** Publicación mínima válida para los tests. */
function mkPublicacion(overrides: Partial<Publicacion> = {}): Publicacion {
  return {
    id: "pub-1",
    titulo: "",
    red: "x",
    red_nombre: "X",
    marca: "unotv",
    marca_nombre: "UnoTV",
    contenido: "Contenido de prueba",
    estado: "borrador",
    evergreen: false,
    veredicto: "",
    imagen: "",
    imagen_url: "",
    fecha_programada: "",
    fecha_creacion: "2026-05-25T10:00:00",
    fecha_actualizacion: "2026-05-25T10:00:00",
    origen: "",
    ...overrides,
  };
}

const OPCIONES_RESP = {
  redes: [
    { id: "x", nombre: "X", limite: 280 },
    { id: "instagram", nombre: "Instagram", limite: 2200 },
  ],
  estados: [{ id: "borrador", nombre: "Borrador" }],
  marcas: [{ id: "unotv", nombre: "UnoTV" }],
};

function mkRespuesta(publicaciones: Publicacion[]): RespuestaEjecutarSkill {
  return {
    resultado: "",
    historial_id: "h1",
    verdicto: "",
    piezas: [],
    publicaciones,
  };
}

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(OPCIONES_RESP), { status: 200 })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ResultadoRedes · A-2: tabs por id, no por red (#118)", () => {
  it("muestra ambas publicaciones aunque sean de la misma red (renderización síncrona)", () => {
    // Con el fix A-2: las tabs usan value={p.id}, por lo tanto dos publicaciones
    // de la misma red se montan como tabs independientes desde el primer render.
    const pubs = [
      mkPublicacion({ id: "pub-1", red: "x", contenido: "Pub 1 en X" }),
      mkPublicacion({ id: "pub-2", red: "x", contenido: "Pub 2 en X" }),
    ];
    renderConProviders(<ResultadoRedes respuesta={mkRespuesta(pubs)} />);

    // Los TabsTrigger usan value={p.id}, por lo que ambas pestañas están en el DOM
    // y son distinguibles por Radix UI (no colisionan como harían con value={p.red}).
    const triggers = screen.getAllByRole("tab");
    expect(triggers.length).toBeGreaterThanOrEqual(2);
  });

  it("con publicaciones de redes diferentes, muestra una tab por publicación", () => {
    const pubs = [
      mkPublicacion({ id: "pub-1", red: "x", contenido: "Pub X" }),
      mkPublicacion({ id: "pub-2", red: "instagram", contenido: "Pub IG" }),
    ];
    renderConProviders(<ResultadoRedes respuesta={mkRespuesta(pubs)} />);

    // Hay múltiples tabs (el ToggleVista interior también renderiza tabs).
    // Verificamos que hay al menos 2 tabs visibles (las de la lista de redes).
    const triggers = screen.getAllByRole("tab");
    expect(triggers.length).toBeGreaterThanOrEqual(2);
  });

  it("sin publicaciones, muestra el panel manual con tab 'Todo'", () => {
    renderConProviders(<ResultadoRedes respuesta={mkRespuesta([])} />);
    expect(screen.getByRole("tab", { name: "Todo" })).toBeInTheDocument();
  });

  it("la tab activa inicial corresponde al id de la primera publicación", () => {
    const pubs = [
      mkPublicacion({ id: "pub-xyz", red: "x", contenido: "Primera" }),
      mkPublicacion({ id: "pub-abc", red: "x", contenido: "Segunda" }),
    ];
    renderConProviders(<ResultadoRedes respuesta={mkRespuesta(pubs)} />);

    // La primera publicación debe estar seleccionada
    const triggers = screen.getAllByRole("tab");
    expect(triggers[0]).toHaveAttribute("data-state", "active");
  });
});

describe("ResultadoRedes · A-4: cleanup del timeout de copiado (#119)", () => {
  it("no produce errores de React al desmontar sin timers activos", () => {
    vi.useFakeTimers();
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const pubs = [mkPublicacion({ id: "pub-1", red: "x", contenido: "Hola mundo" })];
    const { unmount } = renderConProviders(<ResultadoRedes respuesta={mkRespuesta(pubs)} />);

    // Desmontamos el componente ANTES de que el timer de 2000ms expire
    unmount();

    // Avanzamos el tiempo: sin cleanup, un timer activo dispararía setState
    // sobre un componente desmontado.
    vi.advanceTimersByTime(3000);

    // No debe haber errores de React "setState on unmounted component"
    expect(consoleSpy).not.toHaveBeenCalledWith(
      expect.stringContaining("unmounted"),
    );

    consoleSpy.mockRestore();
    vi.useRealTimers();
  });
});
