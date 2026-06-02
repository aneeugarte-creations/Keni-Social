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

/** Cadena de los dos OK: Edición (OK de Ana) → Coordinación (el OK que toca ahora). */
function cadenaOK(over: Partial<TCadena> = {}): TCadena {
  return {
    niveles: [
      nivel({ id: "n1", nivel: 1, etiqueta: "Edición", decision: "aprobado", decisor_id: "ana", decisor_nombre: "Ana" }),
      nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación" }),
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
    veredictoIA,
  }: { autorPiezaId?: string; usuario?: Partial<UsuarioSesion>; veredictoIA?: string } = {},
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
        <CadenaAprobacion
          cadena={cadena}
          plataformaId="p1"
          autorPiezaId={autorPiezaId}
          veredictoIA={veredictoIA}
        />
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("CadenaAprobacion · panel «dale el OK»", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("muestra cuántos OK van y de quién + lo que falta", () => {
    renderCadena(cadenaOK());
    expect(screen.getByText("OK 1/2")).toBeInTheDocument();
    expect(screen.getByText(/Ana/)).toBeInTheDocument();
    expect(screen.getByText(/Faltan 1 OK/i)).toBeInTheDocument();
  });

  it("pinta el veredicto de IA cuando hay (🟢 lista)", () => {
    renderCadena(cadenaOK(), { veredictoIA: "listo" });
    expect(screen.getByText(/IA: lista/i)).toBeInTheDocument();
  });

  it("«Dar mi OK» pega al endpoint del nivel actual (decisión por orden)", async () => {
    const fetchMock = vi.fn(
      async (_url: string | URL) =>
        new Response(JSON.stringify({ nivel: {}, estado: "pendiente", niveles: [] }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderCadena(cadenaOK());
    fireEvent.click(screen.getByRole("button", { name: /dar mi ok/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const url = String(fetchMock.mock.calls[0]?.[0] ?? "");
    expect(url).toContain("/aprobacion-nivel/n2/decidir");
  });

  it("GATE autor: el autor (no admin) no puede dar OK a su propia pieza", () => {
    renderCadena(cadenaOK(), { autorPiezaId: "u1", usuario: { id: "u1", rol: "editor" } });
    expect(screen.getByText(/no puedes dar ok a tu propia pieza/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /dar mi ok/i })).toBeDisabled();
  });

  it("GATE «otra persona»: quien ya dio un OK no puede dar el otro", () => {
    // El usuario de sesión (u1) es quien aprobó Edición (decisor_id ana → lo ponemos a u1).
    const c = cadenaOK({
      niveles: [
        nivel({ id: "n1", nivel: 1, etiqueta: "Edición", decision: "aprobado", decisor_id: "u1", decisor_nombre: "Yo" }),
        nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación" }),
      ],
    });
    renderCadena(c, { usuario: { id: "u1", rol: "editor" } });
    expect(screen.getByText(/ya diste tu ok/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /dar mi ok/i })).toBeDisabled();
  });

  it("GATE autor: un admin SÍ puede dar OK aunque sea el autor (desatascar)", () => {
    renderCadena(cadenaOK(), { autorPiezaId: "u1", usuario: { id: "u1", rol: "admin" } });
    expect(screen.getByRole("button", { name: /dar mi ok/i })).toBeEnabled();
  });

  it("cadena RECHAZADA: no ofrece OK y explica que vuelve a redacción", () => {
    const c = cadenaOK({
      niveles: [
        nivel({ id: "n1", nivel: 1, etiqueta: "Edición", decision: "rechazado", decisor_nombre: "Ana" }),
        nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación" }),
      ],
      estado: "rechazado",
      nivel_actual: "",
    });
    renderCadena(c);
    expect(screen.getByText(/vuelve a la redacción/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /dar mi ok/i })).not.toBeInTheDocument();
  });

  it("cadena TOTALMENTE aprobada: «Lista para publicar»", () => {
    const c = cadenaOK({
      niveles: [
        nivel({ id: "n1", nivel: 1, etiqueta: "Edición", decision: "aprobado", decisor_id: "ana", decisor_nombre: "Ana" }),
        nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación", decision: "aprobado", decisor_id: "leo", decisor_nombre: "Leo" }),
      ],
      estado: "aprobado",
      nivel_actual: "",
    });
    renderCadena(c);
    expect(screen.getByText(/lista para publicar/i)).toBeInTheDocument();
    expect(screen.getByText("OK 2/2")).toBeInTheDocument();
  });
});
