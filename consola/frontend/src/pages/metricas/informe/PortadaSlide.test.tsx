import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PortadaSlide } from "./Informe";
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
    expect(img?.getAttribute("src")).toMatch(/claro-sports/);
  });
});
