import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Comentario, ComentariosPorRed } from "@/types";

import { PanelComentarios } from "./PanelComentarios";

function comentario(over: Partial<Comentario> = {}): Comentario {
  return {
    id: "co-1",
    red: "instagram",
    pendiente: true,
    autor: { id: "aud-1", nombre: "Beto Fan", avatar: null },
    texto: "Gran jugada",
    fecha: "2026-06-20T12:00:00-06:00",
    permalink: "https://instagram.com/p/abc/comment/1",
    post_id: "p-1",
    post_texto: "Resumen del partido de anoche con todos los goles y las mejores jugadas",
    post_enlace: "https://instagram.com/p/abc",
    post_media: ["https://cdn/thumb.jpg"],
    respuestas: [
      {
        id: "r-1",
        autor: { id: "aud-2", nombre: "Caro", avatar: null },
        texto: "Totalmente",
        fecha: "2026-06-20T12:10:00-06:00",
        pendiente: false,
      },
    ],
    ...over,
  };
}

describe("PanelComentarios", () => {
  it("pinta autor, texto, contexto de la publicación, enlaces y respuestas", () => {
    const porRed: ComentariosPorRed[] = [
      { red: "instagram", comentarios: [comentario()] },
    ];
    render(<PanelComentarios porRed={porRed} />);
    expect(screen.getByText("Instagram")).toBeInTheDocument();
    expect(screen.getByText("Beto Fan")).toBeInTheDocument();
    expect(screen.getByText("Gran jugada")).toBeInTheDocument();
    expect(screen.getByText("Pendiente")).toBeInTheDocument();
    // Contexto de la publicación: enlace y miniatura.
    expect(screen.getByText("Ver publicación").closest("a")).toHaveAttribute(
      "href",
      "https://instagram.com/p/abc",
    );
    expect(screen.getByText("Ver comentario").closest("a")).toHaveAttribute(
      "href",
      "https://instagram.com/p/abc/comment/1",
    );
    // Respuesta anidada.
    expect(screen.getByText("Caro")).toBeInTheDocument();
    expect(screen.getByText("Totalmente")).toBeInTheDocument();
  });

  it("cae a un placeholder cuando la miniatura de la publicación falla al cargar", () => {
    const { container } = render(
      <PanelComentarios porRed={[{ red: "instagram", comentarios: [comentario()] }]} />,
    );
    const miniatura = screen.getByAltText("Publicación comentada");
    fireEvent.error(miniatura);
    expect(screen.queryByAltText("Publicación comentada")).not.toBeInTheDocument();
    expect(container.querySelector(".lucide-image")).toBeInTheDocument();
  });

  it("muestra el placeholder cuando la publicación no trae miniatura (post_media vacío)", () => {
    const { container } = render(
      <PanelComentarios
        porRed={[{ red: "instagram", comentarios: [comentario({ post_media: [] })] }]}
      />,
    );
    expect(screen.queryByAltText("Publicación comentada")).not.toBeInTheDocument();
    expect(container.querySelector(".lucide-image")).toBeInTheDocument();
  });

  it("muestra el estado vacío cuando no hay redes con datos", () => {
    render(<PanelComentarios porRed={[]} />);
    expect(screen.getByText("Sin comentarios")).toBeInTheDocument();
  });

  it("degrada un comentario sin autor ni respuestas", () => {
    const porRed: ComentariosPorRed[] = [
      {
        red: "facebook",
        comentarios: [
          comentario({ autor: null, respuestas: [], pendiente: false, post_media: [] }),
        ],
      },
    ];
    render(<PanelComentarios porRed={porRed} />);
    expect(screen.getByText("Sin nombre")).toBeInTheDocument();
    expect(screen.queryByText("Pendiente")).not.toBeInTheDocument();
  });
});
