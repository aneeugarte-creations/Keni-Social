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
            aj("KENI_PRODUCCION", "Producción"),
            aj("KENI_PIPELINE_REDACTAR", "Redactar"),
            aj("KENI_PIPELINE_ILUSTRAR", "Ilustrar"),
            aj("KENI_AUTO_PREAPROBACION", "Aprobar"),
            aj("KENI_PUBLICAR_REAL", "Publicar"),
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

function renderProduccion(onAbrirFase = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <PanelPipeline
        titulo="Producción"
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

describe("PanelPipeline · solo las filas con contenido son clicables", () => {
  it("una fila con contenido (Redactar) navega; una con solo toggle (Publicar) no es clicable pero mantiene su switch", async () => {
    const onAbrir = renderProduccion();
    // Espera a que el catálogo cargue (Publicar pinta su switch).
    expect(
      await screen.findByRole("switch", { name: /Publicar \(switch de la fase Publicar\)/ }),
    ).toBeInTheDocument();

    // Redactar tiene prompt + contexto + cola + etapa: su fila es clicable (role button) y navega.
    const redactar = within(filaDe("Redactar")).getByRole("button");
    redactar.click();
    expect(onAbrir).toHaveBeenCalledTimes(1);
    expect(onAbrir.mock.calls[0][0].nombre).toBe("Redactar");

    // Publicar solo tiene su switch (sin prompt/contexto/logs/cola): su fila NO es clicable…
    const fila = filaDe("Publicar");
    expect(within(fila).queryByRole("button")).not.toBeInTheDocument();
    // …pero sigue mostrando su interruptor.
    expect(
      within(fila).getByRole("switch", { name: /Publicar \(switch de la fase Publicar\)/ }),
    ).toBeInTheDocument();
    // …y su aviso rojo de precaución (postea de verdad, no en simulación).
    expect(within(fila).getByText("Publica de verdad")).toBeInTheDocument();
  });

  it("ninguna fila vacía: ya no se pintan Agrupar (Investigación) ni Revisar (Producción)", () => {
    renderProduccion();
    expect(screen.queryByText("Revisar")).not.toBeInTheDocument();
    expect(screen.queryByText("Agrupar")).not.toBeInTheDocument();
  });
});
