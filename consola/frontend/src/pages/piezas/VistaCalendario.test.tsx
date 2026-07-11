import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Pieza } from "@/types";

import { VistaCalendario, rangoVisibleCalendario } from "./VistaCalendario";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

/** Una `Pieza` mínima viable (los campos que VistaCalendario/PildoraPub leen). */
function pub(over: Partial<Pieza> = {}): Pieza {
  return {
    id: "p1",
    publicacion_id: "c1",
    pipeline_id: "",
    titulo: "Gol",
    marca: "claro-sports",
    marca_nombre: "Claro Sports",
    red: "x",
    red_nombre: "X",
    contenido: "Copy.",
    copy_in: "",
    hashtags_sugeridos: [],
    falta_hashtags: false,
    estado: "programado",
    revision: "",
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
    categoria: "",
    imagen: "",
    imagen_url: "",
    evergreen: false,
    etapa_ia: "generando_arte",
    ...over,
  };
}

function renderCalendario(piezas: Pieza[], onEditar = vi.fn(), ancla?: Date) {
  const onVerFeed = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      {/* marca sin pasar (undefined) => la query de franjas queda DESHABILITADA: sin red. */}
      <VistaCalendario
        piezas={piezas}
        onEditar={onEditar}
        onVerFeed={onVerFeed}
        ancla={ancla}
      />
    </QueryClientProvider>,
  );
  return { onEditar, onVerFeed };
}

describe("VistaCalendario — aviso sin fecha y píldora terminal", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sin piezas programadas avisa y remite a la Lista del Feed para las piezas sin fecha", () => {
    // El calendario solo recibe piezas con fecha (la API lo acota por rango): el vacío
    // remite a la Lista, donde viven las piezas sin programar.
    renderCalendario([]);
    expect(
      screen.getByText(/No hay piezas programadas en esta ventana/),
    ).toBeInTheDocument();
    expect(screen.getByText(/se trabajan desde\s+la Lista del Feed/)).toBeInTheDocument();
  });

  it("una pieza ya PUBLICADA no es arrastrable (su post ya salió: no se reprograma)", () => {
    renderCalendario(
      [pub({ titulo: "Gol", estado: "publicado" })],
      vi.fn(),
      new Date(2026, 5, 15),
    );
    fireEvent.click(screen.getByRole("button", { name: "Semana" }));
    // El arrastre vive en el contenedor de la píldora (un <div>), no en el botón del título.
    const pildora = screen.getByText("Gol").closest("[draggable]");
    expect(pildora).toHaveAttribute("draggable", "false");
  });

  it("una pieza PROGRAMADA sí es arrastrable (se puede reprogramar)", () => {
    renderCalendario(
      [pub({ titulo: "Gol", estado: "programado" })],
      vi.fn(),
      new Date(2026, 5, 15),
    );
    fireEvent.click(screen.getByRole("button", { name: "Semana" }));
    // El arrastre vive en el contenedor de la píldora (un <div>), no en el botón del título.
    const pildora = screen.getByText("Gol").closest("[draggable]");
    expect(pildora).toHaveAttribute("draggable", "true");
  });

  it("clic en una pieza abre la caja del feed (no el editor)", () => {
    const { onVerFeed, onEditar } = renderCalendario(
      [pub({ titulo: "Gol", estado: "programado" })],
      vi.fn(),
      new Date(2026, 5, 15),
    );
    fireEvent.click(screen.getByRole("button", { name: "Semana" }));
    // El título de la pieza es un botón: lo pulsa quien quiere VERLA en el feed. Reprogramar
    // (cambiar día/hora) vive ahora solo en el menú contextual, no en el clic sobre la hora.
    fireEvent.click(screen.getByText("Gol"));
    expect(onVerFeed).toHaveBeenCalledTimes(1);
    expect(onVerFeed.mock.calls[0][0]).toMatchObject({ titulo: "Gol" });
    expect(onEditar).not.toHaveBeenCalled();
  });
});

describe("VistaCalendario — agrupar espejos (mismo post, misma hora, varias redes)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("colapsa el mismo post a la misma hora en una sola fila con un logo por red", () => {
    renderCalendario(
      [
        pub({ id: "a", red: "x", publicacion_id: "c1" }),
        pub({ id: "b", red: "instagram", publicacion_id: "c1" }),
        pub({ id: "c", red: "facebook", publicacion_id: "c1" }),
      ],
      vi.fn(),
      new Date(2026, 5, 15),
    );
    fireEvent.click(screen.getByRole("button", { name: "Semana" }));
    // Un único título (no tres) para el post espejo, con su logo por cada red.
    expect(screen.getAllByText("Gol")).toHaveLength(1);
    expect(screen.getByLabelText("X")).toBeInTheDocument();
    expect(screen.getByLabelText("Instagram")).toBeInTheDocument();
    expect(screen.getByLabelText("Facebook")).toBeInTheDocument();
  });

  it("NO agrupa si una red se reprograma a otra hora (deja de ser espejo)", () => {
    renderCalendario(
      [
        pub({ id: "a", red: "x", publicacion_id: "c1", fecha_programada: "2026-06-15T18:00" }),
        pub({ id: "b", red: "instagram", publicacion_id: "c1", fecha_programada: "2026-06-15T20:00" }),
      ],
      vi.fn(),
      new Date(2026, 5, 15),
    );
    fireEvent.click(screen.getByRole("button", { name: "Semana" }));
    // Distinta hora → dos filas separadas.
    expect(screen.getAllByText("Gol")).toHaveLength(2);
  });

  it("NO agrupa posts distintos (otra publicación) aunque coincidan en hora", () => {
    renderCalendario(
      [
        pub({ id: "a", titulo: "Gol", red: "x", publicacion_id: "c1" }),
        pub({ id: "b", titulo: "Penal", red: "x", publicacion_id: "c2" }),
      ],
      vi.fn(),
      new Date(2026, 5, 15),
    );
    fireEvent.click(screen.getByRole("button", { name: "Semana" }));
    expect(screen.getByText("Gol")).toBeInTheDocument();
    expect(screen.getByText("Penal")).toBeInTheDocument();
  });
});

describe("VistaCalendario — kill-switch de huecos del plan", () => {
  afterEach(() => vi.restoreAllMocks());

  it("con mostrarHuecosPlan=false avisa de que los huecos quedan ocultos", () => {
    // Los huecos van por red, así que el filtro NO los apaga; el kill-switch solo se usa cuando
    // la foto no es fiable (p. ej. rango truncado).
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <VistaCalendario piezas={[]} onEditar={vi.fn()} mostrarHuecosPlan={false} />
      </QueryClientProvider>,
    );
    expect(screen.getByText(/Huecos del plan ocultos/)).toBeInTheDocument();
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
