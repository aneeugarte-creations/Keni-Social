import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as apiMod from "@/lib/api";
import type { Publicacion } from "@/types";

import { VistaLista } from "./VistaLista";

/** Una `Publicacion` mínima viable (los campos que VistaLista/Tarjeta leen). */
function pub(over: Partial<Publicacion> = {}): Publicacion {
  return {
    id: "p1",
    contenido_id: "c1",
    titulo: "Tema",
    marca: "piso-15",
    marca_nombre: "Piso 15",
    red: "x",
    red_nombre: "X",
    contenido: "Copy.",
    copy_in: "",
    estado: "pendiente",
    veredicto: "",
    autor_id: "",
    autor_nombre: "",
    enviado_a_revision_en: "",
    revisor_id: "",
    revisor_nombre: "",
    revisado_en: "",
    preparado_en: "",
    id_post_metricool: "",
    tipo_contenido: "ia",
    formato: "foto",
    imagen_fuente: "",
    foto: "",
    falta_copy: false,
    falta_imagen: true,
    falta_revision: true,
    falta_publicar: true,
    falta_video: false,
    video: "",
    fecha_creacion: "",
    fecha_actualizacion: "",
    fecha_programada: "",
    fecha_fuente: "",
    origen: "pipeline",
    imagen: "",
    imagen_url: "",
    evergreen: false,
    etapa_ia: "generando_arte",
    ...over,
  } as Publicacion;
}

function renderLista(publicaciones: Publicacion[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <VistaLista
          publicaciones={publicaciones}
          onEditar={vi.fn()}
          onDuplicar={vi.fn()}
          onConfigurarCadencia={vi.fn()}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("VistaLista — selección múltiple y borrado en masa", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sin selección no muestra la barra de borrado en masa", () => {
    renderLista([pub()]);
    expect(screen.queryByRole("button", { name: /^Borrar \d/ })).toBeNull();
  });

  it("al seleccionar aparece la barra y 'Seleccionar todo' marca todas", () => {
    renderLista([pub({ id: "p1", titulo: "Uno" }), pub({ id: "p2", titulo: "Dos" })]);
    fireEvent.click(screen.getByRole("checkbox", { name: /Seleccionar "Uno"/ }));
    expect(screen.getByText("1 seleccionada")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Seleccionar todo/ }));
    expect(screen.getByText("2 seleccionadas")).toBeInTheDocument();
  });

  it("borra en lote SOLO las seleccionadas (un DELETE por pieza) tras confirmar", async () => {
    const borrar = vi
      .spyOn(apiMod.api, "eliminarPublicacion")
      .mockResolvedValue({ mensaje: "ok" } as never);
    renderLista([
      pub({ id: "p1", titulo: "Uno" }),
      pub({ id: "p2", titulo: "Dos" }),
      pub({ id: "p3", titulo: "Tres" }),
    ]);

    fireEvent.click(screen.getByRole("checkbox", { name: /Seleccionar "Uno"/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /Seleccionar "Tres"/ }));

    // Abre el diálogo de confirmación desde la barra y confirma dentro de él.
    fireEvent.click(screen.getByRole("button", { name: /^Borrar 2$/ }));
    const dialogo = await screen.findByRole("dialog");
    fireEvent.click(within(dialogo).getByRole("button", { name: /^Borrar 2$/ }));

    await waitFor(() => expect(borrar).toHaveBeenCalledTimes(2));
    const ids = borrar.mock.calls.map((c) => c[0]).sort();
    expect(ids).toEqual(["p1", "p3"]);
  });
});
