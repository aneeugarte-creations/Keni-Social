/**
 * Pestaña "Uso" del editor de documentos: dónde se inyecta este documento.
 *
 * Tres secciones (Procesos, Pipelines, Máquinas) con encabezado, icono y badges
 * consistentes, más un estado vacío legible cuando el documento no está cableado
 * a nada (se ejecuta a mano o se auto-adjunta por clase/marca).
 */
import { Layers, Sparkles, Workflow, Zap } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import type { DocumentoTexto, EtapaPrompt, RespuestaMaquinaTexto } from "@/types";

function Seccion({
  icono: Icono,
  titulo,
  children,
}: {
  icono: React.ComponentType<{ className?: string }>;
  titulo: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-2">
      <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <Icono className="h-3.5 w-3.5 text-keni" aria-hidden />
        {titulo}
      </h4>
      {children}
    </section>
  );
}

export function PanelUso({
  doc,
  maquina,
}: {
  doc: DocumentoTexto;
  maquina?: RespuestaMaquinaTexto;
}) {
  // Posición del doc en las TRES máquinas: etapas `prompt` cuyo doc_id es este doc.
  const etapas = React.useMemo(
    () =>
      (maquina?.maquinas ?? []).flatMap((m) =>
        m.etapas
          .filter((e): e is EtapaPrompt => e.tipo === "prompt" && e.doc_id === doc.id)
          .map((e) => ({ maquina: m.titulo, etapa: e.titulo })),
      ),
    [maquina, doc.id],
  );
  const procesos = doc.procesos ?? [];
  const pipelines = doc.pipelines ?? [];
  const nada =
    procesos.length === 0 && pipelines.length === 0 && etapas.length === 0 && !doc.rol;

  if (nada) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed border-border px-4 py-10 text-center">
        <Sparkles className="h-6 w-6 text-muted-foreground" aria-hidden />
        <div className="space-y-1">
          <p className="text-sm font-medium">No está cableado a ningún flujo</p>
          <p className="text-xs text-muted-foreground">
            Se ejecuta a mano con «Probar» o se adjunta automáticamente según su clase y
            marcas.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5 text-sm">
      {procesos.length > 0 ? (
        <Seccion icono={Zap} titulo="Procesos donde se inyecta">
          <ul className="space-y-1.5">
            {procesos.map((p) => (
              <li key={p} className="flex items-start gap-2">
                <span className="mt-0.5 select-none text-keni" aria-hidden>
                  →
                </span>
                <span className="leading-snug">{p}</span>
              </li>
            ))}
          </ul>
        </Seccion>
      ) : null}

      {pipelines.length > 0 || doc.rol ? (
        <Seccion icono={Workflow} titulo="Pipelines">
          <div className="flex flex-wrap gap-1.5">
            {doc.rol ? (
              <Badge variant="secondary" className="rounded-full">
                rol: {doc.rol}
              </Badge>
            ) : null}
            {pipelines.map((p) => (
              <Badge key={p} variant="outline" className="rounded-full">
                {p}
              </Badge>
            ))}
          </div>
        </Seccion>
      ) : null}

      {etapas.length > 0 ? (
        <Seccion icono={Layers} titulo="En las máquinas">
          <ul className="space-y-1.5">
            {etapas.map((e) => (
              <li
                key={`${e.maquina}-${e.etapa}`}
                className="flex flex-wrap items-center gap-1.5 leading-snug"
              >
                <span className="font-medium">{e.maquina}</span>
                <span className="text-muted-foreground" aria-hidden>
                  →
                </span>
                <span>{e.etapa}</span>
              </li>
            ))}
          </ul>
        </Seccion>
      ) : null}
    </div>
  );
}
