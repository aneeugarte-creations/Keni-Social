/**
 * Pestaña "Acerca de" del editor de documentos: explica EN PROSA, para humanos, qué es
 * este archivo y para qué sirve dentro del pipeline. Reúne en una sola vista dónde se
 * inyecta el documento y su metadata: aquí no hay tablas ni campos, solo párrafos
 * compuestos a partir de los datos del documento (su descripción, y dónde entra:
 * procesos, pipelines y su sitio en la línea de la máquina).
 */
import * as React from "react";

import type { DocumentoTexto, EtapaPrompt, RespuestaMaquinaTexto } from "@/types";

/** Une una lista de frases en castellano natural: "a", "a y b", "a, b y c". */
function enumerar(items: string[]): string {
  if (items.length === 0) return "";
  if (items.length === 1) return items[0];
  return `${items.slice(0, -1).join(", ")} y ${items[items.length - 1]}`;
}

export function PanelAcerca({
  doc,
  maquina,
}: {
  doc: DocumentoTexto;
  maquina?: RespuestaMaquinaTexto;
}) {
  // Posición del doc en las máquinas: etapas `prompt` cuyo doc_id es este doc.
  const etapas = React.useMemo(
    () =>
      (maquina?.maquinas ?? []).flatMap((m) =>
        m.etapas
          .filter((e): e is EtapaPrompt => e.tipo === "prompt" && e.doc_id === doc.id)
          .map((e) => ({ maquina: m.titulo, etapa: e.titulo })),
      ),
    [maquina, doc.id],
  );

  const esPrompt = doc.tipo === "prompt";
  const descripcion = (doc.descripcion ?? "").trim();
  const procesos = doc.procesos ?? [];
  const pipelines = doc.pipelines ?? [];
  const cableado = procesos.length > 0 || pipelines.length > 0 || etapas.length > 0 || !!doc.rol;

  // ── Clase `desarrollo`: NO es contexto de marca; gobierna a los agentes Ralph y a las fases
  //    del carril de auto-desarrollo. El texto genérico de "pieza editorial" no aplica. ──
  const esDesarrollo = doc.clase === "desarrollo";
  const usoDesarrollo = doc.id.endsWith("/ralph-operativo")
    ? "Se inyecta como CLAUDE.md del Ralph Operativo (el asistente del equipo) cada vez que lo lanzas desde la burbuja. Editarlo cambia su comportamiento sin tocar código."
    : doc.id.endsWith("/ralph")
      ? "Se inyecta como instrucciones del Ralph Desarrollo cada vez que lo lanzas desde la burbuja. Editarlo cambia su comportamiento sin tocar código."
      : "Es el prompt de una fase del carril de auto-desarrollo (kanban de Sugerencias): lo usa el motor al construir una idea.";

  // ── Párrafo 1: qué ES este archivo. ──
  const queEs = esDesarrollo
    ? "Es contexto de AUTO-DESARROLLO: gobierna a los agentes Ralph y a las fases del kanban de Sugerencias (no es contexto de marca)."
    : esPrompt
      ? "Es un prompt: el conjunto de instrucciones que recibe el modelo cuando genera contenido."
      : "Es una pieza editorial: contexto de marca, voz o reglas que se inyecta en las generaciones para que el resultado suene auténtico.";

  // ── Párrafo 2: para qué sirve (la descripción del equipo, si la hay). ──

  // ── Párrafo 3: dónde entra dentro del pipeline. ──
  const frasesUso: string[] = [];
  if (procesos.length > 0) {
    frasesUso.push(
      `Se inyecta en ${procesos.length === 1 ? "el proceso" : "los procesos"} ${enumerar(procesos)}.`,
    );
  }
  if (etapas.length > 0) {
    const sitios = etapas.map((e) => `${e.etapa} (${e.maquina})`);
    frasesUso.push(
      `En la línea de la máquina ocupa ${etapas.length === 1 ? "el sitio" : "los sitios"} ${enumerar(sitios)}.`,
    );
  }
  if (pipelines.length > 0 || doc.rol) {
    const rol = doc.rol ? `con el rol «${doc.rol}»` : "";
    const pipes =
      pipelines.length > 0
        ? `forma parte de ${pipelines.length === 1 ? "el pipeline" : "los pipelines"} ${enumerar(pipelines)}`
        : "está cableado a un pipeline";
    frasesUso.push(`${[pipes, rol].filter(Boolean).join(" ")}.`);
  }

  return (
    <div className="space-y-4 text-sm leading-relaxed">
      <p>{queEs}</p>

      {descripcion ? (
        <p className="text-muted-foreground">{descripcion}</p>
      ) : (
        <p className="text-muted-foreground">
          Todavía no tiene una descripción. Añádela para que el equipo sepa de un vistazo
          qué cubre este archivo.
        </p>
      )}

      {esDesarrollo ? (
        <p>{usoDesarrollo}</p>
      ) : cableado ? (
        <p>{frasesUso.join(" ")}</p>
      ) : (
        <p className="text-muted-foreground">
          No está cableado a ningún flujo: se adjunta automáticamente según su clase y
          marcas, o se usa de forma puntual.
        </p>
      )}
    </div>
  );
}
