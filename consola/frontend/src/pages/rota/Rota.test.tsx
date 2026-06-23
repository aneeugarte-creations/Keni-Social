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
    "obtenerConfigFranjas",
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

describe("Turnos — la sección «Calendario» (horario; el trabajo vive en su propio destino)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("«Horario» abre en el MES ACTUAL (el que contiene hoy), no en otro", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-06-15T12:00:00Z")); // junio 2026 (CDMX)
    renderRota();
    // «Horario» es la home (mensual del equipo para el admin): pide los turnos del MES de hoy.
    await vi.waitFor(() =>
      expect(
        vi
          .mocked(apiMod.api.turnosMes)
          .mock.calls.some(([arg]) => (arg as { mes?: string })?.mes === "2026-06"),
      ).toBe(true),
    );
  });

  it("abre en «Horario» (el calendario) por defecto; el trabajo y «Hoy» ya NO son pestaña", async () => {
    renderRota();
    // La subnav unificada (topbar) son botones de sección con `aria-current`, agrupados en
    // el landmark «Secciones»; la activa lleva aria-current="page".
    const nav = await screen.findByRole("navigation", { name: "Secciones" });
    expect(within(nav).getByRole("button", { name: "Horario" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    // «Hoy» (resumen del día) se retiró; el trabajo (eventos/tareas/cobertura) tiene su propio destino.
    expect(within(nav).queryByRole("button", { name: "Hoy" })).toBeNull();
    expect(within(nav).queryByRole("button", { name: "Cobertura" })).toBeNull();
    expect(within(nav).queryByRole("button", { name: "Trabajo" })).toBeNull();
  });

  it("el admin ve 2 pestañas (Horario · Gestión); «Hoy», «Cambios y ausencias», «Trabajo» y «Mi jornada» ya NO son pestaña", async () => {
    renderRota();
    // «Horario» es la home. «Cambios y ausencias» vive en el panel de Gestión (no es pestaña para
    // el admin). El trabajo tiene su propio destino. «Hoy» (resumen del día) se retiró.
    const nav = await screen.findByRole("navigation", { name: "Secciones" });
    const tabs = within(nav).getAllByRole("button");
    expect(tabs).toHaveLength(2);
    expect(tabs.map((t) => t.textContent)).toEqual(["Horario", "Gestión"]);
    expect(within(nav).queryByRole("button", { name: "Hoy" })).toBeNull();
    expect(within(nav).queryByRole("button", { name: /Cambios y ausencias/ })).toBeNull();
    expect(within(nav).queryByRole("button", { name: "Trabajo" })).toBeNull();
  });

  it("«Horario» es el calendario MENSUAL de turnos (Equipo/Yo + Imprimir), sin vista Semana", async () => {
    renderRota();
    // «Horario» es la home; ya muestra el mensual de jornada directamente.
    expect(await screen.findByRole("button", { name: "Equipo" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Yo" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Imprimir \/ PDF/ })).toBeInTheDocument();
    // Ya NO hay conmutador Semana|Mes: la rejilla semanal editable vive en «Gestión».
    expect(screen.queryByRole("button", { name: "Semana" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Mes" })).toBeNull();
  });

  it("deep-link legacy ?tab=mis-turnos cae en «Horario» (el calendario mensual)", async () => {
    renderRotaConTab("mis-turnos");
    expect(await screen.findByRole("button", { name: "Horario" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    // «Horario» ya ES el mensual de jornada (su ámbito Yo/Equipo).
    expect(await screen.findByRole("button", { name: "Equipo" })).toBeInTheDocument();
  });

  it("para el admin, «Horario» abre en «Equipo» (turnos de todos)", async () => {
    renderRota();
    // El admin no está en la rota: arranca en «Equipo» (jornada de todo el equipo), no en «Yo».
    expect(
      await screen.findByRole("button", { name: "Equipo", pressed: true }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Yo", pressed: false }),
    ).toBeInTheDocument();
  });

  it("para un editor, «Horario» abre en «Yo» (su propia jornada)", async () => {
    renderRota({ rol: "editor" });
    // El editor sí está en la rota: arranca en «Yo» (su jornada), no en «Equipo».
    expect(
      await screen.findByRole("button", { name: "Yo", pressed: true }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Equipo", pressed: false }),
    ).toBeInTheDocument();
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

describe("Turnos — Calendario: gating de coordinador", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("el trabajador (no-admin) NO ve el menú ⋯ de coordinador", async () => {
    renderRota({ rol: "editor" });
    fireEvent.click(await screen.findByRole("button", { name: "Horario" }));
    // «Horario» (mensual de jornada) montado y SIN el menú ⋯ (Carga/Export son de Gestión).
    await screen.findByRole("button", { name: "Equipo" });
    expect(screen.queryByRole("button", { name: "Más acciones" })).toBeNull();
  });

  it("el admin tampoco ve el ⋯ en el Calendario; vive en «Gestión»", async () => {
    renderRota(); // admin por defecto
    fireEvent.click(await screen.findByRole("button", { name: "Horario" }));
    await screen.findByRole("button", { name: "Equipo" });
    expect(screen.queryByRole("button", { name: "Más acciones" })).toBeNull();
    // El ⋯ (Franjas/Copiar/Carga/Export) vive en la pestaña admin «Gestión» (Mes único, sin Semana).
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
    // Trabajador: Horario · Cambios y ausencias (sin «Hoy»; el trabajo salió a su propio destino).
    expect(within(nav).getAllByRole("button")).toHaveLength(2);
  });

  it("«Gestión» = Mes único: sin conmutador Semana|Mes y con el panel de reparto al lado", async () => {
    renderRota();
    fireEvent.click(await screen.findByRole("button", { name: "Gestión" }));
    // El panel de reparto arranca abierto junto al mes (Mes único).
    expect(
      await screen.findByRole("complementary", { name: "Asignar turnos" }),
    ).toBeInTheDocument();
    // Ya no hay conmutador de vistas: ni «Semana» ni «Mes».
    expect(screen.queryByRole("button", { name: "Semana" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Mes" })).toBeNull();
    // Imprimir/PDF queda como icono suelto en la barra del mensual.
    expect(screen.getByRole("button", { name: /Imprimir/ })).toBeInTheDocument();
  });

  it("«Gestión» abre «Ajustes de turnos» desde el ⋯ (interruptor de horas en Equipo)", async () => {
    renderRota();
    fireEvent.click(await screen.findByRole("button", { name: "Gestión" }));
    fireEvent.click(await screen.findByRole("button", { name: "Más acciones" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Ajustes de turnos" }));
    // El diálogo de ajustes con el interruptor de mostrar horas en «Equipo».
    expect(await screen.findByRole("dialog", { name: "Ajustes de turnos" })).toBeInTheDocument();
    expect(
      screen.getByRole("switch", { name: /Mostrar horas en el calendario de Equipo/ }),
    ).toBeInTheDocument();
  });

  it("«Gestión» NO muestra el conmutador Equipo/Yo (coordinar es siempre del equipo)", async () => {
    renderRota();
    fireEvent.click(await screen.findByRole("button", { name: "Gestión" }));
    // El ámbito queda fijo en «Equipo»: el admin no está en la rota, así que «Yo» sería un vacío.
    // Ver la jornada propia es cosa de «Horario» (que SÍ conserva el conmutador).
    await screen.findByRole("button", { name: "Más acciones" });
    expect(screen.queryByRole("button", { name: "Equipo" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Yo" })).toBeNull();
  });

  it("«Gestión» tiene «Asignar turnos»; ya no existe «Aprobar y publicar» (sin paso de aprobación)", async () => {
    renderRota();
    fireEvent.click(await screen.findByRole("button", { name: "Horario" }));
    await screen.findByRole("button", { name: "Equipo" });
    expect(screen.queryByRole("button", { name: "Asignar turnos" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Aprobar y publicar/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Gestión" }));
    // Mes único: «Asignar turnos» (toggle del panel) vive en la barra del mes, sin pasar por Semana.
    expect(await screen.findByRole("button", { name: "Asignar turnos" })).toBeInTheDocument();
    // Sin paso de aprobación: lo asignado ya lo ve el equipo, no hay «Aprobar y publicar» ni «Despublicar».
    expect(screen.queryByRole("button", { name: /Aprobar y publicar/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Despublicar" })).toBeNull();
  });

  it("el panel de reparto de «Gestión» arranca abierto (columna lateral, no un modal)", async () => {
    renderRota();
    fireEvent.click(await screen.findByRole("button", { name: "Gestión" }));
    // El reparto está junto al mes (un <aside>, NO un role=dialog que lo tape) y arranca abierto.
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

  it("deep-link ?tab=gestion para un no-admin cae en «Horario»", async () => {
    renderRotaConTab("gestion", { rol: "editor" });
    const nav = await screen.findByRole("navigation", { name: "Secciones" });
    expect(within(nav).getByRole("button", { name: "Horario" })).toHaveAttribute(
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
