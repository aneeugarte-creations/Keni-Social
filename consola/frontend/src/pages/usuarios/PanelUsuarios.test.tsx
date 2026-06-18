import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionProvider } from "@/hooks/use-sesion";

import PanelUsuarios from "./PanelUsuarios";

const ADMIN = {
  id: "u0",
  usuario: "admin",
  rol: "admin",
  debe_cambiar_password: false,
  es_superadmin: true,
};

const USUARIOS = [
  {
    id: "u0",
    usuario: "admin",
    rol: "admin",
    creado: "2026-01-10T10:00:00",
    ultimo_acceso: "2026-05-20T08:00:00",
    cargo: "director",
    nombre: "Dir Admin",
    manager_id: "",
    marcas: ["claro-sports", "unotv"],
    superadmin: true,
  },
  {
    id: "u1",
    usuario: "ana",
    rol: "editor",
    creado: "2026-02-01T10:00:00",
    ultimo_acceso: null,
    cargo: "community_manager",
    nombre: "Ana López",
    manager_id: "u0",
    marcas: ["claro-sports"],
  },
];

const OPCIONES_PIEZAS = {
  marcas: [
    { id: "claro-sports", nombre: "Claro Sports" },
    { id: "unotv", nombre: "UnoTV" },
  ],
  redes: [],
  estados: [],
};

function stubFetch(opciones: { esSuperadmin?: boolean } = {}) {
  const { esSuperadmin = true } = opciones;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL) => {
      const ruta = String(url);
      if (ruta.includes("/api/auth/me")) {
        return new Response(
          JSON.stringify({ usuario: { ...ADMIN, es_superadmin: esSuperadmin } }),
          { status: 200 },
        );
      }
      if (ruta.includes("/api/piezas/opciones")) {
        return new Response(JSON.stringify(OPCIONES_PIEZAS), { status: 200 });
      }
      if (ruta.includes("/api/usuarios")) {
        return new Response(JSON.stringify({ usuarios: USUARIOS }), { status: 200 });
      }
      return new Response("{}", { status: 200 });
    }),
  );
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionProvider>
        <MemoryRouter>
          <PanelUsuarios />
        </MemoryRouter>
      </SesionProvider>
    </QueryClientProvider>,
  );
}

describe("PanelUsuarios", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lista cada persona en una fila con nombre y usuario", async () => {
    stubFetch();
    renderPanel();

    expect(await screen.findByText("Ana López")).toBeInTheDocument();
    expect(screen.getByText("Dir Admin")).toBeInTheDocument();
    expect(screen.getByText("@ana")).toBeInTheDocument();
  });

  it("el buscador filtra las filas por nombre", async () => {
    stubFetch();
    renderPanel();

    expect(await screen.findByText("Ana López")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Buscar usuarios"), { target: { value: "ana" } });

    await waitFor(() => expect(screen.queryByText("Dir Admin")).not.toBeInTheDocument());
    expect(screen.getByText("Ana López")).toBeInTheDocument();
  });

  it("niega el acceso a quien no es superadmin", async () => {
    stubFetch({ esSuperadmin: false });
    renderPanel();

    expect(await screen.findByText("No tienes permiso")).toBeInTheDocument();
    expect(screen.queryByText("Ana López")).not.toBeInTheDocument();
  });
});
