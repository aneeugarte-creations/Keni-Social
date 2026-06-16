import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PanelAcerca } from "./PanelAcerca";
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
      ],
    },
  ],
};

describe("PanelAcerca", () => {
  it("explica en prosa qué es una pieza editorial y avisa si no está cableada", () => {
    render(<PanelAcerca doc={doc()} />);
    expect(screen.getByText(/pieza editorial/)).toBeInTheDocument();
    expect(screen.getByText(/No está cableado a ningún flujo/)).toBeInTheDocument();
  });

  it("redacta la descripción y dónde se inyecta el documento", () => {
    render(
      <PanelAcerca
        doc={doc({
          descripcion: "Define el tono de UnoTV.",
          procesos: ["copy_diario"],
          pipelines: ["produccion"],
          rol: "copy",
        })}
        maquina={maquina}
      />,
    );
    expect(screen.getByText("Define el tono de UnoTV.")).toBeInTheDocument();
    expect(screen.getByText(/Se inyecta en el proceso copy_diario/)).toBeInTheDocument();
    expect(screen.getByText(/Redacción \(Producción\)/)).toBeInTheDocument();
    expect(screen.getByText(/pipeline produccion/)).toBeInTheDocument();
    expect(screen.getByText(/rol «copy»/)).toBeInTheDocument();
  });

  it("describe un prompt como instrucciones para el modelo", () => {
    render(<PanelAcerca doc={doc({ tipo: "prompt" })} />);
    expect(screen.getByText(/Es un prompt/)).toBeInTheDocument();
  });
});
