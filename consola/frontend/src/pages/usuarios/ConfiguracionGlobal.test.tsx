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
    clave: "KENI_CONSOLA_MFA",
    tipo: "bool",
    etiqueta: "Passkey obligatorio para todo el equipo",
    ayuda: "Cada cuenta debe inscribir una llave de acceso.",
    grupo: "seguridad",
    peligroso: false,
    valor: false,
    fuente: "defecto",
    defecto: false,
  },
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

  it("el flag global pide confirmación y solo PATCHea al confirmar", async () => {
    const capturas: Captura[] = [];
    stubFetch(capturas);
    renderConfig();

    const sw = await screen.findByRole("switch", {
      name: "Passkey obligatorio para todo el equipo",
    });
    fireEvent.click(sw);

    // Aparece la confirmación; aún no se ha PATCHeado nada.
    const confirmar = await screen.findByRole("button", { name: "Activar para todos" });
    expect(
      capturas.find(
        (c) => c.url.includes("/api/usuarios/configuracion") && c.metodo === "PATCH",
      ),
    ).toBeUndefined();

    fireEvent.click(confirmar);

    await waitFor(() => {
      const patch = capturas.find(
        (c) => c.url.includes("/api/usuarios/configuracion") && c.metodo === "PATCH",
      );
      expect(patch?.body).toMatchObject({ clave: "KENI_CONSOLA_MFA", valor: true });
    });
  });

  it("cancelar la confirmación del flag global NO PATCHea", async () => {
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
    expect(
      capturas.find(
        (c) =>
          c.url.includes("/api/usuarios/configuracion") &&
          c.metodo === "PATCH" &&
          (c.body as { clave?: string })?.clave === "KENI_CONSOLA_MFA",
      ),
    ).toBeUndefined();
  });
});
