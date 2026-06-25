import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Conversacion, ConversacionesPorRed } from "@/types";

import { PanelConversaciones } from "./PanelConversaciones";

function conversacion(over: Partial<Conversacion> = {}): Conversacion {
  return {
    id: "c-1",
    red: "facebook",
    pendiente: true,
    creado: "2026-06-20T10:00:00-06:00",
    actualizado: "2026-06-20T12:30:00-06:00",
    participantes: [{ id: "aud-1", nombre: "Ana Audiencia", avatar: null }],
    mensajes: [
      { id: "m-1", autor_id: "aud-1", texto: "Hola, ¿precio?", fecha: "2026-06-20T12:00:00-06:00", adjuntos: 0 },
      { id: "m-2", autor_id: "pagina", texto: "Te paso info", fecha: "2026-06-20T12:30:00-06:00", adjuntos: 2 },
    ],
    ...over,
  };
}

describe("PanelConversaciones", () => {
  it("pinta la conversación con red, audiencia, badge pendiente y contador de adjuntos", () => {
    const porRed: ConversacionesPorRed[] = [
      { red: "facebook", conversaciones: [conversacion()] },
    ];
    render(<PanelConversaciones porRed={porRed} />);
    expect(screen.getByText("Facebook")).toBeInTheDocument();
    expect(screen.getByText("Ana Audiencia")).toBeInTheDocument();
    expect(screen.getByText("Pendiente")).toBeInTheDocument();
    expect(screen.getByText("Hola, ¿precio?")).toBeInTheDocument();
    expect(screen.getByText("2 adjuntos")).toBeInTheDocument();
  });

  it("no muestra el badge pendiente cuando la conversación no lo está", () => {
    const porRed: ConversacionesPorRed[] = [
      { red: "instagram", conversaciones: [conversacion({ pendiente: false })] },
    ];
    render(<PanelConversaciones porRed={porRed} />);
    expect(screen.queryByText("Pendiente")).not.toBeInTheDocument();
    expect(screen.getByText("Instagram")).toBeInTheDocument();
  });

  it("muestra el estado vacío cuando no hay redes con datos", () => {
    render(<PanelConversaciones porRed={[]} />);
    expect(screen.getByText("Sin mensajes directos")).toBeInTheDocument();
  });

  it("ignora una red sin conversaciones", () => {
    const porRed: ConversacionesPorRed[] = [
      { red: "facebook", conversaciones: [] },
      { red: "instagram", conversaciones: [conversacion({ red: "instagram" })] },
    ];
    render(<PanelConversaciones porRed={porRed} />);
    expect(screen.queryByText("Facebook")).not.toBeInTheDocument();
    expect(screen.getByText("Instagram")).toBeInTheDocument();
  });
});
