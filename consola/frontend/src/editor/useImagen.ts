// Carga un objeto de media (`/api/media/{objeto}`) como HTMLImageElement para pintarlo en Konva.
// Same-origin: la cookie de sesión viaja sola. `crossOrigin=anonymous` evita tintar el canvas si
// más adelante exportamos en cliente.

import { useEffect, useState } from "react";

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
