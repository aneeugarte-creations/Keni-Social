import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  MarcaActivaContexto,
  type ValorMarcaActiva,
} from "@/hooks/marca-activa-contexto";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import * as apiMod from "@/lib/api";
import type { CatalogosContenido, Contenido, EventoRota, UsuarioSesion } from "@/types";

import Tareas from "./Tareas";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

function tarea(over: Partial<Contenido> = {}): Contenido {
  return {
    id: "t1",
    clase: "tarea",
    flujo: "",
    titulo: "Editar el clip",
    descripcion: "",
    marca: "claro-sports",
    marca_nombre: "Claro Sports",
    evento_id: "",
    programa: "",
    prioridad: "media",
    estado: "pendiente",
    fecha_objetivo: "",
    hora_objetivo: "",
    fecha_entrega: "",
    responsable_id: "",
    responsable_nombre: "",
    autor_nombre: "",
    origen: "manual",
    notas: "",
    tipo_contenido: "ia",
    formato: "foto",
    vencido: false,
    plataformas: [],
    etiquetas: [],
    ...over,
  };
}

function evento(over: Partial<EventoRota> = {}): EventoRota {
  return {
    id: "ev1",
    titulo: "Cruz Azul vs América",
    fecha: "2026-07-01",
    hora: "20:00",
    contenido: "",
    nota: "",
    tipo_cobertura: "transmision",
    prioridad: "media",
    cambiado: false,
    actualizado: "",
    es_sabado: false,
    marca: "claro-sports",
    marca_nombre: "Claro Sports",
    ...over,
  };
}

function catalogos(): CatalogosContenido {
  return {
    usuarios: [
      { id: "u-luis", usuario: "luis" },
      { id: "u-ana", usuario: "ana" },
    ],
    marcas: [{ id: "claro-sports", nombre: "Claro Sports" }],
    redes: [],
    flujos: [],
    prioridades: ["alta", "media", "baja"],
    estados_contenido: ["pendiente", "en_curso", "hecha"],
    estados_plataforma: [],
    eventos: [],
    etiquetas: [],
    variables: [],
  };
}

function usuario(rol: UsuarioSesion["rol"] = "editor", id = "u1"): UsuarioSesion {
  return { id, usuario: "yo", rol, debe_cambiar_password: false, marcas: ["claro-sports"] };
}

function sesionValor(u: UsuarioSesion | null): ValorSesion {
  return {
    usuario: u,
    cargando: false,
    iniciarSesion: vi.fn(),
    verificarConPasskey: vi.fn(),
    verificarConCodigo: vi.fn(),
    cerrarSesion: vi.fn(),
    refrescar: vi.fn(),
  };
}

function valorMarca(marcaActiva: string | null): ValorMarcaActiva {
  return {
    marcaActiva,
    marcaPrimaria: marcaActiva,
    enMarcaPrimaria: true,
    esMultiMarca: false,
    puedeTodas: false,
    marcasParaSwitch: [],
    nombreActiva: "Claro Sports",
    cambiarMarca: vi.fn(),
    volverAPrimaria: vi.fn(),
  };
}

