/**
 * PanelPipeline · independencia de toggles (bug «tocar uno apaga todos»).
 *
 * Las fases SIN flag físico propio resuelven su clave efectiva al MAESTRO del proceso
 * (`KENI_INVESTIGACION`). Antes cada una pintaba un switch que ERA el maestro: tocar cualquiera
 * apagaba el proceso entero. Ahora esas fases NO muestran switch («· sigue al maestro»), el maestro
 * se surfacea UNA sola vez en la cabecera, y solo las fases dueñas de un flag propio
 * (Recolectar/Verificar) tienen su switch por fila. Las seguidoras NO pintan nada a la derecha
 * (ni texto «· sigue …» ni chevron): la fila sigue siendo clicable, solo desaparecen esos adornos.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  FASES_INVESTIGACION,
  FASES_PRODUCCION,
  MAESTRO_INVESTIGACION,
  MAESTRO_PRODUCCION,
} from "@/pages/maquina/fases";
import { ControlesMaquina, PanelPipeline } from "@/pages/monitor/PanelPipeline";
import type { AjusteAdmin } from "@/types";

function aj(clave: string, etiqueta: string, valor = true): AjusteAdmin {
  return {
    clave,
    tipo: "bool",
    etiqueta,
    ayuda: "",
    grupo: "g",
    peligroso: false,
    valor,
    fuente: "store",
    defecto: false,
  };
}

vi.mock("@/lib/api", () => ({
  api: {
    ajustes: vi.fn().mockResolvedValue({
      grupos: [
        {
          id: "g",
          titulo: "g",
          ajustes: [
            aj("KENI_MAQUINA", "Máquina"),
            aj("KENI_INVESTIGACION", "Investigación"),
            aj("KENI_PIPELINE_RECOLECTAR", "Recolectar"),
            aj("KENI_PIPELINE_VERIFICAR", "Verificar"),
            aj("KENI_PRODUCCION", "Producción"),
            aj("KENI_PIPELINE_REDACTAR", "Redactar"),
            aj("KENI_PIPELINE_ILUSTRAR", "Ilustrar"),
          ],
        },
      ],
    }),
    guardarAjuste: vi.fn(),
  },
  mensajeError: (e: unknown) => String(e),
}));

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PanelPipeline
        fases={FASES_INVESTIGACION}
        queuePorTipo={{}}
        claveMaestro={MAESTRO_INVESTIGACION}
      />
    </QueryClientProvider>,
  );
}

/** ControlesMaquina (junto a las pestañas): maestro del proceso + interruptor general «Máquina». */
function renderControles() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ControlesMaquina claveMaestro={MAESTRO_INVESTIGACION} />
    </QueryClientProvider>,
  );
}

function renderProduccion(onAbrirFase = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <PanelPipeline
        fases={FASES_PRODUCCION}
        queuePorTipo={{}}
        claveMaestro={MAESTRO_PRODUCCION}
        onAbrirFase={onAbrirFase}
      />
    </QueryClientProvider>,
  );
  return onAbrirFase;
}

/** La fila (li) de una fase por su nombre, para inspeccionar su rol/click. */
function filaDe(nombre: string): HTMLElement {
  const li = screen.getByText(nombre).closest("li");
  if (!li) throw new Error(`fila ${nombre} no encontrada`);
  return li as HTMLElement;
}

describe("PanelPipeline · toggles independientes", () => {
  it("el maestro vive junto a las pestañas (ControlesMaquina), no como switch por fila", async () => {
    // El maestro aparece como control ÚNICO en ControlesMaquina…
    renderControles();
    expect(
      await screen.findByRole("switch", {
        name: /Investigación \(maestro del proceso/,
      }),
    ).toBeInTheDocument();
    // …y dentro del PanelPipeline NINGUNA fase pinta un switch que sea el maestro («switch de la fase»).
    renderPanel();
    expect(
      screen.queryByRole("switch", { name: /Investigación \(switch de la fase/ }),
    ).not.toBeInTheDocument();
  });

  it("solo las fases con flag propio tienen switch; las seguidoras no pintan nada", async () => {
    renderPanel();
    expect(
      await screen.findByRole("switch", { name: /Recolectar \(switch de la fase Recolectar\)/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("switch", { name: /Verificar \(switch de la fase Verificar\)/ }),
    ).toBeInTheDocument();
    // Las seguidoras YA NO muestran el texto «· sigue …» a la derecha.
    expect(screen.queryByText(/· sigue (al maestro|a Recolectar)/)).not.toBeInTheDocument();
  });
});

describe("PanelPipeline · solo las filas con contenido son clicables", () => {
  it("las fases con contenido (Redactar, Ilustrar) son clicables y navegan a su detalle", async () => {
    const onAbrir = renderProduccion();
    // Espera a que el catálogo cargue (Redactar pinta su switch).
    expect(
      await screen.findByRole("switch", { name: /Redactar \(switch de la fase Redactar\)/ }),
    ).toBeInTheDocument();

    // Redactar tiene prompt + contexto + cola + etapa: su fila es clicable (role button) y navega.
    within(filaDe("Redactar")).getByRole("button").click();
    expect(onAbrir).toHaveBeenCalledTimes(1);
    expect(onAbrir.mock.calls[0][0].nombre).toBe("Redactar");

    // Ilustrar también tiene prompt + cola + etapa: igualmente clicable y navega.
    within(filaDe("Ilustrar")).getByRole("button").click();
    expect(onAbrir).toHaveBeenCalledTimes(2);
    expect(onAbrir.mock.calls[1][0].nombre).toBe("Ilustrar");
  });

  it("ninguna fila vacía: ya no se pintan Agrupar (Investigación) ni Revisar (Producción)", () => {
    renderProduccion();
    expect(screen.queryByText("Revisar")).not.toBeInTheDocument();
    expect(screen.queryByText("Agrupar")).not.toBeInTheDocument();
  });
});
