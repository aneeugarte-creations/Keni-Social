/**
 * Tests del editor de SUBTÍTULOS (corrección humana es-MX) — respaldo de cambios sin guardar:
 *  - Editar un segmento respalda el borrador en sessionStorage (`keni:video:subs:<id>`).
 *  - Al volver con un respaldo pendiente, se RESTAURA (gana al dato del servidor) con aviso
 *    "cambios sin guardar restaurados" y «Guardar correcciones» habilitado.
 *  - Guardar en el servidor limpia el respaldo y el aviso.
 *  - Un respaldo CORRUPTO se descarta con `console.warn` (rastro) y gana el dato del servidor.
 *
 * `useGeneracion` se mockea (aquí no se ejercita la transcripción en vivo).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as apiMod from "@/lib/api";
import type { Subtitulo } from "@/lib/video";

import { EditorSubtitulos } from "./EditorSubtitulos";

vi.mock("@/hooks/use-generacion", () => ({
  useGeneracion: () => ({ generacion: null, ejecutando: false, iniciar: vi.fn() }),
}));

const CLAVE = "keni:video:subs:comp-7";

function subFixture(): Subtitulo {
  return {
    id: "sub-1",
    composicion_id: "comp-7",
    idioma: "es-MX",
    estado: "transcrito",
    segmentos: [{ id: "seg-0", inicio: 0, fin: 2, texto: "ola desde mejico" }],
  };
}

function renderEditor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <EditorSubtitulos
        composicionId="comp-7"
        baseMediaId="videos/abc.mp4"
        onSubtituloLigado={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

describe("EditorSubtitulos (respaldo de correcciones sin guardar)", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.spyOn(apiMod.api.video, "subtitulosDe").mockResolvedValue({ subtitulo: subFixture() });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it("editar un segmento respalda el borrador en sessionStorage", async () => {
    renderEditor();
    const caja = await screen.findByDisplayValue("ola desde mejico");
    fireEvent.change(caja, { target: { value: "Hola desde México" } });
    await waitFor(() => {
      const crudo = sessionStorage.getItem(CLAVE);
      expect(crudo).toBeTruthy();
      expect(JSON.parse(crudo!)[0].texto).toBe("Hola desde México");
    });
    // Sin respaldo previo restaurado, el aviso NO aparece.
    expect(screen.queryByText(/cambios sin guardar restaurados/i)).not.toBeInTheDocument();
  });

  it("restaura el respaldo pendiente al volver, con aviso y guardado habilitado", async () => {
    sessionStorage.setItem(
      CLAVE,
      JSON.stringify([{ id: "seg-0", inicio: 0, fin: 2, texto: "Hola desde México (corregido)" }]),
    );
    renderEditor();
    // Gana el respaldo, no el texto del servidor.
    expect(await screen.findByDisplayValue("Hola desde México (corregido)")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("ola desde mejico")).not.toBeInTheDocument();
    expect(screen.getByText(/cambios sin guardar restaurados/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /guardar correcciones/i })).not.toBeDisabled();
  });

  it("guardar en el servidor limpia el respaldo y el aviso", async () => {
    sessionStorage.setItem(
      CLAVE,
      JSON.stringify([{ id: "seg-0", inicio: 0, fin: 2, texto: "Hola corregido" }]),
    );
    const guardar = vi
      .spyOn(apiMod.api.video, "guardarSubtitulo")
      .mockResolvedValue({ subtitulo: { ...subFixture(), estado: "editado" } });
    renderEditor();
    await screen.findByDisplayValue("Hola corregido");
    fireEvent.click(screen.getByRole("button", { name: /guardar correcciones/i }));
    await waitFor(() => expect(guardar).toHaveBeenCalledTimes(1));
    expect(guardar.mock.calls[0][0]).toBe("sub-1");
    expect(guardar.mock.calls[0][1].estado).toBe("editado");
    await waitFor(() => expect(sessionStorage.getItem(CLAVE)).toBeNull());
    await waitFor(() =>
      expect(screen.queryByText(/cambios sin guardar restaurados/i)).not.toBeInTheDocument(),
    );
  });

  it("un respaldo corrupto se descarta con console.warn y gana el dato del servidor", async () => {
    sessionStorage.setItem(CLAVE, "{respaldo-corrupto");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    renderEditor();
    // Cae al dato del servidor, sin aviso de restauración (no había nada restaurable).
    expect(await screen.findByDisplayValue("ola desde mejico")).toBeInTheDocument();
    expect(screen.queryByText(/cambios sin guardar restaurados/i)).not.toBeInTheDocument();
    // Y deja rastro con CONTEXTO (la clave del respaldo) + el error original.
    expect(warn).toHaveBeenCalledWith(expect.stringContaining(CLAVE), expect.anything());
  });
});
