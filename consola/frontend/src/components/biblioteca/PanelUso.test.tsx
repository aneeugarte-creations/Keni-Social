import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PanelUso } from "./PanelUso";
import type { DocumentoTexto, RespuestaMaquinaTexto } from "@/types";

function doc(parcial: Partial<DocumentoTexto> = {}): DocumentoTexto {
  return {
    id: "doc-1",
    titulo: "Voz de marca",
    tipo: "voz",
    carpeta: "",
    cuerpo: "",
    creado: "2026-01-01T00:00:00",
    actualizado: "2026-01-01T00:00:00",
    clase: "voz",
    marcas: [],
    ...parcial,
  };
}

const maquina: RespuestaMaquinaTexto = {
  maquinas: [
    {
      id: "produccion",
      titulo: "Producción",
      subtitulo: "",
      etapas: [
        { tipo: "mecanica", id: "m1", titulo: "Ingesta" },
        {
          tipo: "prompt",
          id: "e1",
          titulo: "Redacción",
          doc_id: "doc-1",
          produccion: null,
          sha_actual: null,
          sin_publicar: false,
        },
        {
          tipo: "prompt",
          id: "e2",
          titulo: "Otra",
          doc_id: "otro",
          produccion: null,
          sha_actual: null,
          sin_publicar: false,
        },
      ],
    },
  ],
};

describe("PanelUso", () => {
  it("muestra el estado vacío cuando no está cableado a nada", () => {
    render(<PanelUso doc={doc()} />);
    expect(screen.getByText(/No está cableado a ningún flujo/)).toBeInTheDocument();
  });

  it("lista procesos, pipelines con rol y la etapa de la máquina", () => {
    render(
      <PanelUso
        doc={doc({ procesos: ["copy_diario"], pipelines: ["produccion"], rol: "copy" })}
        maquina={maquina}
      />,
    );
    expect(screen.getByText("copy_diario")).toBeInTheDocument();
    expect(screen.getByText("rol: copy")).toBeInTheDocument();
    expect(screen.getByText("produccion")).toBeInTheDocument();
    // Solo la etapa cuyo doc_id coincide con el documento.
    expect(screen.getByText("Producción")).toBeInTheDocument();
    expect(screen.getByText("Redacción")).toBeInTheDocument();
    expect(screen.queryByText("Otra")).not.toBeInTheDocument();
    expect(screen.queryByText(/No está cableado/)).not.toBeInTheDocument();
  });
});
