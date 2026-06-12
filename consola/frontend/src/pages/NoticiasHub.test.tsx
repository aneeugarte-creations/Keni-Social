/**
 * Tests de NoticiasHub (ADR 0011, C3 + Fase 3): la página de Investigación muestra el RIEL del
 * proceso encima de Cobertura y un CHIP compacto del loop (enlace al Monitor prefiltrado). Los
 * AJUSTES del motor ya NO viven aquí: migraron al drawer del Monitor (sección «Investigación»),
 * así que la página no monta ningún menú «⋮».
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  MarcaActivaContexto,
  type ValorMarcaActiva,
} from "@/hooks/marca-activa-contexto";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import * as apiMod from "@/lib/api";
import type { AjusteAdmin, ColaMonitor, RespuestaAjustes, UsuarioSesion } from "@/types";

import NoticiasHub from "./NoticiasHub";

function usuario(rol: "admin" | "editor"): UsuarioSesion {
  return { id: "u1", usuario: "u", rol, debe_cambiar_password: false, marcas: ["unotv"] };
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

function valorMarcaActiva(): ValorMarcaActiva {
  return {
    marcaActiva: "unotv",
    marcaPrimaria: "unotv",
    enMarcaPrimaria: true,
    esMultiMarca: false,
    puedeTodas: false,
    marcasParaSwitch: [],
    nombreActiva: "UnoTV",
    cambiarMarca: vi.fn(),
    volverAPrimaria: vi.fn(),
  };
}

function bool(clave: string, grupo: string, valor: boolean, etiqueta: string): AjusteAdmin {
  return {
    clave,
    tipo: "bool",
    etiqueta,
    ayuda: "",
    grupo,
    peligroso: false,
    valor,
    fuente: "store",
    defecto: false,
  };
}

const AJUSTES: RespuestaAjustes = {
  grupos: [
    {
      id: "maestros_investigacion",
      titulo: "Investigación (todas las marcas)",
      ajustes: [bool("KENI_INVESTIGACION", "maestros_investigacion", true, "Investigación")],
    },
  ],
};

/** Snapshot mínimo de la cola con desglose por proceso (lo que consume el chip). */
function snapshotCola(procesando: number, pendientes: number): ColaMonitor {
  return {
    marca: "",
    capacidad: { max_jobs: 2, max_cola: 4, tope: 6 },
    conteo: { pendientes, reclamados: procesando, terminados: 0, activos: procesando + pendientes },
    cola_llena: false,
    procesando,
    slots_libres: 2 - procesando,
    workers_activos: [],
    por_proceso: {
      investigacion: { procesando, pendientes },
      produccion: { procesando: 0, pendientes: 0 },
    },
    en_curso: [],
    esperando: [],
    daemons: [],
  };
}

function renderHub(u: UsuarioSesion) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesionValor(u)}>
        <MarcaActivaContexto.Provider value={valorMarcaActiva()}>
          <MemoryRouter>
            <NoticiasHub />
          </MemoryRouter>
        </MarcaActivaContexto.Provider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.spyOn(apiMod.api, "ajustes").mockResolvedValue(AJUSTES);
  vi.spyOn(apiMod.api, "cola").mockResolvedValue(snapshotCola(2, 3));
  vi.spyOn(apiMod.api.noticias, "cobertura").mockResolvedValue({ feeds_con_error: 0 });
  vi.spyOn(apiMod.api.noticias, "mesa").mockResolvedValue({
    marca: "unotv",
    plan: false,
    lineas: [],
    fuera_de_plan: { en_pool: 0, historias: [] },
    total_objetivo: 0,
    total_generados: 0,
  });
  vi.spyOn(apiMod.api.noticias, "historias").mockResolvedValue({ historias: [], total: 0 });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("NoticiasHub · proceso de Investigación", () => {
  it("muestra el riel del proceso encima de Cobertura", async () => {
    renderHub(usuario("editor"));
    expect(screen.getByTestId("riel-investigacion")).toBeTruthy();
    expect(screen.getByTestId("etapa-verificación")).toBeTruthy();
  });

  it("muestra el chip del loop con sus conteos, enlazando al Monitor prefiltrado (Fase 3)", async () => {
    renderHub(usuario("editor"));
    const chip = await screen.findByTestId("chip-investigacion");
    expect(chip.textContent).toContain("Investigación");
    expect(chip.textContent).toContain("2");
    expect(chip.textContent).toContain("en curso");
    expect(chip.textContent).toContain("3");
    expect(chip.textContent).toContain("en cola");
    expect(chip.getAttribute("href")).toBe("/datos/produccion/monitor?proceso=investigacion");
  });

  it("admin: la página ya NO monta el menú «⋮» de ajustes (viven en el drawer del Monitor)", async () => {
    renderHub(usuario("admin"));
    await screen.findByTestId("riel-investigacion");
    expect(screen.queryByRole("button", { name: /Acciones/i })).toBeNull();
  });
});
