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
    puede_coordinar: false,
    nombre: "Dir Admin",
    manager_id: "",
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
    puede_coordinar: false,
    nombre: "Ana López",
    manager_id: "u0",
    marcas: ["claro-sports"],
  },
];

const OPCIONES_PIEZAS = {
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
      // Catalogo de marcas para el selector multi (lo expone piezas/opciones).
      if (ruta.includes("/api/piezas/opciones")) {
        return new Response(JSON.stringify(OPCIONES_PIEZAS), { status: 200 });
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

/** Abre el panel de edición de una persona pulsando su tarjeta del organigrama. */
async function abrirPanel(nombre: RegExp) {
  fireEvent.click(await screen.findByRole("button", { name: nombre }));
  return screen.findByRole("dialog");
}

describe("Usuarios · administración", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lista a cada persona con nombre, área por marca e icono de quien tiene reportes", async () => {
    stubFetch();
    renderUsuarios();

    // Nombres humanos (no el login) en las filas.
    expect(await screen.findByText("Ana López")).toBeInTheDocument();
    expect(screen.getByText("Dir Admin")).toBeInTheDocument();
    // El área de Ana (community manager de Claro Sports) define una zona "Claro Sports".
    expect(screen.getAllByText(/claro sports/i).length).toBeGreaterThan(0);
    // Cada fila es accionable (abre el panel de edición).
    expect(screen.getByRole("button", { name: /editar a ana lópez/i })).toBeInTheDocument();
    // Solo el director (tiene a Ana a su cargo) lleva el icono; Ana, sin reportes, no.
    expect(screen.getAllByLabelText("Tiene personas a su cargo")).toHaveLength(1);
  });

  it("muestra aviso de permiso ante un 403", async () => {
    stubFetch({ usuariosStatus: 403 });
    renderUsuarios();

    expect(await screen.findByText("No tienes permiso")).toBeInTheDocument();
    expect(screen.queryByText("Ana López")).not.toBeInTheDocument();
  });

  it("crea una persona nueva (POST con usuario/password/rol)", async () => {
    const capturas: Captura[] = [];
    stubFetch({ capturas });
    renderUsuarios();

    // "Nueva persona" vive ahora en el menú "⋯" de la cabecera: ábrelo primero.
    fireEvent.click(await screen.findByRole("button", { name: "Acciones" }));
    fireEvent.click(screen.getByRole("menuitem", { name: /nueva persona/i }));
    fireEvent.change(screen.getByLabelText("Usuario"), { target: { value: "nuevo" } });
    fireEvent.change(screen.getByLabelText("Contraseña inicial"), {
      target: { value: "contrasena1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /crear persona/i }));

    await waitFor(() => {
      const alta = capturas.find((c) => c.url.endsWith("/api/usuarios") && c.metodo === "POST");
      expect(alta?.body).toMatchObject({ usuario: "nuevo", password: "contrasena1", rol: "editor" });
    });
  });

  it("resetea la contraseña desde el panel (PATCH password)", async () => {
    const capturas: Captura[] = [];
    stubFetch({ capturas });
    renderUsuarios();

    const dialogo = await abrirPanel(/editar a ana lópez/i);
    fireEvent.change(within(dialogo).getByLabelText("Nueva contraseña"), {
      target: { value: "nuevaclave1" },
    });
    fireEvent.click(within(dialogo).getByRole("button", { name: /resetear/i }));

    await waitFor(() => {
      const patch = capturas.find((c) => c.url.includes("/api/usuarios/u1") && c.metodo === "PATCH");
      expect(patch?.body).toMatchObject({ password: "nuevaclave1" });
    });
  });

  it("edita el nombre de cuenta desde el panel (PATCH usuario)", async () => {
    const capturas: Captura[] = [];
    stubFetch({ capturas });
    renderUsuarios();

    const dialogo = await abrirPanel(/editar a ana lópez/i);
    const campo = within(dialogo).getByLabelText("Usuario (inicio de sesión)");
    fireEvent.change(campo, { target: { value: "ana2" } });
    fireEvent.blur(campo);

    await waitFor(() => {
      const patch = capturas.find((c) => c.url.includes("/api/usuarios/u1") && c.metodo === "PATCH");
      expect(patch?.body).toMatchObject({ usuario: "ana2" });
    });
  });

  it("edita una marca desde el panel (PATCH marcas)", async () => {
    const capturas: Captura[] = [];
    stubFetch({ capturas });
    renderUsuarios();

    const dialogo = await abrirPanel(/editar a ana lópez/i);
    // Ana tiene claro-sports; añadir UnoTV manda la lista completa.
    fireEvent.click(within(dialogo).getByLabelText("UnoTV"));

    await waitFor(() => {
      const patch = capturas.find((c) => c.url.includes("/api/usuarios/u1") && c.metodo === "PATCH");
      expect(patch?.body).toBeDefined();
      expect((patch?.body as { marcas: string[] }).marcas).toEqual(
        expect.arrayContaining(["claro-sports", "unotv"]),
      );
    });
  });

  it("elimina una persona tras confirmar (DELETE)", async () => {
    const capturas: Captura[] = [];
    stubFetch({ capturas });
    renderUsuarios();

    const dialogo = await abrirPanel(/editar a ana lópez/i);
    fireEvent.click(within(dialogo).getByRole("button", { name: /eliminar persona/i }));
    // Confirmación inline: pulsar "Eliminar".
    fireEvent.click(within(dialogo).getByRole("button", { name: /^eliminar$/i }));

    await waitFor(() => {
      const del = capturas.find((c) => c.url.includes("/api/usuarios/u1") && c.metodo === "DELETE");
      expect(del).toBeDefined();
    });
  });

  it("no permite eliminar la propia cuenta (acción deshabilitada)", async () => {
    stubFetch();
    renderUsuarios();

    const dialogo = await abrirPanel(/editar a dir admin/i);
    expect(
      within(dialogo).getByRole("button", { name: /no puedes eliminar tu propia cuenta/i }),
    ).toBeDisabled();
  });
});
