import { PanelAjustes } from "@/pages/configuracion/SeccionFuncionalidad";

// Grupos del catálogo que gobiernan la publicación (global + por marca).
const GRUPOS_PUBLICACION = ["publicacion", "publicacion_marca"] as const;
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
import { DialogoImportarCalendario } from "@/pages/publicaciones/DialogoImportarCalendario";
import { PanelCadencia } from "@/pages/publicaciones/GestionCadencia";
import { PanelPlan } from "@/pages/publicaciones/GestionPlan";
import { GestionPublicaciones } from "@/pages/publicaciones/GestionPublicaciones";
import { PanelLineasPlan } from "@/pages/publicaciones/PanelLineasPlan";

/**
 * Página "Programación" (`/operacion/programacion`): la rejilla mensual de publicaciones
 * programadas (`GestionPublicaciones` en modo calendario), por marca activa del workspace.
 * Antes era la pestaña "Programación" del hub Calendario; ahora es una página plana del
 * sidebar (su hermana es "Turnos"). Desde la cabecera se gestiona la CADENCIA por
 * red (cada cuántos minutos puede salir un post, el reparto que alimenta este calendario) y se
 * importa un calendario externo. Un enlace `?cadencia=1` abre la cadencia directamente (lo usa
 * el aviso "sin cadencia" de la lista de contenido).
 */
export default function CalendarioContenido() {
  const { marcaActiva, nombreActiva } = useMarcaActiva();
  const [importarAbierto, setImportarAbierto] = React.useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  // Deep-link `?cadencia=1` (lo usa el aviso «sin cadencia» de la lista de contenido): abre el
  // panel de ajustes con la sección Cadencia ya desplegada. Se congela en el PRIMER render (el
  // panel y la sección capturan su estado inicial); el efecto de abajo limpia luego el parámetro.
  const [cadenciaDeepLink] = React.useState(() => searchParams.get("cadencia") === "1");

  // Catálogos para poblar los diálogos de importación (marcas) y cadencia (marcas + redes).
  const catalogosQuery = useQuery({
    queryKey: ["contenido", "catalogos"],
    queryFn: ({ signal }) => api.contenido({}, signal),
  });
  const marcas = catalogosQuery.data?.catalogos?.marcas ?? [];
  const redes = catalogosQuery.data?.catalogos?.redes ?? [];

  // Si se llega con ?cadencia=1, limpia el parámetro de la URL (el panel ya abrió desplegado en
  // Cadencia por `cadenciaDeepLink`, congelado en el primer render).
  React.useEffect(() => {
    if (searchParams.get("cadencia") === "1") {
      const next = new URLSearchParams(searchParams);
      next.delete("cadencia");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  return (
    <>
      <TituloPagina titulo="Programación" icono={CalendarDays} />
      <AccionesPagina>
        {/* Barra superior limpia: UN "⋮" con la ACCIÓN (importar) y la entrada «Ajustes»
            (plan y horarios + cadencia + publicación real). */}
        <MenuAcciones
          ajustesTitulo="Ajustes de programación"
          ajustesAbiertoInicial={cadenciaDeepLink}
          ajustes={
            <>
              {/* Plan y cadencia INLINE: el formulario vive en la capa base del panel (sección
                  colapsable), no escondido tras un botón que abre un diálogo. */}
              {marcaActiva && (
                <SeccionColapsable
                  titulo="Plan y horarios"
                >
                  <PanelPlan marca={marcaActiva} />
                </SeccionColapsable>
              )}
              <SeccionColapsable
                titulo="Cadencia"
                descripcion="Intervalo mínimo entre posts por red."
                abiertaInicial={cadenciaDeepLink}
              >
                <PanelCadencia marcas={marcas} redes={redes} />
              </SeccionColapsable>
              {/* Ajustes CONTEXTUALES (admin): la publicación real (global y por marca) se
                  ajusta AQUÍ, donde se programa lo que sale (reparto: cada ajuste en su página). */}
              <PanelAjustes
                grupos={GRUPOS_PUBLICACION}
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

      <GestionPublicaciones modo="calendario" />

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
