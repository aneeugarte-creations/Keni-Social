/**
 * Tests de la página AgentesInvestigacion (Ola 6).
 *
 * Cubren:
 * 1. Renderiza el encabezado de la página.
 * 2. Muestra los briefs cargados desde la API.
 * 3. "Investigar ahora" llama a api.investigacion.correr con el brief_id.
 * 4. Muestra los candidatos del día.
 * 5. "Enviar al feed" llama a api.investigacion.aceptar.
 * 6. "Descartar" llama a api.investigacion.descartar.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import { MarcaActivaProvider } from "@/hooks/use-marca-activa";
import * as apiMod from "@/lib/api";
import type { UsuarioSesion } from "@/types";

import AgentesInvestigacion from "./AgentesInvestigacion";

// ── Helpers ───────────────────────────────────────────────────────────────────

function usuario(): UsuarioSesion {
  return {
    id: "u1",
    usuario: "ana",
    rol: "editor",
    debe_cambiar_password: false,
    marcas: ["unotv"],
  };
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

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesionValor(usuario())}>
        <MarcaActivaProvider>
          <MemoryRouter>{ui}</MemoryRouter>
        </MarcaActivaProvider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

const BRIEF_UNOTV = {
  id: "brief-1",
  nombre: "Noticias UnoTV",
  marca: "unotv",
  linea: "Nacional",
  instrucciones: "Busca notas de política y sociedad en México.",
  idiomas: "es",
  activo: 1,
  creado: "2026-06-01T10:00:00",
};

const BRIEFS_VACIOS = { briefs: [] };
const BRIEFS_CON_DATOS = { briefs: [BRIEF_UNOTV] };

const CANDIDATO_NUEVO = {
  id: "cand-1",
  brief_id: "brief-1",
  fecha: "2026-06-05",
  marca: "unotv",
  marca_nombre: "UnoTV",
  linea: "Nacional",
  titulo: "Propuesta de reforma constitucional avanza en el Congreso",
  resumen: "El Congreso aprobó en comisiones una propuesta clave.",
  por_que: "Tema político de alto interés hoy.",
  fuente: "Reforma",
  enlace: "https://reforma.com/nota-1",
  idioma: "es",
  estado: "nuevo",
  contenido_id: "",
  creado: "2026-06-05T08:00:00",
};

const CANDIDATOS_VACIOS = { candidatos: [] };
const CANDIDATOS_CON_DATOS = { candidatos: [CANDIDATO_NUEVO] };

// `correr` ahora es ASÍNCRONO: el back encola un job (el worker corre Haiku) y devuelve la
// generación a sondear. Se entrega ya `completado` para que la prueba no dependa del sondeo.
const CORRER_RESP = {
  generacion: {
    id: "gen-inv-1",
    tipo: "investigacion",
    marca: "unotv",
    etiqueta: "Investigar: Noticias UnoTV",
    estado: "completado",
    fase: "completado",
    motivo: "",
    salida: "",
    error: "",
    metricas: null,
    resultado: { candidatos: 1 },
    autor_id: "",
    autor_nombre: "",
    fecha_inicio: "2026-06-05T06:00:00",
    fecha_fin: "2026-06-05T06:00:10",
  },
};

// ── Setup / teardown ──────────────────────────────────────────────────────────

beforeEach(() => {
  vi.restoreAllMocks();
  const store = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
  });
});
afterEach(() => vi.unstubAllGlobals());

// ── Helpers de mock ───────────────────────────────────────────────────────────

function mockApi(
  briefsPayload: object = BRIEFS_VACIOS,
  candidatosPayload: object = CANDIDATOS_VACIOS,
) {
  vi.spyOn(apiMod.api.investigacion, "briefs").mockResolvedValue(briefsPayload as never);
  vi.spyOn(apiMod.api.investigacion, "candidatos").mockResolvedValue(candidatosPayload as never);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("AgentesInvestigacion", () => {
  it("renderiza el encabezado de la página", async () => {
    mockApi();
    renderConProviders(<AgentesInvestigacion />);

    expect(
      await screen.findByRole("heading", { name: "Agentes de investigación" }),
    ).toBeInTheDocument();
  });

  it("muestra los briefs cuando la API devuelve datos", async () => {
    mockApi(BRIEFS_CON_DATOS, CANDIDATOS_VACIOS);
    renderConProviders(<AgentesInvestigacion />);

    expect(await screen.findByText("Noticias UnoTV")).toBeInTheDocument();
    // Badge de marca y línea
    expect(screen.getByText("unotv")).toBeInTheDocument();
    expect(screen.getByText("Nacional")).toBeInTheDocument();
  });

  it("muestra estado vacío cuando no hay briefs", async () => {
    mockApi(BRIEFS_VACIOS, CANDIDATOS_VACIOS);
    renderConProviders(<AgentesInvestigacion />);

    expect(
      await screen.findByText(/Aún no hay briefs/),
    ).toBeInTheDocument();
  });

  it("'Investigar ahora' llama a api.investigacion.correr con el brief_id correcto", async () => {
    const correrMock = vi
      .spyOn(apiMod.api.investigacion, "correr")
      .mockResolvedValue(CORRER_RESP as never);
    mockApi(BRIEFS_CON_DATOS, CANDIDATOS_VACIOS);

    renderConProviders(<AgentesInvestigacion />);

    await screen.findByText("Noticias UnoTV");

    const boton = screen.getByRole("button", { name: /Investigar ahora con brief "Noticias UnoTV"/ });
    fireEvent.click(boton);

    await waitFor(() => {
      expect(correrMock).toHaveBeenCalledWith({ brief_id: "brief-1" });
    });
  });

  it("muestra los candidatos del día cuando la API devuelve datos", async () => {
    mockApi(BRIEFS_VACIOS, CANDIDATOS_CON_DATOS);
    renderConProviders(<AgentesInvestigacion />);

    expect(
      await screen.findByText("Propuesta de reforma constitucional avanza en el Congreso"),
    ).toBeInTheDocument();
    expect(screen.getByText("El Congreso aprobó en comisiones una propuesta clave.")).toBeInTheDocument();
    // Badges
    expect(screen.getByText("UnoTV")).toBeInTheDocument();
    expect(screen.getByText("Reforma")).toBeInTheDocument();
  });

  it("'Enviar al feed' llama a api.investigacion.aceptar con el id del candidato", async () => {
    const aceptarMock = vi
      .spyOn(apiMod.api.investigacion, "aceptar")
      .mockResolvedValue({
        candidato: { ...CANDIDATO_NUEVO, estado: "aceptado", contenido_id: "c-nuevo" },
        contenido_id: "c-nuevo",
      } as never);
    mockApi(BRIEFS_VACIOS, CANDIDATOS_CON_DATOS);

    renderConProviders(<AgentesInvestigacion />);

    await screen.findByText("Propuesta de reforma constitucional avanza en el Congreso");

    const boton = screen.getByRole("button", {
      name: /Enviar al feed "Propuesta de reforma constitucional avanza en el Congreso"/,
    });
    fireEvent.click(boton);

    await waitFor(() => {
      expect(aceptarMock).toHaveBeenCalledWith("cand-1", { generar: false });
    });
  });

  it("'Descartar' llama a api.investigacion.descartar con el id del candidato", async () => {
    const descartarMock = vi
      .spyOn(apiMod.api.investigacion, "descartar")
      .mockResolvedValue({
        candidato: { ...CANDIDATO_NUEVO, estado: "descartado" },
      } as never);
    mockApi(BRIEFS_VACIOS, CANDIDATOS_CON_DATOS);

    renderConProviders(<AgentesInvestigacion />);

    await screen.findByText("Propuesta de reforma constitucional avanza en el Congreso");

    const boton = screen.getByRole("button", {
      name: /Descartar "Propuesta de reforma constitucional avanza en el Congreso"/,
    });
    fireEvent.click(boton);

    await waitFor(() => {
      expect(descartarMock).toHaveBeenCalledWith("cand-1");
    });
  });

  it("muestra estado vacío cuando no hay candidatos", async () => {
    mockApi(BRIEFS_VACIOS, CANDIDATOS_VACIOS);
    renderConProviders(<AgentesInvestigacion />);

    expect(
      await screen.findByText(/No hay candidatos para esta fecha/),
    ).toBeInTheDocument();
  });

  it("pasa la marca activa a api.investigacion.candidatos", async () => {
    const candidatosMock = vi
      .spyOn(apiMod.api.investigacion, "candidatos")
      .mockResolvedValue(CANDIDATOS_VACIOS as never);
    vi.spyOn(apiMod.api.investigacion, "briefs").mockResolvedValue(BRIEFS_VACIOS as never);

    renderConProviders(<AgentesInvestigacion />);

    await screen.findByRole("heading", { name: "Agentes de investigación" });

    // El usuario del helper tiene marcas: ["unotv"], así que marcaActiva = "unotv"
    await waitFor(() => {
      expect(candidatosMock).toHaveBeenCalledWith(
        expect.objectContaining({ marca: "unotv" }),
        expect.anything(),
      );
    });
  });

  it("pre-rellena el campo marca del brief nuevo con la marca activa", async () => {
    mockApi(BRIEFS_VACIOS, CANDIDATOS_VACIOS);
    renderConProviders(<AgentesInvestigacion />);

    await screen.findByRole("heading", { name: "Agentes de investigación" });

    // Hay dos botones "Nuevo": uno para crear brief y otro es el filtro de estado.
    // El de brief tiene un icono Plus y está primero en el DOM (dentro del card de briefs).
    const botonesNuevo = screen.getAllByRole("button", { name: /Nuevo/i });
    // El botón de "Nuevo brief" tiene el icono SVG plus, aparece antes que el filtro
    // de estado de candidatos. Usamos el primero.
    fireEvent.click(botonesNuevo[0]);

    // El campo de marca debe estar pre-rellenado con la marca activa
    await waitFor(() => {
      const inputMarca = screen.getByRole("textbox", { name: /Marca \(id\)/i });
      expect((inputMarca as HTMLInputElement).value).toBe("unotv");
    });
  });

  it("candidato aceptado muestra badge 'En el feed' (sin botones de acción)", async () => {
    const candidatoAceptado = { ...CANDIDATO_NUEVO, estado: "aceptado" as const };
    mockApi(BRIEFS_VACIOS, { candidatos: [candidatoAceptado] });

    renderConProviders(<AgentesInvestigacion />);

    await screen.findByText("Propuesta de reforma constitucional avanza en el Congreso");
    expect(screen.getByText("En el feed")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Enviar al feed/ })).not.toBeInTheDocument();
  });
});
