// Carga un objeto de media (`/api/media/{objeto}`) como HTMLImageElement para pintarlo en Konva.
// Same-origin: la cookie de sesión viaja sola. `crossOrigin=anonymous` evita tintar el canvas si
// más adelante exportamos en cliente.

import { useEffect, useState } from "react";

// Dimensiones NATURALES (px) de una imagen accesible por URL, sin insertarla en el documento.
// Tolerante: devuelve `null` si el navegador no puede decodificarla. Se usa al insertar una imagen
// suelta para que la capa adopte el aspect-ratio real de la foto (caja == foto, estilo Canva).
export function leerDimensionesUrl(url: string): Promise<{ w: number; h: number } | null> {
  return new Promise((resolve) => {
    const img = new window.Image();
    img.onload = () => resolve({ w: img.naturalWidth, h: img.naturalHeight });
    img.onerror = () => resolve(null);
    img.src = url;
  });
}

export function useImagen(objeto: string | undefined | null): HTMLImageElement | null {
  const [img, setImg] = useState<HTMLImageElement | null>(null);

  useEffect(() => {
    if (!objeto) {
      setImg(null);
      return;
    }
    let vivo = true;
    const el = new window.Image();
    el.crossOrigin = "anonymous";
    el.onload = () => {
      if (vivo) setImg(el);
    };
    el.onerror = () => {
      if (vivo) setImg(null);
    };
    el.src = `/api/media/${objeto}`;
    return () => {
      vivo = false;
    };
  }, [objeto]);

  return img;
}
