import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CadenaAprobacion as TCadena, NivelAprobacion } from "@/types";

import { CadenaAprobacion } from "./CadenaAprobacion";

/** Construye un nivel con valores por defecto razonables (sobreescribibles). */
function nivel(over: Partial<NivelAprobacion>): NivelAprobacion {
  return {
    id: "n?",
    pieza_id: "p1",
    publicacion_id: "c1",
    nivel: 1,
    etiqueta: "Edición",
    decision: "pendiente",
    decisor_id: "",
    decisor_nombre: "",
    comentario: "",
    creado: "",
    decidido_en: "",
    cargo_requerido: "",
    ...over,
  };
}

/** Cadena de los dos OK: Edición (OK de Ana) → Coordinación (el OK que toca ahora). */
function cadenaOK(over: Partial<TCadena> = {}): TCadena {
  return {
    niveles: [
      nivel({ id: "n1", nivel: 1, etiqueta: "Edición", decision: "aprobado", decisor_id: "ana", decisor_nombre: "Ana" }),
      nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación" }),
    ],
    estado: "pendiente",
    nivel_actual: "n2",
    aprobados: 1,
    minimo_aprobaciones: 0,
    comentarios_sin_resolver: 0,
    ...over,
  };
}

function renderCadena(cadena: TCadena) {
  return render(<CadenaAprobacion cadena={cadena} />);
}

describe("CadenaAprobacion · panel de estado (solo lectura)", () => {
  it("muestra cuántos OK van (solo el conteo) y de quién, sin texto de 'faltan'", () => {
    renderCadena(cadenaOK());
    expect(screen.getByText("1/2")).toBeInTheDocument();
    expect(screen.getByText(/Ana/)).toBeInTheDocument();
    expect(screen.queryByText(/Faltan/i)).not.toBeInTheDocument();
  });

  it("NO pinta el revision de IA (menos IA de cara al equipo): ni 'IA: …' ni el nivel verificación", () => {
    // La cadena trae el nivel automático «revision» (revisión IA) aprobado; NO debe pintarse como badge.
    const c = cadenaOK({
      niveles: [
        nivel({ id: "revision", nivel: 0, etiqueta: "revision", decision: "aprobado" }),
        nivel({ id: "n1", nivel: 1, etiqueta: "Edición", decision: "aprobado", decisor_id: "ana", decisor_nombre: "Ana" }),
        nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación" }),
      ],
    });
    renderCadena(c);
    expect(screen.queryByText(/^IA:/)).not.toBeInTheDocument();
    expect(screen.queryByText("IA: lista")).not.toBeInTheDocument();
    // El nivel verificación se excluye del conteo de OK humanos: siguen siendo 1/2 (Ana + Coordinación).
    expect(screen.getByText("1/2")).toBeInTheDocument();
  });

  it("NO renderiza botones de acción (la acción vive en la fila del post; el override de forzar, en el toast del primer OK)", () => {
    renderCadena(cadenaOK());
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByText(/forzar/i)).not.toBeInTheDocument();
  });

  it("con comentarios sin resolver añade la línea de bloqueo dentro del panel", () => {
    render(<CadenaAprobacion cadena={cadenaOK()} sinResolver={2} />);
    expect(screen.getByText(/Resuelve 2 comentarios antes de publicar/)).toBeInTheDocument();
  });

  it("cadena RECHAZADA: lo señala", () => {
    const c = cadenaOK({
      niveles: [
        nivel({ id: "n1", nivel: 1, etiqueta: "Edición", decision: "rechazado", decisor_nombre: "Ana" }),
        nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación" }),
      ],
      estado: "rechazado",
      nivel_actual: "",
    });
    renderCadena(c);
    expect(screen.getByText(/^Rechazada$/i)).toBeInTheDocument();
  });

  it("cadena TOTALMENTE aprobada: «Lista para publicar» y 2/2", () => {
    const c = cadenaOK({
      niveles: [
        nivel({ id: "n1", nivel: 1, etiqueta: "Edición", decision: "aprobado", decisor_id: "ana", decisor_nombre: "Ana" }),
        nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación", decision: "aprobado", decisor_id: "leo", decisor_nombre: "Leo" }),
      ],
      estado: "aprobado",
      nivel_actual: "",
    });
    renderCadena(c);
    expect(screen.getByText(/lista para publicar/i)).toBeInTheDocument();
    expect(screen.getByText("2/2")).toBeInTheDocument();
  });

  it("umbral de marca: cadena de 2 niveles con minimo_aprobaciones=1 pinta '0/1', no '0/2'", () => {
    // Pieza de una marca que solo pide UN OK (p. ej. `fundacion`) pero con una cadena LEGADA de
    // dos niveles humanos. El denominador es el umbral de la marca (1), no los niveles (2).
    const c = cadenaOK({
      niveles: [
        nivel({ id: "n1", nivel: 1, etiqueta: "Edición" }),
        nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación" }),
      ],
      estado: "pendiente",
      nivel_actual: "n1",
      minimo_aprobaciones: 1,
    });
    renderCadena(c);
    expect(screen.getByText("0/1")).toBeInTheDocument();
    expect(screen.queryByText("0/2")).not.toBeInTheDocument();
  });

  it("umbral de marca: con 1 OK y minimo_aprobaciones=1 pinta '1/1' y «Lista para publicar»", () => {
    const c = cadenaOK({
      niveles: [
        nivel({ id: "n1", nivel: 1, etiqueta: "Edición", decision: "aprobado", decisor_id: "ana", decisor_nombre: "Ana" }),
        nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación" }),
      ],
      estado: "aprobado",
      nivel_actual: "",
      minimo_aprobaciones: 1,
    });
    renderCadena(c);
    expect(screen.getByText("1/1")).toBeInTheDocument();
    expect(screen.getByText(/lista para publicar/i)).toBeInTheDocument();
  });

  it("acota la X mostrada al umbral: 2 OK con minimo_aprobaciones=1 no pinta '2/1'", () => {
    const c = cadenaOK({
      niveles: [
        nivel({ id: "n1", nivel: 1, etiqueta: "Edición", decision: "aprobado", decisor_id: "ana", decisor_nombre: "Ana" }),
        nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación", decision: "aprobado", decisor_id: "leo", decisor_nombre: "Leo" }),
      ],
      estado: "aprobado",
      nivel_actual: "",
      minimo_aprobaciones: 1,
    });
    renderCadena(c);
    expect(screen.getByText("1/1")).toBeInTheDocument();
    expect(screen.queryByText("2/1")).not.toBeInTheDocument();
  });

  it("con la Crítica IA aprobada muestra su like (3er OK, el de la máquina), no solo el desenlace", () => {
    const c = cadenaOK({
      niveles: [
        nivel({ id: "n1", nivel: 1, etiqueta: "Edición", decision: "aprobado", decisor_id: "ana", decisor_nombre: "Ana" }),
        nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación", decision: "aprobado", decisor_id: "leo", decisor_nombre: "Leo" }),
        nivel({ id: "ia", nivel: 3, etiqueta: "Crítica IA", decision: "aprobado", cargo_requerido: "ia-critico", decisor_nombre: "Crítica IA" }),
      ],
      estado: "aprobado",
      nivel_actual: "",
    });
    renderCadena(c);
    expect(screen.getByText(/Crítica IA: aprobada/i)).toBeInTheDocument();
    expect(screen.getByText(/lista para publicar/i)).toBeInTheDocument();
    // El nivel IA NO cuenta como OK humano: siguen siendo 2/2.
    expect(screen.getByText("2/2")).toBeInTheDocument();
  });
});