function renderTareas(tareas: Contenido[], eventos: EventoRota[] = [], u = usuario()) {
  vi.spyOn(apiMod.api, "contenido").mockResolvedValue({
    contenidos: tareas,
    catalogos: catalogos(),
  });
  vi.spyOn(apiMod.api, "rotaEventos").mockResolvedValue({ eventos });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesionValor(u)}>
        <MarcaActivaContexto.Provider value={valorMarca("claro-sports")}>
          <MemoryRouter>
            <Tareas />
          </MemoryRouter>
        </MarcaActivaContexto.Provider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("Tareas — lista compartida de eventos + encargos", () => {
  afterEach(() => vi.restoreAllMocks());

  it("un EVENTO sin tarea sale como «Por cubrir» y «La cubro yo» llama a cubrirEvento", async () => {
    const cubrir = vi
      .spyOn(apiMod.api, "cubrirEvento")
      .mockResolvedValue({ contenido: { responsable_nombre: "yo" } } as never);
    renderTareas([], [evento({ id: "ev9", titulo: "Cruz Azul vs América" })]);

    // En el Panorama (por defecto) el evento es una fila compacta; se despliega para actuar.
    fireEvent.click(await screen.findByText("Cruz Azul vs América"));
    fireEvent.click(screen.getByRole("button", { name: /La cubro yo/ }));
    await waitFor(() => expect(cubrir).toHaveBeenCalledTimes(1));
    expect(cubrir).toHaveBeenCalledWith("ev9", undefined);
  });

  it("un evento 'no_cubrir' NO aparece en la lista", async () => {
    renderTareas([], [evento({ id: "ev-x", titulo: "Amistoso sin señal", tipo_cobertura: "no_cubrir" })]);
    await waitFor(() => expect(apiMod.api.rotaEventos).toHaveBeenCalled());
    expect(screen.queryByText("Amistoso sin señal")).toBeNull();
  });

  it("una tarea LIBRE (encargo) ofrece 'Coger' y llama a cogerContenido", async () => {
    const coger = vi
      .spyOn(apiMod.api, "cogerContenido")
      .mockResolvedValue({ contenido: {} } as never);
    renderTareas([tarea({ id: "t9", titulo: "Grabar el saque" })]);

    // Desplegar la fila del Panorama para llegar a la tarjeta accionable.
    fireEvent.click(await screen.findByText("Grabar el saque"));
    fireEvent.click(screen.getByRole("button", { name: /Coger/ }));
    await waitFor(() => expect(coger).toHaveBeenCalledTimes(1));
    expect(coger).toHaveBeenCalledWith("t9");
  });

  it("la lente 'Mis tareas' deja solo lo del usuario de la sesión", async () => {
    renderTareas(
      [
        tarea({ id: "t1", titulo: "Mía", responsable_id: "u1", responsable_nombre: "yo" }),
        tarea({ id: "t2", titulo: "De Ana", responsable_id: "u-ana", responsable_nombre: "ana" }),
      ],
      [],
      usuario("editor", "u1"),
    );
    // En el Panorama el título sale en la fila Y en la banda «lo último cogido», así que hay ≥1.
    expect((await screen.findAllByText("Mía")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("De Ana").length).toBeGreaterThan(0);

    // Radix Tabs activa en pointer-down (no en click) — patrón del resto de la suite.
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Mis tareas" }), { button: 0 });
    await waitFor(() => expect(screen.queryByText("De Ana")).toBeNull());
    expect(screen.getByText("Mía")).toBeInTheDocument();
  });

  it("un MANAGER (admin) ve 'Asignar'; un editor NO", async () => {
    const { unmount } = renderTareas([tarea({ titulo: "Reparto" })], [], usuario("admin", "u-admin"));
    fireEvent.click(await screen.findByText("Reparto")); // desplegar la fila del Panorama
    expect(await screen.findByRole("button", { name: /Asignar/ })).toBeInTheDocument();
    unmount();

    vi.restoreAllMocks();
    renderTareas([tarea({ titulo: "Reparto" })], [], usuario("editor", "u2"));
    fireEvent.click(await screen.findByText("Reparto"));
    await screen.findByRole("button", { name: /Coger/ });
    expect(screen.queryByRole("button", { name: /Asignar/ })).toBeNull();
  });

  it("el 'Panorama' (por defecto) mezcla eventos por cubrir y tareas con dueño, y muestra lo último cogido", async () => {
    renderTareas(
      [
        tarea({
          id: "t-luis",
          titulo: "Clip de Luis",
          responsable_id: "u-luis",
          responsable_nombre: "luis",
          fecha_objetivo: "2026-07-01",
          actualizado: "2026-06-12 10:00:00",
        }),
      ],
      [evento({ id: "ev-pool", titulo: "Partido por cubrir", fecha: "2026-07-01" })],
    );

    // El Panorama es la vista por defecto: no hay que cambiar de pestaña. El evento (sin dueño)
    // sale una sola vez; «Clip de Luis» sale en su fila Y en la banda de lo recién cogido.
    expect(await screen.findByText("Partido por cubrir")).toBeInTheDocument();
    expect(screen.getAllByText("Clip de Luis").length).toBeGreaterThan(0);

    // El evento sin dueño se marca «Por cubrir» y la banda de lo recién cogido aparece.
    expect(screen.getAllByText("Por cubrir").length).toBeGreaterThan(0);
    expect(screen.getByText(/Lo último que ha cogido el equipo/)).toBeInTheDocument();

    // La carga por persona deja filtrar; «luis» aparece como chip.
    expect(screen.getByRole("button", { name: "Ver solo lo de luis" })).toBeInTheDocument();
  });

  it("'Panorama': filtrar por una persona deja solo lo suyo", async () => {
    renderTareas([
      tarea({ id: "t-luis", titulo: "Clip de Luis", responsable_id: "u-luis", responsable_nombre: "luis" }),
      tarea({ id: "t-ana", titulo: "Foto de Ana", responsable_id: "u-ana", responsable_nombre: "ana" }),
    ]);

    const chip = await screen.findByRole("button", { name: "Ver solo lo de luis" });
    expect(screen.getAllByText("Foto de Ana").length).toBeGreaterThan(0);

    fireEvent.click(chip);
    // Al filtrar se oculta la banda y la agenda deja solo lo de luis.
    await waitFor(() => expect(screen.queryByText("Foto de Ana")).toBeNull());
    expect(screen.getByText("Clip de Luis")).toBeInTheDocument();
  });

  it("'Panorama': al desplegar una fila aparece la tarjeta accionable", async () => {
    renderTareas(
      [tarea({ id: "t-luis", titulo: "Clip de Luis", responsable_id: "u-luis", responsable_nombre: "luis" })],
      [],
      usuario("admin", "u-admin"),
    );

    // La fila compacta (un botón) se despliega y muestra la tarjeta con «Reasignar».
    fireEvent.click(await screen.findByRole("button", { name: /Clip de Luis/ }));
    expect(await screen.findByRole("button", { name: /Reasignar/ })).toBeInTheDocument();
  });

  it("'Añadir' abre el diálogo", async () => {
    renderTareas([]);
    fireEvent.click(await screen.findByRole("button", { name: /Añadir/ }));
    expect(await screen.findByText("Añadir a la lista")).toBeInTheDocument();
  });

  it("pega un enlace, analiza, revisa los partidos propuestos y los acepta", async () => {
    vi.spyOn(apiMod.api, "importarEventos").mockResolvedValue({
      propuesta_id: "p1",
      gen_id: "g1",
    });
    vi.spyOn(apiMod.api, "propuestaParrilla").mockResolvedValue({
      id: "p1",
      estado: "pendiente",
      semana: "",
      resumen: "",
      error: "",
      operaciones: [
        {
          tipo: "crear_evento",
          conflicto: false,
          fecha: "2026-07-01",
          hora: "20:00",
          titulo: "Cruz Azul vs América",
        },
      ],
    } as never);
    const aplicar = vi
      .spyOn(apiMod.api, "aplicarPropuestaParrilla")
      .mockResolvedValue({ mensaje: "ok" } as never);

    renderTareas([]);
    fireEvent.click(await screen.findByRole("button", { name: /Añadir/ }));
    fireEvent.change(screen.getByPlaceholderText(/Pega el enlace/), {
      target: { value: "https://liga.test/jornada" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Analizar/ }));

    // El partido propuesto aparece para revisar y se acepta.
    expect(await screen.findByText("Cruz Azul vs América")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Aceptar y añadir/ }));
    await waitFor(() => expect(aplicar).toHaveBeenCalledWith("p1"));
  });
});
