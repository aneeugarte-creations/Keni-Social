/**
 * Tests de los badges de Investigación por historia en TarjetaHistoria (ADR 0011, C3):
 *   - La MARCA de la historia se pinta como chip (marca_nombre, con fallback a marca).
 *   - El mini-badge «IA» aparece solo si `marca_clasificada_por_ia`.
 *   - La VERIFICACIÓN de la fuente (`verificacion_fuente`) se pinta como badge solo si no está vacío:
 *     'no_verificado' → «Verificada»; 'problema' → «Problema en la fuente»; '' → nada.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
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

function renderTarjeta(h: Historia) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TarjetaHistoria historia={h} clavesAInvalidar={[["x"]]} />
    </QueryClientProvider>,
  );
}

describe("TarjetaHistoria · badges de Investigación", () => {
  it("pinta la marca de la historia como chip", () => {
    renderTarjeta(historia());
    expect(screen.getByTestId("chip-marca").textContent).toMatch(/UnoTV/);
    // Sin clasificar por IA: no hay mini-badge.
    expect(screen.queryByTestId("badge-marca-ia")).toBeNull();
  });

  it("cae a `marca` cuando falta `marca_nombre`", () => {
    renderTarjeta(historia({ marca_nombre: "", marca: "claro-sports" }));
    expect(screen.getByTestId("chip-marca").textContent).toMatch(/claro-sports/);
  });

  it("añade el mini-badge «IA» si la marca la asignó el clasificador", () => {
    renderTarjeta(historia({ marca_clasificada_por_ia: true }));
    expect(screen.getByTestId("badge-marca-ia").textContent).toMatch(/IA/);
  });

  it("no pinta verificacion cuando `verificacion_fuente` está vacío", () => {
    renderTarjeta(historia({ verificacion_fuente: "" }));
    expect(screen.queryByTestId("badge-verificacion-verificada")).toBeNull();
    expect(screen.queryByTestId("badge-verificacion-problema")).toBeNull();
  });

  it("'no_verificado' → badge «Verificada»", () => {
    renderTarjeta(historia({ verificacion_fuente: "no_verificado" }));
    expect(screen.getByTestId("badge-verificacion-verificada").textContent).toMatch(/Verificada/);
  });

  it("'problema' → badge «Problema en la fuente»", () => {
    renderTarjeta(historia({ verificacion_fuente: "problema" }));
    expect(screen.getByTestId("badge-verificacion-problema").textContent).toMatch(/Problema en la fuente/);
  });
});
