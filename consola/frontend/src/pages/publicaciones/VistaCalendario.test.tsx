import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as apiMod from "@/lib/api";
import type { Publicacion } from "@/types";

import { VistaCalendario, rangoVisibleCalendario } from "./VistaCalendario";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

/** Una `Publicacion` mínima viable (los campos que VistaCalendario/PildoraPub leen). */
function pub(over: Partial<Publicacion> = {}): Publicacion {
  return {
    id: "p1",
    contenido_id: "c1",
    pipeline_id: "",
    titulo: "Gol",
    marca: "claro-sports",
    marca_nombre: "Claro Sports",
    red: "x",
    red_nombre: "X",
    contenido: "Copy.",
    copy_in: "",
    estado: "programado",
    veredicto: "",
    autor_id: "",
    autor_nombre: "",
    responsable_id: "",
    responsable_nombre: "",
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
    fecha_programada: "2026-06-15T18:00",
    fecha_fuente: "",
    fuente_original: "",
    origen: "pipeline",
    imagen: "",
    imagen_url: "",
    evergreen: false,
    etapa_ia: "generando_arte",
    ...over,
  };
}

function renderCalendario(publicaciones: Publicacion[], onEditar = vi.fn(), ancla?: Date) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      {/* marca sin pasar (undefined) => la query de franjas queda DESHABILITADA: sin red. */}
      <VistaCalendario publicaciones={publicaciones} onEditar={onEditar} ancla={ancla} />
    </QueryClientProvider>,
  );
  return { onEditar };
}

describe("VistaCalendario — sello «libre» (coger en táctil) y aviso sin fecha", () => {
  afterEach(() => vi.restoreAllMocks());

  it("click en el sello «libre» llama a cogerContenido (tema padre) y NO abre el editor", async () => {
    const coger = vi
      .spyOn(apiMod.api, "cogerContenido")
      .mockResolvedValue({ contenido: {} } as never);
    // La pieza está programada el 2026-06-15 (CDMX): anclamos esa semana para que se pinte.
    const { onEditar } = renderCalendario(
      [pub({ contenido_id: "c9", titulo: "Gol" })],
      vi.fn(),
      new Date(2026, 5, 15),
    );
    // En vista MES solo hay conteos; pasamos a SEMANA, donde la píldora (y su sello) se ven.
    fireEvent.click(screen.getByRole("button", { name: "semana" }));

    const sello = screen.getByRole("button", { name: 'Coger "Gol" (me la asigno)' });
    fireEvent.click(sello);

    await waitFor(() => expect(coger).toHaveBeenCalledTimes(1));
    expect(coger).toHaveBeenCalledWith("c9");
    // stopPropagation: tocar el sello NO debe abrir el editor de la pieza.
    expect(onEditar).not.toHaveBeenCalled();
  });

  it("Enter/Espacio sobre el sello «libre» también cogen la pieza (accesible por teclado)", async () => {
    const coger = vi
      .spyOn(apiMod.api, "cogerContenido")
      .mockResolvedValue({ contenido: {} } as never);
    const { onEditar } = renderCalendario(
      [pub({ contenido_id: "c9", titulo: "Gol" })],
      vi.fn(),
      new Date(2026, 5, 15),
    );
    fireEvent.click(screen.getByRole("button", { name: "semana" }));

    const sello = screen.getByRole("button", { name: 'Coger "Gol" (me la asigno)' });
    fireEvent.keyDown(sello, { key: "Enter" });

    await waitFor(() => expect(coger).toHaveBeenCalledTimes(1));
    expect(coger).toHaveBeenCalledWith("c9");
    expect(onEditar).not.toHaveBeenCalled();
  });

  it("sin piezas programadas avisa y remite a la Lista del Feed para las piezas sin fecha", () => {
    // El calendario solo recibe piezas con fecha (la API lo acota por rango): el vacío
    // remite a la Lista, donde viven las piezas sin programar. No deriva ya un conteo
    // de "sin fecha" de su propio listado (ese conteo era siempre 0 en producción).
    renderCalendario([]);
    expect(
      screen.getByText(/No hay piezas programadas en esta ventana/),
    ).toBeInTheDocument();
    expect(screen.getByText(/se trabajan desde\s+la Lista del Feed/)).toBeInTheDocument();
  });
});

describe("rangoVisibleCalendario — ventana que pide el calendario (mes ± 1 semana)", () => {
  it("cubre la rejilla de 42 celdas del mes con margen, en ISO YYYY-MM-DD", () => {
    // Junio 2026: la rejilla va del 1-jun al 12-jul; con ±1 semana, 25-may a 19-jul.
    expect(rangoVisibleCalendario(new Date(2026, 5, 15))).toEqual({
      desde: "2026-05-25",
      hasta: "2026-07-19",
    });
  });

  it("el rango contiene siempre el día del ancla", () => {
    const { desde, hasta } = rangoVisibleCalendario(new Date(2026, 5, 15));
    expect(desde <= "2026-06-15").toBe(true);
    expect(hasta >= "2026-06-15").toBe(true);
  });
});
