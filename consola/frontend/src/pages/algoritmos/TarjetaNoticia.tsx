import { Archive, ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { confirmar } from "@/components/comunes/confirmar";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
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

  const acciones: EntradaMenuContextual[] = [
    {
      etiqueta: "Archivar",
      icono: Archive,
      onClick: async () => {
        if (
          await confirmar({
            mensaje: `¿Archivar la noticia "${noticia.titulo || "(sin título)"}"?`,
            destructivo: true,
            textoConfirmar: "Archivar",
          })
        )
          onArchivar(noticia);
      },
      destructivo: true,
      deshabilitado: archivando,
    },
  ];

  if (noticia.enlace) {
    acciones.push({
      etiqueta: "Abrir enlace",
      icono: ExternalLink,
      onClick: () => window.open(noticia.enlace, "_blank"),
    });
  }

  return (
    <FilaConAcciones
      como="li"
      onPrimaria={() => onProponer(noticia)}
      acciones={acciones}
      kebab="nunca"
      realce
      className="rounded-lg border border-border/60 p-3"
    >
      <div className="flex flex-wrap items-center gap-1.5 pb-1">
        <Badge variant="outline">{noticia.plataforma_nombre || noticia.plataforma}</Badge>
        <Badge variant={nivel.variante}>{nivel.texto}</Badge>
        {noticia.es_cambio && (
          <Badge variant="aviso" title="Candidato a la ficha editorial">
            Cambio de algoritmo
          </Badge>
        )}
        {noticia.tipo === "oficial" && <Badge variant="info">Oficial</Badge>}
        {noticia.aplicada && (
          <Badge variant="ok" title="Ya propuesta a la Texto">
            En texto
          </Badge>
        )}
      </div>

      <p className="text-sm font-medium">
        {noticia.titulo || "(sin título)"}
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
      </div>
    </FilaConAcciones>
  );
}
