/**
 * Diff de PROSA legible para no técnicos (estilo "modo sugerencias" de Google Docs):
 * se muestra el texto final completo, con lo añadido en verde y lo borrado en rojo
 * tachado. NO es un diff de líneas estilo código.
 *
 * Cómo funciona:
 *   1. Diff a nivel de PÁRRAFO (`diffArrays` de jsdiff sobre los párrafos): localiza
 *      qué bloques cambiaron sin pagar un diff de palabras sobre todo el texto (los
 *      prompts son markdown de varias KB).
 *   2. Dentro de cada bloque cambiado, diff por PALABRAS con tokenización propia que
 *      trata `{{VARIABLE}}` como token ATÓMICO (un diff nunca parte una variable por
 *      la mitad) y las variables se pintan como pastillas, coherentes con el editor.
 *   3. `soloCambios` colapsa las rachas de párrafos sin cambios tras un separador
 *      "··· N párrafos sin cambios" (clic para desplegarlos).
 *
 * Antes de NADA, ambos lados pasan por `aProsaPlana` (ver `diffProsa.lib.ts`): se les quita
 * el frontmatter y el markup markdown y se les normaliza el whitespace con el MISMO pipeline,
 * de forma que (a) no se vea markdown crudo, (b) los metadatos no entren al diff y (c) los
 * cambios fantasma de formato (viñeta `*` vs `-`, espacios, hard-breaks) se cancelen. Las
 * pastillas de `{{VARIABLE}}` sobreviven intactas. Además, un fragmento que sea PURO
 * whitespace nunca se pinta como añadido/borrado: un salto de línea no es un "cambio".
 */
import { diffArrays } from "diff";
import * as React from "react";

import {
  aProsaPlana,
  esSoloEspacios,
  normalizarEspacios,
} from "@/components/prompts/diffProsa.lib";
import { cn } from "@/lib/utils";

// `{{VARIABLE}}` | racha de espacios | racha sin espacios. Cubre TODO el texto, así
// `tokens.join("") === texto` (sin pérdida) y la variable viaja entera por el diff.
const RE_TOKEN = /\{\{[A-Z_]+\}\}|\s+|[^\s]+/g;

const RE_PARTIR_VARIABLE = /(\{\{[A-Z_]+\}\})/g;

function tokenizar(texto: string): string[] {
  return texto.match(RE_TOKEN) ?? [];
}

/** Párrafos de un markdown: bloques separados por línea(s) en blanco. */
function partirParrafos(texto: string): string[] {
  const limpio = texto.replace(/\r\n/g, "\n").trim();
  if (!limpio) return [];
  return limpio.split(/\n{2,}/);
}

/** Texto plano con las `{{VARIABLES}}` pintadas como pastilla (estática, sin tooltip). */
function TextoConVariables({ texto }: { texto: string }) {
  const partes = texto.split(RE_PARTIR_VARIABLE);
  return (
    <>
      {partes.map((p, i) =>
        /^\{\{[A-Z_]+\}\}$/.test(p) ? (
          <span
            key={i}
            className="mx-px inline-flex items-center rounded-md border border-border bg-muted/70 px-1 py-0 align-baseline font-medium text-foreground/80"
          >
            {p.slice(2, -2)}
          </span>
        ) : (
          <React.Fragment key={i}>{p}</React.Fragment>
        ),
      )}
    </>
  );
}

/** Un fragmento del diff de palabras: igual / añadido / borrado. */
function Fragmento({ texto, tipo }: { texto: string; tipo: "igual" | "mas" | "menos" }) {
  if (tipo === "mas") {
    return (
      <ins className="rounded-sm bg-emerald-500/15 px-0.5 text-emerald-700 no-underline dark:text-emerald-300">
        <TextoConVariables texto={texto} />
      </ins>
    );
  }
  if (tipo === "menos") {
    return (
      <del className="rounded-sm bg-red-500/10 px-0.5 text-red-700 line-through decoration-red-700/60 dark:text-red-400 dark:decoration-red-400/60">
        <TextoConVariables texto={texto} />
      </del>
    );
  }
  return <TextoConVariables texto={texto} />;
}

/** Bloque CAMBIADO: diff por palabras entre el texto viejo y el nuevo del bloque. */
function BloqueCambiado({ antes, despues }: { antes: string; despues: string }) {
  const partes = React.useMemo(
    () => diffArrays(tokenizar(antes), tokenizar(despues)),
    [antes, despues],
  );
  return (
    <p className="whitespace-pre-wrap leading-relaxed">
      {partes.map((p, i) => {
        const texto = p.value.join("");
        // Un fragmento de SOLO whitespace (espacios/saltos) jamás se resalta: el cambio de
        // whitespace es estructura, no contenido. Se pinta como contexto (tipo "igual").
        const tipo = esSoloEspacios(texto)
          ? "igual"
          : p.added
            ? "mas"
            : p.removed
              ? "menos"
              : "igual";
        return <Fragmento key={i} texto={texto} tipo={tipo} />;
      })}
    </p>
  );
}

