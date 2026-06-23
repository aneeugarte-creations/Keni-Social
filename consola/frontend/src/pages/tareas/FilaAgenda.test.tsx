import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import type { CatalogosPublicacion, EventoRota, UsuarioSesion } from "@/types";

import { FilaAgenda } from "./PanoramaAgenda";
import type { Item } from "./tipos";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));
vi.mock("@/components/comunes/confirmar", () => ({
  confirmar: vi.fn().mockResolvedValue(true),
  elegir: vi.fn().mockResolvedValue(null),
}));

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
    serie_id: "",
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

function usuario(rol: UsuarioSesion["rol"] = "editor"): UsuarioSesion {
  return { id: "u1", usuario: "yo", rol, debe_cambiar_password: false, marcas: ["claro-sports"] };
}

function sesion(u: UsuarioSesion): ValorSesion {
  return {
    usuario: u,
    cargando: false,
    errorConexion: false,
    iniciarSesion: vi.fn(),
    verificarConPasskey: vi.fn(),
    entrarConPasskey: vi.fn(),
    cerrarSesion: vi.fn(),
    refrescar: vi.fn(),
  };
}

const itemEventoPorCubrir: Item = {
  kind: "evento",
  clave: "ev1",
  orden: "2026-07-01",
  evento: evento(),
  cubiertoPorTurno: false,
};

function montar(asignarResaltado: boolean, rol: UsuarioSesion["rol"] = "admin") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesion(usuario(rol))}>
        <FilaAgenda
          item={itemEventoPorCubrir}
          abierta={false}
          onToggle={() => {}}
          catalogos={catalogos()}
          asignarResaltado={asignarResaltado}
        />
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("FilaAgenda — asignarResaltado", () => {
  it("con asignarResaltado, «Asignar» es un botón VISIBLE (no enterrado en el kebab)", () => {
    montar(true);
    expect(screen.getByRole("button", { name: "Asignar" })).toBeInTheDocument();
    // Y no se duplica dentro del kebab «Más acciones».
    fireEvent.click(screen.getByRole("button", { name: "Más acciones" }));
    expect(screen.queryByRole("menuitem", { name: "Asignar a…" })).toBeNull();
  });

  it("sin asignarResaltado (por defecto), «Asignar» vive en el kebab «Más acciones»", async () => {
    montar(false);
    expect(screen.queryByRole("button", { name: "Asignar" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Más acciones" }));
    expect(await screen.findByRole("menuitem", { name: "Asignar a…" })).toBeInTheDocument();
  });

  it("un no-admin no ve ni el botón «Asignar» ni el kebab", () => {
    montar(true, "editor");
    expect(screen.queryByRole("button", { name: "Asignar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Más acciones" })).toBeNull();
  });
});
