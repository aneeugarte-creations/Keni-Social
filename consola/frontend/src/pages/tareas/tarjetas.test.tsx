import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SemaforoCobertura } from "./tarjetas";

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
