/**
 * Estrategia de marcas: la superficie editorial POR MARCA de la Texto. Reúne
 *   - LÍNEAS de contenido (etiquetas clase `vertical`) y ORÍGENES (clase `origen` =
 *     interno / externo), cada una con sus `keywords` (CSV para auto-clasificar);
 *   - el catálogo de ETIQUETAS editoriales transversales (campaña / tipo) y los
 *     GRUPOS de HASHTAGS por marca, accesibles desde la cabecera.
 *
 * Es CRUD sobre `/api/etiquetas` (acotado por clase) y `/api/hashtags`. El filtro
 * por marca lo manda SIEMPRE el switch global de la barra superior
 * (`useMarcaActiva`): no hay selector de marca propio. Aquí el equipo afina la
 * estrategia editorial de cada marca.
 *
 * Este fichero es solo el CONTENEDOR fino: los paneles y diálogos viven en
 * `./gestion-lineas/`.
 */
import { useQuery } from "@tanstack/react-query";
import { Hash, Tag } from "lucide-react";
import * as React from "react";

import { AccionesPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { api } from "@/lib/api";
import { GestionHashtags } from "@/pages/piezas/GestionHashtags";

import { DialogoEtiquetas } from "./gestion-lineas/DialogoEtiquetas";
import { PanelClase } from "./gestion-lineas/PanelClase";

export function GestionLineas() {
  const [etiquetasAbierto, setEtiquetasAbierto] = React.useState(false);
  const [hashtagsAbierto, setHashtagsAbierto] = React.useState(false);

  // Marcas para poblar los diálogos de etiquetas y hashtags (los paneles de
  // líneas/orígenes traen las suyas desde /api/etiquetas).
  const catalogosQuery = useQuery({
    queryKey: ["contenido", "catalogos"],
    queryFn: ({ signal }) => api.contenido({}, signal),
  });
  const marcas = catalogosQuery.data?.catalogos?.marcas ?? [];

  return (
    <>
      <AccionesPagina>
        <MenuAcciones>
          <ItemMenu icono={Tag} onClick={() => setEtiquetasAbierto(true)}>
            Etiquetas
          </ItemMenu>
          <ItemMenu icono={Hash} onClick={() => setHashtagsAbierto(true)}>
            Hashtags
          </ItemMenu>
        </MenuAcciones>
      </AccionesPagina>

      <div className="grid gap-6 lg:grid-cols-2">
        <PanelClase clase="vertical" />
        <PanelClase clase="origen" />
      </div>

      <DialogoEtiquetas
        abierto={etiquetasAbierto}
        onCerrar={() => setEtiquetasAbierto(false)}
        marcas={marcas}
      />
      <GestionHashtags
        abierto={hashtagsAbierto}
        onCerrar={() => setHashtagsAbierto(false)}
        marcas={marcas}
      />
    </>
  );
}
