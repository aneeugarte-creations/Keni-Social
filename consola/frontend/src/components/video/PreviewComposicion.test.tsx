/**
 * Tests del PLAYER del preview de composición (PreviewComposicion):
 *  - Sin clip base: placeholder y SIN controles de reproducción.
 *  - Play/pausa: el botón llama a `video.play()`/`pause()` y refleja el estado vía eventos.
 *  - El reloj usa la duración del documento como fallback y la real al cargar metadatos.
 *  - Los subtítulos siguen el tiempo actual (`timeupdate`): el segmento activo se pinta en su
 *    ventana y desaparece fuera de ella.
 *  - Scrubbing: pointer down sobre la barra busca (seek) a la fracción correspondiente.
 *  - Espacio = play/pausa global, salvo foco en un campo editable o `atajoEspacio` apagado.
 *  - RECORTE: la reproducción lo respeta como el render (play desde fuera salta a `recorte_in`,
 *    al alcanzar `recorte_out` pausa clavada en el corte); el scrubbing recorre el clip entero
 *    y el reloj muestra el tiempo del VÍDEO FINAL con las zonas descartadas atenuadas.
 *  - PiP EDITABLE: arrastrar mueve la caja en vivo (estado local) y COMMITEA x/y al soltar, con
 *    clamp al lienzo y snap a bordes/centro con guías; la esquina inferior derecha redimensiona
 *    manteniendo la proporción; las flechas mueven ±1 % (Shift ±5 %); sin `pipEditable` la caja
 *    no es interactiva.
 *
 * jsdom no implementa HTMLMediaElement.play/pause: se mockean en el prototipo despachando los
 * eventos `play`/`pause` reales (los mismos que dispararía el navegador).
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  composicionVacia,
  setClipBase,
  setClipPip,
  setRecorteBase,
  type ComposicionVideo,
  type SegmentoSub,
} from "@/lib/video";

import { PreviewComposicion, type PreviewPlayerHandle } from "./PreviewComposicion";

function docConBase(duracionMs = 30000): ComposicionVideo {
  return setClipBase(composicionVacia("9:16", "unotv"), "videos/abc.mp4", duracionMs);
}

/** Clip de 30 s recortado a 6–21 s: el vídeo final durará 15 s. */
function docRecortado(): ComposicionVideo {
  return setRecorteBase(docConBase(30000), 6000, 21000, 30000);
}

