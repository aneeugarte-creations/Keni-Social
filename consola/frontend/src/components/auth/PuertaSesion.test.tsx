import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PuertaSesion } from "@/components/auth/PuertaSesion";
import { SesionProvider } from "@/hooks/use-sesion";

const EDITOR = { id: "u1", usuario: "ana", rol: "editor", debe_cambiar_password: false };

interface Captura {
  url: string;
  metodo: string;
  body: unknown;
}

/**
 * Stub de fetch para los endpoints de auth. `meResponde` controla qué devuelve
 * `GET /api/auth/me` (la primera llamada al cargar): un usuario o un 401.
 * `loginResponde` controla `POST /api/auth/login`.
 */
function stubFetch(opciones: {
  me?: { status: number; usuario?: unknown };
  login?: { status: number; usuario?: unknown };
  capturas?: Captura[];
}) {
  const { me = { status: 401 }, login, capturas = [] } = opciones;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL, init?: RequestInit) => {
      const ruta = String(url);
      const metodo = (init?.method ?? "GET").toUpperCase();
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      capturas.push({ url: ruta, metodo, body });

      if (ruta.includes("/api/auth/me")) {
        if (me.status === 200) {
          return new Response(JSON.stringify({ usuario: me.usuario }), { status: 200 });
        }
        return new Response(JSON.stringify({ error: "no autenticado" }), { status: me.status });
      }
      if (ruta.includes("/api/auth/login")) {
        const l = login ?? { status: 401 };
        if (l.status === 200) {
          return new Response(JSON.stringify({ usuario: l.usuario }), { status: 200 });
        }
        return new Response(JSON.stringify({ error: "credenciales" }), { status: l.status });
      }
      return new Response("{}", { status: 200 });
    }),
  );
}

function renderPuerta() {
  return render(
    <SesionProvider>
      <PuertaSesion>
        <div>CONTENIDO PROTEGIDO</div>
      </PuertaSesion>
    </SesionProvider>,
  );
}

describe("PuertaSesion · guard de sesión", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("muestra el login cuando GET /api/auth/me devuelve 401", async () => {
    stubFetch({ me: { status: 401 } });
    renderPuerta();

    expect(await screen.findByLabelText("Usuario")).toBeInTheDocument();
    expect(screen.getByLabelText("Contraseña")).toBeInTheDocument();
    expect(screen.queryByText("CONTENIDO PROTEGIDO")).not.toBeInTheDocument();
  });

  it("entra a la app cuando GET /api/auth/me devuelve 200", async () => {
    stubFetch({ me: { status: 200, usuario: EDITOR } });
    renderPuerta();

    expect(await screen.findByText("CONTENIDO PROTEGIDO")).toBeInTheDocument();
    expect(screen.queryByLabelText("Usuario")).not.toBeInTheDocument();
  });

  it("fuerza el cambio de contraseña si debe_cambiar_password es true", async () => {
    stubFetch({ me: { status: 200, usuario: { ...EDITOR, debe_cambiar_password: true } } });
    renderPuerta();

    expect(await screen.findByText("Cambia tu contraseña")).toBeInTheDocument();
    expect(screen.queryByText("CONTENIDO PROTEGIDO")).not.toBeInTheDocument();
  });

  it("login correcto: envía credenciales y revela la app", async () => {
    const capturas: Captura[] = [];
    stubFetch({
      me: { status: 401 },
      login: { status: 200, usuario: EDITOR },
      capturas,
    });
    renderPuerta();

    fireEvent.change(await screen.findByLabelText("Usuario"), { target: { value: "ana" } });
    fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "secreta123" } });
    fireEvent.click(screen.getByRole("button", { name: /entrar/i }));

    expect(await screen.findByText("CONTENIDO PROTEGIDO")).toBeInTheDocument();
    const login = capturas.find((c) => c.url.includes("/api/auth/login"));
    expect(login?.body).toMatchObject({ usuario: "ana", password: "secreta123" });
  });

  it("login fallido: muestra error genérico y no entra", async () => {
    stubFetch({ me: { status: 401 }, login: { status: 401 } });
    renderPuerta();

    fireEvent.change(await screen.findByLabelText("Usuario"), { target: { value: "ana" } });
    fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "mala" } });
    fireEvent.click(screen.getByRole("button", { name: /entrar/i }));

    expect(await screen.findByText("Usuario o contraseña incorrectos.")).toBeInTheDocument();
    expect(screen.queryByText("CONTENIDO PROTEGIDO")).not.toBeInTheDocument();
  });
});
