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

function renderEditor(composicionId = "comp-7") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = (id: string) => (
    <QueryClientProvider client={client}>
      <EditorSubtitulos composicionId={id} baseMediaId="videos/abc.mp4" onSubtituloLigado={vi.fn()} />
    </QueryClientProvider>
  );
  const utils = render(tree(composicionId));
  return { ...utils, cambiarComposicion: (id: string) => utils.rerender(tree(id)) };
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
    expect(screen.queryByText(/cambios sin guardar/i)).not.toBeInTheDocument();
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
    expect(screen.getByText(/cambios sin guardar/i)).toBeInTheDocument();
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
      expect(screen.queryByText(/cambios sin guardar/i)).not.toBeInTheDocument(),
    );
  });

  it("al cambiar de composición resetea el estado y no cruza correcciones", async () => {
    vi.spyOn(apiMod.api.video, "subtitulosDe").mockImplementation(async (id: string) =>
      id === "comp-7"
        ? { subtitulo: subFixture() }
        : {
            subtitulo: {
              ...subFixture(),
              id: "sub-9",
              composicion_id: "comp-9",
              segmentos: [{ id: "seg-0", inicio: 0, fin: 2, texto: "otra composicion" }],
            },
          },
    );
    const { cambiarComposicion } = renderEditor("comp-7");
    const caja = await screen.findByDisplayValue("ola desde mejico");
    fireEvent.change(caja, { target: { value: "Hola desde México" } });
    await screen.findByDisplayValue("Hola desde México");

    cambiarComposicion("comp-9");

    // Aparece el texto de la nueva composición; la corrección de la anterior no se cuela.
    expect(await screen.findByDisplayValue("otra composicion")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("Hola desde México")).not.toBeInTheDocument();
    // El respaldo de comp-9 no hereda las correcciones de comp-7.
    expect(sessionStorage.getItem("keni:video:subs:comp-9")).toBeNull();
  });

  it("un respaldo corrupto se descarta con console.warn y gana el dato del servidor", async () => {
    sessionStorage.setItem(CLAVE, "{respaldo-corrupto");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    renderEditor();
    // Cae al dato del servidor, sin aviso de restauración (no había nada restaurable).
    expect(await screen.findByDisplayValue("ola desde mejico")).toBeInTheDocument();
    expect(screen.queryByText(/cambios sin guardar/i)).not.toBeInTheDocument();
    // Y deja rastro con CONTEXTO (la clave del respaldo) + el error original.
    expect(warn).toHaveBeenCalledWith(expect.stringContaining(CLAVE), expect.anything());
  });

  it("clic en el timestamp de un segmento llama onSeek con el segundo de inicio", async () => {
    const onSeek = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <EditorSubtitulos
          composicionId="comp-7"
          baseMediaId="videos/abc.mp4"
          onSubtituloLigado={vi.fn()}
          onSeek={onSeek}
        />
      </QueryClientProvider>,
    );
    // Espera a que carguen los segmentos.
    const btnTimestamp = await screen.findByRole("button", { name: /ir al segundo/i });
    fireEvent.click(btnTimestamp);
    // El fixture tiene inicio=0 (segundos, según normalizarSegmentos convierte ms→s si necesario).
    expect(onSeek).toHaveBeenCalledTimes(1);
  });
});
