import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GuionPartido, SemaforoCobertura } from "./tarjetas";

describe("SemaforoCobertura — fase del evento por su reloj maestro", () => {
  // AHORA fijo = 2026-06-14 00:00 UTC = 2026-06-13 18:00 CDMX (UTC-6).
  afterEach(() => vi.useRealTimers());
  function conAhora(fn: () => void) {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-14T00:00:00Z"));
    fn();
  }

  it("PRE-LIVE: a ≤ 2 h del pitido muestra «Empieza en X min» (ámbar), no «Programado»", () => {
    conAhora(() => {
      // 18:30 CDMX de hoy, ahora 18:00 CDMX → faltan 30 min.
      render(<SemaforoCobertura fecha="2026-06-13" hora="18:30" />);
      expect(screen.getByText("Empieza en 30 min")).toBeInTheDocument();
      expect(screen.queryByText("Programado")).toBeNull();
    });
  });

  it("futuro lejano (> 2 h) → «Programado» plano", () => {
    conAhora(() => {
      render(<SemaforoCobertura fecha="2026-06-20" hora="18:00" />);
      expect(screen.getByText("Programado")).toBeInTheDocument();
    });
  });

  it("durante la ventana → «En vivo»; ya pasó → «Cubierto»", () => {
    conAhora(() => {
      const { unmount } = render(<SemaforoCobertura fecha="2026-06-13" hora="17:00" />);
      expect(screen.getByText("En vivo")).toBeInTheDocument();
      unmount();
      render(<SemaforoCobertura fecha="2026-06-12" hora="20:00" />);
      expect(screen.getByText("Cubierto")).toBeInTheDocument();
    });
  });

  it("compacto en PRE-LIVE: punto con tooltip «Empieza pronto»", () => {
    conAhora(() => {
      render(<SemaforoCobertura fecha="2026-06-13" hora="18:30" compacto />);
      expect(screen.getByTitle("Empieza pronto")).toBeInTheDocument();
    });
  });
});

describe("GuionPartido — checklist de referencia neutra (colapsable)", () => {
  const abrir = () =>
    fireEvent.click(screen.getByRole("button", { name: /guion del partido/i }));

  it("va COLAPSADO por defecto: el encabezado se ve, las fases no hasta abrir", () => {
    render(<GuionPartido />);
    expect(screen.getByText("Guion del partido")).toBeInTheDocument();
    expect(screen.queryByText("Antes")).toBeNull();
    expect(screen.queryByText("Gráfico de matchday")).toBeNull();
  });

  it("el toggle EXPANDE y vuelve a COLAPSAR el guion", () => {
    render(<GuionPartido />);
    abrir();
    expect(screen.getByText("Antes")).toBeInTheDocument();
    expect(screen.getByText("Durante el partido")).toBeInTheDocument();
    expect(screen.getByText("Después")).toBeInTheDocument();
    expect(screen.getByText("Gráfico de matchday")).toBeInTheDocument();
    abrir();
    expect(screen.queryByText("Antes")).toBeNull();
  });

  it("expandido: entregables NEUTROS (sin marcadores de cubierto; la cobertura la dice RolesCubiertos)", () => {
    render(<GuionPartido />);
    abrir();
    expect(screen.getByText("Partido normal")).toBeInTheDocument();
    expect(screen.queryAllByLabelText("cubierto")).toHaveLength(0);
  });

  it("«solo imágenes» (tipo_cobertura) oculta la fase «Durante» (entregables de directo)", () => {
    render(<GuionPartido tipoCobertura="imagenes" />);
    abrir();
    expect(screen.getByText("Antes")).toBeInTheDocument();
    expect(screen.getByText("Después")).toBeInTheDocument();
    expect(screen.queryByText("Durante el partido")).toBeNull();
  });

  it("«transmisión» mantiene el guion completo (incluida la fase «Durante»)", () => {
    render(<GuionPartido tipoCobertura="transmision" />);
    abrir();
    expect(screen.getByText("Durante el partido")).toBeInTheDocument();
  });
});
