import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  MarcaActivaContexto,
  type ValorMarcaActiva,
} from "@/hooks/marca-activa-contexto";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import * as apiMod from "@/lib/api";
import type { UsuarioSesion } from "@/types";

import Rota from "./index";
import { interaccionEnCapaHija } from "./coberturaDialogo";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

function usuario(rol: UsuarioSesion["rol"] = "admin"): UsuarioSesion {
  return {
    id: "u1",
    usuario: "yo",
    rol,
    debe_cambiar_password: false,
    marcas: ["claro-sports"],
  };
}

function sesionValor(rol: UsuarioSesion["rol"] = "admin"): ValorSesion {
  return {
    usuario: usuario(rol),
    cargando: false,
    errorConexion: false,
    iniciarSesion: vi.fn(),
    verificarConPasskey: vi.fn(),
    entrarConPasskey: vi.fn(),
    cerrarSesion: vi.fn(),
    refrescar: vi.fn(),
  };
}

function valorMarca(): ValorMarcaActiva {
  return {
    marcaActiva: "claro-sports",
    marcaPrimaria: "claro-sports",
    enMarcaPrimaria: true,
    esMultiMarca: false,
    puedeTodas: false,
    marcasParaSwitch: [],
    nombreActiva: "Claro Sports",
    cambiarMarca: vi.fn(),
    volverAPrimaria: vi.fn(),
  };
}

/**
 * Sobreescrituras opcionales de las respuestas de API que el Calendario consume. Por defecto
 * van vacías (las lecturas están guardadas con `?? []`); los tests que necesitan un evento en
 * la rejilla inyectan `cobertura` (eventos), `contenido` (tareas+catálogos) y `listarTurnos`
 * (franjas vivas, sin las cuales el evento no se bucketea a ninguna celda).
 */
type OpcionesRender = {
  cobertura?: unknown;
  contenido?: unknown;
  listarTurnos?: unknown;
  misTurnosMes?: unknown;
  rotaEventos?: unknown;
  /** Rol del usuario montado (por defecto `admin`). El modo «Mes» del Calendario arranca en
   *  «Equipo» para el admin y en «Yo» para un editor (que sí está en la rota). */
  rol?: UsuarioSesion["rol"];
};

function renderRota(opts: OpcionesRender = {}, tab?: string) {
  // El Calendario de Turnos dispara varias consultas de rota; las dejamos vacías (sus
  // lecturas están guardadas con `?? []`) para centrarnos en la pestaña «Cobertura».
  for (const m of [
    "cobertura",
    "listarTurnos",
    "rotaEquipo",
    "rotaEquipoTodos",
    "rotaAusencias",
    "listarCoordinacionSemana",
    "listarSwaps",
    "misTurnos",
    "misTurnosMes",
    "turnosMes",
  ] as const) {
    vi.spyOn(apiMod.api, m).mockResolvedValue({} as never);
  }
  // La pestaña «Cobertura» monta el TareasBoard: necesita estas dos.
  vi.spyOn(apiMod.api, "contenido").mockResolvedValue({
    contenidos: [],
    catalogos: { usuarios: [] },
  } as never);
  vi.spyOn(apiMod.api, "rotaEventos").mockResolvedValue({ eventos: [] } as never);

  if (opts.cobertura !== undefined)
    vi.spyOn(apiMod.api, "cobertura").mockResolvedValue(opts.cobertura as never);
  if (opts.listarTurnos !== undefined)
    vi.spyOn(apiMod.api, "listarTurnos").mockResolvedValue(opts.listarTurnos as never);
  if (opts.contenido !== undefined)
    vi.spyOn(apiMod.api, "contenido").mockResolvedValue(opts.contenido as never);
  if (opts.misTurnosMes !== undefined)
    vi.spyOn(apiMod.api, "misTurnosMes").mockResolvedValue(opts.misTurnosMes as never);
  if (opts.rotaEventos !== undefined)
    vi.spyOn(apiMod.api, "rotaEventos").mockResolvedValue(opts.rotaEventos as never);

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const entradas = tab ? [`/?tab=${tab}`] : ["/"];
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesionValor(opts.rol)}>
        <MarcaActivaContexto.Provider value={valorMarca()}>
          <MemoryRouter initialEntries={entradas}>
            <Rota />
          </MemoryRouter>
        </MarcaActivaContexto.Provider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