/** Carga los metadatos del <video> (jsdom no los emite): duración real del clip crudo. */
function cargarMetadatos(container: HTMLElement, durSeg = 30): HTMLVideoElement {
  const video = container.querySelector("video")!;
  Object.defineProperty(video, "duration", { value: durSeg, configurable: true });
  fireEvent(video, new Event("loadedmetadata"));
  return video;
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
    // El documento dice `recorte_out` = 30 s, así que los 15 s extra cuentan como RECORTE: el
    // render aplicará -to 30 s y el slider lo expone como vídeo final (igual que la reproducción).
    cargarMetadatos(container, 45);
    expect(barra).toHaveAttribute(
      "aria-valuetext",
      "00:00 de 00:45 (vídeo final: 00:00 de 00:30)",
    );
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

  it("play desde fuera del recorte salta a recorte_in; desde dentro no recoloca", async () => {
    const { container } = render(<PreviewComposicion doc={docRecortado()} baseUrl="videos/abc.mp4" />);
    const video = cargarMetadatos(container);
    // t=0 está ANTES del corte (6–21 s): play arranca en recorte_in.
    fireEvent.click(screen.getByRole("button", { name: "Reproducir" }));
    expect(video.currentTime).toBeCloseTo(6, 5);
    expect(playMock).toHaveBeenCalledTimes(1);
    // Pausa, busca DENTRO del corte y reanuda: play NO recoloca (sigue donde estaba).
    fireEvent.click(await screen.findByRole("button", { name: "Pausar" }));
    video.currentTime = 10;
    fireEvent(video, new Event("timeupdate"));
    fireEvent.click(await screen.findByRole("button", { name: "Reproducir" }));
    expect(video.currentTime).toBeCloseTo(10, 5);
  });

  it("al alcanzar recorte_out la reproducción se pausa clavada en el corte, lista para replay", async () => {
    const { container } = render(<PreviewComposicion doc={docRecortado()} baseUrl="videos/abc.mp4" />);
    const video = cargarMetadatos(container);
    fireEvent.click(screen.getByRole("button", { name: "Reproducir" }));
    expect(pauseMock).not.toHaveBeenCalled();
    // La reproducción cruza recorte_out (21 s): el player pausa y clava el frame en el corte.
    video.currentTime = 21.3;
    fireEvent(video, new Event("timeupdate"));
    expect(pauseMock).toHaveBeenCalledTimes(1);
    expect(video.currentTime).toBeCloseTo(21, 5);
    // Replay: el siguiente play vuelve a recorte_in.
    fireEvent.click(await screen.findByRole("button", { name: "Reproducir" }));
    expect(video.currentTime).toBeCloseTo(6, 5);
  });

  it("en pausa, el scrubbing puede inspeccionar la zona descartada sin que el player la corrija", () => {
    const { container } = render(<PreviewComposicion doc={docRecortado()} baseUrl="videos/abc.mp4" />);
    const video = cargarMetadatos(container);
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
    // 90 % de 30 s = 27 s, DESPUÉS de recorte_out: el seek se respeta (inspección libre).
    fireEvent.mouseDown(barra, { clientX: 90 });
    fireEvent.mouseUp(window);
    expect(video.currentTime).toBeCloseTo(27, 5);
    expect(pauseMock).not.toHaveBeenCalled();
  });

  it("el reloj muestra el tiempo del VÍDEO FINAL y la barra atenúa las zonas descartadas", () => {
    const { container } = render(<PreviewComposicion doc={docRecortado()} baseUrl="videos/abc.mp4" />);
    const video = cargarMetadatos(container);
    // Zonas descartadas atenuadas: cabeza 6/30 = 20 %, cola (30−21)/30 = 30 %.
    expect(screen.getByTestId("barra-descarte-in").style.width).toBe("20%");
    expect(screen.getByTestId("barra-descarte-out").style.width).toBe("30%");
    // Antes del corte, el reloj del vídeo final marca 0 de 15 s.
    video.currentTime = 2;
    fireEvent(video, new Event("timeupdate"));
    expect(screen.getByText("00:00 / 00:15")).toBeInTheDocument();
    // Dentro del corte: 10 s del clip = 4 s del vídeo final; el slider expone ambos ejes.
    video.currentTime = 10;
    fireEvent(video, new Event("timeupdate"));
    expect(screen.getByText("00:04 / 00:15")).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: /posición de reproducción/i })).toHaveAttribute(
      "aria-valuetext",
      "00:10 de 00:30 (vídeo final: 00:04 de 00:15)",
    );
  });

  it("sin recorte efectivo no hay zonas atenuadas y el reloj es el del clip", () => {
    const { container } = render(<PreviewComposicion doc={docConBase(30000)} baseUrl="videos/abc.mp4" />);
    cargarMetadatos(container);
    expect(screen.queryByTestId("barra-descarte-in")).not.toBeInTheDocument();
    expect(screen.queryByTestId("barra-descarte-out")).not.toBeInTheDocument();
    expect(screen.getByText("00:00 / 00:30")).toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────────────────────
// PiP EDITABLE: arrastrar/redimensionar/flechas sobre el preview (estilo Canva).
//
// Geometría de los tests: lienzo 9:16 = 1080×1920; `altoMax` 960 → escala 0,5 EXACTA (jsdom no
// mide anchos: el clamp por contenedor no aplica). La caja PiP por defecto de `setClipPip` es
// w=367, h=206 en x=673, y=1674 (esquina inferior derecha con margen 40).
// ─────────────────────────────────────────────────────────────────────────────────────────────
describe("PreviewComposicion (PiP editable)", () => {
  /** Doc con base de 30 s + PiP por defecto (x=673, y=1674, w=367, h=206). */
  function docConPip(): ComposicionVideo {
    return setClipPip(docConBase(30000), "videos/pip.mp4", 10000);
  }

  function renderPipEditable(onCajaPip = vi.fn()) {
    render(
      <PreviewComposicion
        doc={docConPip()}
        baseUrl="videos/abc.mp4"
        pipUrl="videos/pip.mp4"
        altoMax={960}
        pipEditable
        onCajaPip={onCajaPip}
      />,
    );
    return { onCajaPip, caja: screen.getByRole("group", { name: "Ventana PiP" }) };
  }

  it("sin `pipEditable` la caja PiP se pinta pero NO es interactiva", () => {
    render(<PreviewComposicion doc={docConPip()} baseUrl="videos/abc.mp4" altoMax={960} />);
    const caja = screen.getByTestId("caja-pip");
    expect(caja).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Ventana PiP" })).not.toBeInTheDocument();
    expect(caja).not.toHaveAttribute("tabindex");
    expect(screen.queryByTestId("pip-redimensionar")).not.toBeInTheDocument();
  });

  it("arrastrar mueve la caja EN VIVO (sin tocar el modelo) y commitea x/y al soltar", () => {
    const { onCajaPip, caja } = renderPipEditable();
    fireEvent.mouseDown(caja, { clientX: 500, clientY: 500 });
    // Δpantalla (−50, −20) a escala 0,5 = Δlienzo (−100, −40): la caja sigue al puntero…
    fireEvent.mouseMove(window, { clientX: 450, clientY: 480 });
    expect(caja.style.left).toBe(`${(673 - 100) * 0.5}px`);
    expect(caja.style.top).toBe(`${(1674 - 40) * 0.5}px`);
    // …pero el modelo NO se toca durante el gesto (transform local, commit único al soltar).
    expect(onCajaPip).not.toHaveBeenCalled();
    fireEvent.mouseUp(window);
    expect(onCajaPip).toHaveBeenCalledTimes(1);
    expect(onCajaPip).toHaveBeenCalledWith({ x: 573, y: 1634 });
    // Al soltar se quitan los listeners: mover el ratón ya no arrastra ni re-commitea.
    fireEvent.mouseMove(window, { clientX: 300, clientY: 300 });
    fireEvent.mouseUp(window);
    expect(onCajaPip).toHaveBeenCalledTimes(1);
  });

  it("clamp + snap a BORDES: no sale del lienzo, se imanta y pinta guías que mueren al soltar", () => {
    const { onCajaPip, caja } = renderPipEditable();
    fireEvent.mouseDown(caja, { clientX: 500, clientY: 500 });
    // Δlienzo (+30, +200): x=703 cae a ≤16 px (umbral 8/0,5) del borde derecho (713) → snap;
    // y=1874 excede el lienzo → clamp a 1714 (que ES el borde inferior) → snap con guía.
    fireEvent.mouseMove(window, { clientX: 515, clientY: 600 });
    expect(screen.getByTestId("guia-snap-v").style.left).toBe(`${1080 * 0.5}px`);
    expect(screen.getByTestId("guia-snap-h").style.top).toBe(`${1920 * 0.5}px`);
    fireEvent.mouseUp(window);
    expect(onCajaPip).toHaveBeenCalledWith({ x: 713, y: 1714 });
    expect(screen.queryByTestId("guia-snap-v")).not.toBeInTheDocument();
    expect(screen.queryByTestId("guia-snap-h")).not.toBeInTheDocument();
  });

  it("snap al CENTRO horizontal con guía en mitad del lienzo", () => {
    const { onCajaPip, caja } = renderPipEditable();
    fireEvent.mouseDown(caja, { clientX: 500, clientY: 500 });
    // Δlienzo −316 → x=357, a 0,5 px del centrado ((1080−367)/2 = 356,5) → imanta al centro.
    fireEvent.mouseMove(window, { clientX: 342, clientY: 500 });
    expect(screen.getByTestId("guia-snap-v").style.left).toBe(`${540 * 0.5}px`);
    fireEvent.mouseUp(window);
    expect(onCajaPip).toHaveBeenCalledWith({ x: 357, y: 1674 });
  });

  it("la esquina inferior derecha REDIMENSIONA manteniendo la proporción (sin arrastrar la caja)", () => {
    const { onCajaPip } = renderPipEditable();
    const asa = screen.getByTestId("pip-redimensionar");
    fireEvent.mouseDown(asa, { clientX: 300, clientY: 300 });
    // Δlienzo +20 en X: w 367→387; h sigue la proporción (387·206/367 ≈ 217).
    fireEvent.mouseMove(window, { clientX: 310, clientY: 300 });
    fireEvent.mouseUp(window);
    // Un solo commit y SOLO de tamaño: el mousedown del asa no arrancó también el arrastre.
    expect(onCajaPip).toHaveBeenCalledTimes(1);
    expect(onCajaPip).toHaveBeenCalledWith({ w: 387, h: 217 });
  });

  it("el redimensionado respeta el MÍNIMO (ningún lado por debajo de 80 px de lienzo)", () => {
    const { onCajaPip } = renderPipEditable();
    const asa = screen.getByTestId("pip-redimensionar");
    fireEvent.mouseDown(asa, { clientX: 300, clientY: 300 });
    // Encoger muchísimo: el alto clava en 80 y el ancho en 80·(367/206) ≈ 143.
    fireEvent.mouseMove(window, { clientX: 100, clientY: 100 });
    fireEvent.mouseUp(window);
    expect(onCajaPip).toHaveBeenCalledWith({ w: 143, h: 80 });
  });

  it("con foco, las flechas mueven ±1 % del lienzo y Shift ±5 %", () => {
    const { onCajaPip, caja } = renderPipEditable();
    // 1 % de 1080 = 10,8 → 11 px de lienzo a la izquierda.
    fireEvent.keyDown(caja, { key: "ArrowLeft" });
    expect(onCajaPip).toHaveBeenLastCalledWith({ x: 673 - 11 });
    // Shift: 5 % de 1920 = 96 px hacia abajo (el clamp final lo aplica `setCajaPip`).
    fireEvent.keyDown(caja, { key: "ArrowDown", shiftKey: true });
    expect(onCajaPip).toHaveBeenLastCalledWith({ y: 1674 + 96 });
    // Una tecla ajena no commitea nada.
    fireEvent.keyDown(caja, { key: "Enter" });
    expect(onCajaPip).toHaveBeenCalledTimes(2);
  });
});
