import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { RespuestaAgencias } from "@/types";

import { SeccionAgencias } from "./SeccionAgencias";

// Admin: la sección solo se pinta para administradores.
vi.mock("@/hooks/sesion-contexto", () => ({
  useSesion: () => ({ usuario: { rol: "admin" } }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
// Confirmación destructiva: en test siempre acepta.
vi.mock("@/components/comunes/confirmar", () => ({ confirmar: () => Promise.resolve(true) }));

// AFP (configurada, con secretos + base_url) y Reuters (sin configurar). Cada agencia declara
// SUS campos: el front los pinta por metadatos. La pista llega ya con prefijo `····`.
const RESP: RespuestaAgencias = {
  agencias: [
    {
      agencia: "afp",
      nombre: "AFP",
      configurado: true,
      disponible: true,
      motivo: "",
      campos: [
        {
          clave: "client_id",
          etiqueta: "Client ID",
          secreto: true,
          opcional: false,
          configurado: true,
          pista: "····1234",
        },
        {
          clave: "client_secret",
          etiqueta: "Client Secret",
          secreto: true,
          opcional: false,
          configurado: false,
          pista: "",
        },
        {
          clave: "base_url",
          etiqueta: "Base URL",
          secreto: false,
          opcional: true,
          valor: "https://afp.example/api",
        },
      ],
    },
    {
      agencia: "reuters",
      nombre: "Reuters",
      configurado: false,
      disponible: false,
      motivo: "Falta la API key",
      campos: [
        {
          clave: "api_key",
          etiqueta: "API key (Bearer)",
          secreto: true,
          opcional: false,
          configurado: false,
          pista: "",
        },
        {
          clave: "base_url",
          etiqueta: "Base URL",
          secreto: false,
          opcional: true,
          valor: "https://reuters.example/api",
        },
      ],
    },
  ],
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

/** La sección arranca colapsada (SeccionColapsable): se abre pulsando su cabecera. */
function abrir() {
  fireEvent.click(screen.getByText("Agencias · Credenciales"));
}

describe("SeccionAgencias", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renderiza AFP y Reuters con sus campos por metadatos; un secreto configurado muestra la pista sin exponer el valor", async () => {
    vi.spyOn(api, "estadoAgencias").mockResolvedValue(RESP);
    renderConProviders(<SeccionAgencias />);
    abrir();

    expect(await screen.findByText("AFP")).toBeInTheDocument();
    expect(screen.getByText("Reuters")).toBeInTheDocument();
    // Campos declarados por cada agencia.
    expect(screen.getByLabelText(/Client ID/)).toBeInTheDocument();
    expect(screen.getByLabelText(/API key \(Bearer\)/)).toBeInTheDocument();

    // El secreto configurado muestra su pista; el secreto vacío no expone valor (input vacío).
    expect(screen.getByText("Configurada ····1234")).toBeInTheDocument();
    const clientId = screen.getByLabelText(/Client ID/) as HTMLInputElement;
    expect(clientId.type).toBe("password");
    expect(clientId.value).toBe("");

    // base_url (no secreto) llega con su valor efectivo, editable.
    const baseAfp = screen.getByLabelText(/Base URL/, { selector: "#agencia-afp-base_url" });
    expect((baseAfp as HTMLInputElement).value).toBe("https://afp.example/api");
  });

  it("guarda enviando solo los campos tocados (secreto vacío no se manda; base_url sí)", async () => {
    vi.spyOn(api, "estadoAgencias").mockResolvedValue(RESP);
    const guardar = vi.spyOn(api, "guardarAgencia").mockResolvedValue(RESP.agencias[0]);
    renderConProviders(<SeccionAgencias />);
    abrir();

    await screen.findByText("AFP");
    fireEvent.change(screen.getByLabelText(/Client ID/), { target: { value: "id-nuevo" } });
    // El primer botón Guardar es el de AFP.
    fireEvent.click(screen.getAllByRole("button", { name: "Guardar" })[0]);

    await waitFor(() =>
      expect(guardar).toHaveBeenCalledWith("afp", {
        client_id: "id-nuevo",
        base_url: "https://afp.example/api",
      }),
    );
  });

  it("Probar muestra el mensaje devuelto", async () => {
    vi.spyOn(api, "estadoAgencias").mockResolvedValue(RESP);
    vi.spyOn(api, "probarAgencia").mockResolvedValue({ ok: true, mensaje: "Conexión correcta" });
    renderConProviders(<SeccionAgencias />);
    abrir();

    await screen.findByText("AFP");
    fireEvent.click(screen.getAllByRole("button", { name: "Probar" })[0]);

    expect(await screen.findByText("Conexión correcta")).toBeInTheDocument();
  });

  it("Quitar llama a eliminarAgencia para una agencia configurada", async () => {
    vi.spyOn(api, "estadoAgencias").mockResolvedValue(RESP);
    const eliminar = vi.spyOn(api, "eliminarAgencia").mockResolvedValue(RESP.agencias[0]);
    renderConProviders(<SeccionAgencias />);
    abrir();

    await screen.findByText("AFP");
    // Solo AFP está configurada: hay un único botón Quitar.
    fireEvent.click(screen.getByRole("button", { name: "Quitar" }));

    await waitFor(() => expect(eliminar).toHaveBeenCalledWith("afp"));
  });
});
