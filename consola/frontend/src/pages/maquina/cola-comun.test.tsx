import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Backlog, ColaJob } from "@/types";

import { TablaBacklog, TablaJobs } from "./cola-comun";

// El menú contextual dispara `confirmar`/`elegir` (diálogos imperativos): los mockeamos para
// resolver sin montar su contenedor y poder probar el cableado de las acciones.
vi.mock("@/components/comunes/confirmar", () => ({
  confirmar: vi.fn().mockResolvedValue(true),
  elegir: vi.fn().mockResolvedValue("75"),
}));

const BACKLOG: Backlog = {
  marcas: [
    {
      marca: "claro-sports",
      nombre: "Claro Sports",
      etapas: {
        pool_sin_admitir: 3,
        pipeline_en_proceso: 1,
        esperando_copy: 600,
        generando_copy: 4,
        generando_arte: 2,
        lista_para_revisar: 5,
      },
      total: 615,
    },
    {
      marca: "unotv",
      nombre: "UnoTV",
      etapas: {
        pool_sin_admitir: 0,
        pipeline_en_proceso: 0,
        esperando_copy: 0,
        generando_copy: 0,
        generando_arte: 0,
        lista_para_revisar: 0,
      },
      total: 0,
    },
  ],
};

describe("TablaBacklog", () => {
  it("pinta una fila por marca y las 6 etapas en orden de cadena + total", () => {
    render(<TablaBacklog backlog={BACKLOG} />);

    // Una fila por marca.
    expect(screen.getByText("Claro Sports")).toBeInTheDocument();
    expect(screen.getByText("UnoTV")).toBeInTheDocument();

    // Las 6 etapas como cabeceras, EN ORDEN de cadena (entrada → salida) + Total.
    const cabeceras = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(cabeceras).toEqual([
      "Marca",
      "Pool",
      "En proceso",
      "Esperando copy",
      "Generando copy",
      "Generando arte",
      "Lista para revisar",
      "Total",
    ]);

    // La fila de Claro Sports muestra el "embalse oculto" de 600 esperando copy y su total.
    const filaClaro = screen.getByText("Claro Sports").closest("tr");
    expect(filaClaro).not.toBeNull();
    expect(within(filaClaro as HTMLElement).getByText("600")).toBeInTheDocument();
    expect(within(filaClaro as HTMLElement).getByText("615")).toBeInTheDocument();
  });

  it("usa el título por defecto, y lo enmarca por página cuando se le pasa `titulo`", () => {
    const { rerender } = render(<TablaBacklog backlog={BACKLOG} />);
    expect(screen.getByText("Embalse del tablero (antes de la cola)")).toBeInTheDocument();

    rerender(<TablaBacklog backlog={BACKLOG} titulo="Trabajo pendiente (backlog que costará)" />);
    expect(screen.getByText("Trabajo pendiente (backlog que costará)")).toBeInTheDocument();
    expect(screen.queryByText("Embalse del tablero (antes de la cola)")).toBeNull();
  });
});

function job(parcial: Partial<ColaJob> = {}): ColaJob {
  return {
    job_id: "j1",
    gen_id: "g1",
    estado: "pendiente",
    worker: "",
    etiqueta: "Tema 1",
    tipo: "copy",
    marca: "unotv",
    proceso: "produccion",
    gen_estado: "ejecutando",
    fase: "",
    prioridad: 0,
    encolado_hace_s: 30,
    corriendo_hace_s: null,
    etapa: "Redactar",
    prompt_chars: 8200,
    tokens_estimados: 12000,
    tokens_in: null,
    tokens_out: null,
    coste_usd: null,
    ...parcial,
  };
}

function renderTabla(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("TablaJobs · columnas Etapa y Tokens", () => {
  it("un job ESPERANDO muestra la etapa legible y el estimado de tokens («est.») + chars", () => {
    renderTabla(
      <TablaJobs
        jobs={[job()]}
        mostrarWorker={false}
        esAdmin={false}
        onCancelar={() => {}}
        cancelandoId={null}
      />,
    );
    expect(screen.getByText("Redactar")).toBeInTheDocument();
    expect(screen.getByText(/12\s*k est\./)).toBeInTheDocument();
    expect(screen.getByText(/8\.2\s*k chars/)).toBeInTheDocument();
  });

  it("un job CORRIENDO con métricas muestra tokens reales in/out + coste", () => {
    renderTabla(
      <TablaJobs
        jobs={[
          job({
            estado: "reclamado",
            worker: "w1",
            corriendo_hace_s: 12,
            tokens_in: 12000,
            tokens_out: 3000,
            coste_usd: 0.05,
          }),
        ]}
        mostrarWorker
        esAdmin={false}
        onCancelar={() => {}}
        cancelandoId={null}
      />,
    );
    expect(screen.getByText(/12\s*k in · 3\s*k out/)).toBeInTheDocument();
    expect(screen.getByText(/0\.050/)).toBeInTheDocument();
  });
});

describe("TablaJobs · acción Eliminar", () => {
  it("la acción Eliminar (admin) llama a onEliminar con el gen_id tras confirmar", async () => {
    const onEliminar = vi.fn();
    renderTabla(
      <TablaJobs
        jobs={[job()]}
        mostrarWorker={false}
        esAdmin
        onCancelar={() => {}}
        cancelandoId={null}
        onEliminar={onEliminar}
        eliminandoId={null}
      />,
    );
    // Abre el menú contextual de la fila (click derecho) y dispara «Eliminar».
    fireEvent.contextMenu(screen.getByText("Tema 1"));
    const item = await screen.findByRole("menuitem", { name: /Eliminar/i });
    fireEvent.click(item);
    await vi.waitFor(() => expect(onEliminar).toHaveBeenCalledWith("g1"));
  });
});
