import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionProvider } from "@/hooks/use-sesion";

import Usuarios from "./Usuarios";

const ADMIN = { id: "u0", usuario: "admin", rol: "admin", debe_cambiar_password: false };

const USUARIOS = [
  {
    id: "u0",
    usuario: "admin",
    rol: "admin",
    creado: "2026-01-10T10:00:00",
    ultimo_acceso: "2026-05-20T08:00:00",
    cargo: "director",
    cobertura: false,
    marcas: ["claro-sports", "unotv"],
  },
  {
    id: "u1",
    usuario: "ana",
    rol: "editor",
    creado: "2026-02-01T10:00:00",
    ultimo_acceso: null,
    cargo: "community_manager",
    cobertura: true,
    marcas: ["claro-sports"],
  },
];

const OPCIONES_PUBLICACIONES = {
  marcas: [
    { id: "claro-sports", nombre: "Claro Sports" },
    { id: "unotv", nombre: "UnoTV" },
    { id: "fundacion", nombre: "Fundación" },
  ],
  redes: [],
  estados: [],
};

interface Captura {
  url: string;
  metodo: string;
  body: unknown;
}

/**
 * Stub de fetch para el flujo de usuarios. `me` siempre devuelve el admin (para
 * que el provider de sesión entre). `usuariosStatus` controla GET /api/usuarios
 * (200 con la lista, o 403 para el caso "sin permiso").
 */
function stubFetch(opciones: { usuariosStatus?: number; capturas?: Captura[] } = {}) {
  const { usuariosStatus = 200, capturas = [] } = opciones;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL, init?: RequestInit) => {
      const ruta = String(url);
      const metodo = (init?.method ?? "GET").toUpperCase();
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      if (metodo !== "GET") capturas.push({ url: ruta, metodo, body });

      if (ruta.includes("/api/auth/me")) {
        return new Response(JSON.stringify({ usuario: ADMIN }), { status: 200 });
      }
      // Catalogo de marcas para el selector multi (lo expone publicaciones/opciones).
      if (ruta.includes("/api/publicaciones/opciones")) {
        return new Response(JSON.stringify(OPCIONES_PUBLICACIONES), { status: 200 });
      }
      // POST /api/usuarios (crear)
      if (ruta.endsWith("/api/usuarios") && metodo === "POST") {
        return new Response(
          JSON.stringify({ id: "u2", usuario: body?.usuario, rol: body?.rol }),
          { status: 201 },
        );
      }
      // PATCH/DELETE /api/usuarios/{id}
      if (ruta.includes("/api/usuarios/")) {
        if (metodo === "DELETE") return new Response(null, { status: 204 });
        return new Response(
          JSON.stringify({
            id: "u1",
            usuario: "ana",
            rol: body?.rol ?? "editor",
            cargo: body?.cargo ?? "community_manager",
            cobertura: body?.cobertura ?? true,
            marcas: body?.marcas ?? ["claro-sports"],
          }),
          { status: 200 },
        );
      }
      // GET /api/usuarios (listado): el backend envuelve la lista en {usuarios:[...]}.
      if (ruta.includes("/api/usuarios")) {
        if (usuariosStatus !== 200) {
          return new Response(JSON.stringify({ error: "prohibido" }), { status: usuariosStatus });
        }
        return new Response(JSON.stringify({ usuarios: USUARIOS }), { status: 200 });
      }
      return new Response("{}", { status: 200 });
    }),
  );
}

function renderUsuarios() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionProvider>
        <MemoryRouter>
          <Usuarios />
        </MemoryRouter>
      </SesionProvider>
    </QueryClientProvider>,
  );
}

describe("Usuarios · administración", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lista los usuarios con sus columnas de organigrama", async () => {
    stubFetch();
    renderUsuarios();

    expect(await screen.findByText("ana")).toBeInTheDocument();
    expect(screen.getByText("admin")).toBeInTheDocument();
    // Cabeceras nuevas de la ola feat/roles-marcas:
    expect(screen.getByRole("columnheader", { name: /cargo/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /cobertura/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /marcas/i })).toBeInTheDocument();
    // El "último acceso" nulo se muestra como guion (al menos una vez).
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("muestra aviso de permiso ante un 403", async () => {
    stubFetch({ usuariosStatus: 403 });
    renderUsuarios();

    expect(await screen.findByText("No tienes permiso")).toBeInTheDocument();
    expect(screen.queryByText("ana")).not.toBeInTheDocument();
  });

  it("crea un usuario nuevo (POST con usuario/password/rol)", async () => {
    const capturas: Captura[] = [];
    stubFetch({ capturas });
    renderUsuarios();

    fireEvent.click(await screen.findByRole("button", { name: /nuevo usuario/i }));
    fireEvent.change(screen.getByLabelText("Usuario"), { target: { value: "nuevo" } });
    fireEvent.change(screen.getByLabelText("Contraseña inicial"), {
      target: { value: "contrasena1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /crear usuario/i }));

    await waitFor(() => {
      const alta = capturas.find((c) => c.url.endsWith("/api/usuarios") && c.metodo === "POST");
      expect(alta?.body).toMatchObject({ usuario: "nuevo", password: "contrasena1", rol: "editor" });
    });
  });

  it("resetea la contraseña de un usuario (PATCH password)", async () => {
    const capturas: Captura[] = [];
    stubFetch({ capturas });
    renderUsuarios();

    await screen.findByText("ana");
    fireEvent.click(screen.getByRole("button", { name: /resetear contraseña de ana/i }));
    fireEvent.change(screen.getByLabelText("Contraseña nueva"), {
      target: { value: "nuevaclave1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /guardar contraseña/i }));

    await waitFor(() => {
      const patch = capturas.find((c) => c.url.includes("/api/usuarios/u1") && c.metodo === "PATCH");
      expect(patch?.body).toMatchObject({ password: "nuevaclave1" });
    });
  });

  it("elimina un usuario tras confirmar", async () => {
    const capturas: Captura[] = [];
    stubFetch({ capturas });
    renderUsuarios();

    await screen.findByText("ana");
    fireEvent.click(screen.getByRole("button", { name: /eliminar a ana/i }));
    // Diálogo de confirmación: pulsar "Eliminar".
    const dialogo = await screen.findByRole("dialog");
    fireEvent.click(within(dialogo).getByRole("button", { name: /^eliminar$/i }));

    await waitFor(() => {
      const del = capturas.find((c) => c.url.includes("/api/usuarios/u1") && c.metodo === "DELETE");
      expect(del).toBeDefined();
    });
  });

  it("no permite eliminar la propia cuenta (botón deshabilitado)", async () => {
    stubFetch();
    renderUsuarios();

    await screen.findByText("admin");
    // El admin actual (id u0) tiene el botón de eliminar deshabilitado.
    expect(screen.getByRole("button", { name: /eliminar a admin/i })).toBeDisabled();
  });
});
