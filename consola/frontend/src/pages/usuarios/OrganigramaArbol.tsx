import * as React from "react";

import {
  hijosPorManager,
  indexarPorId,
  raices,
  zonaDe,
  zonasOrdenadas,
} from "@/lib/organigrama";
import { type MarcaDisponible, type UsuarioAdmin } from "@/types";

import { DialogoMiembro } from "./DialogoMiembro";
import { TarjetaMiembro } from "./TarjetaMiembro";

// --- Lista plana (una persona por línea) -------------------------------------

interface Fila {
  usuario: UsuarioAdmin;
  /** Tiene personas a su cargo → marca de coordinación/dirección. */
  tieneReportes: boolean;
  /** Zona de la persona (deriva el color del avatar). */
  zona: string;
}

/**
 * Organigrama como lista plana: cada persona en su propia línea con nombre, cargo y marcas.
 * El orden replica la lógica del árbol (Dirección → cada área por marca → cabeza y sus
 * reportes en profundidad) para que cada área quede contigua, pero sin indentación. Al hacer
 * clic en una persona se abre el panel de edición. Quien tiene reportes lleva un icono.
 */
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

  // Aplana el árbol en una lista ordenada, conservando la agrupación por área (zona).
  const filas = React.useMemo<Fila[]>(() => {
    const out: Fila[] = [];
    const tiene = (u: UsuarioAdmin) => (hijos.get(u.id)?.length ?? 0) > 0;
    const visitar = (u: UsuarioAdmin) => {
      out.push({ usuario: u, tieneReportes: tiene(u), zona: zonaDe(u, porId) });
      for (const h of hijos.get(u.id) ?? []) visitar(h);
    };
    for (const raiz of cima) {
      out.push({ usuario: raiz, tieneReportes: tiene(raiz), zona: zonaDe(raiz, porId) });
      for (const { cabezas } of zonasOrdenadas(hijos.get(raiz.id) ?? [])) {
        for (const cabeza of cabezas) visitar(cabeza);
      }
    }
    return out;
  }, [cima, hijos, porId]);

  const [seleccionado, setSeleccionado] = React.useState<string | null>(null);
  const usuarioSel = seleccionado ? (porId.get(seleccionado) ?? null) : null;

  return (
    <div className="space-y-4">
      <ul className="flex flex-col gap-1.5">
        {filas.map(({ usuario, tieneReportes, zona }) => (
          <li key={usuario.id}>
            <TarjetaMiembro
              usuario={usuario}
              zona={zona}
              tieneReportes={tieneReportes}
              esYoMismo={usuario.id === idActual}
              onAbrir={setSeleccionado}
            />
          </li>
        ))}
      </ul>

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
