import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import type { CadenaAprobacion as TCadena, NivelAprobacion, UsuarioSesion } from "@/types";

import { CadenaAprobacion } from "./CadenaAprobacion";

/** Construye un nivel con valores por defecto razonables (sobreescribibles). */
function nivel(over: Partial<NivelAprobacion>): NivelAprobacion {
  return {
    id: "n?",
    plataforma_id: "p1",
    contenido_id: "c1",
    nivel: 1,
    etiqueta: "Edición",
    decision: "pendiente",
    decisor_id: "",
    decisor_nombre: "",
    comentario: "",
    creado: "",
    decidido_en: "",
    cargo_requerido: "",
    ...over,
  };
}

/** Cadena de 3 niveles: Edición (aprobado) → Coordinación (actual, pendiente) → Dirección. */
function cadena3(over: Partial<TCadena> = {}): TCadena {
  return {
    niveles: [
      nivel({ id: "n1", nivel: 1, etiqueta: "Edición", decision: "aprobado", decisor_nombre: "Ana" }),
      nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación", cargo_requerido: "coordinador" }),
      nivel({ id: "n3", nivel: 3, etiqueta: "Dirección", cargo_requerido: "director" }),
    ],
    estado: "pendiente",
    nivel_actual: "n2",
    aprobados: 1,
    minimo_aprobaciones: 0,
    comentarios_sin_resolver: 0,
    ...over,
  };
}

function renderCadena(
  cadena: TCadena,
  {
    autorPiezaId = "autorX",
    usuario = {},
  }: { autorPiezaId?: string; usuario?: Partial<UsuarioSesion> } = {},
) {
  const valor: ValorSesion = {
    usuario: {
      id: "u1",
      usuario: "revisor",
      rol: "editor",
      debe_cambiar_password: false,
      ...usuario,
    } as UsuarioSesion,
    cargando: false,
    iniciarSesion: vi.fn(),
    cerrarSesion: vi.fn(),
    refrescar: vi.fn(),
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={valor}>
        <CadenaAprobacion cadena={cadena} plataformaId="p1" autorPiezaId={autorPiezaId} />
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("CadenaAprobacion · UI multinivel", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("pinta cada nivel con su estado: aprobado, actual (pendiente) y en espera", () => {
    renderCadena(cadena3());
    // Los 3 niveles con sus etiquetas (Coordinación aparece también en "toca decidir").
    expect(screen.getByText("Edición")).toBeInTheDocument();
    expect(screen.getAllByText("Coordinación").length).toBeGreaterThan(0);
    expect(screen.getByText("Dirección")).toBeInTheDocument();
    // Estado por nivel: el primero aprobado, el último (no es su turno) en espera.
    expect(screen.getByText("Aprobado")).toBeInTheDocument();
    expect(screen.getByText("En espera")).toBeInTheDocument();
    // El badge global resume "En aprobación".
    expect(screen.getByText("En aprobación")).toBeInTheDocument();
  });

  it("solo ofrece decidir el nivel ACTUAL por orden (Coordinación)", () => {
    renderCadena(cadena3());
    expect(screen.getByText(/toca decidir/i)).toHaveTextContent("Coordinación");
    expect(screen.getByRole("button", { name: /aprobar nivel/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /rechazar/i })).toBeInTheDocument();
  });

  it("llama al endpoint del nivel actual al aprobar (decisión por orden)", async () => {
    const fetchMock = vi.fn(async (_url: string | URL) =>
      new Response(JSON.stringify({ nivel: {}, estado: "pendiente", niveles: [] }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderCadena(cadena3());
    fireEvent.click(screen.getByRole("button", { name: /aprobar nivel/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    // Pega al endpoint del nivel actual (n2), no a otro.
    const url = String(fetchMock.mock.calls[0]?.[0] ?? "");
    expect(url).toContain("/aprobacion-nivel/n2/decidir");
  });

  it("GATE autor: el autor (no admin) no puede decidir su propia pieza", () => {
    renderCadena(cadena3(), { autorPiezaId: "u1", usuario: { id: "u1", rol: "editor" } });
    expect(screen.getByText(/no puedes aprobar tu propia pieza/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /aprobar nivel/i })).not.toBeInTheDocument();
  });

  it("GATE autor: un admin SÍ puede decidir aunque sea el autor (desatascar)", () => {
    renderCadena(cadena3(), { autorPiezaId: "u1", usuario: { id: "u1", rol: "admin" } });
    expect(screen.queryByText(/no puedes aprobar tu propia pieza/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /aprobar nivel/i })).toBeInTheDocument();
  });

  it("cadena RECHAZADA: no ofrece decisión y explica que vuelve a redacción", () => {
    const c = cadena3({
      niveles: [
        nivel({ id: "n1", nivel: 1, etiqueta: "Edición", decision: "rechazado", decisor_nombre: "Ana" }),
        nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación" }),
      ],
      estado: "rechazado",
      nivel_actual: "",
    });
    renderCadena(c);
    expect(screen.getByText("Rechazada")).toBeInTheDocument();
    expect(screen.getByText(/vuelve a la redacción/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /aprobar nivel/i })).not.toBeInTheDocument();
  });

  it("cadena TOTALMENTE aprobada: sin decisión pendiente", () => {
    const c = cadena3({
      niveles: [
        nivel({ id: "n1", nivel: 1, etiqueta: "Edición", decision: "aprobado" }),
        nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación", decision: "aprobado" }),
      ],
      estado: "aprobado",
      nivel_actual: "",
    });
    renderCadena(c);
    expect(screen.getByText("Aprobada")).toBeInTheDocument();
    expect(screen.getByText(/todos los niveles están aprobados/i)).toBeInTheDocument();
  });
});
