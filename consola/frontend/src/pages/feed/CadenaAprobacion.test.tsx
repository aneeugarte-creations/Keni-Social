import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CadenaAprobacion as TCadena, NivelAprobacion } from "@/types";

import { CadenaAprobacion } from "./CadenaAprobacion";

/** Construye un nivel con valores por defecto razonables (sobreescribibles). */
function nivel(over: Partial<NivelAprobacion>): NivelAprobacion {
  return {
    id: "n?",
    plataforma_id: "p1",
    contenido_id: "c1",
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

  it("NO pinta el revision de IA (menos IA de cara al equipo): ni 'IA: …' ni el nivel QA", () => {
    // La cadena trae el nivel automático «QA Editorial» aprobado; NO debe pintarse como badge.
    const c = cadenaOK({
      niveles: [
        nivel({ id: "qa", nivel: 0, etiqueta: "QA Editorial", decision: "aprobado" }),
        nivel({ id: "n1", nivel: 1, etiqueta: "Edición", decision: "aprobado", decisor_id: "ana", decisor_nombre: "Ana" }),
        nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación" }),
      ],
    });
    renderCadena(c);
    expect(screen.queryByText(/^IA:/)).not.toBeInTheDocument();
    expect(screen.queryByText("IA: lista")).not.toBeInTheDocument();
    // El nivel QA se excluye del conteo de OK humanos: siguen siendo 1/2 (Ana + Coordinación).
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
});
