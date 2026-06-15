/**
 * Tests del RielInvestigacion CONSOLIDADO (ADR 0011): un panel de TARJETAS con todas las fases del
 * tramo aguas arriba (Recolectar · Agrupar · Fusionar · Traducir · Clasificar · Priorizar ·
 * Admitir · Verificar). El SWITCH es el indicador de estado (no hay puntos de color); solo admin
 * lee/edita el catálogo. Las fases con prompt abren su doc al clicar la tarjeta.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import * as apiMod from "@/lib/api";
import type { RespuestaAjustes, UsuarioSesion } from "@/types";

import { RielInvestigacion } from "./RielInvestigacion";

function usuario(rol: "admin" | "editor"): UsuarioSesion {
  return { id: "u1", usuario: "u", rol, debe_cambiar_password: false, marcas: ["unotv"] };
}

function sesionValor(u: UsuarioSesion | null): ValorSesion {
  return {
    usuario: u,
    cargando: false,
    iniciarSesion: vi.fn(),
    verificarConPasskey: vi.fn(),
    verificarConCodigo: vi.fn(),
    cerrarSesion: vi.fn(),
    refrescar: vi.fn(),
  };
}

function ajustes(valor: boolean): RespuestaAjustes {
  return {
    grupos: [
      {
        id: "maestros_investigacion",
        titulo: "Investigación",
        ajustes: [
          {
            clave: "KENI_INVESTIGACION",
            tipo: "bool",
            etiqueta: "Investigación",
            ayuda: "",
            grupo: "maestros_investigacion",
            peligroso: false,
            valor,
            fuente: "store",
            defecto: false,
          },
        ],
      },
    ],
  };
}

function renderRiel(esAdmin: boolean) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesionValor(usuario(esAdmin ? "admin" : "editor"))}>
        <MemoryRouter>
          <RielInvestigacion esAdmin={esAdmin} />
        </MemoryRouter>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

const NOMBRES = [
  "Recolectar",
  "Agrupar",
  "Fusionar",
  "Traducir",
  "Clasificar",
  "Priorizar",
  "Admitir",
  "Verificar",
];

beforeEach(() => {
  vi.spyOn(apiMod.api, "ajustes").mockResolvedValue(ajustes(true));
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("RielInvestigacion (pipeline consolidado)", () => {
  it("pinta una tarjeta por cada fase del proceso", () => {
    renderRiel(true);
    for (const n of NOMBRES) expect(screen.getByText(n)).toBeTruthy();
  });

  it("admin: cada fase muestra su switch (el toggle indica encendido)", async () => {
    renderRiel(true);
    await waitFor(() =>
      expect(screen.getAllByRole("switch").length).toBeGreaterThanOrEqual(NOMBRES.length),
    );
    // Maestro Investigación ON → los switches de las fases salen encendidos.
    expect(screen.getAllByRole("switch")[0].getAttribute("aria-checked")).toBe("true");
  });

  it("admin: el maestro OFF deja los switches apagados", async () => {
    vi.spyOn(apiMod.api, "ajustes").mockResolvedValue(ajustes(false));
    renderRiel(true);
    await waitFor(() =>
      expect(screen.getAllByRole("switch")[0]?.getAttribute("aria-checked")).toBe("false"),
    );
  });

  it("una fase con prompt abre el editor in-place al clicar la tarjeta", async () => {
    renderRiel(true);
    // Verificar tiene prompt: clicar su tarjeta lanza la acción primaria (Editar prompt) → overlay.
    fireEvent.click(screen.getByText("Verificar"));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeTruthy());
  });

  it("no admin: ni switches ni consulta del catálogo (informativo)", () => {
    const spy = vi.spyOn(apiMod.api, "ajustes");
    renderRiel(false);
    for (const n of NOMBRES) expect(screen.getByText(n)).toBeTruthy();
    expect(screen.queryAllByRole("switch").length).toBe(0);
    expect(spy).not.toHaveBeenCalled();
  });
});
