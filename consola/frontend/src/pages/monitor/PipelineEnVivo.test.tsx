/**
 * Tests de la tira «Pipeline en vivo»: en concreto, que el lápiz «Editar prompt» de una etapa
 * abre el editor en un OVERLAY (encima de la página, sin navegar), en vez del antiguo deep-link
 * a la Biblioteca (`/contenido/texto/documentos?doc=…`). Decisión «in-place + biblioteca».
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import * as apiMod from "@/lib/api";
import type { ColaMonitor, UsuarioSesion } from "@/types";

import { PipelineEnVivo } from "./PipelineEnVivo";

function usuario(): UsuarioSesion {
  return { id: "u1", usuario: "u", rol: "admin", debe_cambiar_password: false, marcas: ["unotv"] };
}

function sesionValor(u: UsuarioSesion): ValorSesion {
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

const COLA: ColaMonitor = {
  marca: "",
  capacidad: { max_jobs: 4, max_cola: 100, tope: 4 },
  conteo: { pendientes: 0, reclamados: 0, terminados: 0, activos: 0 },
  cola_llena: false,
  procesando: 0,
  slots_libres: 4,
  workers_activos: [],
  en_curso: [],
  esperando: [],
  daemons: [],
};

function renderTira() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesionValor(usuario())}>
        <MemoryRouter>
          <PipelineEnVivo
            cola={COLA}
            esAdmin
            soloProceso="produccion"
            docPorEtapa={{ copy: "prompt/copy" }}
          />
        </MemoryRouter>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.spyOn(apiMod.api, "ajustes").mockResolvedValue({ grupos: [] });
  vi.spyOn(apiMod.api, "maquinaTexto").mockResolvedValue({ maquinas: [] });
  vi.spyOn(apiMod.api, "marcasTexto").mockResolvedValue({ marcas: [] });
  // Pendiente para siempre: el editor muestra su esqueleto dentro del overlay (basta para
  // comprobar que el overlay se abre, sin montar todo el detalle).
  vi.spyOn(apiMod.api, "documento").mockReturnValue(new Promise(() => {}));
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("PipelineEnVivo · «Editar prompt» (overlay)", () => {
  it("la etapa con prompt es accionable y NO es un enlace (no navega)", () => {
    renderTira();
    const etapa = screen.getByText("Copy").closest('[role="button"]') as HTMLElement;
    expect(etapa).toBeTruthy();
    expect(etapa.tagName).not.toBe("A");
    expect(etapa.getAttribute("href")).toBeNull();
  });

  it("al pulsar la etapa (acción primaria) abre el editor en un overlay, sin navegar", async () => {
    renderTira();
    expect(screen.queryByRole("dialog")).toBeNull();
    const etapa = screen.getByText("Copy").closest('[role="button"]') as HTMLElement;
    fireEvent.click(etapa);
    await waitFor(() => expect(screen.getByRole("dialog")).toBeTruthy());
    // El editor se monta dentro del overlay (esqueleto mientras carga el doc).
    expect(screen.getByTestId("detalle-cargando")).toBeTruthy();
  });

  it("el menú (click derecho) ofrece «Editar el prompt de Copy»", async () => {
    renderTira();
    const etapa = screen.getByText("Copy").closest('[role="button"]') as HTMLElement;
    fireEvent.contextMenu(etapa);
    expect(
      await screen.findByRole("menuitem", { name: "Editar el prompt de Copy" }),
    ).toBeInTheDocument();
  });
});
