import { PanelAjustes } from "@/pages/configuracion/SeccionFuncionalidad";

// Grupos del catálogo que gobiernan la publicación (global + por marca).
const GRUPOS_PIEZA = ["pieza", "publicacion_marca"] as const;
import { CalendarDays } from "lucide-react";
import { Navigate, useSearchParams } from "react-router-dom";

import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { MenuAcciones } from "@/components/layout/MenuAcciones";
import { GestionPiezas } from "@/pages/piezas/GestionPiezas";

/**
 * Pestaña "Programación" del hub Programa (`/operacion/programa/programacion`): la rejilla mensual
 * de piezas programadas (`GestionPiezas` en modo calendario), por marca activa del workspace. Su
 * hermana es "Plan" (las líneas: hashtag derivado y keywords del clasificador), donde se editan el
 * plan/cupo y los horarios. Aquí solo se ve el calendario. Un enlace `?horarios=1` (aviso "sin
 * franjas") salta directo a Plan.
 */
export default function CalendarioPublicacion() {
  const [searchParams] = useSearchParams();
  // Deep-link `?horarios=1`: el plan y los horarios viven ahora en la pestaña «Plan».
  if (searchParams.get("horarios") === "1") {
    return <Navigate to="/operacion/programa/plan" replace />;
  }

  return (
    <>
      <TituloPagina titulo="Programación" icono={CalendarDays} />
      <AccionesPagina>
        <MenuAcciones
          ajustesTitulo="Ajustes de programación"
          ajustes={
            <PanelAjustes
              grupos={GRUPOS_PIEZA}
              titulo="Ajustes de publicación"
              acento="amber"
              descripcion="Habilita/deshabilita publicación automática en redes, con excepciones por marca."
            />
          }
        />
      </AccionesPagina>

      <GestionPiezas modo="calendario" />
    </>
  );
}
