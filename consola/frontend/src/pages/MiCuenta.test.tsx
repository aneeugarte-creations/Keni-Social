import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionProvider } from "@/hooks/use-sesion";

import MiCuenta from "./MiCuenta";

const ME = {
  id: "u1",
  usuario: "ana",
  rol: "editor",
  debe_cambiar_password: false,
  creado: "2026-01-10T10:00:00",
  ultimo_acceso: "2026-05-20T08:30:00",
};

interface Captura {
  url: string;
  metodo: string;
  body: unknown;
}

/**
 * Stub de fetch: `GET /api/auth/me` devuelve el usuario actual (con creado/último
 * acceso) y `POST /api/auth/cambiar-password` responde 204. `cambioStatus` permite
 * simular un fallo (p. ej. 400 de contraseña actual incorrecta).
 */
function stubFetch(opciones: { cambioStatus?: number; capturas?: Captura[] } = {}) {
  const { cambioStatus = 204, capturas = [] } = opciones;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL, init?: RequestInit) => {
      const ruta = String(url);
      const metodo = (init?.method ?? "GET").toUpperCase();
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      if (metodo !== "GET") capturas.push({ url: ruta, metodo, body });

      if (ruta.includes("/api/auth/cambiar-password")) {
        if (cambioStatus === 204) return new Response(null, { status: 204 });
        return new Response(JSON.stringify({ error: "La contraseña actual no es correcta." }), {
          status: cambioStatus,
        });
      }
      if (ruta.includes("/api/auth/me")) {
        return new Response(JSON.stringify({ usuario: ME }), { status: 200 });
      }
      return new Response("{}", { status: 200 });
    }),
  );
}

function renderMiCuenta() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionProvider>
        <MemoryRouter>
          <MiCuenta />
        </MemoryRouter>
      </SesionProvider>
    </QueryClientProvider>,
  );
}

describe("MiCuenta · cuenta propia", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("muestra los datos de la cuenta (usuario y rol legible)", async () => {
    stubFetch();
    renderMiCuenta();

    expect(await screen.findByText("ana")).toBeInTheDocument();
    expect(screen.getByText("Editor")).toBeInTheDocument();
  });

  it("cambia la contraseña (POST con actual + nueva)", async () => {
    const capturas: Captura[] = [];
    stubFetch({ capturas });
    renderMiCuenta();

    await screen.findByText("ana");
    fireEvent.change(screen.getByLabelText("Contraseña actual"), { target: { value: "vieja-clave" } });
    fireEvent.change(screen.getByLabelText("Contraseña nueva"), { target: { value: "nueva-clave-1" } });
    fireEvent.change(screen.getByLabelText("Repite la contraseña nueva"), {
      target: { value: "nueva-clave-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /cambiar contraseña/i }));

    await waitFor(() => {
      const cambio = capturas.find((c) => c.url.includes("/api/auth/cambiar-password"));
      expect(cambio?.body).toMatchObject({
        password_actual: "vieja-clave",
        password_nueva: "nueva-clave-1",
      });
    });
  });

  it("no envía si la confirmación no coincide (avisa y deja el botón deshabilitado)", async () => {
    const capturas: Captura[] = [];
    stubFetch({ capturas });
    renderMiCuenta();

    await screen.findByText("ana");
    fireEvent.change(screen.getByLabelText("Contraseña actual"), { target: { value: "vieja-clave" } });
    fireEvent.change(screen.getByLabelText("Contraseña nueva"), { target: { value: "nueva-clave-1" } });
    fireEvent.change(screen.getByLabelText("Repite la contraseña nueva"), {
      target: { value: "otra-distinta" },
    });

    expect(screen.getByText("Las contraseñas no coinciden.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cambiar contraseña/i })).toBeDisabled();
    expect(capturas.find((c) => c.url.includes("/api/auth/cambiar-password"))).toBeUndefined();
  });
});
