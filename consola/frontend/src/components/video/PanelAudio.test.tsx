/** Tests del PanelAudio: separar el audio del base (volumen/silenciar) y añadir/quitar música. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";

import { PanelAudio } from "./PanelAudio";
import { composicionVacia, setClipBase, setMusica } from "@/lib/video";

function docBase() {
  return setClipBase(composicionVacia("9:16", "unotv"), "videos/abc.mp4", 30000);
}

/** `EditorVideo` (uploader de música) usa react-query: hace falta un QueryClientProvider. */
function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function renderPanel(ui: React.ReactElement) {
  return render(ui, { wrapper: Wrapper });
}

describe("PanelAudio", () => {
  it("silenciar el audio base llama onAudioBase({ silenciar: true })", () => {
    const onAudioBase = vi.fn();
    renderPanel(
      <PanelAudio
        doc={docBase()}
        musicaUrl=""
        onAudioBase={onAudioBase}
        onCambioMusica={vi.fn()}
        onVolumenMusica={vi.fn()}
        onQuitarMusica={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /silenciar audio base/i }));
    expect(onAudioBase).toHaveBeenCalledWith({ silenciar: true });
  });

  it("ajustar el volumen base llama onAudioBase con el volumen 0..1", () => {
    const onAudioBase = vi.fn();
    renderPanel(
      <PanelAudio
        doc={docBase()}
        musicaUrl=""
        onAudioBase={onAudioBase}
        onCambioMusica={vi.fn()}
        onVolumenMusica={vi.fn()}
        onQuitarMusica={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText("Volumen del audio base"), { target: { value: "0.4" } });
    expect(onAudioBase).toHaveBeenCalledWith({ volumen: 0.4 });
  });

  it("sin música ofrece subirla; con música ofrece quitarla", () => {
    const onQuitarMusica = vi.fn();
    const { rerender } = renderPanel(
      <PanelAudio
        doc={docBase()}
        musicaUrl=""
        onAudioBase={vi.fn()}
        onCambioMusica={vi.fn()}
        onVolumenMusica={vi.fn()}
        onQuitarMusica={onQuitarMusica}
      />,
    );
    // Sin música: zona de subida (EditorVideo compacto) y SIN botón de quitar.
    expect(screen.getByRole("button", { name: /subir video/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /quitar música/i })).not.toBeInTheDocument();

    const conMusica = setMusica(docBase(), "videos/m.mp3", 12000);
    rerender(
      <PanelAudio
        doc={conMusica}
        musicaUrl="/api/media/videos/m.mp3"
        onAudioBase={vi.fn()}
        onCambioMusica={vi.fn()}
        onVolumenMusica={vi.fn()}
        onQuitarMusica={onQuitarMusica}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /quitar música/i }));
    expect(onQuitarMusica).toHaveBeenCalled();
  });
});
