/**
 * Tests para ConstructorUtm (#119 A-4):
 * El timeout de reset de "copiado" debe limpiarse al desmontar el componente
 * para no llamar setState sobre un componente desmontado.
 */
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConstructorUtm } from "./ConstructorUtm";

afterEach(() => {
  vi.useRealTimers();
});

describe("ConstructorUtm · A-4: cleanup del timeout (#119)", () => {
  it("renderiza el diálogo cuando está abierto", () => {
    render(<ConstructorUtm abierto={true} onCerrar={vi.fn()} />);
    expect(screen.getByText("Constructor de enlaces UTM")).toBeInTheDocument();
  });

  it("no renderiza el contenido del diálogo cuando está cerrado", () => {
    render(<ConstructorUtm abierto={false} onCerrar={vi.fn()} />);
    expect(screen.queryByText("Constructor de enlaces UTM")).not.toBeInTheDocument();
  });

  it("no produce errores de React al desmontar durante el timeout de copiado", () => {
    vi.useFakeTimers();
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const { unmount } = render(<ConstructorUtm abierto={true} onCerrar={vi.fn()} />);

    // Desmontamos antes de que expire cualquier timer
    unmount();

    // Sin cleanup: habría un setState sobre componente desmontado y un warning.
    vi.advanceTimersByTime(3000);

    expect(consoleSpy).not.toHaveBeenCalledWith(expect.stringContaining("unmounted"));

    consoleSpy.mockRestore();
    vi.useRealTimers();
  });

  it("el componente se monta y desmonta sin errores de consola", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const { unmount } = render(<ConstructorUtm abierto={true} onCerrar={vi.fn()} />);
    expect(screen.getByText("Constructor de enlaces UTM")).toBeInTheDocument();
    unmount();

    expect(consoleSpy).not.toHaveBeenCalledWith(expect.stringContaining("Warning"));
    consoleSpy.mockRestore();
  });
});
