import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  MarcaActivaContexto,
  type ValorMarcaActiva,
} from "@/hooks/marca-activa-contexto";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import * as apiMod from "@/lib/api";
import type { CatalogosContenido, Contenido, UsuarioSesion } from "@/types";

import Tareas from "./Tareas";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

function tarea(over: Partial<Contenido> = {}): Contenido {
  return {
    id: "t1",
    clase: "tarea",
    flujo: "",
    titulo: "Cubrir el partido",
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

function usuario(rol = "editor", id = "u1"): UsuarioSesion {
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

function renderTareas(tareas: Contenido[], u = usuario()) {
  vi.spyOn(apiMod.api, "contenido").mockResolvedValue({
    contenidos: tareas,
    catalogos: catalogos(),
  });
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

describe("Tareas — tablero compartido del equipo (clase='tarea')", () => {
  afterEach(() => vi.restoreAllMocks());

  it("una tarea LIBRE ofrece 'Coger' y al pulsarlo llama a cogerContenido", async () => {
    const coger = vi
      .spyOn(apiMod.api, "cogerContenido")
      .mockResolvedValue({ contenido: {} } as never);
    renderTareas([tarea({ id: "t9", titulo: "Grabar el saque" })]);

    fireEvent.click(await screen.findByRole("button", { name: /Coger/ }));
    await waitFor(() => expect(coger).toHaveBeenCalledTimes(1));
    expect(coger).toHaveBeenCalledWith("t9");
  });

  it("la lente 'Mis tareas' deja solo las del usuario de la sesión", async () => {
    renderTareas(
      [
        tarea({ id: "t1", titulo: "Mía", responsable_id: "u1", responsable_nombre: "yo" }),
        tarea({ id: "t2", titulo: "De Ana", responsable_id: "u-ana", responsable_nombre: "ana" }),
      ],
      usuario("editor", "u1"),
    );
    expect(await screen.findByText("Mía")).toBeInTheDocument();
    expect(screen.getByText("De Ana")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Mis tareas" }));
    await waitFor(() => expect(screen.queryByText("De Ana")).toBeNull());
    expect(screen.getByText("Mía")).toBeInTheDocument();
  });

  it("un MANAGER (admin) ve 'Asignar'; un editor NO", async () => {
    const { unmount } = renderTareas([tarea({ titulo: "Reparto" })], usuario("admin", "u-admin"));
    expect(await screen.findByRole("button", { name: /Asignar/ })).toBeInTheDocument();
    unmount();

    vi.restoreAllMocks();
    renderTareas([tarea({ titulo: "Reparto" })], usuario("editor", "u2"));
    await screen.findByRole("button", { name: /Coger/ });
    expect(screen.queryByRole("button", { name: /Asignar/ })).toBeNull();
  });

  it("'Nueva tarea' abre el diálogo de crear", async () => {
    renderTareas([]);
    fireEvent.click(await screen.findByRole("button", { name: /Nueva tarea/ }));
    expect(await screen.findByText("Nueva tarea del equipo")).toBeInTheDocument();
  });
});
