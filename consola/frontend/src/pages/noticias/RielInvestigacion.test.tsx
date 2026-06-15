/**
 * Tests del RielInvestigacion (ADR 0011, C3): la tira de las cinco etapas del proceso
 * (Ingesta · Fusión · Clasificación · Ranking · Verificación) con su estado ON/OFF leído del
 * catálogo de ajustes. El estado solo es legible por admin; el resto ve la tira informativa.
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

function renderRiel(u: UsuarioSesion | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesionValor(u)}>
        <MemoryRouter>
          <RielInvestigacion />
        </MemoryRouter>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

const ETAPAS = ["ingesta", "fusión", "clasificación", "ranking", "verificación"];

beforeEach(() => {
  vi.spyOn(apiMod.api, "ajustes").mockResolvedValue(ajustes(true));
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("RielInvestigacion", () => {
  it("pinta las cinco etapas del proceso en orden", async () => {
    renderRiel(usuario("admin"));
    for (const e of ETAPAS) expect(screen.getByTestId(`etapa-${e}`)).toBeTruthy();
  });

  it("admin: el maestro ON deja todas las etapas en estado «on»", async () => {
    renderRiel(usuario("admin"));
    await waitFor(() =>
      expect(screen.getByTestId("etapa-ingesta").getAttribute("data-estado")).toBe("on"),
    );
    for (const e of ETAPAS)
      expect(screen.getByTestId(`etapa-${e}`).getAttribute("data-estado")).toBe("on");
  });

  it("admin: el maestro OFF deja las etapas en «off»", async () => {
    vi.spyOn(apiMod.api, "ajustes").mockResolvedValue(ajustes(false));
    renderRiel(usuario("admin"));
    await waitFor(() =>
      expect(screen.getByTestId("etapa-ingesta").getAttribute("data-estado")).toBe("off"),
    );
  });

  it("el lápiz de una etapa con prompt es un botón (no deep-link) que abre el editor in-place", () => {
    renderRiel(usuario("admin"));
    const lapiz = screen.getByLabelText("Editar el prompt de Verificación");
    expect(lapiz.tagName).toBe("BUTTON");
    expect(lapiz.getAttribute("href")).toBeNull();
    // La ingesta es mecánica (sin prompt): no lleva lápiz.
    expect(screen.queryByLabelText(/Editar el prompt de Ingesta/)).toBeNull();
    // Al pulsarlo se abre el overlay «Editar prompt» encima del cockpit (sin salir).
    fireEvent.click(lapiz);
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("no admin: no consulta el catálogo y las etapas quedan «desconocido»", async () => {
    const spy = vi.spyOn(apiMod.api, "ajustes");
    renderRiel(usuario("editor"));
    expect(screen.getByTestId("etapa-ingesta").getAttribute("data-estado")).toBe("desconocido");
    expect(spy).not.toHaveBeenCalled();
    // Sin estado legible, tampoco el pie de «Ajustes».
    expect(screen.queryByText(/Ajustes del motor/i)).toBeNull();
  });
});
