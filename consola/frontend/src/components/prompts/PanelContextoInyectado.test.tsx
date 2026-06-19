/**
 * Test de la lista de editoriales que inyecta un prompt (sección «Editorial» de la pestaña
 * «Acompaña»): lista los editoriales para la marca ACTIVA (selector global), muestra estado vacío
 * cuando el prompt no inyecta, y clicar una fila llama a `onAbrirDoc` (abre su subpágina).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MarcaActivaContexto, type ValorMarcaActiva } from "@/hooks/marca-activa-contexto";

import { PanelContextoInyectado } from "./PanelContextoInyectado";

const contextoInyectado = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    contextoInyectado: (...a: unknown[]) => contextoInyectado(...a),
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
  const onAbrirDoc = vi.fn();
  const utils = render(
    <QueryClientProvider client={qc}>
      <MarcaActivaContexto.Provider value={valorMarcaActiva(marca)}>
        <PanelContextoInyectado docId={docId} onAbrirDoc={onAbrirDoc} />
      </MarcaActivaContexto.Provider>
    </QueryClientProvider>,
  );
  return { ...utils, onAbrirDoc };
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

  it("clicar una fila llama a onAbrirDoc con el id del editorial (abre su subpágina)", async () => {
    contextoInyectado.mockResolvedValue({
      prompt_id: "prompt/redactar",
      inyecta: true,
      pipeline: "redactar",
      marca: "unotv",
      adjuntos: [
        { id: "editorial/rrss/unotv/voz", titulo: "Voz y tono · UnoTV", clase: "voz", prioridad: 0 },
      ],
    });
    const { onAbrirDoc } = renderPanel("prompt/redactar");
    fireEvent.click(await screen.findByText("Voz y tono · UnoTV"));
    expect(onAbrirDoc).toHaveBeenCalledWith("editorial/rrss/unotv/voz");
  });
});
