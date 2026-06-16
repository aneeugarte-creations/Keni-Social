// dataURL (`data:image/png;base64,…`) -> Blob/File, SIN `fetch`.
//
// La CSP del sitio es `connect-src 'self'`, que BLOQUEA `fetch('data:…')` (lanza "Failed to fetch").
// `img-src` sí permite `data:` (por eso una <img src=dataURL> se ve), pero subir esa foto convertida
// con `fetch` no funciona. Decodificar el base64 a mano lo evita. Robusto y testeable. Lo usan la
// subida de la foto de muestra (galería/editor) y el horneado de la descarga del editor.

/** dataURL -> Blob, sin `fetch`. */
export function dataUrlABlob(dataUrl: string): Blob {
  const coma = dataUrl.indexOf(",");
  const cabecera = dataUrl.slice(5, coma); // tras "data:"
  const datos = dataUrl.slice(coma + 1);
  const mime = cabecera.split(";")[0] || "image/png";
  const esBase64 = /;base64/i.test(cabecera);
  const binario = esBase64 ? atob(datos) : decodeURIComponent(datos);
  const bytes = new Uint8Array(binario.length);
  for (let i = 0; i < binario.length; i++) bytes[i] = binario.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

/** dataURL -> File (`<nombre>.<ext>` con la extensión deducida del mime), sin `fetch`. */
export function dataUrlAArchivo(dataUrl: string, nombre: string): File {
  const blob = dataUrlABlob(dataUrl);
  const ext = (blob.type.split("/")[1] || "png").replace("jpeg", "jpg");
  return new File([blob], `${nombre}.${ext}`, { type: blob.type || "image/png" });
}
