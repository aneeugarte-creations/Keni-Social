/**
 * Test de la pestaña «Editorial» del editor de un prompt: lista los editoriales que inyecta para la
 * marca ACTIVA (selector global), y muestra estado vacío cuando el prompt no inyecta contexto.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MarcaActivaContexto, type ValorMarcaActiva } from "@/hooks/marca-activa-contexto";

import { PanelContextoInyectado } from "./PanelContextoInyectado";

const contextoInyectado = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    contextoInyectado: (...a: unknown[]) => contextoInyectado(...a),
    // Lo usa EditorPromptOverlay si se abriera (no en este test).
    maquinaPrompts: vi.fn().mockResolvedValue({ maquinas: [] }),
  },
  mensajeError: (e: unknown) => String(e),
}));

function valorMarcaActiva(marca: string | null): ValorMarcaActiva {
  return {
    marcaActiva: marca,
    marcaPrimaria: marca,
    enMarcaPrimaria: true,
    esMultiMarca: true,
    puedeTodas: true,
    marcasParaSwitch: [],
    nombreActiva: null,
    cambiarMarca: () => {},
    volverAPrimaria: () => {},
  };
}

function renderPanel(docId: string, marca: string | null = "unotv") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MarcaActivaContexto.Provider value={valorMarcaActiva(marca)}>
        <PanelContextoInyectado docId={docId} />
      </MarcaActivaContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("PanelContextoInyectado", () => {
  it("lista los editoriales que inyecta el prompt para la marca activa", async () => {
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
    // La marca activa global se usa SIN selector propio.
    expect(contextoInyectado).toHaveBeenCalledWith("prompt/redactar", "unotv", expect.anything());
  });

  it("muestra estado vacío cuando el prompt no inyecta contexto", async () => {
    contextoInyectado.mockResolvedValue({
      prompt_id: "prompt/idear",
      inyecta: false,
      pipeline: null,
      marca: "unotv",
      adjuntos: [],
    });
    renderPanel("prompt/idear");
    await waitFor(() =>
      expect(screen.getByText("Este prompt no inyecta contexto editorial.")).toBeInTheDocument(),
    );
  });
});
