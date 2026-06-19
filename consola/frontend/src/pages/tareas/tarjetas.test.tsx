import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Publicacion } from "@/types";

import { ChipsRolFaltante, SemaforoCobertura } from "./tarjetas";

function cubridor(over: Partial<Publicacion> = {}): Publicacion {
  return {
    id: "c1",
    clase: "tarea",
    evento_id: "ev1",
    responsable_id: "u1",
    responsable_nombre: "luis",
    formato: "foto",
    ...over,
  } as unknown as Publicacion;
}

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

  it("durante la ventana → «En vivo»; ya pasó → «Terminado»", () => {
    conAhora(() => {
      const { unmount } = render(<SemaforoCobertura fecha="2026-06-13" hora="17:00" />);
      expect(screen.getByText("En vivo")).toBeInTheDocument();
      unmount();
      render(<SemaforoCobertura fecha="2026-06-12" hora="20:00" />);
      expect(screen.getByText("Terminado")).toBeInTheDocument();
    });
  });

  it("compacto en PRE-LIVE: la cuenta atrás se ve en la fila («30′»), no solo en hover", () => {
    conAhora(() => {
      render(<SemaforoCobertura fecha="2026-06-13" hora="18:30" compacto />);
      expect(screen.getByText("30′")).toBeInTheDocument();
      expect(screen.getByTitle("Empieza en 30 min")).toBeInTheDocument();
    });
  });
});

describe("ChipsRolFaltante — coger un rol libre de un toque", () => {
  it("sin cubridores ofrece los 4 roles como chips", () => {
    render(<ChipsRolFaltante cubridores={[]} onCoger={() => {}} />);
    for (const r of ["Foto", "Video", "Texto", "Live"]) {
      expect(screen.getByRole("button", { name: `Coger ${r}` })).toBeInTheDocument();
    }
  });

  it("con foto y video cubiertos solo ofrece texto y live", () => {
    render(
      <ChipsRolFaltante
        cubridores={[cubridor({ id: "a", formato: "foto" }), cubridor({ id: "b", formato: "video" })]}
        onCoger={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: "Coger Foto" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Coger Video" })).toBeNull();
    expect(screen.getByRole("button", { name: "Coger Texto" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Coger Live" })).toBeInTheDocument();
  });

  it("clic en un chip llama a onCoger con ESE rol", () => {
    const onCoger = vi.fn();
    render(<ChipsRolFaltante cubridores={[]} onCoger={onCoger} />);
    fireEvent.click(screen.getByRole("button", { name: "Coger Texto" }));
    expect(onCoger).toHaveBeenCalledWith("texto");
  });

  it("con los 4 roles cubiertos no pinta chips", () => {
    const { container } = render(
      <ChipsRolFaltante
        cubridores={["foto", "video", "texto", "live"].map((f, i) => cubridor({ id: `r${i}`, formato: f }))}
        onCoger={() => {}}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
