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
    // El rol por defecto (Foto) viaja como `formato`: la cobertura es por rol.
    expect(cubrir).toHaveBeenCalledWith("ev9", undefined, "foto");
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

  it("MULTI-COBERTURA: varias personas cubren UN evento → una sola fila, y otra puede apuntarse", async () => {
    const cubrir = vi
      .spyOn(apiMod.api, "cubrirEvento")
      .mockResolvedValue({ contenido: { responsable_nombre: "yo" } } as never);
    // Dos tareas de cobertura del MISMO evento (evento_id "ev1"), distintos dueños.
    renderTareas([
      tarea({ id: "t-luis", titulo: "Cruz Azul vs América", evento_id: "ev1", responsable_id: "u-luis", responsable_nombre: "luis", fecha_objetivo: "2026-07-01" }),
      tarea({ id: "t-ana", titulo: "Cruz Azul vs América", evento_id: "ev1", responsable_id: "u-ana", responsable_nombre: "ana", fecha_objetivo: "2026-07-01" }),
    ]);

    // El evento sale UNA sola vez en la agenda (no una fila por cubridor).
    const filas = await screen.findAllByRole("button", { name: /Cruz Azul vs América/ });
    expect(filas).toHaveLength(1);
    const titulosAntes = screen.getAllByText("Cruz Azul vs América").length;

    // Al desplegar: lo cubren los dos, y yo (no cubridor) puedo apuntarme.
    fireEvent.click(filas[0]);
    expect(await screen.findByText("Cubren:")).toBeInTheDocument();
    // Las tarjetas de cada cubridor encabezan por la PERSONA, no repiten el título del
    // evento (antes salía una vez por cubridor): expandir no añade apariciones del título.
    expect(screen.getAllByText("Cruz Azul vs América")).toHaveLength(titulosAntes);
    expect(screen.getAllByText("luis").length).toBeGreaterThan(0);
    expect(screen.getAllByText("ana").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /Apuntarme/ }));
    await waitFor(() => expect(cubrir).toHaveBeenCalledWith("ev1", undefined, "foto"));
  });

  it("SEMÁFORO: la cobertura se pinta sola por fecha/hora, sin botones de estado", async () => {
    // Evento YA jugado (fecha pasada) → semáforo verde «Cubierto». El equipo no marca
    // estados a mano (les hace perder tiempo): no hay «Empezar» ni «Marcar hecha».
    renderTareas([
      tarea({
        id: "t-pasado",
        titulo: "Final ya jugada",
        evento_id: "ev-p",
        responsable_id: "u-luis",
        responsable_nombre: "luis",
        fecha_objetivo: "2020-01-01",
        hora_objetivo: "19:00",
      }),
    ]);
    fireEvent.click(await screen.findByRole("button", { name: /Final ya jugada/ }));
    // Verde «Cubierto» (en la fila colapsada y en la tarjeta del cubridor), sin botones de avance.
    expect((await screen.findAllByTitle("Cubierto")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /Empezar/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Marcar hecha/ })).toBeNull();
  });

  it("la barra de carga muestra «+» para añadir persona (solo admin y marca concreta)", async () => {
    const { unmount } = renderTareas([], [], usuario("admin", "u-admin"));
    expect(
      await screen.findByRole("button", { name: "Añadir persona al equipo" }),
    ).toBeInTheDocument();
    unmount();

    vi.restoreAllMocks();
    renderTareas([], [], usuario("editor", "u1"));
    await screen.findByRole("button", { name: "Ver solo lo por cubrir" }); // el panorama ya cargó
    expect(screen.queryByRole("button", { name: "Añadir persona al equipo" })).toBeNull();
  });

  it("RECUPERACIÓN: una cobertura soltada (sin dueño) reaparece como «Por cubrir» y se re-coge", async () => {
    const coger = vi
      .spyOn(apiMod.api, "cogerContenido")
      .mockResolvedValue({ contenido: {} } as never);
    // Tarea de cobertura HUÉRFANA (evento_id pero sin responsable, como tras «Soltar»): el
    // partido NO se borró, debe reaparecer como «Por cubrir» y poder re-cogerse.
    renderTareas([
      tarea({ id: "t-huerfana", titulo: "Brasil vs Marruecos", evento_id: "ev2", responsable_id: "", responsable_nombre: "", fecha_objetivo: "2026-07-02" }),
    ]);

    fireEvent.click(await screen.findByText("Brasil vs Marruecos"));
    fireEvent.click(screen.getByRole("button", { name: /La cubro yo/ }));
    await waitFor(() => expect(coger).toHaveBeenCalledWith("t-huerfana"));
  });

  it("SEMÁFORO POR ROLES: la fila del evento muestra qué roles están cubiertos (Foto · Video)", async () => {
    // Dos cubridores del MISMO evento con roles distintos (formato foto y video): el indicador
    // agregado del evento resume los roles cubiertos.
    renderTareas([
      tarea({ id: "t-f", titulo: "Cruz Azul vs América", evento_id: "ev1", responsable_id: "u-luis", responsable_nombre: "luis", formato: "foto", fecha_objetivo: "2026-07-01" }),
      tarea({ id: "t-v", titulo: "Cruz Azul vs América", evento_id: "ev1", responsable_id: "u-ana", responsable_nombre: "ana", formato: "video", fecha_objetivo: "2026-07-01" }),
    ]);
    expect((await screen.findAllByText("Foto · Video")).length).toBeGreaterThan(0);
  });

  it("ELEGIR ROL: al cubrir un evento se manda el rol elegido en el selector", async () => {
    const cubrir = vi
      .spyOn(apiMod.api, "cubrirEvento")
      .mockResolvedValue({ contenido: { responsable_nombre: "yo" } } as never);
    renderTareas([], [evento({ id: "ev9", titulo: "Cruz Azul vs América" })]);

    fireEvent.click(await screen.findByText("Cruz Azul vs América")); // desplegar la fila
    fireEvent.click(screen.getByRole("button", { name: "Video" })); // elegir rol Video
    fireEvent.click(screen.getByRole("button", { name: /La cubro yo/ }));
    await waitFor(() => expect(cubrir).toHaveBeenCalledWith("ev9", undefined, "video"));
  });

  it("QUITARME: en MI cobertura libera mi rol con soltarContenido (NO borra el partido)", async () => {
    const soltar = vi
      .spyOn(apiMod.api, "soltarContenido")
      .mockResolvedValue({ contenido: {} } as never);
    // Soy la cubridora (responsable_id == id de mi sesión): mi tarjeta ofrece «Quitarme».
    renderTareas(
      [tarea({ id: "t-mia", titulo: "Cruz Azul vs América", evento_id: "ev1", responsable_id: "u-yo", responsable_nombre: "yo", formato: "video", fecha_objetivo: "2026-07-01" })],
      [],
      usuario("editor", "u-yo"),
    );

    fireEvent.click(await screen.findByRole("button", { name: /Cruz Azul vs América/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Quitarme/ }));
    await waitFor(() => expect(soltar).toHaveBeenCalledWith("t-mia"));
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
