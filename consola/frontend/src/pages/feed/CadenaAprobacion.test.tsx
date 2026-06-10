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

function renderCadena(cadena: TCadena, veredictoIA?: string) {
  return render(<CadenaAprobacion cadena={cadena} veredictoIA={veredictoIA} />);
}

describe("CadenaAprobacion · panel de estado (solo lectura)", () => {
  it("muestra cuántos OK van (solo el conteo) y de quién, sin texto de 'faltan'", () => {
    renderCadena(cadenaOK());
    expect(screen.getByText("1/2")).toBeInTheDocument();
    expect(screen.getByText(/Ana/)).toBeInTheDocument();
    // La explicación "Faltan X OK…" se quitó (el conteo basta).
    expect(screen.queryByText(/Faltan/i)).not.toBeInTheDocument();
  });

  it("pinta el veredicto de IA cuando hay, como badge SIN emoji", () => {
    renderCadena(cadenaOK(), "listo");
    expect(screen.getByText("IA: lista")).toBeInTheDocument();
    // El veredicto va como Badge ok/aviso/error (icono + color), no triple-codificado con emoji.
    expect(document.body.textContent).not.toContain("🟢");
  });

  it("NO renderiza botones de acción (la acción vive en la fila del post)", () => {
    renderCadena(cadenaOK());
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("cadena RECHAZADA: explica que vuelve a redacción", () => {
    const c = cadenaOK({
      niveles: [
        nivel({ id: "n1", nivel: 1, etiqueta: "Edición", decision: "rechazado", decisor_nombre: "Ana" }),
        nivel({ id: "n2", nivel: 2, etiqueta: "Coordinación" }),
      ],
      estado: "rechazado",
      nivel_actual: "",
    });
    renderCadena(c);
    expect(screen.getByText(/vuelve a la redacción/i)).toBeInTheDocument();
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
