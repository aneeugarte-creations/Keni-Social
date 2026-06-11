/**
 * Tests de NoticiasHub (ADR 0011, C3): la página de Investigación muestra el RIEL del proceso
 * encima de Cobertura, y su panel de ajustes (admin) incluye el maestro `maestros_investigacion`
 * ADEMÁS de los grupos del motor de noticias.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  MarcaActivaContexto,
  type ValorMarcaActiva,
} from "@/hooks/marca-activa-contexto";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import * as apiMod from "@/lib/api";
import type { AjusteAdmin, RespuestaAjustes, UsuarioSesion } from "@/types";

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
    {
      id: "automatizacion_marca_investigacion",
      titulo: "Investigación · excepciones por marca",
      ajustes: [
        bool(
          "KENI_INVESTIGACION::unotv",
          "automatizacion_marca_investigacion",
          true,
          "UnoTV · Investigación",
        ),
      ],
    },
    {
      id: "noticias_entrada",
      titulo: "Entrada al pool",
      ajustes: [bool("KENI_TRADUCCION", "noticias_entrada", false, "Traducir al español")],
    },
  ],
};

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

  it("admin: el panel de ajustes incluye el maestro de Investigación y un grupo del motor", async () => {
    renderHub(usuario("admin"));
    // Abre el menú «⋮» y luego «Ajustes».
    fireEvent.click(screen.getByRole("button", { name: /Acciones/i }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /Ajustes/i }));
    // El maestro `maestros_investigacion` (interruptor general) y un grupo del motor de noticias.
    await waitFor(() =>
      expect(screen.getByText(/Investigación \(interruptor general\)/i)).toBeTruthy(),
    );
    expect(screen.getByText(/Entrada al pool/i)).toBeTruthy();
  });

  it("admin: el panel de ajustes incluye las excepciones por marca de Investigación (ADR 0011, C4)", async () => {
    renderHub(usuario("admin"));
    fireEvent.click(screen.getByRole("button", { name: /Acciones/i }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /Ajustes/i }));
    // El área de excepciones por marca de Investigación (grupo `automatizacion_marca_investigacion`)
    // vive AQUÍ, no en el Monitor (que solo muestra Producción).
    await waitFor(() => expect(screen.getByText(/Investigación · por marca/i)).toBeTruthy());
  });
});
