import * as React from "react";

import { metaZona } from "@/lib/organigrama";
import { type UsuarioAdmin } from "@/types";

import { TarjetaMiembro } from "./TarjetaMiembro";

/**
 * Nodo recursivo del árbol vertical: una tarjeta-fila y, indentado debajo, el subárbol de
 * sus reportes directos. `zona` (marca) se hereda hacia abajo y colorea la rama (conector
 * y acento de la tarjeta), así cada área se distingue por color.
 */
export function NodoVertical({
  nodo,
  zona,
  hijos,
  idActual,
  onAbrir,
}: {
  nodo: UsuarioAdmin;
  zona: string;
  hijos: Map<string, UsuarioAdmin[]>;
  idActual: string | null;
  onAbrir: (id: string) => void;
}) {
  const reportes = hijos.get(nodo.id) ?? [];
  const meta = metaZona(zona);
  return (
    <li
      className="org-v-node"
      style={{ "--vline": meta.color } as React.CSSProperties}
    >
      <TarjetaMiembro
        usuario={nodo}
        zona={zona}
        esYoMismo={nodo.id === idActual}
        onAbrir={onAbrir}
      />
      {reportes.length > 0 && (
        <ul className="org-v-children">
          {reportes.map((r) => (
            <NodoVertical
              key={r.id}
              nodo={r}
              zona={zona}
              hijos={hijos}
              idActual={idActual}
              onAbrir={onAbrir}
            />
          ))}
        </ul>
      )}
    </li>
  );
}
