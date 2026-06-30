/**
 * Tests del timeline multipista del Estudio de Video (TimelineMultipista):
 *  - Sin segmentos base no renderiza nada.
 *  - Render de N segmentos consecutivos con anchos ∝ a su duración de salida.
 *  - Playhead accesible (role=slider): flechas ±1 s, Shift ±5 s.
 *  - Cuchilla: divide en el playhead → onDividirSegmento(idx, msLocal).
 *  - Asas de trim: arrastrar fija recorte_in/out_ms del segmento (commit al soltar).
 *  - Snap de trim: al arrastrar un asa, si queda a <8px del playhead se enclava en él.
 *  - Audio base: pista separada (barra a lo largo del eje) + toggle de silenciar.
 *  - Música: «+ Música» (sin música) llama onAnadirMusica; con música hay controles y barra.
 *  - Zoom: los botones cambian el ancho del eje y los gestos siguen correctos al ancho escalado.
 *  - `disabled` apaga la edición; el seek sigue activo.
 *  - PiP y subtítulos: clic en la barra llama onSeek con el inicio de esa barra.
 *  - baseUrl: se intenta extraer frames del clip fuente (createElement "video" llamado).
 *  - Trim PiP: arrastrar el asa del carril PiP llama onTrimPip(in, out).
 *  - Marcadores: «＋ Marcador» llama onAgregarMarcador con el ms del playhead.
 *  - Fundidos: cambiar el input de fade in/out llama onFadeMusica con el valor.
 *
 * jsdom no tiene layout: posiciones por estilo (% sobre el eje) y gestos que mockean el
 * `getBoundingClientRect` del eje (su ancho en px = todo el tiempo de salida).
 * La extracción de frames se mockea (jsdom no decodifica vídeo real): se espía
 * document.createElement para verificar que el efecto lo intenta sin colgar el test.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  agregarMarcador,
  composicionVacia,
  dividirClipBase,
  setAudioBase,
  setClipBase,
  setClipPip,
  setMusica,
  type ComposicionVideo,
} from "@/lib/video";

import { TimelineMultipista } from "./TimelineMultipista";

/** Clip base de 30 s (un solo segmento). */
function doc30(): ComposicionVideo {
  return setClipBase(composicionVacia("9:16", "unotv"), "videos/abc.mp4", 30000);
}

/** Dos segmentos consecutivos: 10 s + 20 s (corte en 10 s). */
function doc2segmentos(): ComposicionVideo {
  return dividirClipBase(doc30(), 0, 10000);
}

