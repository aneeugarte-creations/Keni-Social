/**
 * Tests del carrusel lateral editable: navegación entre slides + gestión (añadir/quitar/mover)
 * + horneado debounced de los slides extra al editar su receta.
 *
 * EditorPlacaInline (lienzo + fuentes) y GaleriaPlantillas se MOCKEAN por un stub ligero que
 * expone los callbacks como botones: así probamos el cableado del carrusel, no el lienzo.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EditorCarruselLateral } from "./EditorCarruselLateral";
import { api } from "@/lib/api";
import type { SlideCarrusel } from "@/lib/carrusel";

// Stub de EditorPlacaInline: muestra el copyIn recibido y un botón que lo cambia (simula editar
// el titular del slide activo), más un botón para abrir la galería.
vi.mock("@/components/media/EditorPlacaInline", () => ({
  EditorPlacaInline: (props: {
    copyIn: string;
    onCopyInCambio?: (s: string) => void;
    onAbrirGaleria?: () => void;
  }) => (
    <div data-testid="placa">
      <span data-testid="placa-copyin">{props.copyIn}</span>
      <button type="button" onClick={() => props.onCopyInCambio?.("Editado")}>
        editar-titular
      </button>
      <button type="button" onClick={() => props.onAbrirGaleria?.()}>
        abrir-galeria
      </button>
    </div>
  ),
}));
vi.mock("@/editor/GaleriaPlantillas", () => ({
  GaleriaPlantillas: () => <div data-testid="galeria" />,
}));

const BASE = {
  marca: "unotv",
  piezaId: "pub-1",
  plantillas: [],
  portadaFotos: [{ objeto: "portada.jpg", foco: null, zoom: 0 }],
  onPortadaFotos: vi.fn(),
  portadaCopyIn: "Titular portada",
  onPortadaCopyIn: vi.fn(),
  portadaPlantillaId: "",
  onPortadaPlantillaId: vi.fn(),
  portadaPlacaOculta: false,
  onPortadaPlacaOculta: vi.fn(),
};

function renderLateral(slides: SlideCarrusel[], onSlides = vi.fn()) {
  render(<EditorCarruselLateral {...BASE} slides={slides} onSlides={onSlides} />);
  return { onSlides };
}

describe("EditorCarruselLateral", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.restoreAllMocks());

  it("arranca en la portada y muestra contador + un punto por slide", () => {
    renderLateral([{ tipo: "imagen", objeto: "s2.png", titular: "Clave 2" }]);
    expect(screen.getByText("Portada")).toBeInTheDocument();
    expect(screen.getByText("de 2")).toBeInTheDocument();
    expect(screen.getByTestId("placa-copyin")).toHaveTextContent("Titular portada");
    // 2 puntos de posición (portada + 1 slide).
    expect(screen.getAllByRole("button", { name: /Ir al slide/ })).toHaveLength(2);
  });

  it("navega al siguiente slide (flecha) y muestra su titular", () => {
    renderLateral([{ tipo: "imagen", objeto: "s2.png", titular: "Clave 2" }]);
    fireEvent.click(screen.getByRole("button", { name: "Slide siguiente" }));
    expect(screen.getByText("Slide 2")).toBeInTheDocument();
    expect(screen.getByTestId("placa-copyin")).toHaveTextContent("Clave 2");
  });

  it("'Slide' (+) añade un slide extra en blanco y navega a él", () => {
    const { onSlides } = renderLateral([{ tipo: "imagen", objeto: "s2.png", titular: "Clave 2" }]);
    fireEvent.click(screen.getByRole("button", { name: "Añadir slide" }));
    expect(onSlides).toHaveBeenCalledWith([
      { tipo: "imagen", objeto: "s2.png", titular: "Clave 2" },
      { tipo: "imagen", objeto: "", titular: "" },
    ]);
  });

  it("en un slide extra, 'Quitar' lo elimina; en la portada no hay quitar", () => {
    const { onSlides } = renderLateral([
      { tipo: "imagen", objeto: "s2.png", titular: "A" },
      { tipo: "imagen", objeto: "s3.png", titular: "B" },
    ]);
    // En la portada NO se ofrece quitar.
    expect(screen.queryByRole("button", { name: "Quitar slide" })).toBeNull();
    // Voy al slide 2 y lo quito.
    fireEvent.click(screen.getByRole("button", { name: "Slide siguiente" }));
    fireEvent.click(screen.getByRole("button", { name: "Quitar slide" }));
    expect(onSlides).toHaveBeenCalledWith([{ tipo: "imagen", objeto: "s3.png", titular: "B" }]);
  });

  it("'Carrusel' descarga la portada (/compuesta), re-hornea cada imagen extra y baja el video", async () => {
    const componer = vi
      .spyOn(api, "componerSlide")
      .mockResolvedValue({ id: "artes/h.png", url: "/api/media/artes/h.png" });
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(["x"]) });
    vi.stubGlobal("fetch", fetchSpy);
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    renderLateral([
      { tipo: "imagen", objeto: "s2.png", titular: "Clave 2", foto: "f.jpg" },
      { tipo: "video", objeto: "v.mp4", titular: "" },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Descargar carrusel" }));

    // Una descarga por slide: portada (/compuesta) + imagen re-horneada + video.
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(3));
    expect(fetchSpy.mock.calls[0][0]).toMatch(/\/api\/piezas\/pub-1\/compuesta/);
    expect(componer).toHaveBeenCalledWith("pub-1", {
      foto: "f.jpg",
      titular: "Clave 2",
      plantilla_id: "",
      foto_encuadre: "",
      sin_plantilla: false,
    });
  });

  it("editar el titular de un slide extra lo RE-HORNEA (debounced) y fija el nuevo objeto", async () => {
    vi.useFakeTimers();
    const componer = vi
      .spyOn(api, "componerSlide")
      .mockResolvedValue({ id: "artes/nuevo.png", url: "/api/media/artes/nuevo.png" });
    // Harness CONTROLADO: onSlides actualiza el prop (como hace DialogoEditar) para que el
    // horneado debounced lea la receta YA editada.
    const espia = vi.fn();
    function Controlado() {
      const [slides, setSlides] = React.useState<SlideCarrusel[]>([
        { tipo: "imagen", objeto: "s2.png", titular: "Clave 2", foto: "f.jpg" },
      ]);
      return (
        <EditorCarruselLateral
          {...BASE}
          slides={slides}
          onSlides={(s) => {
            espia(s);
            setSlides(s);
          }}
        />
      );
    }
    render(<Controlado />);
    fireEvent.click(screen.getByRole("button", { name: "Slide siguiente" }));
    fireEvent.click(screen.getByRole("button", { name: "editar-titular" }));
    // Cambio de receta propagado (titular nuevo); aún no se hornea (debounce).
    expect(espia).toHaveBeenCalledWith([
      { tipo: "imagen", objeto: "s2.png", titular: "Editado", foto: "f.jpg" },
    ]);
    expect(componer).not.toHaveBeenCalled();
    await act(async () => {
      vi.advanceTimersByTime(1200);
    });
    expect(componer).toHaveBeenCalledWith("pub-1", {
      foto: "f.jpg",
      titular: "Editado",
      plantilla_id: "",
      foto_encuadre: "",
      sin_plantilla: false,
    });
    vi.useRealTimers();
    // Tras hornear, fija el objeto horneado en ese slide (sin tocar la receta).
    await waitFor(() =>
      expect(espia).toHaveBeenCalledWith([
        { tipo: "imagen", objeto: "artes/nuevo.png", titular: "Editado", foto: "f.jpg" },
      ]),
    );
  });
});
