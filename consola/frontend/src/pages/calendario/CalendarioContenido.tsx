import { PanelAjustes } from "@/pages/configuracion/SeccionFuncionalidad";

// Grupos del catálogo que gobiernan la publicación (global + por marca).
const GRUPOS_PUBLICACION = new Set(["publicacion", "publicacion_marca"]);
import { CalendarDays, Gauge, Target, Upload } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { useQuery } from "@tanstack/react-query";

import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";
import { DialogoImportarCalendario } from "@/pages/publicaciones/DialogoImportarCalendario";
import { GestionCadencia } from "@/pages/publicaciones/GestionCadencia";
import { GestionPlan } from "@/pages/publicaciones/GestionPlan";
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
  const [cadenciaAbierto, setCadenciaAbierto] = React.useState(
    () => searchParams.get("cadencia") === "1",
  );
  const [planAbierto, setPlanAbierto] = React.useState(false);

  // Catálogos para poblar los diálogos de importación (marcas) y cadencia (marcas + redes).
  const catalogosQuery = useQuery({
    queryKey: ["contenido", "catalogos"],
    queryFn: ({ signal }) => api.contenido({}, signal),
  });
  const marcas = catalogosQuery.data?.catalogos?.marcas ?? [];
  const redes = catalogosQuery.data?.catalogos?.redes ?? [];

  // Si se llega con ?cadencia=1, abre el diálogo y limpia el parámetro de la URL.
  React.useEffect(() => {
    if (searchParams.get("cadencia") === "1") {
      setCadenciaAbierto(true);
      const next = new URLSearchParams(searchParams);
      next.delete("cadencia");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  return (
    <>
      <TituloPagina titulo="Programación" icono={CalendarDays} />
      <AccionesPagina>
        <MenuAcciones>
          {marcaActiva && (
            <ItemMenu icono={Target} onClick={() => setPlanAbierto(true)}>
              Plan y horarios
            </ItemMenu>
          )}
          <ItemMenu icono={Gauge} onClick={() => setCadenciaAbierto(true)}>
            Cadencia
          </ItemMenu>
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

      {marcaActiva && (
        <GestionPlan
          abierto={planAbierto}
          onCerrar={() => setPlanAbierto(false)}
          marca={marcaActiva}
          nombreMarca={nombreActiva ?? marcaActiva}
        />
      )}

      <GestionCadencia
        abierto={cadenciaAbierto}
        onCerrar={() => setCadenciaAbierto(false)}
        marcas={marcas}
        redes={redes}
      />

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

      {/* Ajustes CONTEXTUALES (admin): la publicación real (global y por marca) se
          ajusta AQUÍ, donde se programa lo que sale (reparto: cada ajuste en su página). */}
      <div className="mt-6">
        <PanelAjustes
          ids={GRUPOS_PUBLICACION}
          titulo="Ajustes de publicación"
          descripcion="El interruptor de publicación real y sus excepciones por marca. Peligroso: con esto encendido, lo aprobado SALE a las redes."
        />
      </div>
    </>
  );
}
