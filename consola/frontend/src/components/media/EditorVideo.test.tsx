/**
 * Tests para EditorVideo (Ola F): zona de upload de video para piezas de tipo video.
 *
 * - Renderiza zona de upload cuando no hay video.
 * - Llama a `subirVideo` al seleccionar un archivo (via fetch stub).
 * - Muestra el reproductor <video> cuando hay URL.
 * - Botón quitar llama a onCambio("", "").
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EditorVideo } from "./EditorVideo";

/** Respuesta de subirVideo */
const MEDIA_RESP = { id: "vid-001", url: "/api/media/vid-001" };

function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(MEDIA_RESP), { status: 200 })),
  );
}

function renderEditor(props: Partial<React.ComponentProps<typeof EditorVideo>> = {}) {
  const onCambio = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <EditorVideo
        video={props.video ?? ""}
        videoUrl={props.videoUrl}
        onCambio={props.onCambio ?? onCambio}
        disabled={props.disabled}
        idPrefijo={props.idPrefijo ?? "vid-test"}
        red={props.red}
      />
    </QueryClientProvider>,
  );
  return { onCambio };
}

describe("EditorVideo · Ola F", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sin video muestra zona de upload con botón 'Subir video'", () => {
    renderEditor({ video: "" });
    expect(screen.getByText(/Subir video/i)).toBeInTheDocument();
    expect(screen.queryByRole("main")).not.toBeInTheDocument();
  });

  it("con videoUrl muestra el reproductor <video>", () => {
    renderEditor({ video: "clip.mp4", videoUrl: "/api/media/clip.mp4" });
    const video = screen.getByLabelText(/previsualización del video/i);
    expect(video).toBeInTheDocument();
    expect(video).toHaveAttribute("src", "/api/media/clip.mp4");
  });

  it("al seleccionar archivo llama a POST /api/media/video y notifica onCambio", async () => {
    stubFetch();
    const { onCambio } = renderEditor({ video: "" });

    const input = document.querySelector<HTMLInputElement>("input[type='file']");
    expect(input).not.toBeNull();
    const archivo = new File(["x"], "test.mp4", { type: "video/mp4" });
    fireEvent.change(input!, { target: { files: [archivo] } });

    await waitFor(() => expect(onCambio).toHaveBeenCalled());
    const llamada = onCambio.mock.calls[0] as [string, string];
    expect(llamada[0]).toBe("vid-001");
    expect(llamada[1]).toBe("/api/media/vid-001");

    // Verifica que se llamó a la ruta correcta
    const fetchMock = vi.mocked(fetch);
    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toContain("/api/media/video");
  });

  it("botón quitar llama a onCambio('', '')", () => {
    const onCambio = vi.fn();
    renderEditor({ video: "clip.mp4", videoUrl: "/api/media/clip.mp4", onCambio });

    // Con kebab="nunca" las acciones viven en el menú contextual de la preview.
    const preview = screen.getByLabelText(/previsualización del video/i);
    fireEvent.contextMenu(preview);

    const menuItemQuitar = screen.getByRole("menuitem", { name: /quitar video/i });
    fireEvent.click(menuItemQuitar);

    expect(onCambio).toHaveBeenCalledWith("", "");
  });

  it("muestra sugerencia de límite para la red dada", () => {
    renderEditor({ video: "", red: "tiktok" });
    // El límite de TikTok contiene "287 MB" (ver LIMITES_VIDEO).
    expect(screen.getByText(/287 MB/i)).toBeInTheDocument();
  });
});
