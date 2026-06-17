import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SesionContexto } from "@/hooks/sesion-contexto";
import * as apiMod from "@/lib/api";
import type { Pieza } from "@/types";

import { VistaLista, kebabSegunPuntero } from "./VistaLista";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

/** Una `Pieza` mínima viable (los campos que VistaLista/Tarjeta leen). */
function pub(over: Partial<Pieza> = {}): Pieza {
  return {
    id: "p1",
    publicacion_id: "c1",
    pipeline_id: "",
    titulo: "Tema",
    marca: "piso-15",
    marca_nombre: "Piso 15",
    red: "x",
    red_nombre: "X",
    contenido: "Copy.",
    copy_in: "",
    estado: "borrador",
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
    fecha_programada: "",
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

/**
 * Monta la lista; con `usuario` la envuelve además en un `SesionContexto.Provider`
 * (la Tarjeta lee la sesión con `useContext` null-safe: sin provider sigue funcionando,
 * pero "es mía"/rol admin necesitan saber quién mira).
 */
function renderLista(
  piezas: Pieza[],
  usuario?: { id: string; rol: string },
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const arbol = (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <VistaLista
          piezas={piezas}
          onEditar={vi.fn()}
          onConfigurarHorarios={vi.fn()}
        />
      </MemoryRouter>
    </QueryClientProvider>
  );
  return render(
    usuario ? (
      <SesionContexto.Provider value={{ usuario } as never}>{arbol}</SesionContexto.Provider>
    ) : (
      arbol
    ),
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
      .spyOn(apiMod.api, "borrarPiezasLote")
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

  it("reporta los fallos parciales del lote (toast de error con el resumen)", async () => {
    vi.spyOn(apiMod.api, "borrarPiezasLote").mockResolvedValue({
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

describe("VistaLista — 'Añadir a la cola' solo en piezas programadas", () => {
  afterEach(() => vi.restoreAllMocks());

  it("una pieza PROGRAMADA ofrece 'Añadir a la cola' en el menú", async () => {
    renderLista([pub({ id: "p1", titulo: "Programada", estado: "programado" })]);
    fireEvent.contextMenu(screen.getByText("Programada").closest('[role="button"]')!);
    expect(
      await screen.findByRole("menuitem", { name: /Añadir a la cola/ }),
    ).toBeInTheDocument();
  });

  it("un BORRADOR NO ofrece 'Añadir a la cola' (encolar saltaría la revisión)", async () => {
    renderLista([pub({ id: "p1", titulo: "Borrador", estado: "borrador" })]);
    // "Borrador" aparece como título y como badge de estado: toma el primero (el título).
    fireEvent.contextMenu(screen.getAllByText("Borrador")[0].closest('[role="button"]')!);
    // El menú abre con otras acciones, pero la de encolar NO está: el camino del borrador es
    // el flujo de aprobación (que auto-programa al aprobarse), no un encolado a mano.
    await screen.findByRole("menuitem", { name: /Borrar/ });
    expect(screen.queryByRole("menuitem", { name: /Añadir a la cola/ })).toBeNull();
  });

  it("una pieza PUBLICADA NO ofrece 'Añadir a la cola' (no se re-encola)", async () => {
    renderLista([pub({ id: "p1", titulo: "Salió", estado: "publicado" })]);
    fireEvent.contextMenu(screen.getByText("Salió").closest('[role="button"]')!);
    await screen.findByRole("menuitem", { name: /Borrar/ });
    expect(screen.queryByRole("menuitem", { name: /Añadir a la cola/ })).toBeNull();
  });
});

describe("VistaLista — el menú es 'Aprobar o Borrar' (sin Duplicar ni evergreen)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("un BORRADOR ofrece 'Aprobar' y 'Borrar', y NO 'Duplicar' ni evergreen", async () => {
    renderLista([pub({ id: "p1", titulo: "Borrador", estado: "borrador" })]);
    fireEvent.contextMenu(screen.getAllByText("Borrador")[0].closest('[role="button"]')!);
    expect(await screen.findByRole("menuitem", { name: /Aprobar/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Borrar/ })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /Duplicar/ })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: /evergreen/i })).toBeNull();
  });

  it("'Aprobar' registra el OK por la cadena (POST /aprobar)", async () => {
    const aprobar = vi
      .spyOn(apiMod.api, "aprobarPieza")
      .mockResolvedValue({ pieza: pub({ estado: "en_revision" }) } as never);
    renderLista([pub({ id: "p1", titulo: "Pieza a revisar", estado: "en_revision" })]);
    fireEvent.contextMenu(screen.getByText("Pieza a revisar").closest('[role="button"]')!);
    fireEvent.click(await screen.findByRole("menuitem", { name: /Aprobar/ }));
    await waitFor(() => expect(aprobar).toHaveBeenCalledWith("p1"));
  });

  it("una pieza PUBLICADA NO ofrece 'Aprobar' (ya salió)", async () => {
    renderLista([pub({ id: "p1", titulo: "Salió", estado: "publicado" })]);
    fireEvent.contextMenu(screen.getByText("Salió").closest('[role="button"]')!);
    await screen.findByRole("menuitem", { name: /Borrar/ });
    expect(screen.queryByRole("menuitem", { name: /Aprobar/ })).toBeNull();
  });
});

describe("kebabSegunPuntero — visibilidad del kebab según el puntero (táctil)", () => {
  it("puntero grueso (táctil, sin hover): kebab SIEMPRE visible", () => {
    expect(kebabSegunPuntero(true)).toBe("siempre");
  });

  it("puntero fino (ratón): kebab al hover, como hoy", () => {
    expect(kebabSegunPuntero(false)).toBe("hover");
  });
});
