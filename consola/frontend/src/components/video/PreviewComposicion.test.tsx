/**
 * Tests del PLAYER del preview de composición (PreviewComposicion):
 *  - Sin clip base: placeholder y SIN controles de reproducción.
 *  - Play/pausa: el botón llama a `video.play()`/`pause()` y refleja el estado vía eventos.
 *  - El reloj usa la duración del documento como fallback y la real al cargar metadatos.
 *  - Los subtítulos siguen el tiempo actual (`timeupdate`): el segmento activo se pinta en su
 *    ventana y desaparece fuera de ella.
 *  - Scrubbing: pointer down sobre la barra busca (seek) a la fracción correspondiente.
 *  - Espacio = play/pausa global, salvo foco en un campo editable o `atajoEspacio` apagado.
 *
 * jsdom no implementa HTMLMediaElement.play/pause: se mockean en el prototipo despachando los
 * eventos `play`/`pause` reales (los mismos que dispararía el navegador).
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { composicionVacia, setClipBase, type ComposicionVideo, type SegmentoSub } from "@/lib/video";

import { PreviewComposicion, type PreviewPlayerHandle } from "./PreviewComposicion";

function docConBase(duracionMs = 30000): ComposicionVideo {
  return setClipBase(composicionVacia("9:16", "unotv"), "videos/abc.mp4", duracionMs);
}

const SEGMENTOS: SegmentoSub[] = [{ id: "s1", inicio: 1, fin: 2, texto: "Hola México" }];

describe("PreviewComposicion (player)", () => {
  let playMock: ReturnType<typeof vi.fn>;
  let pauseMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    playMock = vi.fn(function (this: HTMLMediaElement) {
      this.dispatchEvent(new Event("play"));
      return Promise.resolve();
    });
    pauseMock = vi.fn(function (this: HTMLMediaElement) {
      this.dispatchEvent(new Event("pause"));
    });
    vi.spyOn(window.HTMLMediaElement.prototype, "play").mockImplementation(
      playMock as unknown as () => Promise<void>,
    );
    vi.spyOn(window.HTMLMediaElement.prototype, "pause").mockImplementation(
      pauseMock as unknown as () => void,
    );
  });

  afterEach(() => vi.restoreAllMocks());

  it("sin clip base muestra el placeholder y NO los controles", () => {
    render(<PreviewComposicion doc={composicionVacia("9:16", "unotv")} />);
    expect(screen.getByText(/sube un video base/i)).toBeInTheDocument();
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /reproducir/i })).not.toBeInTheDocument();
  });

  it("el botón reproduce y pausa, reflejando el estado vía eventos del <video>", async () => {
    render(<PreviewComposicion doc={docConBase()} baseUrl="videos/abc.mp4" />);
    fireEvent.click(screen.getByRole("button", { name: "Reproducir" }));
    expect(playMock).toHaveBeenCalledTimes(1);
    // El evento `play` (despachado por el mock) pasa el estado a "reproduciendo".
    const pausar = await screen.findByRole("button", { name: "Pausar" });
    fireEvent.click(pausar);
    expect(pauseMock).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("button", { name: "Reproducir" })).toBeInTheDocument();
  });

  it("el reloj cae a la duración del documento y adopta la real al cargar metadatos", () => {
    const { container } = render(<PreviewComposicion doc={docConBase(30000)} baseUrl="videos/abc.mp4" />);
    const barra = screen.getByRole("slider", { name: /posición de reproducción/i });
    expect(barra).toHaveAttribute("aria-valuetext", "00:00 de 00:30");
    // Metadatos reales: 45 s (jsdom expone `duration` solo-lectura; se redefine en la instancia).
    const video = container.querySelector("video")!;
    Object.defineProperty(video, "duration", { value: 45, configurable: true });
    fireEvent(video, new Event("loadedmetadata"));
    expect(barra).toHaveAttribute("aria-valuetext", "00:00 de 00:45");
  });

  it("pinta el subtítulo activo SINCRONIZADO con el tiempo del video (timeupdate)", () => {
    const { container } = render(
      <PreviewComposicion doc={docConBase()} baseUrl="videos/abc.mp4" segmentos={SEGMENTOS} />,
    );
    // En t=0 el segmento (1s–2s) NO está activo.
    expect(screen.queryByText("Hola México")).not.toBeInTheDocument();
    const video = container.querySelector("video")!;
    video.currentTime = 1.5;
    fireEvent(video, new Event("timeupdate"));
    expect(screen.getByText("Hola México")).toBeInTheDocument();
    // Y desaparece al salir de su ventana.
    video.currentTime = 3;
    fireEvent(video, new Event("timeupdate"));
    expect(screen.queryByText("Hola México")).not.toBeInTheDocument();
  });

  it("scrubbing: mousedown sobre la barra busca, y arrastrar sigue buscando", () => {
    const { container } = render(<PreviewComposicion doc={docConBase(30000)} baseUrl="videos/abc.mp4" />);
    const barra = screen.getByRole("slider", { name: /posición de reproducción/i });
    vi.spyOn(barra, "getBoundingClientRect").mockReturnValue({
      left: 0,
      top: 0,
      width: 100,
      height: 4,
      right: 100,
      bottom: 4,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect);
    fireEvent.mouseDown(barra, { clientX: 50 });
    const video = container.querySelector("video")!;
    // 50% de 30 s = 15 s.
    expect(video.currentTime).toBeCloseTo(15, 5);
    expect(barra).toHaveAttribute("aria-valuenow", "15");
    // Arrastre: el move va a window (no se pierde el gesto al salir de la barra).
    fireEvent.mouseMove(window, { clientX: 75 });
    expect(video.currentTime).toBeCloseTo(22.5, 5);
    // Al soltar, mover el ratón ya no busca.
    fireEvent.mouseUp(window);
    fireEvent.mouseMove(window, { clientX: 10 });
    expect(video.currentTime).toBeCloseTo(22.5, 5);
  });

  it("las flechas sobre la barra buscan ±5 s (accesibilidad de teclado)", () => {
    const { container } = render(<PreviewComposicion doc={docConBase(30000)} baseUrl="videos/abc.mp4" />);
    const barra = screen.getByRole("slider", { name: /posición de reproducción/i });
    fireEvent.keyDown(barra, { key: "ArrowRight" });
    const video = container.querySelector("video")!;
    expect(video.currentTime).toBeCloseTo(5, 5);
    fireEvent.keyDown(barra, { key: "ArrowLeft" });
    expect(video.currentTime).toBeCloseTo(0, 5);
  });

  it("Espacio = play/pausa salvo que el foco esté en un campo editable", () => {
    render(
      <>
        <input aria-label="campo" />
        <PreviewComposicion doc={docConBase()} baseUrl="videos/abc.mp4" />
      </>,
    );
    // Con el foco en un input NO se dispara.
    fireEvent.keyDown(screen.getByLabelText("campo"), { code: "Space" });
    expect(playMock).not.toHaveBeenCalled();
    // Sobre el body sí.
    fireEvent.keyDown(document.body, { code: "Space" });
    expect(playMock).toHaveBeenCalledTimes(1);
  });

  it("con `atajoEspacio` apagado, Espacio no hace nada (lo usa otro editor, p. ej. el Lienzo)", () => {
    render(<PreviewComposicion doc={docConBase()} baseUrl="videos/abc.mp4" atajoEspacio={false} />);
    fireEvent.keyDown(document.body, { code: "Space" });
    expect(playMock).not.toHaveBeenCalled();
  });

  it("notifica el reloj (onTiempo) y la duración (onDuracion), y expone buscarA vía playerRef", () => {
    const onTiempo = vi.fn();
    const onDuracion = vi.fn();
    const ref = React.createRef<PreviewPlayerHandle>();
    const { container } = render(
      <PreviewComposicion
        doc={docConBase(30000)}
        baseUrl="videos/abc.mp4"
        playerRef={ref}
        onTiempo={onTiempo}
        onDuracion={onDuracion}
      />,
    );
    const video = container.querySelector("video")!;
    // El reloj del player fluye hacia fuera (alimenta el playhead del timeline).
    video.currentTime = 7;
    fireEvent(video, new Event("timeupdate"));
    expect(onTiempo).toHaveBeenLastCalledWith(7);
    // La duración real fluye al cargar metadatos.
    Object.defineProperty(video, "duration", { value: 45, configurable: true });
    fireEvent(video, new Event("loadedmetadata"));
    expect(onDuracion).toHaveBeenLastCalledWith(45);
    // Y el mando externo busca en el MISMO player (sin duplicarlo).
    act(() => ref.current!.buscarA(12));
    expect(video.currentTime).toBeCloseTo(12, 5);
    expect(onTiempo).toHaveBeenLastCalledWith(12);
  });
});
