/**
 * Barra de formato Markdown opcional para un textarea.
 *
 * Inserta marcas (negrita, cursiva, lista, enlace) envolviendo la selección
 * actual del textarea, o un texto guía si no hay selección. Tras insertar,
 * notifica el nuevo valor por `onContenido` y restaura el foco/selección.
 *
 * Es deliberadamente ligera: opera sobre el `value` controlado y la ref del
 * textarea, sin estado propio.
 */
import { Bold, Italic, Link2, List } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";

type Accion = "negrita" | "cursiva" | "lista" | "enlace";

export interface BarraFormatoProps {
  /** Ref al textarea destino (Textarea o AutoTextarea reenvían su ref). */
  refArea: React.RefObject<HTMLTextAreaElement>;
  /** Valor controlado actual. */
  valor: string;
  /** Notifica el nuevo valor tras insertar formato. */
  onContenido: (valor: string) => void;
  className?: string;
}

/** Aplica una acción de formato a `[inicio, fin)` de `texto`. */
function aplicar(
  accion: Accion,
  texto: string,
  inicio: number,
  fin: number,
): { texto: string; selInicio: number; selFin: number } {
  const sel = texto.slice(inicio, fin);
  const antes = texto.slice(0, inicio);
  const despues = texto.slice(fin);

  switch (accion) {
    case "negrita": {
      const cuerpo = sel || "texto en negrita";
      const nuevo = `${antes}**${cuerpo}**${despues}`;
      return { texto: nuevo, selInicio: inicio + 2, selFin: inicio + 2 + cuerpo.length };
    }
    case "cursiva": {
      const cuerpo = sel || "texto en cursiva";
      const nuevo = `${antes}*${cuerpo}*${despues}`;
      return { texto: nuevo, selInicio: inicio + 1, selFin: inicio + 1 + cuerpo.length };
    }
    case "lista": {
      const base = sel || "Elemento";
      const lineas = base.split("\n").map((l) => `- ${l}`);
      // Asegura salto de línea antes si no estamos al principio de línea.
      const prefijo = inicio > 0 && !antes.endsWith("\n") ? "\n" : "";
      const bloque = prefijo + lineas.join("\n");
      const nuevo = `${antes}${bloque}${despues}`;
      return {
        texto: nuevo,
        selInicio: inicio + bloque.length,
        selFin: inicio + bloque.length,
      };
    }
    case "enlace": {
      const cuerpo = sel || "texto del enlace";
      const nuevo = `${antes}[${cuerpo}](https://)${despues}`;
      // Deja seleccionada la URL para reemplazarla rápido.
      const urlInicio = inicio + 1 + cuerpo.length + 2;
      return { texto: nuevo, selInicio: urlInicio, selFin: urlInicio + 8 };
    }
  }
}

export function BarraFormato({ refArea, valor, onContenido, className }: BarraFormatoProps) {
  function ejecutar(accion: Accion) {
    const area = refArea.current;
    const inicio = area?.selectionStart ?? valor.length;
    const fin = area?.selectionEnd ?? valor.length;
    const res = aplicar(accion, valor, inicio, fin);
    onContenido(res.texto);
    // Restaura foco y selección tras el re-render controlado.
    window.requestAnimationFrame(() => {
      const a = refArea.current;
      if (!a) return;
      a.focus();
      a.setSelectionRange(res.selInicio, res.selFin);
    });
  }

  const botones: { accion: Accion; label: string; icono: React.ReactNode }[] = [
    { accion: "negrita", label: "Negrita", icono: <Bold className="h-3.5 w-3.5" /> },
    { accion: "cursiva", label: "Cursiva", icono: <Italic className="h-3.5 w-3.5" /> },
    { accion: "lista", label: "Lista", icono: <List className="h-3.5 w-3.5" /> },
    { accion: "enlace", label: "Enlace", icono: <Link2 className="h-3.5 w-3.5" /> },
  ];

  return (
    <div className={className}>
      <div className="inline-flex items-center gap-0.5 rounded-md border border-border p-0.5">
        {botones.map((b) => (
          <Tooltip key={b.accion} label={b.label}>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => ejecutar(b.accion)}
              aria-label={b.label}
            >
              {b.icono}
            </Button>
          </Tooltip>
        ))}
      </div>
    </div>
  );
}
