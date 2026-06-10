/**
 * Tests de la línea de tiempo del Estudio de Video (LineaTiempo):
 *  - Sin clip base no renderiza nada (no hay qué cronometrar).
 *  - Regla con marcas de tiempo y tarjeta del clip con ancho ∝ duración recortada.
 *  - Playhead accesible (role=slider): flechas ±1 s, Shift ±5 s.
 *  - Mousedown/arrastre sobre la banda = seek a la fracción del puntero (scrub).
 *  - Asas de trim: arrastrar fija recorte_in/out_ms (commit al SOLTAR vía onRecorte, con
 *    etiqueta mm:ss viva durante el gesto y salto del preview al borde), mínimo 1 s.
 *  - `disabled` apaga el trim (las asas no recortan); el seek sigue activo.
 *  - PiP y subtítulos aparecen como barras finas solo-lectura.
 *
 * jsdom no tiene layout: las posiciones se asertan por estilo (% sobre el eje) y los gestos
 * mockean `getBoundingClientRect` de la banda.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  composicionVacia,
  setClipBase,
  setClipPip,
  setRecorteBase,
  type ComposicionVideo,
  type SegmentoSub,
} from "@/lib/video";

import { LineaTiempo } from "./LineaTiempo";

function doc30(): ComposicionVideo {
  return setClipBase(composicionVacia("9:16", "unotv"), "videos/abc.mp4", 30000);
}

/** Mockea el rect de la banda a 100px de ancho (1px = 1% del eje temporal). */
function mockearBanda() {
  const banda = screen.getByLabelText("Línea de tiempo de la composición");
  vi.spyOn(banda, "getBoundingClientRect").mockReturnValue({
    left: 0,
    top: 0,
    width: 100,
    height: 96,
    right: 100,
    bottom: 96,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect);
  return banda;
}

describe("LineaTiempo", () => {
  it("sin clip base no renderiza nada", () => {
    render(
      <LineaTiempo
        doc={composicionVacia("9:16", "unotv")}
        tiempoSeg={0}
        onSeek={() => {}}
      />,
    );
    expect(screen.queryByTestId("linea-tiempo")).not.toBeInTheDocument();
  });

  it("pinta la regla con marcas de tiempo (paso 5 s para un clip de 30 s)", () => {
    render(<LineaTiempo doc={doc30()} duracionClipMs={30000} tiempoSeg={0} onSeek={() => {}} />);
    expect(screen.getByText("00:00")).toBeInTheDocument();
    expect(screen.getByText("00:05")).toBeInTheDocument();
    expect(screen.getByText("00:25")).toBeInTheDocument();
  });

  it("la tarjeta del clip ocupa el ancho proporcional a su recorte", () => {
    // Recorte 6 s–21 s de un clip de 30 s = left 20%, width 50%.
    const doc = setRecorteBase(doc30(), 6000, 21000, 30000);
    render(<LineaTiempo doc={doc} duracionClipMs={30000} tiempoSeg={0} onSeek={() => {}} />);
    const tarjeta = screen.getByTestId("clip-base");
    expect(tarjeta.style.left).toBe("20%");
    expect(tarjeta.style.width).toBe("50%");
    // La etiqueta muestra la duración recortada (15 s).
    expect(screen.getByText(/clip base · 00:15/i)).toBeInTheDocument();
  });

  it("el playhead es un slider accesible: flechas ±1 s y Shift ±5 s", () => {
    const onSeek = vi.fn();
    render(<LineaTiempo doc={doc30()} duracionClipMs={30000} tiempoSeg={10} onSeek={onSeek} />);
    const playhead = screen.getByRole("slider", { name: /cursor de reproducción/i });
    expect(playhead).toHaveAttribute("aria-valuemax", "30");
    expect(playhead).toHaveAttribute("aria-valuenow", "10");
    fireEvent.keyDown(playhead, { key: "ArrowRight" });
    expect(onSeek).toHaveBeenLastCalledWith(11);
    fireEvent.keyDown(playhead, { key: "ArrowRight", shiftKey: true });
    expect(onSeek).toHaveBeenLastCalledWith(15);
    fireEvent.keyDown(playhead, { key: "ArrowLeft" });
    expect(onSeek).toHaveBeenLastCalledWith(9);
    fireEvent.keyDown(playhead, { key: "Home" });
    expect(onSeek).toHaveBeenLastCalledWith(0);
  });

  it("mousedown y arrastre sobre la banda buscan a la fracción del puntero", () => {
    const onSeek = vi.fn();
    render(<LineaTiempo doc={doc30()} duracionClipMs={30000} tiempoSeg={0} onSeek={onSeek} />);
    const banda = mockearBanda();
    fireEvent.mouseDown(banda, { clientX: 50 });
    expect(onSeek).toHaveBeenLastCalledWith(15); // 50% de 30 s
    fireEvent.mouseMove(window, { clientX: 75 });
    expect(onSeek).toHaveBeenLastCalledWith(22.5);
    fireEvent.mouseUp(window);
    onSeek.mockClear();
    fireEvent.mouseMove(window, { clientX: 10 });
    expect(onSeek).not.toHaveBeenCalled(); // soltar termina el gesto
  });

  it("arrastrar el asa derecha recorta con etiqueta viva y el commit va al soltar", () => {
    const onSeek = vi.fn();
    const onRecorte = vi.fn();
    render(
      <LineaTiempo
        doc={doc30()}
        duracionClipMs={30000}
        tiempoSeg={0}
        onSeek={onSeek}
        onRecorte={onRecorte}
      />,
    );
    mockearBanda();
    const asa = screen.getByRole("button", { name: /recortar fin del clip/i });
    fireEvent.mouseDown(asa, { clientX: 100 });
    expect(onRecorte).not.toHaveBeenCalled(); // nada hasta soltar
    fireEvent.mouseMove(window, { clientX: 50 });
    // Etiqueta mm:ss VIVA del borde en arrastre (además de la marca 00:15 de la regla) y
    // tarjeta encogida en vivo.
    expect(screen.getAllByText("00:15").length).toBe(2);
    expect(screen.getByTestId("clip-base").style.width).toBe("50%");
    fireEvent.mouseUp(window);
    expect(onRecorte).toHaveBeenCalledWith(0, 15000);
    expect(onSeek).toHaveBeenLastCalledWith(15); // el preview salta al borde recortado
  });

  it("respeta el mínimo de 1 s al recortar (asa izquierda clampada a out-1s)", () => {
    const onRecorte = vi.fn();
    render(
      <LineaTiempo
        doc={doc30()}
        duracionClipMs={30000}
        tiempoSeg={0}
        onSeek={() => {}}
        onRecorte={onRecorte}
      />,
    );
    mockearBanda();
    const asa = screen.getByRole("button", { name: /recortar inicio del clip/i });
    fireEvent.mouseDown(asa, { clientX: 0 });
    fireEvent.mouseMove(window, { clientX: 100 }); // intenta pasar del final
    fireEvent.mouseUp(window);
    expect(onRecorte).toHaveBeenCalledWith(29000, 30000);
  });

  it("un click seco en el asa (sin arrastre) no recorta nada", () => {
    const onRecorte = vi.fn();
    render(
      <LineaTiempo
        doc={doc30()}
        duracionClipMs={30000}
        tiempoSeg={0}
        onSeek={() => {}}
        onRecorte={onRecorte}
      />,
    );
    mockearBanda();
    fireEvent.mouseDown(screen.getByRole("button", { name: /recortar fin del clip/i }), {
      clientX: 100,
    });
    fireEvent.mouseUp(window);
    expect(onRecorte).not.toHaveBeenCalled();
  });

  it("con `disabled` las asas están deshabilitadas y no recortan", () => {
    const onRecorte = vi.fn();
    render(
      <LineaTiempo
        doc={doc30()}
        duracionClipMs={30000}
        tiempoSeg={0}
        onSeek={() => {}}
        onRecorte={onRecorte}
        disabled
      />,
    );
    mockearBanda();
    const asa = screen.getByRole("button", { name: /recortar fin del clip/i });
    expect(asa).toBeDisabled();
    fireEvent.mouseDown(asa, { clientX: 100 });
    fireEvent.mouseMove(window, { clientX: 50 });
    fireEvent.mouseUp(window);
    expect(onRecorte).not.toHaveBeenCalled();
  });

  it("PiP y subtítulos aparecen como barras finas solo-lectura ancladas a sus tiempos", () => {
    const doc = setClipPip(doc30(), "videos/pip.mp4", 10000);
    const segmentos: SegmentoSub[] = [{ id: "s1", inicio: 3, fin: 6, texto: "Hola México" }];
    render(
      <LineaTiempo
        doc={doc}
        duracionClipMs={30000}
        tiempoSeg={0}
        onSeek={() => {}}
        segmentos={segmentos}
      />,
    );
    // PiP: arranca con el recorte base (0) y dura su recorte (10 s de 30 = 33.33%).
    const pip = screen.getByLabelText("Barra de PiP");
    expect(pip.style.left).toBe("0%");
    expect(pip).toHaveAttribute("title", "PiP");
    // Subtítulos: un marcador por segmento, en el tiempo del clip base (10%..20%).
    const seg = screen.getByTitle("Hola México");
    expect(seg.style.left).toBe("10%");
    expect(seg.style.width).toBe("10%");
  });
});
