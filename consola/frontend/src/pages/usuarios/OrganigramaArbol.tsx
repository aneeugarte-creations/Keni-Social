import * as React from "react";

import "@/components/organigrama/org-tree.css";
import {
  hijosPorManager,
  indexarPorId,
  raices,
  ZONA_DIRECCION,
  zonaDe,
  zonasOrdenadas,
} from "@/lib/organigrama";
import { type MarcaDisponible, type UsuarioAdmin } from "@/types";

import { DialogoMiembro } from "./DialogoMiembro";
import { Leyenda } from "./Leyenda";
import { NodoVertical } from "./NodoVertical";
import { TarjetaMiembro } from "./TarjetaMiembro";

// --- Árbol vertical (indentado) ----------------------------------------------

export function OrganigramaArbol({
  usuarios,
  idActual,
  catalogoMarcas,
}: {
  usuarios: UsuarioAdmin[];
  idActual: string | null;
  catalogoMarcas: MarcaDisponible[];
}) {
  const porId = React.useMemo(() => indexarPorId(usuarios), [usuarios]);
  const hijos = React.useMemo(() => hijosPorManager(usuarios), [usuarios]);
  const cima = React.useMemo(() => raices(usuarios, porId), [usuarios, porId]);

  // Zonas presentes (para la leyenda): las marcas/transversal que tengan a alguien.
  const zonasPresentes = React.useMemo(() => {
    const set = new Set<string>();
    for (const u of usuarios) {
      const z = zonaDe(u, porId);
      if (z !== ZONA_DIRECCION) set.add(z);
    }
    return set;
  }, [usuarios, porId]);

  const [seleccionado, setSeleccionado] = React.useState<string | null>(null);
  const usuarioSel = seleccionado ? (porId.get(seleccionado) ?? null) : null;

  return (
    <div className="space-y-4">
      <Leyenda zonas={zonasPresentes} />

      <div className="org-v overflow-x-auto rounded-lg border bg-muted/20">
        <ul className="org-v-root">
          {cima.map((raiz) => {
            // Hijos del director ordenados por ÁREA (marca) para que cada zona quede
            // contigua; cada cabeza lleva su zona para colorear su rama.
            const areas = zonasOrdenadas(hijos.get(raiz.id) ?? []);
            return (
              <li key={raiz.id} className="org-v-node">
                <TarjetaMiembro
                  usuario={raiz}
                  zona={ZONA_DIRECCION}
                  esYoMismo={raiz.id === idActual}
                  onAbrir={setSeleccionado}
                />
                {areas.length > 0 && (
                  <ul className="org-v-children">
                    {areas.flatMap(({ zona, cabezas }) =>
                      cabezas.map((cabeza) => (
                        <NodoVertical
                          key={cabeza.id}
                          nodo={cabeza}
                          zona={zona}
                          hijos={hijos}
                          idActual={idActual}
                          onAbrir={setSeleccionado}
                        />
                      )),
                    )}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </div>

      <DialogoMiembro
        usuario={usuarioSel}
        usuarios={usuarios}
        porId={porId}
        hijos={hijos}
        idActual={idActual}
        catalogoMarcas={catalogoMarcas}
        onCerrar={() => setSeleccionado(null)}
      />
    </div>
  );
}
