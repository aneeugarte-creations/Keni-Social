import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { confirmar } from "@/components/comunes/confirmar";
import {
  MarcaActivaContexto,
  type ValorMarcaActiva,
} from "@/hooks/marca-activa-contexto";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import * as apiMod from "@/lib/api";
import { hoyCDMX } from "@/lib/fecha";
import type {
  CatalogosPublicacion,
  EventoRota,
  FranjaSemana,
  Publicacion,
  RotaSemana,
  TurnoRota,
  UsuarioSesion,
} from "@/types";

import { PanoramaAgenda } from "./PanoramaAgenda";
import Tareas from "./Tareas";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

// El borrado pasa por la confirmación propia de la app; en tests la resolvemos siempre en `true`
// (el `<ContenedorConfirmacion />` no está montado, así que sin mock resolvería `false`).
vi.mock("@/components/comunes/confirmar", () => ({
  confirmar: vi.fn().mockResolvedValue(true),
}));

function tarea(over: Partial<Publicacion> = {}): Publicacion {
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

function catalogos(): CatalogosPublicacion {
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

function semanaVacia(): RotaSemana {
  return { lunes: "", inicio: "", fin: "", dias: [], turnos: [], franjas: [], aprobada: false, total: 0 };
}

// RotaSemana con franja Mañana (08–16) y un turno ese día: cubre por turno los eventos de mañana.
function semanaConTurnoManana(fecha: string): RotaSemana {
  return {
    ...semanaVacia(),
    franjas: [
      {
        id: "fr-m",
        lunes: "",
        nombre: "Mañana",
        inicio: "08:00",
        fin: "16:00",
        orden: 0,
        es_descanso: false,
        marca: "claro-sports",
      } as FranjaSemana,
    ],
    turnos: [{ id: "tr1", fecha, franja_id: "fr-m", miembro_id: "u-luis", miembro_nombre: "luis" } as TurnoRota],
  };
}

function renderTareas(
  tareas: Publicacion[],
  eventos: EventoRota[] = [],
  u = usuario(),
  semana: RotaSemana = semanaVacia(),
) {
  vi.spyOn(apiMod.api, "contenido").mockResolvedValue({
    contenidos: tareas,
    catalogos: catalogos(),
  });
  vi.spyOn(apiMod.api, "rotaEventos").mockResolvedValue({ eventos });
  vi.spyOn(apiMod.api, "listarTurnos").mockResolvedValue(semana);
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
  // `restoreAllMocks` (abajo) borra el valor resuelto del mock de `confirmar` tras cada test;
  // lo re-armamos aquí para que el borrado (que confirma primero) siga su curso por defecto.
  beforeEach(() => {
    vi.mocked(confirmar).mockResolvedValue(true);
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("un EVENTO sin tarea ni turno sale como «Sin cubrir» y «La cubro yo» llama a cubrirEvento", async () => {
    const cubrir = vi
      .spyOn(apiMod.api, "cubrirEvento")
      .mockResolvedValue({ contenido: { responsable_nombre: "yo" } } as never);
    renderTareas([], [evento({ id: "ev9", titulo: "Cruz Azul vs América" })]);

    // En el Panorama (por defecto) el evento es una fila compacta; se despliega para actuar.
    fireEvent.click(await screen.findByText("Cruz Azul vs América"));
    // Item-first: click en la tarjeta (FilaConAcciones host) dispara cubrirEvento.
    const grupo1 = screen.getByRole("group", { name: "Rol de cobertura" });
    fireEvent.click(grupo1.closest("[role='button']")!);
    await waitFor(() => expect(cubrir).toHaveBeenCalledTimes(1));
    // El rol por defecto (Foto) viaja como `formato`: la cobertura es por rol.
    expect(cubrir).toHaveBeenCalledWith("ev9", undefined, "foto");
  });

  it("CUBIERTO POR TURNO: un evento sin coger pero con turno en su franja sale «Cubierto por turno», no «Sin cubrir»", async () => {
    renderTareas(
      [],
      [evento({ id: "ev-cub", titulo: "Cubierto por el turno", fecha: "2026-07-01", hora: "10:00" })],
      usuario(),
      semanaConTurnoManana("2026-07-01"),
    );
    expect(await screen.findByText("Cubierto por el turno")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getAllByText("Cubierto por turno").length).toBeGreaterThan(0),
    );
    expect(screen.queryByText("Sin cubrir")).toBeNull();
  });

  it("PANORAMA: el icono «Asignar» de la fila encarga el evento sin desplegar (cubrirEvento con rol)", async () => {
    const cubrir = vi
      .spyOn(apiMod.api, "cubrirEvento")
      .mockResolvedValue({ contenido: { responsable_nombre: "luis" } } as never);
    renderTareas([], [evento({ id: "ev-asig", titulo: "Tigres vs Rayados" })], usuario("admin", "u-admin"));

    // El icono vive en la fila COMPACTA (no hay que desplegar) y solo lo ve un manager.
    await screen.findByText("Tigres vs Rayados");
    fireEvent.click(screen.getByRole("button", { name: "Asignar a…" }));

    // El diálogo deja elegir persona (y el rol viaja con el default «foto»).
    fireEvent.click(await screen.findByRole("button", { name: "luis" }));
    await waitFor(() => expect(cubrir).toHaveBeenCalledTimes(1));
    expect(cubrir).toHaveBeenCalledWith("ev-asig", "u-luis", "foto");
  });

  it("PANORAMA: un editor NO ve el icono «Asignar» de la fila", async () => {
    renderTareas([], [evento({ id: "ev-ed", titulo: "Partido editor" })], usuario("editor", "u2"));
    await screen.findByText("Partido editor");
    expect(screen.queryByRole("button", { name: "Asignar a…" })).toBeNull();
  });

  it("PANORAMA: un evento PASADO no suma al contador de la persona; uno FUTURO sí", async () => {
    renderTareas([
      // Cobertura de un partido del 10 jun (ya pasó): no es carga pendiente → no cuenta.
      tarea({
        id: "t-pas",
        titulo: "Partido viejo",
        responsable_id: "u-luis",
        responsable_nombre: "luis",
        evento_id: "ev-pas",
        fecha_objetivo: "2026-06-10",
        hora_objetivo: "13:00",
      }),
      // Cobertura de un partido futuro: sí cuenta.
      tarea({
        id: "t-fut",
        titulo: "Partido futuro",
        responsable_id: "u-ana",
        responsable_nombre: "ana",
        evento_id: "ev-fut",
        fecha_objetivo: "2026-07-20",
        hora_objetivo: "13:00",
      }),
    ]);

    const chipLuis = await screen.findByRole("button", { name: "Ver solo lo de luis" });
    const chipAna = await screen.findByRole("button", { name: "Ver solo lo de ana" });
    // luis: su único partido ya pasó → 0 (pero la fila sigue en la agenda). ana: futuro → 1.
    expect(chipLuis).toHaveTextContent(/0/);
    expect(chipAna).toHaveTextContent(/1/);
    // El partido pasado SIGUE visible en el calendario (no se elimina, solo deja de contar).
    expect(screen.getAllByText("Partido viejo").length).toBeGreaterThan(0);
  });

  it("PANORAMA: el marcador de HOY muestra «hechos/total» del día (en vivo)", async () => {
    const hoy = hoyCDMX();
    renderTareas([
      // Cobertura de HOY ya pasada (01:00) → hecha.
      tarea({ id: "cA", evento_id: "evA", responsable_id: "u-luis", responsable_nombre: "luis", fecha_objetivo: hoy, hora_objetivo: "01:00" }),
      // Cobertura de HOY futura (23:59) → pendiente.
      tarea({ id: "cB", evento_id: "evB", responsable_id: "u-ana", responsable_nombre: "ana", fecha_objetivo: hoy, hora_objetivo: "23:59" }),
      // Encargo de HOY hecho → cuenta como hecho.
      tarea({ id: "eC", titulo: "Encargo hecho", fecha_objetivo: hoy, estado: "hecha", responsable_id: "u-luis", responsable_nombre: "luis" }),
      // Encargo de HOY pendiente.
      tarea({ id: "eD", titulo: "Encargo pendiente", fecha_objetivo: hoy, estado: "pendiente" }),
    ]);

    // 4 cosas hoy, 2 hechas (el partido pasado + el encargo hecho) → «2 / 4» (hechas / total).
    const marcador = await screen.findByLabelText(/Avance de hoy/);
    expect(marcador).toHaveTextContent(/2\s*\/\s*4/);
    // 50% (< 90%): la barra es naranja de marca, aún no verde.
    expect(marcador.querySelector(".bg-keni-500")).not.toBeNull();
    expect(marcador.querySelector(".bg-emerald-500")).toBeNull();
  });

  it("PANORAMA: el marcador se pone VERDE al llegar al 90% del día", async () => {
    const hoy = hoyCDMX();
    // 9 hechas + 1 pendiente = 9/10 = 90% → verde.
    const hechas = Array.from({ length: 9 }, (_, i) =>
      tarea({ id: `h${i}`, titulo: `Hecha ${i}`, fecha_objetivo: hoy, estado: "hecha", responsable_id: "u-luis", responsable_nombre: "luis" }),
    );
    renderTareas([
      ...hechas,
      tarea({ id: "pend", titulo: "Pendiente", fecha_objetivo: hoy, estado: "pendiente" }),
    ]);

    const marcador = await screen.findByLabelText(/Avance de hoy/);
    expect(marcador).toHaveTextContent(/9\s*\/\s*10/);
    expect(marcador.querySelector(".bg-emerald-500")).not.toBeNull(); // verde a ≥90%
    expect(marcador.querySelector(".bg-keni-500")).toBeNull();
  });

  it("un evento 'no_cubrir' NO aparece en la lista", async () => {
    renderTareas([], [evento({ id: "ev-x", titulo: "Amistoso sin señal", tipo_cobertura: "no_cubrir" })]);
    await waitFor(() => expect(apiMod.api.rotaEventos).toHaveBeenCalled());
    expect(screen.queryByText("Amistoso sin señal")).toBeNull();
  });

  it("una tarea LIBRE (encargo) ofrece 'Coger' y llama a cogerPublicacion", async () => {
    const coger = vi
      .spyOn(apiMod.api, "cogerPublicacion")
      .mockResolvedValue({ contenido: {} } as never);
    renderTareas([tarea({ id: "t9", titulo: "Grabar el saque" })]);

    // Desplegar la fila del Panorama para llegar a la tarjeta accionable.
    fireEvent.click(await screen.findByText("Grabar el saque"));
    // Item-first: click en la tarjeta «Sin cubrir» → acción primaria = coger. (Hay dos «Sin
    // cubrir» al desplegar: el badge de la fila y el de la tarjeta; la tarjeta es el último.)
    const sinCubrir3 = await screen.findAllByText("Sin cubrir");
    fireEvent.click(sinCubrir3[sinCubrir3.length - 1].closest("[role='button']")!);
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
    // Ambas tareas aparecen en el Panorama (vista por defecto) antes de filtrar.
    expect((await screen.findAllByText("Mía")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("De Ana").length).toBeGreaterThan(0);

    // Radix Tabs activa en pointer-down (no en click) — patrón del resto de la suite.
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Mis tareas" }), { button: 0 });
    await waitFor(() => expect(screen.queryByText("De Ana")).toBeNull());
    expect(screen.getByText("Mía")).toBeInTheDocument();
  });

  it("Mis tareas: una cobertura cuyo partido ya pasó cae a «Hechas», no «En marcha»", async () => {
    renderTareas(
      [
        // Cobertura MÍA de un partido ya jugado (fecha pasada con hora) → hecha.
        tarea({ id: "c-pas", titulo: "Partido jugado", evento_id: "ev-pas", responsable_id: "u1", responsable_nombre: "yo", fecha_objetivo: "2020-01-01", hora_objetivo: "19:00" }),
        // Cobertura MÍA de un partido futuro → sigue en marcha.
        tarea({ id: "c-fut", titulo: "Partido proximo", evento_id: "ev-fut", responsable_id: "u1", responsable_nombre: "yo", fecha_objetivo: "2099-01-01", hora_objetivo: "19:00" }),
      ],
      [],
      usuario("editor", "u1"),
    );
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Mis tareas" }), { button: 0 });

    const hechas = (await screen.findByRole("heading", { name: /Hechas/ })).closest("section")!;
    expect(within(hechas).getAllByText("Partido jugado").length).toBeGreaterThan(0);
    expect(within(hechas).queryAllByText("Partido proximo")).toHaveLength(0);

    const enMarcha = screen.getByRole("heading", { name: /En marcha/ }).closest("section")!;
    expect(within(enMarcha).getAllByText("Partido proximo").length).toBeGreaterThan(0);
    expect(within(enMarcha).queryAllByText("Partido jugado")).toHaveLength(0);
  });

  it("un MANAGER (admin) ve 'Asignar'; un editor NO", async () => {
    const { unmount } = renderTareas([tarea({ titulo: "Reparto" })], [], usuario("admin", "u-admin"));
    fireEvent.click(await screen.findByText("Reparto")); // desplegar la fila del Panorama
    // Asignar está en el menú contextual (kebab="nunca"), no como botón visible.
    const sinCubrirAdm = await screen.findAllByText("Sin cubrir");
    fireEvent.contextMenu(sinCubrirAdm[sinCubrirAdm.length - 1].closest("[role='button']")!);
    expect(await screen.findByRole("menuitem", { name: /Asignar/ })).toBeInTheDocument();
    unmount();

    vi.restoreAllMocks();
    renderTareas([tarea({ titulo: "Reparto" })], [], usuario("editor", "u2"));
    fireEvent.click(await screen.findByText("Reparto"));
    const sinCubrirEd = await screen.findAllByText("Sin cubrir");
    // El editor no tiene acciones secundarias: el menú no abre y Asignar no aparece.
    fireEvent.contextMenu(sinCubrirEd[sinCubrirEd.length - 1].closest("[role='button']")!);
    expect(screen.queryByRole("menuitem", { name: /Asignar/ })).toBeNull();
  });

  it("el 'Panorama' (por defecto) mezcla eventos por cubrir y tareas con dueño", async () => {
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

    // El Panorama es la vista por defecto: no hay que cambiar de pestaña.
    expect(await screen.findByText("Partido por cubrir")).toBeInTheDocument();
    expect(screen.getByText("Clip de Luis")).toBeInTheDocument();

    // Sin turno en su franja (semana vacía), el evento sin dueño se marca «Sin cubrir».
    expect(screen.getAllByText("Sin cubrir").length).toBeGreaterThan(0);

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

    // La fila compacta (un botón) se despliega y muestra la tarjeta accionable.
    fireEvent.click(await screen.findByRole("button", { name: /Clip de Luis/ }));
    // «Asignar a…» está en el menú contextual; se accede con click derecho sobre la tarjeta.
    const luisEls = await screen.findAllByText("luis");
    const cardHostLuis = luisEls.map(el => el.closest("[role='button']")).find(Boolean)!;
    fireEvent.contextMenu(cardHostLuis);
    expect(await screen.findByRole("menuitem", { name: /Asignar a/ })).toBeInTheDocument();
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
    // Item-first: click en el host de TarjetaCobertura (acción primaria = Apuntarme).
    const grupoApuntar = screen.getByRole("group", { name: "Rol de cobertura" });
    fireEvent.click(grupoApuntar.closest("[role='button']")!);
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

  it("RECUPERACIÓN: una cobertura soltada (sin dueño) reaparece como «Sin cubrir» y se re-coge", async () => {
    const coger = vi
      .spyOn(apiMod.api, "cogerPublicacion")
      .mockResolvedValue({ contenido: {} } as never);
    // Tarea de cobertura SUELTA (evento_id pero sin responsable, como tras «Soltar»): el
    // partido NO se borró, debe reaparecer como «Por cubrir» y poder re-cogerse.
    renderTareas([
      tarea({ id: "t-suelta", titulo: "Brasil vs Marruecos", evento_id: "ev2", responsable_id: "", responsable_nombre: "", fecha_objetivo: "2026-07-02" }),
    ]);

    fireEvent.click(await screen.findByText("Brasil vs Marruecos"));
    // Item-first: la cobertura suelta muestra badge «Sin cubrir»; click en la tarjeta = coger
    // (el último «Sin cubrir»: el primero es el badge de la fila del Panorama).
    const sinCubrirSuelta = await screen.findAllByText("Sin cubrir");
    fireEvent.click(sinCubrirSuelta[sinCubrirSuelta.length - 1].closest("[role='button']")!);
    await waitFor(() => expect(coger).toHaveBeenCalledWith("t-suelta"));
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
    fireEvent.click(screen.getByRole("button", { name: "Video" })); // elegir rol Video en SelectorRol
    // Item-first: click en el host de la tarjeta (no en el botón Video) dispara cubrirEvento con el rol elegido.
    const grupoRol = screen.getByRole("group", { name: "Rol de cobertura" });
    fireEvent.click(grupoRol.closest("[role='button']")!);
    await waitFor(() => expect(cubrir).toHaveBeenCalledWith("ev9", undefined, "video"));
  });

  it("QUITARME: en MI cobertura libera mi rol con soltarPublicacion (NO borra el partido)", async () => {
    const soltar = vi
      .spyOn(apiMod.api, "soltarPublicacion")
      .mockResolvedValue({ contenido: {} } as never);
    // Soy la cubridora (responsable_id == id de mi sesión): mi tarjeta ofrece «Quitarme».
    renderTareas(
      [tarea({ id: "t-mia", titulo: "Cruz Azul vs América", evento_id: "ev1", responsable_id: "u-yo", responsable_nombre: "yo", formato: "video", fecha_objetivo: "2026-07-01" })],
      [],
      usuario("editor", "u-yo"),
    );

    fireEvent.click(await screen.findByRole("button", { name: /Cruz Azul vs América/ }));
    // Item-first: la TarjetaTarea (enCobertura, esMia) tiene primaria=soltar.
    // Se identifica por «· tú» que solo aparece cuando esMia=true.
    const tuEl = await screen.findByText(/· tú/);
    fireEvent.click(tuEl.closest("[role='button']")!);
    await waitFor(() => expect(soltar).toHaveBeenCalledWith("t-mia"));
  });

  it("QUITAR-A-OTRO: el × del chip «Cubren:» suelta a esa persona (solo manager)", async () => {
    const soltar = vi
      .spyOn(apiMod.api, "soltarPublicacion")
      .mockResolvedValue({ contenido: {} } as never);
    // Soy manager (admin) y NO soy la cubridora: el chip de «tezcu» ofrece la × para quitarla.
    renderTareas(
      [tarea({ id: "t-tezcu", titulo: "Cruz Azul vs América", evento_id: "ev1", responsable_id: "u-tezcu", responsable_nombre: "tezcu", formato: "foto", fecha_objetivo: "2026-07-01" })],
      [],
      usuario("admin", "u-mgr"),
    );

    fireEvent.click(await screen.findByRole("button", { name: /Cruz Azul vs América/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Quitar a tezcu" }));
    await waitFor(() => expect(soltar).toHaveBeenCalledWith("t-tezcu"));
  });

  it("'Añadir' (barra) abre el diálogo grande de la lista", async () => {
    renderTareas([]);
    // Hay dos «Añadir»: el atajo inline del Panorama (dentro de su <form>) y el de la barra.
    // El de la barra (fuera del form) abre el diálogo rico (import por enlace/documento, encargos).
    const botones = await screen.findAllByRole("button", { name: /Añadir/ });
    const barra = botones.find((b) => !b.closest("form"))!;
    fireEvent.click(barra);
    expect(await screen.findByText("Añadir a la lista")).toBeInTheDocument();
  });

  it("en modo Tarea también aparece la caja inteligente de import (pega/sube/escribe → IA)", async () => {
    renderTareas([]);
    const botones = await screen.findAllByRole("button", { name: /Añadir/ });
    fireEvent.click(botones.find((b) => !b.closest("form"))!);
    await screen.findByText("Añadir a la lista");
    // Cambia al modo Tarea: la caja inteligente (antes solo en Evento) debe seguir ahí.
    fireEvent.click(screen.getByRole("button", { name: "Tarea" }));
    expect(screen.getByRole("button", { name: /Analizar/ })).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("Pega un enlace, o escribe la tarea en una frase…"),
    ).toBeInTheDocument();
  });

  it("AÑADIR-RÁPIDO: el atajo del Panorama crea un ítem «por cubrir» HOY (CDMX) con crearEventoRota", async () => {
    const crear = vi.spyOn(apiMod.api, "crearEventoRota").mockResolvedValue({} as never);
    renderTareas([]);

    const input = await screen.findByPlaceholderText("¿Qué hay que cubrir?");
    fireEvent.change(input, { target: { value: "Reacciones del Toluca" } });
    // El botón del atajo vive en el MISMO <form> que el input (lo separa del «Añadir» de la barra).
    const form = input.closest("form")!;
    fireEvent.click(within(form).getByRole("button", { name: /Añadir/ }));

    await waitFor(() => expect(crear).toHaveBeenCalledTimes(1));
    expect(crear).toHaveBeenCalledWith(
      expect.objectContaining({
        titulo: "Reacciones del Toluca",
        fecha: hoyCDMX(),
        tipo_cobertura: "transmision",
        marca: "claro-sports",
      }),
    );
    // Tras crear, limpia el input para el siguiente atajo.
    await waitFor(() => expect((input as HTMLInputElement).value).toBe(""));
  });

  it("URGENCIA: en HOY, lo «en vivo» flota por encima de un evento más temprano ya pasado", () => {
    // Reloj fijo: 23:30 CDMX del 13-jun (= 05:30 UTC del 14-jun). Sin async (render directo).
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-14T05:30:00Z"));
    const hoy = hoyCDMX(); // "2026-06-13" en CDMX

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <PanoramaAgenda
            tareas={[]}
            eventos={[
              // Más temprano (00:00) y YA pasado → «sin cubrir», pero baja en urgencia.
              evento({ id: "ev-temprano", titulo: "Empezó temprano", fecha: hoy, hora: "00:00" }),
              // En curso ahora (23:00, ventana 180') → «en vivo», debe flotar arriba.
              evento({ id: "ev-vivo", titulo: "En vivo ahora", fecha: hoy, hora: "23:00" }),
            ]}
            catalogos={catalogos()}
            marca="claro-sports"
            cubiertosPorTurno={new Set()}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const vivo = screen.getByText("En vivo ahora");
    const temprano = screen.getByText("Empezó temprano");
    // «En vivo» va ANTES en el DOM que el evento más temprano ya pasado (urgencia > hora).
    expect(vivo.compareDocumentPosition(temprano) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("ORDEN: el cajón «Hoy» va ANTES que un día pasado en el Panorama", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-15T12:00:00Z")); // hoy = 2026-06-15 (CDMX)
    const hoy = hoyCDMX();
    renderPanorama({
      eventos: [
        evento({ id: "ev-pasado", titulo: "Partido pasado", fecha: "2026-06-12", hora: "13:00" }),
        evento({ id: "ev-hoy", titulo: "Partido de hoy", fecha: hoy, hora: "10:00" }),
      ],
    });
    const elHoy = screen.getByText("Partido de hoy");
    const elPasado = screen.getByText("Partido pasado");
    // «Hoy» primero: el de hoy va ANTES en el DOM que el del día pasado, aunque sea más tarde por fecha.
    expect(
      elHoy.compareDocumentPosition(elPasado) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("SIN FECHA: un encargo suelto sin «Para cuándo» SIGUE visible aunque la agenda pagine los días", () => {
    // Regresión (lo que el equipo veía como «la tarea no se guarda»): una tarea sin fecha cae en el
    // cajón «Sin fecha» (orden "9999-99-99"), que `ordenDiaAgenda` manda al FINAL. Con ≥5 días de
    // eventos por delante quedaba FUERA de la ventana `diasVisibles` (5), oculta tras «Cargar más
    // días» —parecía que no se había guardado—. Ahora «Sin fecha» se ancla al fondo y NO se pagina.
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-15T12:00:00Z")); // hoy = 2026-06-15 (CDMX)
    renderPanorama({
      // 6 días FUTUROS distintos (más que la ventana de 5) → el 6º queda tras «Cargar más días».
      eventos: [
        evento({ id: "d1", titulo: "Día 1", fecha: "2026-06-16" }),
        evento({ id: "d2", titulo: "Día 2", fecha: "2026-06-17" }),
        evento({ id: "d3", titulo: "Día 3", fecha: "2026-06-18" }),
        evento({ id: "d4", titulo: "Día 4", fecha: "2026-06-19" }),
        evento({ id: "d5", titulo: "Día 5", fecha: "2026-06-20" }),
        evento({ id: "d6", titulo: "Día 6", fecha: "2026-06-21" }),
      ],
      tareas: [tarea({ id: "t-sin", titulo: "Encargo sin fecha", fecha_objetivo: "" })],
    });

    // La paginación está activa (hay un 6º día oculto)…
    expect(screen.getByRole("button", { name: "Cargar más días" })).toBeInTheDocument();
    // …pero el encargo SIN fecha se muestra igual, bajo su cajón «Sin fecha» anclado al fondo.
    expect(screen.getByText("Encargo sin fecha")).toBeInTheDocument();
    expect(screen.getByText("Sin fecha")).toBeInTheDocument();
  });

  it("AÑADIR-RÁPIDO + ⚡ Urgente: crea el ítem con prioridad «alta»", async () => {
    const crear = vi.spyOn(apiMod.api, "crearEventoRota").mockResolvedValue({} as never);
    renderTareas([]);

    const input = await screen.findByPlaceholderText("¿Qué hay que cubrir?");
    fireEvent.change(input, { target: { value: "Gol de último minuto" } });
    fireEvent.click(screen.getByRole("button", { name: "Urgente" })); // activa el toggle
    const form = input.closest("form")!;
    fireEvent.click(within(form).getByRole("button", { name: /Añadir/ }));

    await waitFor(() => expect(crear).toHaveBeenCalledTimes(1));
    expect(crear).toHaveBeenCalledWith(
      expect.objectContaining({
        titulo: "Gol de último minuto",
        fecha: hoyCDMX(),
        prioridad: "alta",
      }),
    );
  });

  // Helper: renderiza el Panorama AISLADO (síncrono, sin react-query fetch) para probar el ⚡.
  function renderPanorama(props: {
    tareas?: Publicacion[];
    eventos?: EventoRota[];
    cubiertosPorTurno?: Set<string>;
  }) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <PanoramaAgenda
            tareas={props.tareas ?? []}
            eventos={props.eventos ?? []}
            catalogos={catalogos()}
            marca="claro-sports"
            cubiertosPorTurno={props.cubiertosPorTurno ?? new Set()}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it("ESCALAR evento: el ⚡ de un evento por cubrir lo marca urgente vía actualizarEventoRota", async () => {
    const actualizar = vi
      .spyOn(apiMod.api, "actualizarEventoRota")
      .mockResolvedValue({} as never);
    renderPanorama({
      eventos: [evento({ id: "ev9", titulo: "Reacciones del Toluca", fecha: "2026-07-01" })],
    });

    fireEvent.click(screen.getByRole("button", { name: "Marcar urgente" }));
    await waitFor(() =>
      expect(actualizar).toHaveBeenCalledWith("ev9", { prioridad: "alta" }),
    );
  });

  it("ESCALAR cobertura: el ⚡ escala el EVENTO subyacente, no la tarea de cobertura", async () => {
    const actualizar = vi
      .spyOn(apiMod.api, "actualizarEventoRota")
      .mockResolvedValue({} as never);
    renderPanorama({
      tareas: [
        tarea({
          id: "t-cob",
          titulo: "Cruz Azul vs América",
          evento_id: "ev1",
          responsable_id: "u-luis",
          responsable_nombre: "luis",
          fecha_objetivo: "2026-07-01",
        }),
      ],
      eventos: [evento({ id: "ev1", fecha: "2026-07-01" })],
    });

    fireEvent.click(screen.getByRole("button", { name: "Marcar urgente" }));
    await waitFor(() =>
      expect(actualizar).toHaveBeenCalledWith("ev1", { prioridad: "alta" }),
    );
  });

  it("ESCALAR encargo: el ⚡ de una tarea la marca urgente vía actualizarPublicacion", async () => {
    const actualizar = vi
      .spyOn(apiMod.api, "actualizarPublicacion")
      .mockResolvedValue({} as never);
    renderPanorama({
      tareas: [
        tarea({
          id: "t9",
          titulo: "Editar el clip",
          responsable_id: "u-luis",
          responsable_nombre: "luis",
          fecha_objetivo: "2026-07-01",
        }),
      ],
    });

    fireEvent.click(screen.getByRole("button", { name: "Marcar urgente" }));
    await waitFor(() =>
      expect(actualizar).toHaveBeenCalledWith("t9", { prioridad: "alta" }),
    );
  });

  it("DES-ESCALAR: un ítem ya urgente ofrece «Quitar urgente» (→ media)", async () => {
    const actualizar = vi
      .spyOn(apiMod.api, "actualizarEventoRota")
      .mockResolvedValue({} as never);
    // Futuro + «alta» → NO es breaking (no salta a la banda), se queda en su día con su ⚡ encendido.
    renderPanorama({
      eventos: [
        evento({ id: "ev-alta", titulo: "Final de copa", fecha: "2026-07-01", prioridad: "alta" }),
      ],
    });

    fireEvent.click(screen.getByRole("button", { name: "Quitar urgente" }));
    await waitFor(() =>
      expect(actualizar).toHaveBeenCalledWith("ev-alta", { prioridad: "media" }),
    );
  });

  it("BANDA «URGENTE AHORA»: lo urgente de HOY salta al tope; lo de otro día se queda en su día", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-14T18:00:00Z")); // 12:00 CDMX del 14-jun
    const hoy = hoyCDMX(); // "2026-06-14"

    renderPanorama({
      eventos: [
        evento({ id: "ev-hoy", titulo: "Breaking ahora", fecha: hoy, hora: "20:00", prioridad: "alta" }),
        evento({
          id: "ev-prox",
          titulo: "Urgente la próxima semana",
          fecha: "2026-06-21",
          hora: "20:00",
          prioridad: "alta",
        }),
      ],
    });

    const banda = screen.getByRole("region", { name: "Urgente ahora" });
    // Lo urgente de HOY está DENTRO de la banda (salió de su cajón de día).
    expect(within(banda).getByText("Breaking ahora")).toBeInTheDocument();
    // Lo urgente de otro día NO está en la banda…
    expect(within(banda).queryByText("Urgente la próxima semana")).toBeNull();
    // …pero sigue en la página, en su cajón de día (con su badge rojo).
    expect(screen.getByText("Urgente la próxima semana")).toBeInTheDocument();
  });

  it("BANDA «URGENTE AHORA»: un partido urgente YA CUBIERTO no entra en la banda (solo los huecos)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-14T18:00:00Z")); // 12:00 CDMX del 14-jun
    const hoy = hoyCDMX(); // "2026-06-14"

    renderPanorama({
      // Cobertura de HOY, prioridad alta (heredada del evento) PERO con dueño (luis la cubre).
      tareas: [
        tarea({
          id: "t-cub",
          titulo: "Clásico cubierto",
          evento_id: "ev-hot",
          responsable_id: "u-luis",
          responsable_nombre: "luis",
          fecha_objetivo: hoy,
          hora_objetivo: "20:00",
        }),
      ],
      eventos: [evento({ id: "ev-hot", titulo: "Clásico cubierto", fecha: hoy, hora: "20:00", prioridad: "alta" })],
    });

    // Alta + hoy, pero CUBIERTO → no es un hueco: no hay banda «Urgente ahora».
    expect(screen.queryByRole("region", { name: "Urgente ahora" })).toBeNull();
    // Sigue visible en su cajón de día (no se esconde, solo no compite en la banda roja).
    expect(screen.getAllByText("Clásico cubierto").length).toBeGreaterThan(0);
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
    fireEvent.change(screen.getByPlaceholderText(/Pega un enlace/), {
      target: { value: "https://liga.test/jornada" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Analizar/ }));

    // El partido propuesto aparece para revisar y se acepta.
    expect(await screen.findByText("Cruz Azul vs América")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Aceptar y añadir/ }));
    await waitFor(() => expect(aplicar).toHaveBeenCalledWith("p1"));
  });

  it("FETCH: pide los eventos «desde» el día CDMX, no el UTC (no pierde los partidos de la tarde-noche)", async () => {
    // 23:30 CDMX del 13-jun = 05:30 UTC del 14-jun. En UTC «hoy» ya es el 14 (mañana): el bug
    // filtraba `desde: 2026-06-14` y se caían del fetch los partidos de HOY (el horario de partidos).
    // Falseamos SOLO `Date` (no los timers) para que `waitFor`/react-query corran con relojes reales.
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-06-14T05:30:00Z"));
    renderTareas([], []);
    await waitFor(() => expect(apiMod.api.rotaEventos).toHaveBeenCalled());
    // Día CDMX = 13; día UTC = 14. El fetch debe arrancar en el 13, nunca en el 14.
    expect(apiMod.api.rotaEventos).toHaveBeenCalledWith(
      expect.objectContaining({ desde: "2026-06-13" }),
      expect.anything(),
    );
    expect(apiMod.api.rotaEventos).not.toHaveBeenCalledWith(
      expect.objectContaining({ desde: "2026-06-14" }),
      expect.anything(),
    );
  });

  it("ERROR: si el fetch falla sin caché, pinta error+reintento (no «todo cubierto» en blanco)", async () => {
    const contenido = vi
      .spyOn(apiMod.api, "contenido")
      .mockRejectedValue(new Error("caída de red"));
    const rotaEventos = vi
      .spyOn(apiMod.api, "rotaEventos")
      .mockRejectedValue(new Error("caída de red"));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <SesionContexto.Provider value={sesionValor(usuario())}>
          <MarcaActivaContexto.Provider value={valorMarca("claro-sports")}>
            <MemoryRouter>
              <Tareas />
            </MemoryRouter>
          </MarcaActivaContexto.Provider>
        </SesionContexto.Provider>
      </QueryClientProvider>,
    );

    // En vez de listas vacías («No tienes nada asignado»), sale el bloque de error con su reintento.
    expect(await screen.findByText("No se pudo cargar el tablero")).toBeInTheDocument();
    expect(screen.queryByText(/No tienes nada asignado/)).toBeNull();

    // «Reintentar» relanza AMBAS queries (tareas y eventos), no solo una.
    const antesPublicacion = contenido.mock.calls.length;
    const antesEventos = rotaEventos.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: /Reintentar/ }));
    await waitFor(() => {
      expect(contenido.mock.calls.length).toBeGreaterThan(antesPublicacion);
      expect(rotaEventos.mock.calls.length).toBeGreaterThan(antesEventos);
    });
  });

  // --- EDITAR / BORRAR el partido desde la agenda (solo admin) ---

  it("MANAGER EDITA un evento por cubrir: abre el diálogo y guarda vía actualizarEventoRota", async () => {
    const actualizar = vi
      .spyOn(apiMod.api, "actualizarEventoRota")
      .mockResolvedValue({} as never);
    renderTareas(
      [],
      [evento({ id: "ev9", titulo: "Cruz Azul vs América" })],
      usuario("admin", "u-admin"),
    );

    fireEvent.click(await screen.findByText("Cruz Azul vs América")); // desplegar la fila
    const card = screen
      .getByRole("group", { name: "Rol de cobertura" })
      .closest("[role='button']")!;
    fireEvent.contextMenu(card);
    fireEvent.click(await screen.findByRole("menuitem", { name: /Editar/ }));

    // Aparece el diálogo de edición y «Guardar» dispara el PATCH del evento.
    expect(await screen.findByText("Editar evento")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() =>
      expect(actualizar).toHaveBeenCalledWith(
        "ev9",
        expect.objectContaining({ titulo: "Cruz Azul vs América" }),
      ),
    );
  });

  it("MANAGER BORRA un evento por cubrir: confirma y llama a eliminarEventoRota", async () => {
    const borrar = vi
      .spyOn(apiMod.api, "eliminarEventoRota")
      .mockResolvedValue({ mensaje: "ok" } as never);
    renderTareas(
      [],
      [evento({ id: "ev9", titulo: "Cruz Azul vs América" })],
      usuario("admin", "u-admin"),
    );

    fireEvent.click(await screen.findByText("Cruz Azul vs América"));
    const card = screen
      .getByRole("group", { name: "Rol de cobertura" })
      .closest("[role='button']")!;
    fireEvent.contextMenu(card);
    fireEvent.click(await screen.findByRole("menuitem", { name: /Borrar/ }));
    await waitFor(() => expect(borrar).toHaveBeenCalledWith("ev9"));
  });

  it("un EDITOR (no admin) NO ve Editar/Borrar del evento", async () => {
    renderTareas(
      [],
      [evento({ id: "ev9", titulo: "Cruz Azul vs América" })],
      usuario("editor", "u-ed"),
    );
    fireEvent.click(await screen.findByText("Cruz Azul vs América"));
    const card = screen
      .getByRole("group", { name: "Rol de cobertura" })
      .closest("[role='button']")!;
    fireEvent.contextMenu(card);
    // Sin acciones de admin no se abre menú alguno: no hay item «Editar» ni «Borrar».
    expect(screen.queryByRole("menuitem", { name: /Editar/ })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: /Borrar/ })).toBeNull();
  });

  it("BORRAR una cobertura borra el evento Y sus tareas en cascada (el partido se cancela)", async () => {
    const borrarEv = vi
      .spyOn(apiMod.api, "eliminarEventoRota")
      .mockResolvedValue({ mensaje: "ok" } as never);
    const borrarCont = vi
      .spyOn(apiMod.api, "eliminarPublicacion")
      .mockResolvedValue({} as never);
    renderTareas(
      [
        tarea({
          id: "t-cob",
          titulo: "Cruz Azul vs América",
          evento_id: "ev1",
          responsable_id: "u-luis",
          responsable_nombre: "luis",
          fecha_objetivo: "2026-07-01",
        }),
      ],
      [evento({ id: "ev1", titulo: "Cruz Azul vs América", fecha: "2026-07-01" })],
      usuario("admin", "u-admin"),
    );

    // Desplegamos la fila de la agenda (el título vive dentro de su <button> de toggle).
    const titulos = await screen.findAllByText("Cruz Azul vs América");
    const filaBtn = titulos.map((t) => t.closest("button")).find(Boolean)!;
    fireEvent.click(filaBtn);

    const card = screen.getByText("Cubren:").closest("[role='button']")!;
    fireEvent.contextMenu(card);
    fireEvent.click(await screen.findByRole("menuitem", { name: /Borrar/ }));

    await waitFor(() => expect(borrarEv).toHaveBeenCalledWith("ev1"));
    expect(borrarCont).toHaveBeenCalledWith("t-cob");
  });

  // --- Editar/Borrar EN LA PROPIA FILA (junto al ⚡), sin desplegar ---

  it("la fila muestra «Editar» (lápiz) y «Borrar» (papelera) SIN desplegar (admin)", async () => {
    renderTareas(
      [],
      [evento({ id: "ev9", titulo: "Cruz Azul vs América" })],
      usuario("admin", "u-admin"),
    );
    await screen.findByText("Cruz Azul vs América");
    // Botones directos en la fila colapsada (nombre exacto = aria-label, no el título de la fila).
    expect(screen.getByRole("button", { name: "Editar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Borrar" })).toBeInTheDocument();
  });

  it("la papelera de la fila borra el evento por cubrir (confirma → eliminarEventoRota)", async () => {
    const borrar = vi
      .spyOn(apiMod.api, "eliminarEventoRota")
      .mockResolvedValue({ mensaje: "ok" } as never);
    renderTareas(
      [],
      [evento({ id: "ev9", titulo: "Cruz Azul vs América" })],
      usuario("admin", "u-admin"),
    );
    await screen.findByText("Cruz Azul vs América");
    fireEvent.click(screen.getByRole("button", { name: "Borrar" }));
    await waitFor(() => expect(borrar).toHaveBeenCalledWith("ev9"));
  });

  it("el lápiz de la fila abre el diálogo de edición (igual que el calendario)", async () => {
    renderTareas(
      [],
      [evento({ id: "ev9", titulo: "Cruz Azul vs América" })],
      usuario("admin", "u-admin"),
    );
    await screen.findByText("Cruz Azul vs América");
    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    expect(await screen.findByText("Editar evento")).toBeInTheDocument();
  });

  it("la papelera de la fila borra una cobertura en cascada (evento + tareas), sin desplegar", async () => {
    const borrarEv = vi
      .spyOn(apiMod.api, "eliminarEventoRota")
      .mockResolvedValue({ mensaje: "ok" } as never);
    const borrarCont = vi
      .spyOn(apiMod.api, "eliminarPublicacion")
      .mockResolvedValue({} as never);
    renderTareas(
      [
        tarea({
          id: "t-cob",
          titulo: "Cruz Azul vs América",
          evento_id: "ev1",
          responsable_id: "u-luis",
          responsable_nombre: "luis",
          fecha_objetivo: "2026-07-01",
        }),
      ],
      [evento({ id: "ev1", titulo: "Cruz Azul vs América", fecha: "2026-07-01" })],
      usuario("admin", "u-admin"),
    );
    await screen.findAllByText("Cruz Azul vs América");
    fireEvent.click(screen.getByRole("button", { name: "Borrar" }));
    await waitFor(() => expect(borrarEv).toHaveBeenCalledWith("ev1"));
    expect(borrarCont).toHaveBeenCalledWith("t-cob");
  });

  it("un ENCARGO (sin evento) muestra papelera pero NO lápiz; borra vía eliminarPublicacion", async () => {
    const borrar = vi.spyOn(apiMod.api, "eliminarPublicacion").mockResolvedValue({} as never);
    renderTareas(
      [tarea({ id: "t9", titulo: "Grabar el saque" })],
      [],
      usuario("admin", "u-admin"),
    );
    await screen.findByText("Grabar el saque");
    expect(screen.queryByRole("button", { name: "Editar" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Borrar" }));
    await waitFor(() => expect(borrar).toHaveBeenCalledWith("t9"));
  });

  it("un EDITOR (no admin) NO ve los botones de la fila", async () => {
    renderTareas(
      [],
      [evento({ id: "ev9", titulo: "Cruz Azul vs América" })],
      usuario("editor", "u-ed"),
    );
    await screen.findByText("Cruz Azul vs América");
    expect(screen.queryByRole("button", { name: "Editar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Borrar" })).toBeNull();
  });
});
