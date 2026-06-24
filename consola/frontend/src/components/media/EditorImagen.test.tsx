/**
 * REEMPLAZO de imagen en el editor sin marca: elegir un ARTE de la galería DECLARA el origen propio
 * ("galeria") a través de `onCambio`. El padre (DialogoEditar) lo manda como `imagen_origen` al
 * guardar para que el back LIMPIE el metadato de licencia heredado de la foto anterior.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { Arte, RespuestaArtes } from "@/types";

import { EditorImagen } from "./EditorImagen";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function arte(over: Partial<Arte> = {}): Arte {
  return {
    id: "a1",
    objeto: "galeria/arte.png",
    url: "https://media.example/galeria/arte.png",
    marca: "",
    marca_nombre: "",
    tipo: "subida",
    titulo: "Mi arte",
    etiquetas: [],
    creado: "2026-01-01T00:00:00Z",
    ...over,
  };
}

function renderEditor(artes: Arte[]) {
  vi.spyOn(api, "listarArtes").mockResolvedValue({ artes } as RespuestaArtes);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onCambio = vi.fn();
  render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <EditorImagen imagen="" onCambio={onCambio} idPrefijo="t" piezaId="p1" />
      </QueryClientProvider>
    </MemoryRouter>,
  );
  return { onCambio };
}

describe("EditorImagen · REEMPLAZO declara origen propio", () => {
  it("elegir un arte de galería llama a onCambio con origen 'galeria'", async () => {
    const { onCambio } = renderEditor([arte()]);

    // Abre la galería de artes.
    fireEvent.click(screen.getByRole("button", { name: /galería/i }));
    // Elige el arte: la tarjeta (host de `FilaConAcciones`, role=button) envuelve la imagen.
    const img = await screen.findByAltText("Mi arte");
    fireEvent.click(img.closest('[role="button"]')!);

    await vi.waitFor(() => expect(onCambio).toHaveBeenCalled());
    expect(onCambio).toHaveBeenCalledWith(
      "galeria/arte.png",
      "https://media.example/galeria/arte.png",
      "galeria",
    );
  });
});
