/**
 * VistaRevisarCambios: overlay a pantalla completa (estilo Pull Request) con el diff de
 * prosa como protagonista. Modo "lectura" (solo diff) y modo "publicar" (pie con nota
 * obligatoria + acción), con la etiqueta según rol y el envío de la nota recortada.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { VistaRevisarCambios } from "./VistaRevisarCambios";

const ANTES = "El copy debe ser corto.";
const DESPUES = "El copy debe ser largo.";

describe("VistaRevisarCambios", () => {
  it("modo lectura: muestra título, subtítulo y diff; sin nota ni acción", () => {
    render(
      <VistaRevisarCambios
        abierto
        onCerrar={() => {}}
        titulo="Revisar cambios"
        subtitulo="Solicitud de Ana"
        antes={ANTES}
        despues={DESPUES}
      />,
    );
    expect(screen.getByText("Revisar cambios")).toBeInTheDocument();
    expect(screen.getByText("Solicitud de Ana")).toBeInTheDocument();
    // El diff (DiffProsa) marca lo borrado y lo añadido.
    expect(document.querySelector("del")?.textContent).toBe("corto.");
    expect(document.querySelector("ins")?.textContent).toBe("largo.");
    // En lectura no hay pie de publicación.
    expect(screen.queryByText(/Nota del cambio/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Publicar cambios/ })).not.toBeInTheDocument();
  });

  it("modo publicar (admin): acción deshabilitada sin nota y envía la nota recortada", () => {
    const onEnviar = vi.fn();
    render(
      <VistaRevisarCambios
        abierto
        onCerrar={() => {}}
        titulo="Revisar y publicar"
        antes={ANTES}
        despues={DESPUES}
        modo="publicar"
        esAdmin
        onEnviar={onEnviar}
      />,
    );
    const accion = screen.getByRole("button", { name: /Publicar cambios/ });
    expect(accion).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText("Qué cambia y por qué"), {
      target: { value: "  tono más directo  " },
    });
    expect(accion).toBeEnabled();
    fireEvent.click(accion);
    expect(onEnviar).toHaveBeenCalledWith("tono más directo");
  });

  it("modo publicar (no admin): la acción es 'Solicitar publicación'", () => {
    render(
      <VistaRevisarCambios
        abierto
        onCerrar={() => {}}
        titulo="Revisar y solicitar"
        antes={ANTES}
        despues={DESPUES}
        modo="publicar"
        esAdmin={false}
        onEnviar={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: /Solicitar publicación/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Publicar cambios/ })).not.toBeInTheDocument();
  });

  it("usa renderDiff cuando se provee (carga diferida), pasándole el toggle 'Solo cambios'", () => {
    render(
      <VistaRevisarCambios
        abierto
        onCerrar={() => {}}
        titulo="Revisar cambios"
        renderDiff={(soloCambios) => (
          <span>solo-cambios:{String(soloCambios)}</span>
        )}
      />,
    );
    // Arranca en "solo cambios".
    expect(screen.getByText("solo-cambios:true")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch", { name: "Solo cambios" }));
    expect(screen.getByText("solo-cambios:false")).toBeInTheDocument();
  });
});
