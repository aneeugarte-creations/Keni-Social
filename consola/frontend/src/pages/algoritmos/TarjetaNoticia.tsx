import { Archive, ExternalLink, Library } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { NoticiaAlgoritmo } from "@/types";

import { badgeNivel } from "./lib";

/** Tarjeta de una noticia. */
export function TarjetaNoticia({
  noticia,
  onProponer,
  onArchivar,
  archivando,
}: {
  noticia: NoticiaAlgoritmo;
  onProponer: (n: NoticiaAlgoritmo) => void;
  onArchivar: (n: NoticiaAlgoritmo) => void;
  archivando: boolean;
}) {
  const nivel = badgeNivel(noticia.nivel);
  return (
    <li className="rounded-lg border border-border/60 p-3">
      <div className="flex flex-wrap items-center gap-1.5 pb-1">
        <Badge variant="outline">{noticia.plataforma_nombre || noticia.plataforma}</Badge>
        <Badge variant={nivel.variante}>{nivel.texto}</Badge>
        {noticia.es_cambio && (
          <Badge
            variant="outline"
            className="border-amber-500/40 text-amber-700 dark:text-amber-300"
            title="Parece un cambio de algoritmo confirmado: candidato a la ficha editorial."
          >
            Cambio de algoritmo
          </Badge>
        )}
        {noticia.tipo === "oficial" && (
          <Badge variant="outline" className="border-sky-500/40 text-sky-700 dark:text-sky-300">
            Oficial
          </Badge>
        )}
        {noticia.aplicada && (
          <Badge variant="ok" title="Ya propuesta a la texto editorial.">
            En texto
          </Badge>
        )}
      </div>

      <p className="text-sm font-medium">
        {noticia.enlace ? (
          <a
            href={noticia.enlace}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-start gap-1 hover:underline"
          >
            {noticia.titulo || "(sin título)"}
            <ExternalLink className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" aria-hidden="true" />
          </a>
        ) : (
          noticia.titulo || "(sin título)"
        )}
      </p>

      {noticia.resumen && (
        <p className="pt-1 text-xs text-muted-foreground">{noticia.resumen}</p>
      )}

      {noticia.senales.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 pt-2">
          {noticia.senales.map((s) => (
            <span
              key={s}
              className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground"
            >
              {s}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between gap-2 pt-2">
        <span className="truncate text-xs text-muted-foreground">
          {[noticia.fuente_nombre, noticia.fecha].filter(Boolean).join(" · ")}
        </span>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onProponer(noticia)}
            title="Proponer esta noticia a la ficha editorial de la plataforma"
          >
            <Library className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
            A texto
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onArchivar(noticia)}
            disabled={archivando}
            title="Archivar (ocultar de la lista)"
          >
            <Archive className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </div>
      </div>
    </li>
  );
}
