import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Informe, PortadaSlide } from "./Informe";
import { desdeEntradas, type ContextoInforme } from "./desdeEntradas";
import { LOGOS_MARCA } from "./logos";

// ctx EXACTO que envía Descargas.tsx en producción: el id de métricas usa guion_bajo
// (`claro_sports`), mientras que LOGOS_MARCA/COVER_LAYOUT usan guion (`claro-sports`).
const CTX_PROD: ContextoInforme = {
  marca: "Claro Sports",
  red: "Todas las redes",
  formato: "Todos los formatos",
  periodo: "junio 2026",
  marcaId: "claro_sports",
};

describe("PortadaSlide · logo de marca", () => {
  it("el id de métricas (guion_bajo) resuelve un asset en LOGOS_MARCA", () => {
    const props = desdeEntradas([], CTX_PROD);
    expect(props.marcaId).toBe("claro-sports");
    expect(LOGOS_MARCA[props.marcaId ?? ""]).toBeTruthy();
  });

  it("la portada de Claro Sports pinta un <img> de logo, no el wordmark", () => {
    const props = desdeEntradas([], CTX_PROD);
    const { container } = render(
      <PortadaSlide
        marcaId={props.marcaId}
        marcaLabel={props.marcaLabel}
        esTodas={props.esTodas}
        periodo={props.periodo}
      />,
    );
    const img = container.querySelector("img");
    expect(img, "la portada debe contener un <img> de logo").not.toBeNull();
    expect(img?.getAttribute("alt")).toBe("Claro Sports");
    // El logo viaja incrustado (`?inline`): un data-URI no puede dar 404 al rasterizar.
    expect(img?.getAttribute("src")).toMatch(/^data:image\//);
  });
});

describe("PortadaSlide · anatomía AIRE", () => {
  it("el eyebrow arriba lleva el periodo", () => {
    const props = desdeEntradas([], CTX_PROD);
    const { getByText } = render(
      <PortadaSlide
        marcaId={props.marcaId}
        marcaLabel={props.marcaLabel}
        esTodas={props.esTodas}
        periodo={props.periodo}
      />,
    );
    expect(getByText(new RegExp(`Informe de métricas .* ${props.periodo}`))).toBeInTheDocument();
  });

  it("firma «keni» en el pie", () => {
    const props = desdeEntradas([], CTX_PROD);
    const { getByText } = render(
      <PortadaSlide
        marcaId={props.marcaId}
        marcaLabel={props.marcaLabel}
        esTodas={props.esTodas}
        periodo={props.periodo}
      />,
    );
    expect(getByText("keni")).toBeInTheDocument();
  });

  it("la portada NO pinta el veredicto del mes (gobierna la lámina de resumen, no la portada)", () => {
    const props = desdeEntradas([], CTX_PROD);
    const { queryByText } = render(
      <PortadaSlide
        marcaId={props.marcaId}
        marcaLabel={props.marcaLabel}
        esTodas={props.esTodas}
        periodo={props.periodo}
      />,
    );
    expect(props.titularMes).toBeTruthy();
    expect(queryByText(props.titularMes)).toBeNull();
  });

  it("la portada-portfolio anuncia «Todas las marcas» en su eyebrow", () => {
    const props = desdeEntradas([], { ...CTX_PROD, marca: "Todas las marcas", marcaId: undefined });
    const { getByText } = render(
      <PortadaSlide
        marcaId={props.marcaId}
        marcaLabel={props.marcaLabel}
        esTodas={props.esTodas}
        periodo={props.periodo}
      />,
    );
    expect(props.esTodas).toBe(true);
    expect(getByText(/Todas las marcas/)).toBeInTheDocument();
  });
});

describe("Marco · periodo en la cabecera de cada lámina", () => {
  it("las láminas de contenido llevan el periodo en su eyebrow (autoexplicativas si se reenvían)", () => {
    const props = desdeEntradas([], CTX_PROD);
    const { container } = render(<Informe data={props} />);
    // El eyebrow de cada lámina de contenido es el primer <p> de su <header> (etiqueta · periodo);
    // el resumen es la primera lámina de contenido, así que al menos uno debe estar.
    const eyebrows = Array.from(container.querySelectorAll("header")).map(
      (h) => h.querySelector("p")?.textContent ?? "",
    );
    expect(eyebrows.length).toBeGreaterThan(0);
    for (const texto of eyebrows) {
      expect(texto).toContain(props.periodo);
    }
  });
});
