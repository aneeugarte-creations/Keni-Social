import { ImagePlus, Sparkles } from "lucide-react";
import * as React from "react";
import { useLocation } from "react-router-dom";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Skill } from "@/types";

import { esSkillDeImagen } from "./copy/dynamico";
import { FlujoGeneracion } from "./copy/FlujoGeneracion";

/** Modo de la pestaña actual: copy editorial (texto) o imágenes. */
type Modo = "copy" | "imagenes";

const CLAVE_GEN_COPY = "keni:generacion-copy";
const CLAVE_GEN_IMAGENES = "keni:generacion-imagenes";

/** Persiste el último modo elegido por el usuario para reabrir la página ahí. */
const CLAVE_MODO = "keni:generacion-modo";

function leerModoInicial(): Modo {
  if (typeof window === "undefined") return "copy";
  const v = window.sessionStorage.getItem(CLAVE_MODO);
  return v === "imagenes" ? "imagenes" : "copy";
}

/**
 * Generación. Página única que reemplaza las antiguas "Generar copy" e
 * "Imágenes": mismo motor `FlujoGeneracion`, con un toggle superior que cambia
 * el filtro de skills (texto vs imagen). Cada modo conserva su propio estado
 * en sessionStorage para que se pueda saltar entre pestañas sin perder el
 * borrador en curso.
 */
export default function Generacion() {
  const location = useLocation();

  // Estado inicial: 1) lo que pida el call-site vía router state, 2) último
  // modo persistido, 3) "copy" por defecto. No tocamos `location.state` para
  // no pisar otros prefill (p.ej. el `texto` que llega desde Fuentes lo lee
  // FlujoGeneracion).
  const modoSolicitado =
    (location.state as { modo?: Modo } | null | undefined)?.modo;
  const [modo, setModo] = React.useState<Modo>(
    modoSolicitado === "imagenes" || modoSolicitado === "copy"
      ? modoSolicitado
      : leerModoInicial(),
  );

  // Persistimos el modo elegido para conservar el contexto entre visitas.
  React.useEffect(() => {
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(CLAVE_MODO, modo);
    }
  }, [modo]);

  const filtroCopy = React.useCallback((skill: Skill) => !esSkillDeImagen(skill), []);
  const filtroImagen = React.useCallback((skill: Skill) => esSkillDeImagen(skill), []);

  // Barra de pestañas superior. Va sobre el PageHeader del FlujoGeneracion;
  // queda como subnavegación coherente con otras páginas (Publicaciones, etc.).
  const tabs = (
    <Tabs value={modo} onValueChange={(v) => setModo(v as Modo)} className="mb-4">
      <TabsList>
        <TabsTrigger value="copy" className="gap-1.5">
          <Sparkles className="h-4 w-4" />
          Copy
        </TabsTrigger>
        <TabsTrigger value="imagenes" className="gap-1.5">
          <ImagePlus className="h-4 w-4" />
          Imágenes
        </TabsTrigger>
      </TabsList>
    </Tabs>
  );

  // Forzamos remount al cambiar de modo (key distinta) para que cada flujo
  // arranque limpio y lea su propio sessionStorage; así no se contamina entre
  // copy e imágenes.
  return (
    <>
      {tabs}
      {modo === "copy" ? (
        <FlujoGeneracion
          key="copy"
          titulo="Generar copy"
          descripcion="Crea borradores de publicaciones con las skills editoriales para cada marca."
          claveGen={CLAVE_GEN_COPY}
          filtroSkills={filtroCopy}
          vacioMensaje="No hay skills editoriales disponibles. Revisa el catálogo en Skills."
        />
      ) : (
        <FlujoGeneracion
          key="imagenes"
          titulo="Imágenes"
          descripcion="Estudio de imagen: recorta, pon el breaking en marca o genera ilustraciones."
          claveGen={CLAVE_GEN_IMAGENES}
          filtroSkills={filtroImagen}
          etiquetaSkill="Tipo de imagen"
          placeholderSkill="Elige una operación"
          vacioMensaje="No hay skills de imagen disponibles. Revisa el catálogo en Skills."
          iconoGenerar={ImagePlus}
          textoGenerar="Generar imagen"
        />
      )}
    </>
  );
}
