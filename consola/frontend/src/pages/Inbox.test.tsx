/**
 * Tests de la página Inbox (buzón de SOLO lectura).
 *
 * Cubre: sin marca concreta pide enfocar una; con marca activa carga los DMs (y traduce la
 * marca a id_metricas), conmuta a la pestaña de comentarios y los carga con su periodo.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  MarcaActivaContexto,
  type ValorMarcaActiva,
} from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";
import type { RespuestaInboxComentarios, RespuestaInboxConversaciones } from "@/types";

import Inbox from "./Inbox";

function valorMarca(marcaActiva: string | null): ValorMarcaActiva {
  return {
    marcaActiva,
    marcaPrimaria: marcaActiva,
    enMarcaPrimaria: true,
    esMultiMarca: false,
    puedeTodas: false,
    marcasParaSwitch: [],
    nombreActiva: marcaActiva === "claro-sports" ? "Claro Sports" : marcaActiva,
    cambiarMarca: vi.fn(),
    volverAPrimaria: vi.fn(),
  };
}

function renderConProviders(marcaActiva: string | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MarcaActivaContexto.Provider value={valorMarca(marcaActiva)}>
        <MemoryRouter>
          <Inbox />
        </MemoryRouter>
      </MarcaActivaContexto.Provider>
    </QueryClientProvider>,
  );
}

const CONVERSACIONES: RespuestaInboxConversaciones = {
  por_red: [
    {
      red: "facebook",
      conversaciones: [
        {
          id: "c-1",
          red: "facebook",
          pendiente: true,
          creado: "2026-06-20T10:00:00-06:00",
          actualizado: "2026-06-20T12:00:00-06:00",
          participantes: [{ id: "aud-1", nombre: "Ana Audiencia", avatar: null }],
          mensajes: [
            { id: "m-1", autor_id: "aud-1", texto: "Hola", fecha: "2026-06-20T12:00:00-06:00", adjuntos: [] },
          ],
        },
      ],
    },
  ],
  generado_en: "2026-06-20T12:05:00-06:00",
};

const COMENTARIOS: RespuestaInboxComentarios = {
  por_red: [
    {
      red: "instagram",
      comentarios: [
        {
          id: "co-1",
          red: "instagram",
          pendiente: false,
          autor: { id: "aud-9", nombre: "Beto Fan", avatar: null },
          texto: "Buen contenido",
          fecha: "2026-06-20T11:00:00-06:00",
          permalink: "https://instagram.com/p/x/c/1",
          post_id: "p-1",
          post_texto: "El post",
          post_enlace: "https://instagram.com/p/x",
          post_media: [],
          respuestas: [],
        },
      ],
    },
  ],
  dias: 7,
  generado_en: "2026-06-20T12:05:00-06:00",
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Inbox", () => {
  it("pide enfocar una marca cuando el switch global está en 'Todas'", () => {
    renderConProviders(null);
    expect(screen.getByText("Elige una marca")).toBeInTheDocument();
  });

  it("carga los DMs de la marca activa traduciendo a id_metricas", async () => {
    const dms = vi
      .spyOn(api, "inboxConversaciones")
      .mockResolvedValue(CONVERSACIONES);
    vi.spyOn(api, "inboxComentarios").mockResolvedValue(COMENTARIOS);

    renderConProviders("claro-sports");

    expect(screen.getByRole("tab", { name: /Mensajes directos/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Ana Audiencia")).toBeInTheDocument());
    expect(dms).toHaveBeenCalledWith(
      { marca: "claro_sports" },
      expect.anything(),
    );
  });

  it("conmuta a comentarios y los carga con su periodo", async () => {
    vi.spyOn(api, "inboxConversaciones").mockResolvedValue(CONVERSACIONES);
    const coment = vi.spyOn(api, "inboxComentarios").mockResolvedValue(COMENTARIOS);

    renderConProviders("claro-sports");
    // Radix Tabs conmuta en `mouseDown` (modo de activación automática), no en el click sintético.
    const tabComentarios = screen.getByRole("tab", { name: /Comentarios/ });
    fireEvent.mouseDown(tabComentarios);
    fireEvent.click(tabComentarios);

    await waitFor(() => expect(screen.getByText("Beto Fan")).toBeInTheDocument());
    expect(coment).toHaveBeenCalledWith(
      { marca: "claro_sports", dias: "7" },
      expect.anything(),
    );
  });
});
