/**
 * Tests de la pista BASE:
 *  - Con clip muestra la duración del clip y de la composición en mm:ss.
 *  - Duración aún desconocida (0 ms) se muestra como "—" (el render la recalcula).
 *  - Sin clip no hay línea de duraciones ni controles de reencuadre.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { composicionVacia, setClipBase } from "@/lib/video";

import { PistaBase } from "./PistaBase";

function renderPista(duracionMs: number | null) {
  const vacia = composicionVacia("9:16", "unotv");
  const doc = duracionMs === null ? vacia : setClipBase(vacia, "videos/abc.mp4", duracionMs);
  // EditorVideo (la zona de subida embebida) usa useMutation: necesita el provider.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PistaBase
        doc={doc}
        videoKey={duracionMs === null ? "" : "videos/abc.mp4"}
        videoUrl=""
        onCambioVideo={vi.fn()}
        onReencuadre={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

describe("PistaBase", () => {
  it("muestra la duración del clip base y de la composición (mm:ss)", () => {
    renderPista(30000);
    expect(screen.getByText(/clip:/i)).toBeInTheDocument();
    expect(screen.getByText(/composición:/i)).toBeInTheDocument();
    // Clip de 30 s y composición de 30 s.
    expect(screen.getAllByText("00:30")).toHaveLength(2);
  });

  it("duración desconocida (0 ms) se muestra como '—'", () => {
    renderPista(0);
    expect(screen.getAllByText("—")).toHaveLength(2);
  });

  it("sin clip base no muestra duraciones ni reencuadre", () => {
    renderPista(null);
    expect(screen.queryByText(/clip:/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/reencuadre/i)).not.toBeInTheDocument();
  });
});
