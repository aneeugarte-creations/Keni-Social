/**
 * Tests del carrusel lateral editable: navegación entre slides + gestión (añadir/quitar/mover)
 * + horneado debounced de los slides extra al editar su receta.
 *
 * EditorPlacaInline (lienzo + fuentes) y GaleriaPlantillas se MOCKEAN por un stub ligero que
 * expone los callbacks como botones: así probamos el cableado del carrusel, no el lienzo.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EditorCarruselLateral } from "./EditorCarruselLateral";
import { api } from "@/lib/api";
import type { SlideCarrusel } from "@/lib/carrusel";

// Los avisos de un intercambio con la portada BLOQUEADO (video / collage) se asertan.
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

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

  it("'Carrusel' fuerza el guardado de la portada ANTES de pedir su composite", async () => {
    const orden: string[] = [];
    const onGuardarPortada = vi.fn(async () => {
      orden.push("guardar");
    });
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      if (String(url).includes("/compuesta")) orden.push("compuesta");
      return Promise.resolve({ ok: true, blob: async () => new Blob(["x"]) });
    });
    vi.stubGlobal("fetch", fetchSpy);
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    render(
      <EditorCarruselLateral
        {...BASE}
        slides={[]}
        onSlides={vi.fn()}
        onGuardarPortada={onGuardarPortada}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Descargar carrusel" }));

    await waitFor(() => expect(onGuardarPortada).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(orden).toEqual(["guardar", "compuesta"]));
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

  // --- Frontera con la PORTADA: mover el slide 2 al frente intercambia RECETAS --- //

  it("mover el slide 2 a la izquierda lo asciende a portada y baja la portada al puesto 2", async () => {
    const componer = vi.spyOn(api, "componerSlide").mockResolvedValue({
      id: "artes/portada-abajo.png",
      url: "/api/media/artes/portada-abajo.png",
    });
    const { onSlides } = renderLateral([
      { tipo: "imagen", objeto: "s2.png", titular: "Clave 2", foto: "f2.jpg" },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Slide siguiente" }));
    fireEvent.click(screen.getByRole("button", { name: "Mover slide a la izquierda" }));

    // La portada que baja se HORNEA antes de tocar el estado: un slide sin `objeto` lo
    // descarta `serializarCarrusel`, así que un guardado a medias la perdería.
    await waitFor(() =>
      expect(componer).toHaveBeenCalledWith("pub-1", {
        foto: "portada.jpg",
        titular: "Titular portada",
        plantilla_id: "",
        foto_encuadre: "",
        sin_plantilla: false,
      }),
    );
    // El slide asciende: su receta pasa a ser la de la portada.
    await waitFor(() => expect(BASE.onPortadaCopyIn).toHaveBeenCalledWith("Clave 2"));
    expect(BASE.onPortadaFotos).toHaveBeenCalledWith([{ objeto: "f2.jpg", foco: null, zoom: 0 }]);
    // La vieja portada queda de slide 2, con su media ya horneado.
    expect(onSlides).toHaveBeenCalledWith([
      {
        tipo: "imagen",
        objeto: "artes/portada-abajo.png",
        foto: "portada.jpg",
        titular: "Titular portada",
        plantillaId: "",
        fotoEncuadre: "",
        sinPlaca: false,
      },
    ]);
  });

  it("desde la portada, mover a la derecha la baja al puesto 2 y sigue al slide movido", async () => {
    vi.spyOn(api, "componerSlide").mockResolvedValue({
      id: "artes/x.png",
      url: "/api/media/artes/x.png",
    });
    renderLateral([{ tipo: "imagen", objeto: "s2.png", titular: "Clave 2", foto: "f2.jpg" }]);
    // En la portada no hay nada a la izquierda; a la derecha sí.
    expect(screen.getByRole("button", { name: "Mover slide a la izquierda" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Mover slide a la derecha" }));
    await waitFor(() => expect(screen.getByText("Slide 2")).toBeInTheDocument());
  });

  it("un video no puede ascender a portada: avisa y no toca nada", () => {
    const componer = vi.spyOn(api, "componerSlide");
    const { onSlides } = renderLateral([{ tipo: "video", objeto: "v.mp4" }]);
    fireEvent.click(screen.getByRole("button", { name: "Slide siguiente" }));
    fireEvent.click(screen.getByRole("button", { name: "Mover slide a la izquierda" }));
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("video"));
    expect(componer).not.toHaveBeenCalled();
    expect(onSlides).not.toHaveBeenCalled();
    expect(BASE.onPortadaFotos).not.toHaveBeenCalled();
  });

  it("con la portada en collage de varias fotos el intercambio se bloquea (un slide guarda una)", () => {
    const componer = vi.spyOn(api, "componerSlide");
    const onSlides = vi.fn();
    render(
      <EditorCarruselLateral
        {...BASE}
        portadaFotos={[
          { objeto: "a.jpg", foco: null, zoom: 0 },
          { objeto: "b.jpg", foco: null, zoom: 0 },
        ]}
        slides={[{ tipo: "imagen", objeto: "s2.png", titular: "Clave 2", foto: "f2.jpg" }]}
        onSlides={onSlides}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Slide siguiente" }));
    fireEvent.click(screen.getByRole("button", { name: "Mover slide a la izquierda" }));
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("collage"));
    expect(componer).not.toHaveBeenCalled();
    expect(onSlides).not.toHaveBeenCalled();
  });
});
