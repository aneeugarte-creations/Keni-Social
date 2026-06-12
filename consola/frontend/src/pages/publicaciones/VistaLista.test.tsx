import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as apiMod from "@/lib/api";
import type { Publicacion } from "@/types";

import { VistaLista } from "./VistaLista";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

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
    fuente_original: "",
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

  it("borra en lote SOLO las seleccionadas (UNA llamada batch) tras confirmar", async () => {
    const borrar = vi
      .spyOn(apiMod.api, "borrarPublicacionesLote")
      .mockResolvedValue({ borradas: 2, fallos: [] });
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

    // UN solo round-trip con las ids seleccionadas (no un DELETE por pieza).
    await waitFor(() => expect(borrar).toHaveBeenCalledTimes(1));
    expect([...borrar.mock.calls[0][0]].sort()).toEqual(["p1", "p3"]);
  });

  it("reparto ClaroSports: una pieza libre ofrece 'Coger' y llama al claim del tema padre", async () => {
    const coger = vi
      .spyOn(apiMod.api, "cogerContenido")
      .mockResolvedValue({ contenido: {} } as never);
    renderLista([
      pub({ id: "p1", contenido_id: "c9", titulo: "Gol", marca: "claro-sports" }),
    ]);

    // Nombre EXACTO: el menú contextual también ofrece "Coger (me la asigno)".
    const boton = screen.getByRole("button", { name: "Coger" });
    fireEvent.click(boton);
    await waitFor(() => expect(coger).toHaveBeenCalledTimes(1));
    expect(coger).toHaveBeenCalledWith("c9");
  });

  it("reparto ClaroSports: una pieza cogida por otra persona muestra su badge y NO ofrece coger", () => {
    renderLista([
      pub({
        id: "p1",
        titulo: "Gol",
        marca: "claro-sports",
        responsable_id: "u-mariana",
        responsable_nombre: "Mariana",
      } as Partial<Publicacion>),
    ]);
    expect(screen.getByText("Mariana")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Coger/ })).toBeNull();
  });

  it("reparto: las piezas de otras marcas NO llevan botón de coger (flujo sin reparto)", () => {
    renderLista([pub({ id: "p1", titulo: "Nota", marca: "unotv" })]);
    expect(screen.queryByRole("button", { name: /Coger/ })).toBeNull();
  });

  it("reporta los fallos parciales del lote (toast de error con el resumen)", async () => {
    vi.spyOn(apiMod.api, "borrarPublicacionesLote").mockResolvedValue({
      borradas: 1,
      fallos: ["p3"],
    });
    renderLista([pub({ id: "p1", titulo: "Uno" }), pub({ id: "p3", titulo: "Tres" })]);

    fireEvent.click(screen.getByRole("checkbox", { name: /Seleccionar "Uno"/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /Seleccionar "Tres"/ }));
    fireEvent.click(screen.getByRole("button", { name: /^Borrar 2$/ }));
    const dialogo = await screen.findByRole("dialog");
    fireEvent.click(within(dialogo).getByRole("button", { name: /^Borrar 2$/ }));

    const { toast } = await import("sonner");
    await waitFor(() =>
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith(
        expect.stringContaining("Borradas 1 de 2"),
      ),
    );
  });
});
