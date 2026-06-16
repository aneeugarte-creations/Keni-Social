/**
 * Test de la pestaña «Contexto» del editor de un prompt: lista los editoriales que inyecta para la
 * marca elegida, y muestra estado vacío cuando el prompt no inyecta contexto.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PanelContextoInyectado } from "./PanelContextoInyectado";

const marcasPrompts = vi.fn();
const contextoInyectado = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    marcasPrompts: (...a: unknown[]) => marcasPrompts(...a),
    contextoInyectado: (...a: unknown[]) => contextoInyectado(...a),
    // Lo usa EditorPromptOverlay si se abriera (no en este test).
    maquinaPrompts: vi.fn().mockResolvedValue({ maquinas: [] }),
  },
  mensajeError: (e: unknown) => String(e),
}));

function renderPanel(docId: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PanelContextoInyectado docId={docId} />
    </QueryClientProvider>,
  );
}

describe("PanelContextoInyectado", () => {
  it("lista los editoriales que inyecta el prompt para la marca", async () => {
    marcasPrompts.mockResolvedValue({ marcas: [{ id: "unotv", nombre: "UnoTV" }] });
    contextoInyectado.mockResolvedValue({
      prompt_id: "prompt/redactar",
      inyecta: true,
      pipeline: "redactar",
      marca: "unotv",
      adjuntos: [
        { id: "editorial/rrss/unotv/marca", titulo: "Identidad · UnoTV", clase: "marca", prioridad: 0 },
        { id: "editorial/rrss/unotv/voz", titulo: "Voz y tono · UnoTV", clase: "voz", prioridad: 1 },
      ],
    });
    renderPanel("prompt/redactar");
    expect(await screen.findByText("Identidad · UnoTV")).toBeInTheDocument();
    expect(screen.getByText("Voz y tono · UnoTV")).toBeInTheDocument();
  });

  it("muestra estado vacío cuando el prompt no inyecta contexto", async () => {
    marcasPrompts.mockResolvedValue({ marcas: [{ id: "unotv", nombre: "UnoTV" }] });
    contextoInyectado.mockResolvedValue({
      prompt_id: "prompt/asistente/resumir",
      inyecta: false,
      pipeline: null,
      marca: "unotv",
      adjuntos: [],
    });
    renderPanel("prompt/asistente/resumir");
    await waitFor(() =>
      expect(screen.getByText("Este prompt no inyecta contexto editorial.")).toBeInTheDocument(),
    );
  });
});