/** Mockea el rect del eje a 100px de ancho (1px = 1% del tiempo de salida). */
function mockearEje() {
  const eje = screen.getByLabelText("Pistas de la composición");
  vi.spyOn(eje, "getBoundingClientRect").mockReturnValue({
    left: 0,
    top: 0,
    width: 100,
    height: 200,
    right: 100,
    bottom: 200,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect);
  return eje;
}

describe("TimelineMultipista", () => {
  it("sin segmentos base no renderiza nada", () => {
    render(
      <TimelineMultipista doc={composicionVacia("9:16", "unotv")} tiempoSeg={0} onSeek={() => {}} />,
    );
    expect(screen.queryByTestId("timeline-multipista")).not.toBeInTheDocument();
  });

  it("dibuja los segmentos consecutivos con anchos proporcionales a su duración", () => {
    render(<TimelineMultipista doc={doc2segmentos()} tiempoSeg={0} onSeek={() => {}} />);
    const seg0 = screen.getByTestId("segmento-0");
    const seg1 = screen.getByTestId("segmento-1");
    // 10 s de 30 = 33.3% (en 0%) · 20 s de 30 = 66.6% (en 33.3%).
    expect(parseFloat(seg0.style.left)).toBeCloseTo(0, 1);
    expect(parseFloat(seg0.style.width)).toBeCloseTo(33.33, 1);
    expect(parseFloat(seg1.style.left)).toBeCloseTo(33.33, 1);
    expect(parseFloat(seg1.style.width)).toBeCloseTo(66.66, 1);
  });

  it("el playhead es un slider accesible: flechas ±1 s y Shift ±5 s", () => {
    const onSeek = vi.fn();
    render(<TimelineMultipista doc={doc30()} tiempoSeg={10} onSeek={onSeek} />);
    const playhead = screen.getByRole("slider", { name: /cursor de reproducción/i });
    expect(playhead).toHaveAttribute("aria-valuemax", "30");
    expect(playhead).toHaveAttribute("aria-valuenow", "10");
    fireEvent.keyDown(playhead, { key: "ArrowRight" });
    expect(onSeek).toHaveBeenLastCalledWith(11);
    fireEvent.keyDown(playhead, { key: "ArrowRight", shiftKey: true });
    expect(onSeek).toHaveBeenLastCalledWith(15);
  });

  it("la cuchilla divide el segmento bajo el playhead con su tiempo local", () => {
    const onDividirSegmento = vi.fn();
    // Playhead a 15 s: cae en el segmento 1 (10–30 s), local 5 s.
    render(
      <TimelineMultipista
        doc={doc2segmentos()}
        tiempoSeg={15}
        onSeek={() => {}}
        onDividirSegmento={onDividirSegmento}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /dividir en el cursor/i }));
    expect(onDividirSegmento).toHaveBeenCalledWith(1, 5000);
  });

  it("la cuchilla se deshabilita si una mitad quedaría bajo el mínimo", () => {
    const onDividirSegmento = vi.fn();
    // Playhead a 0.5 s: la mitad izquierda (500 ms) < MIN_RECORTE_MS (1 s).
    render(
      <TimelineMultipista
        doc={doc30()}
        tiempoSeg={0.5}
        onSeek={() => {}}
        onDividirSegmento={onDividirSegmento}
      />,
    );
    const knife = screen.getByRole("button", { name: /dividir en el cursor/i });
    expect(knife).toBeDisabled();
    fireEvent.click(knife);
    expect(onDividirSegmento).not.toHaveBeenCalled();
  });

  it("arrastrar el asa derecha recorta el segmento (commit al soltar)", () => {
    const onSeek = vi.fn();
    const onTrimSegmento = vi.fn();
    render(
      <TimelineMultipista
        doc={doc30()}
        tiempoSeg={0}
        onSeek={onSeek}
        onTrimSegmento={onTrimSegmento}
      />,
    );
    mockearEje();
    const asa = screen.getByRole("button", { name: /recortar fin del segmento 1/i });
    fireEvent.mouseDown(asa, { clientX: 100 });
    expect(onTrimSegmento).not.toHaveBeenCalled(); // nada hasta soltar
    fireEvent.mouseMove(window, { clientX: 50 }); // 50% → 15 000 ms de salida
    fireEvent.mouseUp(window);
    expect(onTrimSegmento).toHaveBeenCalledWith(0, 0, 15000);
    expect(onSeek).toHaveBeenLastCalledWith(15); // el preview salta al borde recortado
  });

  it("el snap del trim enclava al playhead cuando queda a <8px de él", () => {
    const onSeek = vi.fn();
    const onTrimSegmento = vi.fn();
    // Playhead a 15 s (50%). Eje = 100px → umbral = 8/100 * 30000 = 2400 ms.
    // Mover a 53px = 15900 ms; distancia al playhead (15000 ms) = 900 ms < 2400 ms → snap.
    render(
      <TimelineMultipista
        doc={doc30()}
        tiempoSeg={15}
        onSeek={onSeek}
        onTrimSegmento={onTrimSegmento}
      />,
    );
    mockearEje();
    const asa = screen.getByRole("button", { name: /recortar fin del segmento 1/i });
    fireEvent.mouseDown(asa, { clientX: 100 });
    fireEvent.mouseMove(window, { clientX: 53 }); // cerca del playhead (50px)
    fireEvent.mouseUp(window);
    // Debe enclavarse en el playhead (15000 ms).
    expect(onTrimSegmento).toHaveBeenCalledWith(0, 0, 15000);
  });

  it("el toggle de silenciar el audio base llama onAudioBase", () => {
    const onAudioBase = vi.fn();
    render(
      <TimelineMultipista doc={doc30()} tiempoSeg={0} onSeek={() => {}} onAudioBase={onAudioBase} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /silenciar audio base/i }));
    expect(onAudioBase).toHaveBeenCalledWith({ silenciar: true });
  });

  it("muestra el audio base como pista separada (barra a lo largo de todo el eje)", () => {
    render(
      <TimelineMultipista doc={doc30()} tiempoSeg={0} onSeek={() => {}} onAudioBase={() => {}} />,
    );
    const barra = screen.getByLabelText("Pista de audio base");
    expect(barra.style.left).toBe("0%");
    expect(barra.style.width).toBe("100%");
    expect(barra).toHaveAttribute("data-silenciado", "false");
  });

  it("la barra de audio refleja el silencio del clip base", () => {
    const doc = setAudioBase(doc30(), { silenciar: true });
    render(<TimelineMultipista doc={doc} tiempoSeg={0} onSeek={() => {}} onAudioBase={() => {}} />);
    expect(screen.getByLabelText("Pista de audio base")).toHaveAttribute("data-silenciado", "true");
  });

  it("con música muestra su pista (barra) además de los controles", () => {
    const doc = setMusica(doc30(), "videos/song.mp4", 30000);
    render(
      <TimelineMultipista doc={doc} tiempoSeg={0} onSeek={() => {}} onVolumenMusica={() => {}} />,
    );
    const barra = screen.getByLabelText("Pista de música");
    expect(barra.style.left).toBe("0%");
    expect(barra.style.width).toBe("100%");
  });

  it("el zoom cambia el ancho del eje y conserva los gestos al ancho escalado", () => {
    const onSeek = vi.fn();
    render(<TimelineMultipista doc={doc30()} tiempoSeg={0} onSeek={onSeek} />);
    const eje = screen.getByLabelText("Pistas de la composición");
    // De partida el eje ajusta al viewport (100%); acercar/alejar lo escalan.
    expect(eje.style.width).toBe("100%");
    fireEvent.click(screen.getByRole("button", { name: /^acercar$/i }));
    expect(parseFloat(eje.style.width)).toBeGreaterThan(100);
    // Gestos correctos al ancho REAL escalado: con el eje a 200px, scrub en x=100 = 50% = 15 s.
    vi.spyOn(eje, "getBoundingClientRect").mockReturnValue({
      left: 0,
      top: 0,
      width: 200,
      height: 200,
      right: 200,
      bottom: 200,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect);
    fireEvent.mouseDown(screen.getByLabelText("Regla de tiempo"), { clientX: 100 });
    expect(onSeek).toHaveBeenLastCalledWith(15);
    fireEvent.mouseUp(window);
    // «Ajustar» vuelve a encajar (100%).
    fireEvent.click(screen.getByRole("button", { name: /ajustar zoom/i }));
    expect(eje.style.width).toBe("100%");
  });

  it("«+ Música» llama onAnadirMusica cuando no hay música", () => {
    const onAnadirMusica = vi.fn();
    render(
      <TimelineMultipista
        doc={doc30()}
        tiempoSeg={0}
        onSeek={() => {}}
        onAnadirMusica={onAnadirMusica}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /añadir música/i }));
    expect(onAnadirMusica).toHaveBeenCalledTimes(1);
  });

  it("con música muestra controles de volumen y quitar (no «+ Música»)", () => {
    const onQuitarMusica = vi.fn();
    const doc = setMusica(doc30(), "videos/song.mp4", 30000);
    render(
      <TimelineMultipista
        doc={doc}
        tiempoSeg={0}
        onSeek={() => {}}
        onVolumenMusica={() => {}}
        onQuitarMusica={onQuitarMusica}
      />,
    );
    expect(screen.queryByRole("button", { name: /añadir música/i })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Volumen de la música")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /quitar música/i }));
    expect(onQuitarMusica).toHaveBeenCalledTimes(1);
  });

  it("`disabled` apaga la cuchilla pero deja vivo el seek por teclado", () => {
    const onSeek = vi.fn();
    const onDividirSegmento = vi.fn();
    render(
      <TimelineMultipista
        doc={doc2segmentos()}
        tiempoSeg={15}
        onSeek={onSeek}
        onDividirSegmento={onDividirSegmento}
        disabled
      />,
    );
    expect(screen.getByRole("button", { name: /dividir en el cursor/i })).toBeDisabled();
    fireEvent.keyDown(screen.getByRole("slider", { name: /cursor de reproducción/i }), {
      key: "ArrowLeft",
    });
    expect(onSeek).toHaveBeenLastCalledWith(14);
  });

  it("clic en la barra de PiP llama onSeek con el inicio del PiP", () => {
    const onSeek = vi.fn();
    const doc = setClipPip(doc30(), "videos/pip.mp4", 30000);
    render(<TimelineMultipista doc={doc} tiempoSeg={0} onSeek={onSeek} />);
    fireEvent.click(screen.getByRole("button", { name: /barra de pip/i }));
    expect(onSeek).toHaveBeenCalledWith(0);
  });

  it("clic en una barra de subtítulos llama onSeek con el inicio del segmento", () => {
    const onSeek = vi.fn();
    const segmentos = [{ id: "s1", texto: "Hola mundo", inicio: 5, fin: 10 }];
    render(
      <TimelineMultipista doc={doc30()} tiempoSeg={0} onSeek={onSeek} segmentos={segmentos} />,
    );
    fireEvent.click(screen.getByTitle("Hola mundo"));
    expect(onSeek).toHaveBeenCalledWith(5);
  });

  it("con baseUrl intenta extraer frames del clip fuente (createElement 'video')", () => {
    const origCreate = document.createElement.bind(document);
    let videoCreated = false;
    vi.spyOn(document, "createElement").mockImplementation(
      (tag: string, ...args: unknown[]) => {
        if (tag === "video") videoCreated = true;
        return origCreate(tag, ...(args as []));
      },
    );
    render(
      <TimelineMultipista
        doc={doc30()}
        tiempoSeg={0}
        onSeek={() => {}}
        baseUrl="https://cdn.example.com/clip.mp4"
      />,
    );
    expect(videoCreated).toBe(true);
    vi.restoreAllMocks();
  });

  it("arrastrar el asa del carril PiP llama onTrimPip con los nuevos recortes", () => {
    const onTrimPip = vi.fn();
    // PiP de 20 s; el eje base es 30 s → 100 px en el mock.
    const doc = setClipPip(doc30(), "videos/pip.mp4", 20000);
    render(
      <TimelineMultipista
        doc={doc}
        tiempoSeg={0}
        onSeek={() => {}}
        onTrimPip={onTrimPip}
      />,
    );
    mockearEje();
    // Asa de fin del PiP: empuja desde el 100% hacia el 50% → recorte out = 0 + 15000.
    const asa = screen.getByRole("button", { name: /recortar fin del pip/i });
    fireEvent.mouseDown(asa, { clientX: 100 });
    fireEvent.mouseMove(window, { clientX: 50 }); // 50% de 30 s = 15000 ms
    fireEvent.mouseUp(window);
    expect(onTrimPip).toHaveBeenCalled();
    // recorte_in original 0, recorte_out nuevo = 0 + 15000 = 15000.
    expect(onTrimPip).toHaveBeenCalledWith(0, 15000);
  });

  it("«＋ Marcador» llama onAgregarMarcador con el ms del playhead", () => {
    const onAgregarMarcador = vi.fn();
    // Playhead a 15 s = 15000 ms.
    render(
      <TimelineMultipista
        doc={doc30()}
        tiempoSeg={15}
        onSeek={() => {}}
        onAgregarMarcador={onAgregarMarcador}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /añadir marcador/i }));
    expect(onAgregarMarcador).toHaveBeenCalledWith(15000);
  });

  it("el control de fundido entrada llama onFadeMusica con fade_in_ms", () => {
    const onFadeMusica = vi.fn();
    const doc = setMusica(doc30(), "videos/song.mp4", 30000);
    render(
      <TimelineMultipista
        doc={doc}
        tiempoSeg={0}
        onSeek={() => {}}
        onFadeMusica={onFadeMusica}
      />,
    );
    fireEvent.change(screen.getByLabelText(/fundido entrada/i), {
      target: { value: "500" },
    });
    expect(onFadeMusica).toHaveBeenCalledWith({ fade_in_ms: 500 });
  });

  it("marcadores del doc se pintan en la regla y clic hace seek", () => {
    const onSeek = vi.fn();
    const doc = agregarMarcador(doc30(), 10000, "intro");
    render(<TimelineMultipista doc={doc} tiempoSeg={0} onSeek={onSeek} />);
    // El pin del marcador tiene aria-label con "intro".
    const pin = screen.getByRole("button", { name: /marcador intro/i });
    fireEvent.mouseDown(pin, { bubbles: true, cancelBubble: false });
    fireEvent.click(pin);
    expect(onSeek).toHaveBeenCalledWith(10); // 10000 ms / 1000 = 10 s
  });
});
