import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SesionContexto } from "@/hooks/sesion-contexto";
import * as apiMod from "@/lib/api";
import type { Publicacion } from "@/types";

import { VistaLista, kebabSegunPuntero } from "./VistaLista";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

/** Una `Publicacion` mínima viable (los campos que VistaLista/Tarjeta leen). */
function pub(over: Partial<Publicacion> = {}): Publicacion {
  return {
    id: "p1",
    contenido_id: "c1",
    pipeline_id: "",
    titulo: "Tema",
    marca: "piso-15",
    marca_nombre: "Piso 15",
    red: "x",
    red_nombre: "X",
    contenido: "Copy.",
    copy_in: "",
    estado: "borrador",
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
  publicaciones: Publicacion[],
  usuario?: { id: string; rol: string },
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const arbol = (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <VistaLista
          publicaciones={publicaciones}
          onEditar={vi.fn()}
          onDuplicar={vi.fn()}
          onConfigurarCadencia={vi.fn()}
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
      }),
    ]);
    expect(screen.getByText("Mariana")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Coger/ })).toBeNull();
  });

  it("reparto: si otra persona la cogió antes (409), el toast de error trae el motivo", async () => {
    vi.spyOn(apiMod.api, "cogerContenido").mockRejectedValue(
      new apiMod.ApiError("Ya la cogió Mariana.", 409),
    );
    renderLista([
      pub({ id: "p1", contenido_id: "c1", titulo: "Gol", marca: "claro-sports" }),
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Coger" }));

    const { toast } = await import("sonner");
    await waitFor(() =>
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith("Ya la cogió Mariana."),
    );
  });

  it("reparto: una pieza MÍA (sesión u1) lleva el badge 'Tuya' y 'Soltar' libera el tema padre", async () => {
    const soltar = vi
      .spyOn(apiMod.api, "soltarContenido")
      .mockResolvedValue({ contenido: {} } as never);
    renderLista(
      [
        pub({
          id: "p1",
          contenido_id: "c1",
          titulo: "Gol",
          marca: "claro-sports",
          responsable_id: "u1",
          responsable_nombre: "Yustine",
        }),
      ],
      { id: "u1", rol: "editor" },
    );

    expect(screen.getByText("Tuya")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Soltar" }));
    await waitFor(() => expect(soltar).toHaveBeenCalledTimes(1));
    expect(soltar).toHaveBeenCalledWith("c1");
  });

  it("reparto: un admin ve en el menú contextual 'Soltar (la lleva Mariana)' en una pieza ajena", async () => {
    renderLista(
      [
        pub({
          id: "p1",
          contenido_id: "c1",
          titulo: "Gol",
          marca: "claro-sports",
          responsable_id: "u-mariana",
          responsable_nombre: "Mariana",
        }),
      ],
      { id: "u-admin", rol: "admin" },
    );

    // No es suya: sin botón inline de Soltar; la vía del admin es el menú (kebab).
    expect(screen.queryByRole("button", { name: "Soltar" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Más acciones" }));
    expect(
      await screen.findByRole("menuitem", { name: /Soltar \(la lleva Mariana\)/ }),
    ).toBeInTheDocument();
  });

  it("reparto: un MANAGER (admin) ve 'Asignar a…' y al elegir persona llama a asignarContenido", async () => {
    vi.spyOn(apiMod.api, "mencionesCandidatos").mockResolvedValue({
      usuarios: [
        { id: "u-luis", nombre: "Luis", usuario: "luis" },
        { id: "u-ana", nombre: "Ana", usuario: "ana" },
      ],
    });
    const asignar = vi
      .spyOn(apiMod.api, "asignarContenido")
      .mockResolvedValue({ contenido: { responsable_nombre: "Ana" } } as never);
    renderLista(
      [pub({ id: "p1", contenido_id: "c9", titulo: "Gol", marca: "claro-sports" })],
      { id: "u-admin", rol: "admin" },
    );

    fireEvent.click(screen.getByRole("button", { name: "Más acciones" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /Asignar a/ }));
    // Diálogo con el equipo de la marca: el manager EMPUJA la pieza a Ana.
    fireEvent.click(await screen.findByRole("button", { name: /Ana/ }));
    await waitFor(() => expect(asignar).toHaveBeenCalledTimes(1));
    expect(asignar).toHaveBeenCalledWith("c9", "u-ana");
  });

  it("reparto: un EDITOR NO ve 'Asignar a…' (empujar trabajo a otros es del manager)", async () => {
    renderLista(
      [pub({ id: "p1", contenido_id: "c9", titulo: "Gol", marca: "claro-sports" })],
      { id: "u1", rol: "editor" },
    );
    fireEvent.click(screen.getByRole("button", { name: "Más acciones" }));
    // El menú abre (Duplicar está), pero "Asignar a…" no: el editor reparte cogiendo del pool.
    await screen.findByRole("menuitem", { name: /Duplicar/ });
    expect(screen.queryByRole("menuitem", { name: /Asignar a/ })).toBeNull();
  });

  it("reparto: las piezas de otras marcas NO llevan botón de coger (flujo sin reparto)", () => {
    renderLista([pub({ id: "p1", titulo: "Nota", marca: "unotv" })]);
    expect(screen.queryByRole("button", { name: /Coger/ })).toBeNull();
  });

  it("reparto POR TEMA: una pieza con 3 hermanas en la lista avisa 'N redes · se cogen juntas'", async () => {
    const coger = vi
      .spyOn(apiMod.api, "cogerContenido")
      .mockResolvedValue({ contenido: {} } as never);
    // 3 filas (una por red) que comparten el mismo `contenido_id`: cogerlas se lleva las 3.
    renderLista([
      pub({ id: "p1", contenido_id: "c9", red: "x", titulo: "Gol", marca: "claro-sports" }),
      pub({ id: "p2", contenido_id: "c9", red: "instagram", titulo: "Gol", marca: "claro-sports" }),
      pub({ id: "p3", contenido_id: "c9", red: "facebook", titulo: "Gol", marca: "claro-sports" }),
    ]);
    // El badge aparece en cada una de las 3 hermanas.
    expect(screen.getAllByText(/3 redes/)).toHaveLength(3);

    // El toast de coger menciona que se llevan las N redes.
    fireEvent.click(screen.getAllByRole("button", { name: "Coger" })[0]);
    const { toast } = await import("sonner");
    await waitFor(() => expect(coger).toHaveBeenCalledTimes(1));
    expect(vi.mocked(toast.success)).toHaveBeenCalledWith(
      expect.stringContaining("y sus 3 redes son tuyas"),
    );
  });

  it("reparto: una pieza SOLA (sin hermanas) no muestra el aviso de multi-red", () => {
    renderLista([
      pub({ id: "p1", contenido_id: "c1", titulo: "Nota", marca: "claro-sports" }),
    ]);
    expect(screen.queryByText(/redes · se cogen juntas/)).toBeNull();
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

describe("VistaLista — 'Añadir a la cola' solo en piezas aprobadas/programadas", () => {
  afterEach(() => vi.restoreAllMocks());

  it("una pieza APROBADA ofrece 'Añadir a la cola' en el menú", async () => {
    renderLista([pub({ id: "p1", titulo: "Aprobada", estado: "aprobado" })]);
    fireEvent.click(screen.getByRole("button", { name: "Más acciones" }));
    expect(
      await screen.findByRole("menuitem", { name: /Añadir a la cola/ }),
    ).toBeInTheDocument();
  });

  it("un BORRADOR NO ofrece 'Añadir a la cola' (encolar saltaría la revisión)", async () => {
    renderLista([pub({ id: "p1", titulo: "Borrador", estado: "borrador" })]);
    fireEvent.click(screen.getByRole("button", { name: "Más acciones" }));
    // El menú abre con otras acciones, pero la de encolar NO está: el camino del borrador es
    // el flujo de aprobación (que auto-programa al aprobarse), no un encolado a mano.
    await screen.findByRole("menuitem", { name: /Duplicar/ });
    expect(screen.queryByRole("menuitem", { name: /Añadir a la cola/ })).toBeNull();
  });

  it("una pieza PUBLICADA NO ofrece 'Añadir a la cola' (no se re-encola)", async () => {
    renderLista([pub({ id: "p1", titulo: "Salió", estado: "publicado" })]);
    fireEvent.click(screen.getByRole("button", { name: "Más acciones" }));
    // El menú abre con otras acciones, pero la de encolar NO está.
    await screen.findByRole("menuitem", { name: /Duplicar/ });
    expect(screen.queryByRole("menuitem", { name: /Añadir a la cola/ })).toBeNull();
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
