import { ImagePlus } from "lucide-react";
import * as React from "react";

import type { Skill } from "@/types";

import { esSkillDeImagen } from "./copy/dynamico";
import { FlujoGeneracion } from "./copy/FlujoGeneracion";

/** Clave de sessionStorage para reanudar la generación en curso al volver a la página. */
const CLAVE_GEN_IMAGENES = "keni:generacion-imagenes";

/**
 * Imágenes. Espacio dedicado al Estudio de imagen: usa el mismo motor que
 * "Generar copy" (`FlujoGeneracion`) pero filtrado a las skills de IMAGEN (las que
 * tienen un campo de archivo cuyo `media_tipos` incluye "image": estudio-imagen,
 * breaking-express, revisa-imagen). Sube una imagen, ajusta los campos y genera.
 */
export default function Imagenes() {
  // Solo las skills de imagen (su sitio es esta pestaña, no "Generar copy").
  const filtro = React.useCallback((skill: Skill) => esSkillDeImagen(skill), []);

  return (
    <FlujoGeneracion
      titulo="Imágenes"
      descripcion="Estudio de imagen: recorta, pon el breaking en marca o genera ilustraciones."
      claveGen={CLAVE_GEN_IMAGENES}
      filtroSkills={filtro}
      etiquetaSkill="Tipo de imagen"
      placeholderSkill="Elige una operación"
      vacioMensaje="No hay skills de imagen disponibles. Revisa el catálogo en Skills."
      iconoGenerar={ImagePlus}
      textoGenerar="Generar imagen"
    />
  );
}
