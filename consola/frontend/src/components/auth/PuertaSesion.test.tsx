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
  // `motivo` simula el campo del 503 del front (deploy|incidente) que distingue actualización
  // de avería; ausente => el cuerpo no lo trae (caída sin pista => la UI cae a "incidente").
  me?: { status: number; usuario?: unknown; motivo?: "deploy" | "incidente" };
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
        const cuerpo = me.motivo
          ? { error: "no disponible", motivo: me.motivo }
          : { error: "no autenticado" };
        return new Response(JSON.stringify(cuerpo), { status: me.status });
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
    fireEvent.click(screen.getByRole("button", { name: /^entrar$/i }));

    expect(await screen.findByText("CONTENIDO PROTEGIDO")).toBeInTheDocument();
    const login = capturas.find((c) => c.url.includes("/api/auth/login"));
    expect(login?.body).toMatchObject({ usuario: "ana", password: "secreta123" });
  });

  it("login fallido: muestra error genérico y no entra", async () => {
    stubFetch({ me: { status: 401 }, login: { status: 401 } });
    renderPuerta();

    fireEvent.change(await screen.findByLabelText("Usuario"), { target: { value: "ana" } });
    fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "mala" } });
    fireEvent.click(screen.getByRole("button", { name: /^entrar$/i }));

    expect(await screen.findByText("Usuario o contraseña incorrectos.")).toBeInTheDocument();
    expect(screen.queryByText("CONTENIDO PROTEGIDO")).not.toBeInTheDocument();
  });

  it("estado degradado HONESTO cuando el me falla por RED: avería, no 'actualizando'", async () => {
    // fetch rechaza => ApiError status 0, sin cuerpo: no es "sin sesión" ni un deploy, es una
    // caída. NO mentimos con "actualizando"; decimos la verdad y que el equipo ya lo sabe.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) => {
        if (String(url).includes("/api/auth/me")) throw new TypeError("network down");
        return new Response("{}", { status: 200 });
      }),
    );
    renderPuerta();

    expect(await screen.findByText(/La consola no está disponible/i)).toBeInTheDocument();
    expect(screen.getByText(/equipo ya ha sido avisado/i)).toBeInTheDocument();
    expect(screen.queryByText(/Estamos actualizando la consola/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Usuario")).not.toBeInTheDocument();
    expect(screen.queryByText("CONTENIDO PROTEGIDO")).not.toBeInTheDocument();
  });

  it("RED sin cuerpo PERO con deploy en curso (sonda): SÍ 'actualizando'", async () => {
    // El `me` cae por RESET de conexión (sin cuerpo con `motivo`): el flag del 503 no llega. La
    // sonda /estado-deploy (que NO pasa por el back) dice que hay deploy -> "actualizando", no
    // "no disponible". Es el fallo que veíamos: un deploy stop-the-world mostraba "incidente".
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) => {
        const u = String(url);
        if (u.includes("/api/auth/me")) throw new TypeError("network down");
        if (u.includes("/estado-deploy"))
          return new Response(JSON.stringify({ desplegando: true }), { status: 200 });
        return new Response("{}", { status: 200 });
      }),
    );
    renderPuerta();

    expect(await screen.findByText(/Estamos actualizando la consola/i)).toBeInTheDocument();
    expect(screen.queryByText(/La consola no está disponible/i)).not.toBeInTheDocument();
  });

  it("estado degradado cuando el me da 503 con motivo=deploy: SÍ 'actualizando'", async () => {
    stubFetch({ me: { status: 503, motivo: "deploy" } });
    renderPuerta();

    expect(await screen.findByText(/Estamos actualizando la consola/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("Usuario")).not.toBeInTheDocument();
  });

  it("estado degradado cuando el me da 503 SIN motivo: avería, no 'actualizando'", async () => {
    stubFetch({ me: { status: 503 } });
    renderPuerta();

    expect(await screen.findByText(/La consola no está disponible/i)).toBeInTheDocument();
    expect(screen.queryByText(/Estamos actualizando la consola/i)).not.toBeInTheDocument();
  });

  it("Reintentar tras una caída entra a la app cuando el me se recupera", async () => {
    let caido = true;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) => {
        const ruta = String(url);
        if (ruta.includes("/api/auth/me")) {
          if (caido) throw new TypeError("network down");
          return new Response(JSON.stringify({ usuario: EDITOR }), { status: 200 });
        }
        return new Response("{}", { status: 200 });
      }),
    );
    renderPuerta();

    await screen.findByText(/La consola no está disponible/i);
    caido = false;
    fireEvent.click(screen.getByRole("button", { name: /reintentar/i }));

    expect(await screen.findByText("CONTENIDO PROTEGIDO")).toBeInTheDocument();
    expect(screen.queryByText(/La consola no está disponible/i)).not.toBeInTheDocument();
  });
});
