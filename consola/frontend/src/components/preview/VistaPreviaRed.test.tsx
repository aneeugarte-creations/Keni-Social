import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VistaPreviaRed } from "./VistaPreviaRed";

/**
 * Copy del feed estilo red social (variante "limpia"): recortado a 2 líneas con un enlace
 * "más"/"menos" cuando el texto desborda. jsdom no calcula layout, así que forzamos que el
 * párrafo "desborde" (scrollHeight > clientHeight) para ejercitar el recorte y el toggle.
 */
describe("VistaPreviaRed · copy con 'leer más' (feed limpio)", () => {
  const origScroll = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollHeight");
  const origClient = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight");

  beforeEach(() => {
    // El párrafo (recortado a 2 líneas) reporta más alto real que el visible -> hay "más".
    Object.defineProperty(HTMLElement.prototype, "scrollHeight", { configurable: true, get: () => 100 });
    Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 40 });
  });
  afterEach(() => {
    if (origScroll) Object.defineProperty(HTMLElement.prototype, "scrollHeight", origScroll);
    if (origClient) Object.defineProperty(HTMLElement.prototype, "clientHeight", origClient);
  });

  it("recorta el copy y alterna al pulsar el área de texto (botón «más»/«menos»)", () => {
    render(
      <VistaPreviaRed
        red="instagram"
        marca="UnoTV"
        contenido={"línea uno\nlínea dos\nlínea tres\nlínea cuatro"}
        variante="limpia"
      />,
    );
    // Sin onAbrir el único role=button es el «más/menos» (con aria-expanded); muestra "más" plegado.
    const toggle = screen.getByRole("button");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("más")).toBeInTheDocument();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("menos")).toBeInTheDocument();
  });

  it("plegado CONTROLADO: clic en el caption llama a onAlternarCaption (no gestiona su estado)", () => {
    const onAlternar = vi.fn();
    const { rerender } = render(
      <VistaPreviaRed
        red="instagram"
        marca="UnoTV"
        contenido={"línea uno\nlínea dos\nlínea tres\nlínea cuatro"}
        variante="limpia"
        captionExpandido={false}
        onAlternarCaption={onAlternar}
      />,
    );
    // El botón refleja el prop (plegado) y al pulsarlo NO togglea solo: avisa al padre.
    const toggle = screen.getByRole("button");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(onAlternar).toHaveBeenCalledTimes(1);
    // El padre decide; al pasar expandido=true, el botón pasa a "menos".
    rerender(
      <VistaPreviaRed
        red="instagram"
        marca="UnoTV"
        contenido={"línea uno\nlínea dos\nlínea tres\nlínea cuatro"}
        variante="limpia"
        captionExpandido={true}
        onAlternarCaption={onAlternar}
      />,
    );
    expect(screen.getByText("menos")).toBeInTheDocument();
  });

  it("plegado, los enlaces del copy salen del tab-order; al expandir con «más» vuelven", () => {
    render(
      <VistaPreviaRed
        red="instagram"
        marca="UnoTV"
        contenido={"mira https://ejemplo.mx/nota\nlínea dos\nlínea tres"}
        variante="limpia"
      />,
    );
    // Con el clamp puesto el enlace puede quedar oculto: focus ring en un punto invisible.
    const enlace = screen.getByRole("link");
    expect(enlace).toHaveAttribute("tabindex", "-1");
    // El usuario de teclado expande con el botón "más" (tabulable); los enlaces entran al foco.
    fireEvent.click(screen.getByText("más"));
    expect(enlace).not.toHaveAttribute("tabindex");
  });

  it("con onAbrir hace la IMAGEN interactiva (sin etiqueta «editar»)", () => {
    const onAbrir = vi.fn();
    render(
      <VistaPreviaRed
        red="instagram"
        marca="UnoTV"
        contenido={"línea uno\nlínea dos\nlínea tres\nlínea cuatro"}
        variante="limpia"
        onAbrir={onAbrir}
      />,
    );
    // La imagen abre la pieza y su nombre accesible ya no dice "editar", solo "Abrir".
    fireEvent.click(screen.getByRole("button", { name: "Abrir" }));
    expect(onAbrir).toHaveBeenCalledTimes(1);
  });
});

/**
 * Carrusel DESLIZABLE de la variante limpia (piezas `formato='carrusel'`): con slides
 * (`carrusel` JSON), la tarjeta pinta el strip portada+slides con contador "n/N", los
 * slides en crudo (img/video): la portada y los slides de IMAGEN abren el editor; los
 * slides de VIDEO no (el clic controla su reproducción).
 */
describe("VistaPreviaRed · carrusel deslizable (feed limpio)", () => {
  const SLIDES =
    '[{"tipo":"imagen","objeto":"s2.jpg"},{"tipo":"video","objeto":"videos/s3.mp4"}]';

  it("pinta portada + slides con contador; portada e imagen abren el editor, el video no", () => {
    const onAbrir = vi.fn();
    const { container } = render(
      <VistaPreviaRed
        red="instagram"
        marca="UnoTV"
        contenido="copy del carrusel"
        imagen_url="/api/media/portada.png"
        carrusel={SLIDES}
        titulo="Nota de presidencia"
        variante="limpia"
        onAbrir={onAbrir}
      />,
    );
    // Strip con rol de carrusel y 3 slides (portada + 2 en crudo).
    const strip = screen.getByRole("group", { name: /Carrusel de 3 slides/ });
    expect(strip).toBeInTheDocument();
    expect(screen.getByText("1/3")).toBeInTheDocument();
    // El slide de imagen en crudo se sirve por /api/media; el de video lleva <video>.
    expect(
      container.querySelector('img[src="/api/media/s2.jpg"]'),
    ).toBeInTheDocument();
    expect(container.querySelector("video")).not.toBeNull();
    // La portada abre el editor.
    fireEvent.click(
      screen.getByRole("button", { name: "Abrir: Nota de presidencia" }),
    );
    expect(onAbrir).toHaveBeenCalledTimes(1);
    // El slide de IMAGEN (no portada) también abre el editor al hacer clic.
    fireEvent.click(
      screen.getByRole("button", {
        name: "Abrir: Nota de presidencia (slide 2 de 3)",
      }),
    );
    expect(onAbrir).toHaveBeenCalledTimes(2);
    // El slide de VIDEO no es interactivo (no abre el editor): solo hay 2 botones de
    // apertura (portada + imagen), no uno por el video.
    expect(
      screen.getAllByRole("button", { name: /^Abrir/ }),
    ).toHaveLength(2);
  });

  it("sin slides (carrusel vacío o ilegible) cae a la imagen única de siempre", () => {
    render(
      <VistaPreviaRed
        red="instagram"
        marca="UnoTV"
        contenido="copy normal"
        imagen_url="/api/media/foto.png"
        carrusel=""
        variante="limpia"
      />,
    );
    expect(screen.queryByRole("group")).toBeNull();
    expect(screen.queryByText(/1\//)).toBeNull();
  });
});
