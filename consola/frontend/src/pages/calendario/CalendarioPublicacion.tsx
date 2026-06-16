import { PanelAjustes } from "@/pages/configuracion/SeccionFuncionalidad";

// Grupos del catálogo que gobiernan la publicación (global + por marca).
const GRUPOS_PIEZA = ["pieza", "publicacion_marca"] as const;
import { CalendarDays, Upload } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { useQuery } from "@tanstack/react-query";

import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";
import { SeccionColapsable } from "@/pages/configuracion/SeccionColapsable";
import { DialogoImportarCalendario } from "@/pages/piezas/DialogoImportarCalendario";
import { PanelPlan } from "@/pages/piezas/GestionPlan";
import { GestionPiezas } from "@/pages/piezas/GestionPiezas";
import { PanelLineasPlan } from "@/pages/piezas/PanelLineasPlan";

/**
 * Página "Programación" (`/operacion/programacion`): la rejilla mensual de piezas
 * programadas (`GestionPiezas` en modo calendario), por marca activa del workspace.
 * Antes era la pestaña "Programación" del hub Calendario; ahora es una página plana del
 * sidebar (su hermana es "Turnos"). Desde la cabecera se gestionan los HORARIOS de
 * publicación (las franjas/huecos que alimentan este calendario) y se importa un calendario
 * externo. Un enlace `?horarios=1` abre los horarios directamente (lo usa el aviso "sin
 * franjas" de la lista de contenido).
 */
export default function CalendarioPublicacion() {
  const { marcaActiva, nombreActiva } = useMarcaActiva();
  const [importarAbierto, setImportarAbierto] = React.useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  // Deep-link `?horarios=1` (lo usa el aviso «sin franjas» de la lista de contenido): abre el
  // panel de ajustes con la sección "Plan y horarios" ya desplegada. Se congela en el PRIMER
  // render (el panel y la sección capturan su estado inicial); el efecto de abajo limpia luego
  // el parámetro.
  const [horariosDeepLink] = React.useState(() => searchParams.get("horarios") === "1");

  // Catálogos para poblar el diálogo de importación (marcas).
  const catalogosQuery = useQuery({
    queryKey: ["contenido", "catalogos"],
    queryFn: ({ signal }) => api.contenido({}, signal),
  });
  const marcas = catalogosQuery.data?.catalogos?.marcas ?? [];

  // Si se llega con ?horarios=1, limpia el parámetro de la URL (el panel ya abrió desplegado en
  // "Plan y horarios" por `horariosDeepLink`, congelado en el primer render).
  React.useEffect(() => {
    if (searchParams.get("horarios") === "1") {
      const next = new URLSearchParams(searchParams);
      next.delete("horarios");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  return (
    <>
      <TituloPagina titulo="Programación" icono={CalendarDays} />
      <AccionesPagina>
        {/* Barra superior limpia: UN "⋮" con la ACCIÓN (importar) y la entrada «Ajustes»
            (plan y horarios + publicación real). */}
        <MenuAcciones
          ajustesTitulo="Ajustes de programación"
          ajustesAbiertoInicial={horariosDeepLink}
          ajustes={
            <>
              {/* Plan y horarios INLINE: el formulario vive en la capa base del panel (sección
                  colapsable), no escondido tras un botón que abre un diálogo. */}
              {marcaActiva && (
                <SeccionColapsable
                  titulo="Plan y horarios"
                  abiertaInicial={horariosDeepLink}
                >
                  <PanelPlan marca={marcaActiva} />
                </SeccionColapsable>
              )}
              {/* Ajustes CONTEXTUALES (admin): la publicación real (global y por marca) se
                  ajusta AQUÍ, donde se programa lo que sale (reparto: cada ajuste en su página). */}
              <PanelAjustes
                grupos={GRUPOS_PIEZA}
                titulo="Ajustes de publicación"
                acento="amber"
                descripcion="Habilita/deshabilita publicación automática en redes, con excepciones por marca."
              />
            </>
          }
        >
          <ItemMenu icono={Upload} onClick={() => setImportarAbierto(true)}>
            Importar calendario…
          </ItemMenu>
        </MenuAcciones>
      </AccionesPagina>

      {/* El pulso del plan diario por línea (generados · publicados / objetivo): vive aquí,
          junto a la parrilla que alimenta. Solo con marca activa y plan configurado. */}
      {marcaActiva && (
        <div className="mb-4">
          <PanelLineasPlan marca={marcaActiva} nombre={nombreActiva ?? marcaActiva} />
        </div>
      )}

      <GestionPiezas modo="calendario" />

      <DialogoImportarCalendario
        abierto={importarAbierto}
        onCerrar={() => setImportarAbierto(false)}
        marcas={marcas}
        onImportado={(creados) => {
          toast.success(
            creados === 1
              ? "1 contenido importado."
              : `${creados} contenidos importados.`,
          );
          void catalogosQuery.refetch();
        }}
      />
    </>
  );
}
