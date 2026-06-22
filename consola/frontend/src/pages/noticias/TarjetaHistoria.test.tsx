/**
 * Tests de la tarjeta LIMPIA de una historia de la Mesa (`TarjetaHistoria`):
 *   - Lo esencial visible: titular, hora·fuente y el score como pastilla.
 *   - ⚡ última hora: el rayito rojo solo si `breaking` y no descartada.
 *   - Su ÚNICA acción es NAVEGAR a la subpágina de detalle; el checkbox de selección NO navega.
 *   - Indicador de estado discreto (En feed/En cola/Generando/Sale sola) según `pieza_estado`.
 *
 * El desglose del score, las fuentes y las acciones (empujar/descartar) ya no viven en la
 * tarjeta: están en la subpágina `DetalleHistoriaPagina`.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { Historia } from "@/types";

import { TarjetaHistoria } from "./TarjetaHistoria";

function historia(overrides: Partial<Historia> = {}): Historia {
  return {
    id: "h-1",
    titulo: "Historia de prueba",
    resumen: "Resumen.",
    marca: "unotv",
    marca_nombre: "UnoTV",
    categoria: "mx",
    geo: "MX",
    n_items: 3,
    n_fuentes: 2,
    idiomas: ["es"],
    senal: 100,
    score: 0.5,
    breaking: 0,
    primer_visto: "2026-06-05T09:00:00",
    ultimo_visto: "2026-06-05T10:00:00",
    estado: "nuevo",
    publicacion_id: "",
    enlaces: [],
    ...overrides,
  };
}

/** Espía la URL actual: deja el detalle de la historia en el DOM cuando se navega. */
function SondaUbicacion() {
  const loc = useLocation();
  return <div data-testid="ubicacion">{loc.pathname}</div>;
}

function renderTarjeta(
  h: Historia,
  props: Partial<Parameters<typeof TarjetaHistoria>[0]> = {},
) {
  return render(
    <MemoryRouter initialEntries={["/maquina/investigacion"]}>
      <Routes>
        <Route path="*" element={<TarjetaHistoria historia={h} {...props} />} />
      </Routes>
      <SondaUbicacion />
    </MemoryRouter>,
  );
}

describe("TarjetaHistoria · tarjeta limpia", () => {
  it("muestra titular, hora·fuente y el score como pastilla", () => {
    renderTarjeta(historia({ primera_fuente_nombre: "Reforma" }));
    expect(screen.getByText("Historia de prueba")).toBeTruthy();
    expect(screen.getByTestId("hora-fuente").textContent).toMatch(/Reforma/);
    expect(screen.getByTestId("punto-prioridad").textContent).toMatch(/Score 50/);
  });

  it("⚡ última hora: el rayito solo aparece en una breaking no descartada", () => {
    renderTarjeta(historia({ breaking: 1 }));
    expect(screen.getByTestId("badge-ultima-hora")).toBeTruthy();
  });

  it("no pinta el rayito de última hora en una historia normal", () => {
    renderTarjeta(historia());
    expect(screen.queryByTestId("badge-ultima-hora")).toBeNull();
  });

  it("al pulsar el titular navega a la subpágina de detalle", () => {
    renderTarjeta(historia({ id: "h-42" }));
    fireEvent.click(screen.getByTestId("btn-detalle"));
    expect(screen.getByTestId("ubicacion").textContent).toBe(
      "/maquina/investigacion/historia/h-42",
    );
  });

  it("el checkbox de selección NO navega", () => {
    let marcado = false;
    renderTarjeta(historia(), {
      seleccionada: false,
      onToggleSeleccion: (c) => {
        marcado = c;
      },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    expect(marcado).toBe(true);
    // Sin navegación: seguimos en la mesa.
    expect(screen.getByTestId("ubicacion").textContent).toBe("/maquina/investigacion");
  });

  it("una extranjera sin traducir muestra «Traduciendo…» en vez del titular original", () => {
    renderTarjeta(historia({ traduciendo: true, titulo: "Traduciendo…" }));
    expect(screen.getByTestId("btn-detalle").textContent).toMatch(/Traduciendo/);
  });

  it("una promovible muestra el indicador «Sale sola al feed»", () => {
    renderTarjeta(historia({ promovible: true, promovible_motivo: "score 0.5 ≥ 0.35" }));
    expect(screen.getByTestId("badge-sale-sola")).toBeTruthy();
  });

  it("una pieza en el feed muestra el indicador «En el feed»", () => {
    renderTarjeta(historia({ estado: "usado", publicacion_id: "c-1", pieza_estado: "en_feed" }));
    expect(screen.getByText(/En el feed/i)).toBeTruthy();
  });
});
