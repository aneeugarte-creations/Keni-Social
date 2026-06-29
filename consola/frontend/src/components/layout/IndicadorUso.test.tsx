import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IndicadorUso } from "@/components/layout/IndicadorUso";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import type { UsoCuenta } from "@/hooks/use-uso-cuenta";
import type { RolUsuario } from "@/types";

// Aislamos la red: el componente solo lee el RESULTADO del hook (en `use-uso-cuenta`). Mockear el
// hook nos deja conducir cada estado (cargando / normal / rojo) sin tocar fetch ni react-query.
const usoMock = vi.fn();
vi.mock("@/hooks/use-uso-cuenta", () => ({
  useUsoCuenta: () => usoMock(),
}));

afterEach(() => {
  vi.clearAllMocks();
});

function valorSesion(rol: RolUsuario): ValorSesion {
  return {
    usuario: { id: "u1", usuario: "x", rol, debe_cambiar_password: false },
    cargando: false,
    errorConexion: false,
    iniciarSesion: async () => ({ mfaRequerido: false }),
    verificarConPasskey: async () => {},
    entrarConPasskey: async () => {},
    cerrarSesion: async () => {},
    refrescar: async () => {},
  };
}

function uso(parcial: Partial<UsoCuenta>): UsoCuenta {
  return {
    conectada: true,
    semana_pct: 42,
    sesion_5h_pct: 18,
    sonnet_pct: null,
    reset_semana_iso: "2026-07-01T00:00:00Z",
    reset_semana_txt: "Jul 1 at 12:00am (UTC)",
    actualizado_ts: 1_700_000_000,
    al_100: false,
    alerta_roja: false,
    ...parcial,
  };
}

function renderIndicador(rol: RolUsuario, colapsado = false) {
  return render(
    <SesionContexto.Provider value={valorSesion(rol)}>
      <IndicadorUso colapsado={colapsado} />
    </SesionContexto.Provider>,
  );
}

describe("IndicadorUso", () => {
  it("no renderiza nada para no-admin (editor)", () => {
    usoMock.mockReturnValue({ data: uso({}) });
    const { container } = renderIndicador("editor");
    expect(container).toBeEmptyDOMElement();
  });

  it("estado de carga (sin dato) es NEUTRO, no rojo: muestra «—» y los medidores", () => {
    usoMock.mockReturnValue({ data: undefined });
    renderIndicador("admin");
    expect(screen.getByText("Semana")).toBeInTheDocument();
    expect(screen.getByText("5h")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.queryByText(/Sin cuenta|100%/)).not.toBeInTheDocument();
  });

  it("estado normal expandido: pinta ambos porcentajes sin alerta roja", () => {
    usoMock.mockReturnValue({ data: uso({ semana_pct: 42, sesion_5h_pct: 18 }) });
    renderIndicador("admin");
    expect(screen.getByText("42%")).toBeInTheDocument();
    expect(screen.getByText("18%")).toBeInTheDocument();
    expect(screen.queryByText(/Sin cuenta/)).not.toBeInTheDocument();
  });

  it("rojo sin cuenta: mensaje «Sin cuenta» en clase destructiva", () => {
    usoMock.mockReturnValue({
      data: uso({ conectada: false, semana_pct: null, sesion_5h_pct: null, alerta_roja: true }),
    });
    renderIndicador("admin");
    const aviso = screen.getByText("Sin cuenta");
    expect(aviso).toBeInTheDocument();
    expect(aviso.className).toContain("text-destructive");
  });

  it("rojo al 100%: mensaje «Límite semanal al 100%»", () => {
    usoMock.mockReturnValue({
      data: uso({ semana_pct: 100, sesion_5h_pct: 60, al_100: true, alerta_roja: true }),
    });
    renderIndicador("admin");
    expect(screen.getByText("Límite semanal al 100%")).toBeInTheDocument();
  });

  it("colapsado: pinta un círculo (svg) con el número semanal, sin barras", () => {
    usoMock.mockReturnValue({ data: uso({ semana_pct: 42 }) });
    const { container } = renderIndicador("admin", true);
    expect(container.querySelector("svg")).toBeInTheDocument();
    // El número semanal va dentro del círculo (sin el «%», que sí aparece en las barras expandidas).
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.queryByText("Semana")).not.toBeInTheDocument();
  });

  it("colapsado rojo: el tooltip/etiqueta lleva el aviso «Sin cuenta»", () => {
    usoMock.mockReturnValue({
      data: uso({ conectada: false, semana_pct: null, sesion_5h_pct: null, alerta_roja: true }),
    });
    renderIndicador("admin", true);
    // Sin barras ni texto suelto en colapsado: el aviso viaja por el aria-label del círculo.
    expect(screen.getByLabelText(/Sin cuenta/)).toBeInTheDocument();
  });
});