/** Atajo: monta la página con un `?tab=` inicial (deep-links / compat legacy). */
function renderRotaConTab(tab: string, opts: OpcionesRender = {}) {
  return renderRota(opts, tab);
}

describe("Turnos — integra el tablero de Tareas en la pestaña «Cobertura»", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("abre en la semana ACTUAL (la que contiene hoy), no en la siguiente", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-06-15T12:00:00Z")); // lunes 15 jun 2026 (CDMX)
    renderRota();
    // «Hoy» es el default; el Calendario monta su rejilla (y pide los turnos) al activar su pestaña.
    fireEvent.click(await screen.findByRole("button", { name: "Calendario" }));
    // El Calendario pide los turnos de la semana por defecto: el lunes de HOY (no el siguiente).
    await vi.waitFor(() =>
      expect(
        vi
          .mocked(apiMod.api.listarTurnos)
          .mock.calls.some(([arg]) => (arg as { lunes?: string })?.lunes === "2026-06-15"),
      ).toBe(true),
    );
  });

  it("abre en «Hoy» por defecto, con Calendario y Cobertura disponibles", async () => {
    renderRota();
    // La subnav unificada (topbar) son botones de sección con `aria-current`, agrupados en
    // el landmark «Secciones»; la activa lleva aria-current="page".
    const nav = await screen.findByRole("navigation", { name: "Secciones" });
    expect(within(nav).getByRole("button", { name: "Hoy" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(nav).getByRole("button", { name: "Calendario" })).not.toHaveAttribute(
      "aria-current",
    );
    expect(within(nav).getByRole("button", { name: "Cobertura" })).toBeInTheDocument();
    // «Hoy» no pinta el «Añadir» del tablero (ese vive en «Cobertura»).
    expect(screen.queryByRole("button", { name: "Añadir" })).toBeNull();
  });

  it("el admin ve 4 pestañas incl. «Gestión»; «Cambios y ausencias» y «Mi jornada» ya NO son pestaña", async () => {
    renderRota();
    // «Hoy» es la home. «Cambios y ausencias» vive ahora en el panel de Gestión (no es pestaña para
    // el admin). «Mi jornada» sigue fundida en el modo «Mes» del Calendario.
    const nav = await screen.findByRole("navigation", { name: "Secciones" });
    const tabs = within(nav).getAllByRole("button");
    expect(tabs).toHaveLength(4);
    expect(tabs.map((t) => t.textContent)).toEqual([
      "Hoy",
      "Calendario",
      "Cobertura",
      "Gestión",
    ]);
    expect(within(nav).queryByRole("button", { name: /Cambios y ausencias/ })).toBeNull();
    expect(within(nav).queryByRole("button", { name: "Mi jornada" })).toBeNull();
  });

  it("el Calendario abre en modo «Semana» y ofrece el conmutador Semana|Mes", async () => {
    renderRota();
    fireEvent.click(await screen.findByRole("button", { name: "Calendario" }));
    // Conmutador con PALABRAS (no iconos crípticos): «Semana» activo por defecto.
    expect(
      await screen.findByRole("button", { name: "Semana", pressed: true }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Mes", pressed: false }),
    ).toBeInTheDocument();
  });

  it("conmutar a «Mes» muestra la vista mensual de jornada (Yo/Equipo + Imprimir)", async () => {
    renderRota();
    fireEvent.click(await screen.findByRole("button", { name: "Calendario" }));
    fireEvent.click(await screen.findByRole("button", { name: "Mes", pressed: false }));
    // El modo «Mes» = la antigua «Mi jornada»: su selector de ámbito y su Imprimir/PDF.
    expect(await screen.findByRole("button", { name: "Equipo" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Yo" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Imprimir \/ PDF/ }),
    ).toBeInTheDocument();
  });

  it("deep-link legacy ?tab=mis-turnos cae en el Calendario en modo «Mes»", async () => {
    renderRotaConTab("mis-turnos");
    // No hay pestaña «Mi jornada»: el Calendario queda activo y abierto en «Mes».
    expect(await screen.findByRole("button", { name: "Calendario" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      await screen.findByRole("button", { name: "Mes", pressed: true }),
    ).toBeInTheDocument();
    // Y la vista mensual de jornada ya está montada (su ámbito Yo/Equipo).
    expect(await screen.findByRole("button", { name: "Equipo" })).toBeInTheDocument();
  });

  it("al abrir «Cobertura» aparece el tablero (Panorama + «Añadir» inline)", async () => {
    renderRota();
    // Radix Tabs activa en pointer-down (patrón de la suite).
    fireEvent.click(await screen.findByRole("button", { name: "Cobertura" }));

    // El tablero embebido pinta su botón «Añadir» inline (barra) y, al cargar, el atajo «Añadir»
    // del Panorama: dos botones «Añadir». Basta con que aparezca alguno (el tablero ya montó).
    expect((await screen.findAllByRole("button", { name: "Añadir" })).length).toBeGreaterThan(0);
    expect(
      await screen.findByRole("button", { name: "Ver solo lo por cubrir" }),
    ).toBeInTheDocument();
  });

  it("para el admin, el modo «Mes» del Calendario abre en «Equipo» (turnos de todos)", async () => {
    renderRota();
    fireEvent.click(await screen.findByRole("button", { name: "Calendario" }));
    fireEvent.click(await screen.findByRole("button", { name: "Mes", pressed: false }));
    // El admin no está en la rota: arranca en «Equipo» (jornada de todo el equipo), no en «Yo».
    expect(
      await screen.findByRole("button", { name: "Equipo", pressed: true }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Yo", pressed: false }),
    ).toBeInTheDocument();
  });

  it("para un editor, el modo «Mes» del Calendario abre en «Yo» (su propia jornada)", async () => {
    renderRota({ rol: "editor" });
    fireEvent.click(await screen.findByRole("button", { name: "Calendario" }));
    fireEvent.click(await screen.findByRole("button", { name: "Mes", pressed: false }));
    // El editor sí está en la rota: arranca en «Yo» (su jornada), no en «Equipo».
    expect(
      await screen.findByRole("button", { name: "Yo", pressed: true }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Equipo", pressed: false }),
    ).toBeInTheDocument();
  });

  it("en el Calendario, clicar el chip de un evento abre su tarjeta de COBERTURA (no la edición)", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-06-15T12:00:00Z")); // lunes 15 jun 2026 (CDMX)
    // Un evento «Por cubrir» (sin tarea de cobertura) en la semana en vista, a una hora que
    // cae en la franja Mañana → se bucketea a una celda y pinta su chip clicable.
    renderRota({
      cobertura: {
        eventos: [
          {
            id: "ev-int",
            titulo: "España vs Cabo Verde",
            fecha: "2026-06-16",
            hora: "10:00",
            tipo_cobertura: "transmision",
            prioridad: "media",
            cambiado: false,
          },
        ],
      },
      // Sin las franjas vivas el evento no se bucketea a ninguna celda y el chip no aparece.
      listarTurnos: {
        turnos: [],
        aprobada: false,
        franjas: [
          {
            id: "f-manana",
            lunes: "2026-06-15",
            nombre: "Mañana",
            inicio: "08:00",
            fin: "14:00",
            orden: 0,
            es_descanso: false,
            marca: "claro-sports",
            marca_nombre: "Claro Sports",
          },
        ],
      },
      // Sin tareas de cobertura → el evento queda «Por cubrir» (TarjetaEventoLibre).
      contenido: { contenidos: [], catalogos: { usuarios: [] } },
    });

    // «Hoy» es el default: activamos «Calendario» para montar la rejilla con el chip del evento.
    fireEvent.click(await screen.findByRole("button", { name: "Calendario" }));
    // El chip de evento es clicable (su aria-label arranca por «Cubrir …»).
    const chip = await screen.findByRole("button", { name: /España vs Cabo Verde/ });
    fireEvent.click(chip);

    // Se abre un diálogo de COBERTURA (no el editor de evento): contiene la tarjeta «Por
    // cubrir» con su badge «Sin cubrir» y el menú de acciones (Asignar/Editar/Borrar).
    const dialogo = await screen.findByRole("dialog");
    expect(dialogo).toBeInTheDocument();
    expect(within(dialogo).getByText("Sin cubrir")).toBeInTheDocument();
    expect(
      within(dialogo).getByRole("button", { name: "Más acciones" }),
    ).toBeInTheDocument();
  });

  it("Calendario → «Asignar a…» del chip abre el diálogo de asignar y encarga a la persona", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-06-15T12:00:00Z"));
    renderRota({
      cobertura: {
        eventos: [
          {
            id: "ev-int",
            titulo: "España vs Cabo Verde",
            fecha: "2026-06-16",
            hora: "10:00",
            tipo_cobertura: "transmision",
            prioridad: "media",
            cambiado: false,
          },
        ],
      },
      listarTurnos: {
        turnos: [],
        aprobada: false,
        franjas: [
          {
            id: "f-manana",
            lunes: "2026-06-15",
            nombre: "Mañana",
            inicio: "08:00",
            fin: "14:00",
            orden: 0,
            es_descanso: false,
            marca: "claro-sports",
            marca_nombre: "Claro Sports",
          },
        ],
      },
      // Con una persona en el catálogo: el «Asignar a…» del manager debe poder encargársela.
      contenido: { contenidos: [], catalogos: { usuarios: [{ id: "u-ana", usuario: "ana" }] } },
    });
    const cubrir = vi
      .spyOn(apiMod.api, "cubrirEvento")
      .mockResolvedValue({ contenido: { responsable_nombre: "ana" } } as never);

    // «Hoy» es el default: activamos «Calendario» para montar la rejilla con el chip del evento.
    fireEvent.click(await screen.findByRole("button", { name: "Calendario" }));
    // Abrir el chip → su diálogo de cobertura, y desde el menú elegir «Asignar a…».
    fireEvent.click(await screen.findByRole("button", { name: /España vs Cabo Verde/ }));
    const dialogo = await screen.findByRole("dialog");
    fireEvent.click(within(dialogo).getByRole("button", { name: "Más acciones" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Asignar a…" }));

    // El sub-diálogo de asignar aparece (el diálogo del chip NO se cierra al pulsar el menú) y
    // deja elegir el ROL con que se encarga: elegir «Video» + persona la encarga con ESE rol
    // (antes caía siempre a «foto», sin selector).
    fireEvent.click(await screen.findByRole("button", { name: "Video" }));
    fireEvent.click(screen.getByRole("button", { name: "ana" }));
    await vi.waitFor(() => expect(cubrir).toHaveBeenCalledWith("ev-int", "u-ana", "video"));
  });
});

// El diálogo de cobertura es modal y sus acciones (kebab, «Asignar a…»/«Editar», borrar) se
// portalizan FUERA de su contenido. La guarda decide qué interacciones externas NO lo cierran.
// jsdom no dispara el onInteractOutside real de Radix con fireEvent, así que fijamos la guarda
// directamente: sin «role=dialog» en el filtro, abrir «Asignar a…» cerraba el padre y la
// asignación «no funcionaba» desde el calendario.
describe("interaccionEnCapaHija (guarda del diálogo de cobertura)", () => {
  function dentroDe(rol: string): HTMLElement {
    const capa = document.createElement("div");
    capa.setAttribute("role", rol);
    const hijo = document.createElement("button");
    capa.appendChild(hijo);
    return hijo;
  }

  it("mantiene el padre abierto ante el menú, el sub-diálogo y la confirmación de borrado", () => {
    expect(interaccionEnCapaHija(dentroDe("menu"))).toBe(true);
    expect(interaccionEnCapaHija(dentroDe("dialog"))).toBe(true);
    expect(interaccionEnCapaHija(dentroDe("alertdialog"))).toBe(true);
  });

  it("deja cerrar el padre ante una interacción fuera de cualquier capa hija", () => {
    expect(interaccionEnCapaHija(document.createElement("div"))).toBe(false);
    expect(interaccionEnCapaHija(null)).toBe(false);
  });
});

describe("Turnos — home «Hoy»", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("HERO: muestra tu turno de hoy (franja + horario)", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-06-15T12:00:00Z"));
    renderRota({
      misTurnosMes: {
        mis_turnos: [
          { id: "tn1", fecha: "2026-06-15", franja_nombre: "Matutina", inicio: "08:00", fin: "14:00", miembro_nombre: "yo" },
        ],
        miembro_nombre: "yo",
      },
    });
    expect(await screen.findByText("Matutina")).toBeInTheDocument();
    expect(screen.getByText("08:00–14:00")).toBeInTheDocument();
    expect(screen.getByText("Tu turno hoy")).toBeInTheDocument();
  });

  it("HERO: si hoy no hay turno, el hero NO se muestra (sin cartel de «libras»)", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-06-15T12:00:00Z"));
    renderRota({ misTurnosMes: { mis_turnos: [] } });
    // Espera a que la página cargue (la sección «Lo mío hoy» siempre está) y comprueba que el hero
    // del turno no aparece: ni el cartel de «libras» ni los rótulos de turno.
    await screen.findByText(/Lo mío hoy/);
    expect(screen.queryByText(/Hoy libras/)).toBeNull();
    expect(screen.queryByText("Tu turno hoy")).toBeNull();
    expect(screen.queryByText("Tu próximo turno")).toBeNull();
  });

  it("POR CUBRIR HOY: un evento de hoy sin dueño ni turno se cuenta en el aviso de huecos", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-06-15T12:00:00Z"));
    renderRota({
      rotaEventos: {
        eventos: [
          { id: "ev1", titulo: "Rueda de prensa", fecha: "2026-06-15", hora: "12:00", tipo_cobertura: "transmision", prioridad: "media", cambiado: false },
        ],
      },
      listarTurnos: { turnos: [], aprobada: false, franjas: [] },
    });
    // «Hoy» arranca COLAPSADO: muestra el conteo como aviso, sin listar los huecos todavía.
    expect(await screen.findByText(/1 por cubrir hoy/i)).toBeInTheDocument();
    expect(screen.queryByText("Rueda de prensa")).not.toBeInTheDocument();
  });

  it("POR CUBRIR HOY: al expandir el aviso, lista los huecos de hoy para coger sin salir de «Hoy»", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-06-15T12:00:00Z"));
    renderRota({
      rotaEventos: {
        eventos: [
          { id: "ev1", titulo: "Rueda de prensa", fecha: "2026-06-15", hora: "12:00", tipo_cobertura: "transmision", prioridad: "media", cambiado: false },
        ],
      },
      listarTurnos: { turnos: [], aprobada: false, franjas: [] },
    });
    // Pulsar el aviso revela la lista de huecos in situ (progressive disclosure), sin ir a «Cobertura».
    const aviso = await screen.findByRole("button", { name: /coger lo que falta por cubrir hoy/i });
    fireEvent.click(aviso);
    expect(await screen.findByText("Rueda de prensa")).toBeInTheDocument();
  });

  it("LO MÍO HOY: una cobertura del usuario, de hoy, aparece bajo «Lo mío hoy»", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-06-15T12:00:00Z"));
    renderRota({
      rotaEventos: {
        eventos: [
          { id: "ev2", titulo: "Partido España", fecha: "2026-06-15", hora: "20:00", tipo_cobertura: "transmision", prioridad: "media", cambiado: false },
        ],
      },
      contenido: {
        contenidos: [
          { id: "t1", clase: "tarea", evento_id: "ev2", titulo: "Partido España", responsable_id: "u1", responsable_nombre: "yo", fecha_objetivo: "2026-06-15", hora_objetivo: "20:00", estado: "pendiente", formato: "video" },
        ],
        catalogos: { usuarios: [{ id: "u1", usuario: "yo" }] },
      },
      listarTurnos: { turnos: [], aprobada: false, franjas: [] },
    });
    const seccion = (await screen.findByRole("heading", { name: /Lo mío hoy/ })).closest("section")!;
    expect(within(seccion).getByText("Partido España")).toBeInTheDocument();
  });
});

describe("Turnos — Calendario: gating de coordinador", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("el trabajador (no-admin) NO ve el menú ⋯ de coordinador", async () => {
    renderRota({ rol: "editor" });
    fireEvent.click(await screen.findByRole("button", { name: "Calendario" }));
    // Calendario montado (conmutador visible) y SIN el menú ⋯ (Carga/Export son de coordinador).
    await screen.findByRole("button", { name: "Semana", pressed: true });
    expect(screen.queryByRole("button", { name: "Más acciones" })).toBeNull();
  });

  it("el admin tampoco ve el ⋯ en el Calendario: ahora vive en «Gestión»", async () => {
    renderRota(); // admin por defecto
    fireEvent.click(await screen.findByRole("button", { name: "Calendario" }));
    await screen.findByRole("button", { name: "Semana", pressed: true });
    expect(screen.queryByRole("button", { name: "Más acciones" })).toBeNull();
    // El ⋯ (Franjas/Copiar/Carga/Export) se reubicó en la pestaña admin «Gestión».
    fireEvent.click(screen.getByRole("button", { name: "Gestión" }));
    expect(await screen.findByRole("button", { name: "Más acciones" })).toBeInTheDocument();
  });
});

describe("Turnos — pestaña «Gestión» (admin)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("el trabajador (no-admin) NO ve «Gestión» pero SÍ «Cambios y ausencias» (su único sitio)", async () => {
    renderRota({ rol: "editor" });
    const nav = await screen.findByRole("navigation", { name: "Secciones" });
    expect(within(nav).queryByRole("button", { name: "Gestión" })).toBeNull();
    // Gestión es admin-only; el trabajador conserva su pestaña para pedir/responder cambios y ausencias.
    expect(within(nav).getByRole("button", { name: /Cambios y ausencias/ })).toBeInTheDocument();
    expect(within(nav).getAllByRole("button")).toHaveLength(4);
  });

  it("«Gestión» tiene «Asignar turnos»; ya no existe «Aprobar y publicar» (sin paso de aprobación)", async () => {
    renderRota();
    fireEvent.click(await screen.findByRole("button", { name: "Calendario" }));
    await screen.findByRole("button", { name: "Semana", pressed: true });
    expect(screen.queryByRole("button", { name: "Asignar turnos" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Aprobar y publicar/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Gestión" }));
    expect(await screen.findByRole("button", { name: "Asignar turnos" })).toBeInTheDocument();
    // Sin paso de aprobación: lo asignado ya lo ve el equipo, no hay «Aprobar y publicar» ni «Despublicar».
    expect(screen.queryByRole("button", { name: /Aprobar y publicar/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Despublicar" })).toBeNull();
  });

  it("en «Gestión», el panel de reparto arranca abierto (columna lateral, no un modal)", async () => {
    renderRota();
    fireEvent.click(await screen.findByRole("button", { name: "Gestión" }));
    // Abierto SIN clic previo: el reparto está junto a la rejilla (un <aside>, NO un role=dialog que la tape).
    const panel = await screen.findByRole("complementary", { name: "Asignar turnos" });
    expect(within(panel).getByText("Horario")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
    // El botón de la cabecera solo lo oculta/muestra.
    const toggle = screen.getByRole("button", { name: "Asignar turnos" });
    fireEvent.click(toggle);
    expect(screen.queryByRole("complementary", { name: "Asignar turnos" })).toBeNull();
    fireEvent.click(toggle);
    expect(await screen.findByRole("complementary", { name: "Asignar turnos" })).toBeInTheDocument();
  });

  it("deep-link ?tab=gestion para un no-admin cae en «Hoy»", async () => {
    renderRotaConTab("gestion", { rol: "editor" });
    const nav = await screen.findByRole("navigation", { name: "Secciones" });
    expect(within(nav).getByRole("button", { name: "Hoy" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(nav).queryByRole("button", { name: "Gestión" })).toBeNull();
  });

  it("deep-link ?tab=gestion para admin abre «Gestión»", async () => {
    renderRotaConTab("gestion");
    const nav = await screen.findByRole("navigation", { name: "Secciones" });
    expect(within(nav).getByRole("button", { name: "Gestión" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});