// Un bloque del diff a nivel de párrafo, listo para render.
type Bloque =
  | { tipo: "igual"; parrafos: string[] }
  | { tipo: "cambio"; antes: string; despues: string };

/** Agrupa el diff de párrafos en bloques: rachas sin cambios vs. pares borrado→añadido. */
function agruparBloques(antes: string, despues: string): Bloque[] {
  const partes = diffArrays(partirParrafos(antes), partirParrafos(despues));
  const bloques: Bloque[] = [];
  let i = 0;
  while (i < partes.length) {
    const parte = partes[i];
    if (!parte.added && !parte.removed) {
      bloques.push({ tipo: "igual", parrafos: parte.value });
      i += 1;
      continue;
    }
    // Racha de cambio: junta el "removed" y el "added" contiguos (en cualquier orden)
    // en UN bloque, para que el diff de palabras case lo viejo contra lo nuevo.
    let quitado: string[] = [];
    let anadido: string[] = [];
    while (i < partes.length && (partes[i].added || partes[i].removed)) {
      if (partes[i].removed) quitado = quitado.concat(partes[i].value);
      else anadido = anadido.concat(partes[i].value);
      i += 1;
    }
    bloques.push({ tipo: "cambio", antes: quitado.join("\n\n"), despues: anadido.join("\n\n") });
  }
  return bloques;
}

export interface DiffProsaProps {
  /** Texto (markdown) de la versión vieja. */
  antes: string;
  /** Texto (markdown) de la versión nueva. */
  despues: string;
  /** `true` => colapsa los párrafos sin cambios ("··· N párrafos sin cambios"). */
  soloCambios?: boolean;
  className?: string;
}

/**
 * Diff de prosa legible: texto final con añadidos en verde y borrados en rojo tachado.
 * Pensado para que una persona de redes (no técnica) entienda QUÉ cambió en un prompt.
 */
export function DiffProsa({ antes, despues, soloCambios = false, className }: DiffProsaProps) {
  // Proyecta AMBOS lados a prosa plana con el MISMO pipeline (strip de frontmatter + limpieza
  // de markdown + normalización de whitespace) ANTES de diffear: ni markdown crudo ni
  // metadatos ni diffs fantasma de formato. Las pastillas `{{VARIABLE}}` sobreviven.
  const antesPlano = React.useMemo(() => aProsaPlana(antes), [antes]);
  const despuesPlano = React.useMemo(() => aProsaPlana(despues), [despues]);
  const bloques = React.useMemo(
    () => agruparBloques(antesPlano, despuesPlano),
    [antesPlano, despuesPlano],
  );
  // Rachas sin cambios desplegadas a mano en modo "solo cambios" (clic en el separador).
  const [desplegados, setDesplegados] = React.useState<Set<number>>(new Set());
  React.useEffect(
    () => setDesplegados(new Set()),
    [antesPlano, despuesPlano, soloCambios],
  );

  const hayCambios = bloques.some((b) => b.tipo === "cambio");
  if (!hayCambios) {
    // El texto plano es idéntico. Si el markdown ORIGINAL (sin frontmatter, con espacios
    // normalizados pero conservando el markup) difiere, el único cambio fue de FORMATO
    // (negritas, títulos, citas...): avisamos para no confundir con "no se guardó nada".
    const soloFormato = normalizarEspacios(antes) !== normalizarEspacios(despues);
    return (
      <p className={cn("text-sm text-muted-foreground", className)}>
        {soloFormato
          ? "ℹ Solo cambios de formato (negritas, títulos…); el texto es el mismo."
          : "Sin cambios."}
      </p>
    );
  }

  return (
    <div className={cn("space-y-3 break-words text-sm text-foreground", className)}>
      {bloques.map((b, i) => {
        if (b.tipo === "cambio") {
          return <BloqueCambiado key={i} antes={b.antes} despues={b.despues} />;
        }
        if (soloCambios && !desplegados.has(i)) {
          return (
            <button
              key={i}
              type="button"
              onClick={() =>
                setDesplegados((prev) => {
                  const s = new Set(prev);
                  s.add(i);
                  return s;
                })
              }
              title="Mostrar los párrafos sin cambios"
              className="block w-full rounded-md border border-dashed border-border py-1 text-center text-xs text-muted-foreground hover:bg-muted/50 hover:text-foreground"
            >
              ··· {b.parrafos.length === 1 ? "1 párrafo sin cambios" : `${b.parrafos.length} párrafos sin cambios`}
            </button>
          );
        }
        return (
          <React.Fragment key={i}>
            {b.parrafos.map((p, j) => (
              <p key={j} className="whitespace-pre-wrap leading-relaxed">
                <TextoConVariables texto={p} />
              </p>
            ))}
          </React.Fragment>
        );
      })}
    </div>
  );
}
