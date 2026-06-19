import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ContenedorConfirmacion } from "@/components/comunes/ContenedorConfirmacion";
import { SesionProvider } from "@/hooks/use-sesion";

import ConfiguracionGlobal from "./ConfiguracionGlobal";

const ADMIN = {
  id: "u0",
  usuario: "admin",
  rol: "admin",
  debe_cambiar_password: false,
  es_superadmin: true,
  mfa_habilitado: true,
};

const AJUSTES = [
  {
    clave: "KENI_CONSOLA_MFA_ADMIN",
    tipo: "bool",
    etiqueta: "Passkey obligatorio para administradores",
    ayuda: "Obliga a los administradores.",
    grupo: "seguridad",
    peligroso: false,
    valor: true,
    fuente: "defecto",
    defecto: true,
  },
  {
    clave: "KENI_CONSOLA_SESION_HORAS",
    tipo: "int",
    etiqueta: "Duración de la sesión (horas)",
    ayuda: "Ventana de inactividad.",
    grupo: "seguridad",
    peligroso: false,
    valor: 12,
    fuente: "store",
    defecto: 12,
    min: 1,
  },
  {
    clave: "KENI_CONSOLA_PASSWORD_MIN",
    tipo: "int",
    etiqueta: "Longitud mínima de contraseña",
    ayuda: "Mínimo de caracteres.",
    grupo: "seguridad",
    peligroso: false,
    valor: 12,
    fuente: "defecto",
    defecto: 12,
    min: 12,
    max: 128,
  },
];

const USUARIOS = [
  { id: "u0", usuario: "admin", rol: "admin", nombre: "Admin", superadmin: true, mfa_activo: true },
  { id: "u1", usuario: "ana", rol: "editor", nombre: "Ana López", mfa_activo: false },
];

interface Captura {
  url: string;
  metodo: string;
  body: unknown;
}

function stubFetch(capturas: Captura[]) {
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
      if (ruta.includes("/api/usuarios/configuracion")) {
        if (metodo === "PATCH") {
          const ajuste = AJUSTES.find((a) => a.clave === body?.clave) ?? AJUSTES[0];
          return new Response(JSON.stringify({ ajuste }), { status: 200 });
        }
        return new Response(JSON.stringify({ ajustes: AJUSTES }), { status: 200 });
      }
      if (ruta.includes("/api/usuarios")) {
        if (metodo === "PATCH") {
          // PATCH /api/usuarios/{id}: la acción masiva marca mfa_requerido por usuario.
          return new Response(JSON.stringify({ id: "x", usuario: "x", rol: "editor" }), {
            status: 200,
          });
        }
        return new Response(JSON.stringify({ usuarios: USUARIOS }), { status: 200 });
      }
      return new Response("{}", { status: 200 });
    }),
  );
}

function renderConfig() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionProvider>
        <MemoryRouter>
          <ConfiguracionGlobal />
          <ContenedorConfirmacion />
        </MemoryRouter>
      </SesionProvider>
    </QueryClientProvider>,
  );
}

describe("ConfiguracionGlobal", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renderiza los ajustes en sus secciones", async () => {
    stubFetch([]);
    renderConfig();

    expect(
      await screen.findByText("Passkey obligatorio para todo el equipo"),
    ).toBeInTheDocument();
    expect(screen.getByText("Longitud mínima de contraseña")).toBeInTheDocument();
    expect(screen.getByText("Acceso")).toBeInTheDocument();
    expect(screen.getByText("Contraseñas")).toBeInTheDocument();
  });

  it("cambiar un valor numérico dispara el PATCH del ajuste (sin confirmación)", async () => {
    const capturas: Captura[] = [];
    stubFetch(capturas);
    renderConfig();

    const input = await screen.findByLabelText("Duración de la sesión (horas)");
    fireEvent.change(input, { target: { value: "24" } });
    fireEvent.blur(input);

    await waitFor(() => {
      const patch = capturas.find(
        (c) => c.url.includes("/api/usuarios/configuracion") && c.metodo === "PATCH",
      );
      expect(patch?.body).toMatchObject({ clave: "KENI_CONSOLA_SESION_HORAS", valor: 24 });
    });
  });

  // Marca el PATCH por-usuario de la acción masiva (PATCH a /api/usuarios/{id}, no a /configuracion).
  const patchUsuario = (c: Captura) =>
    c.metodo === "PATCH" &&
    c.url.includes("/api/usuarios/") &&
    !c.url.includes("/configuracion");

  it("el passkey global es una acción masiva: confirma y marca a cada usuario afectado", async () => {
    const capturas: Captura[] = [];
    stubFetch(capturas);
    renderConfig();

    const sw = await screen.findByRole("switch", {
      name: "Passkey obligatorio para todo el equipo",
    });
    fireEvent.click(sw);

    // Aparece la confirmación; aún no se ha tocado a nadie.
    const confirmar = await screen.findByRole("button", { name: "Activar para todos" });
    expect(capturas.find(patchUsuario)).toBeUndefined();

    fireEvent.click(confirmar);

    // Marca mfa_requerido=true en la persona afectada (ana, editora sin exigir).
    await waitFor(() => {
      const patch = capturas.find(patchUsuario);
      expect(patch?.url).toContain("/api/usuarios/u1");
      expect(patch?.body).toMatchObject({ mfa_requerido: true });
    });
  });

  it("cancelar la confirmación de la acción masiva NO toca a nadie", async () => {
    const capturas: Captura[] = [];
    stubFetch(capturas);
    renderConfig();

    const sw = await screen.findByRole("switch", {
      name: "Passkey obligatorio para todo el equipo",
    });
    fireEvent.click(sw);

    fireEvent.click(await screen.findByRole("button", { name: "Cancelar" }));

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Activar para todos" })).not.toBeInTheDocument(),
    );
    expect(capturas.find(patchUsuario)).toBeUndefined();
  });
});
