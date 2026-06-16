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
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FASES_INVESTIGACION, MAESTRO_INVESTIGACION } from "@/pages/maquina/fases";
import { PanelPipeline } from "@/pages/monitor/PanelPipeline";
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
        titulo="Investigación"
        fases={FASES_INVESTIGACION}
        queuePorTipo={{}}
        claveMaestro={MAESTRO_INVESTIGACION}
      />
    </QueryClientProvider>,
  );
}

describe("PanelPipeline · toggles independientes", () => {
  it("surfacea el maestro UNA vez y no lo pinta como switch por fila", async () => {
    renderPanel();
    // El maestro aparece como control ÚNICO en la cabecera…
    expect(
      await screen.findByRole("switch", {
        name: /Investigación \(maestro del proceso/,
      }),
    ).toBeInTheDocument();
    // …y NINGUNA fase pinta un switch que sea el maestro («switch de la fase»).
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
