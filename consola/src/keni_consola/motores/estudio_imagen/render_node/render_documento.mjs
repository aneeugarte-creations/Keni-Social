#!/usr/bin/env node
// Renderizador determinista de un DOCUMENTO de capas (editor profesional, @napi-rs/canvas).
//
// Lo invoca el back/worker por subproceso desde Python (dominio/estudio_imagen.py), igual que
// `componer.mjs`, pero sobre un documento de capas arbitrarias en vez del spec de slots fijos.
// Protocolo:
//   - argv: `--salida <out.png>`
//   - stdin: `{documento, assets:{<objeto|media_id>: ruta_png}, fuentes?, bindings?, fuentes_extra?,
//             opciones?:{formato:"png"|"jpg", calidad:1-100, escala:0.25-4}}`
//   - salida: escribe el archivo en `out` (rc 0; PNG por defecto, JPEG si `opciones.formato==="jpg"`).
//             En error: stderr + rc≠0.
//
// El render real lo hace `dibujar.mjs::dibujarDocumento` (única fuente de verdad, compartida con
// el editor). Aquí solo se registran fuentes, se cargan las imágenes de las capas, se aplica la
// ESCALA y el ENCODING (png/jpg) del export, y se vuelca el archivo. La escala se aplica agrandando
// el canvas y escalando el contexto ANTES de delegar en `dibujarDocumento`: el motor sigue pintando
// en coordenadas de DOCUMENTO sin enterarse (no se toca `dibujar.mjs`).

import { createCanvas, loadImage, GlobalFonts } from "@napi-rs/canvas";
import { writeFileSync } from "node:fs";
import process from "node:process";

import { dibujarDocumento } from "./dibujar.mjs";
import { registrarFuentes, familiaReal } from "./fuentes.mjs";

function arg(nombre) {
  const i = process.argv.indexOf(nombre);
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : null;
}

async function leerStdin() {
  const trozos = [];
  for await (const t of process.stdin) trozos.push(t);
  return Buffer.concat(trozos).toString("utf-8");
}

async function cargar(ruta) {
  if (!ruta) return null;
  try { return await loadImage(ruta); } catch { return null; }
}

async function main() {
  const salida = arg("--salida");
  if (!salida) { process.stderr.write("Falta --salida\n"); return 2; }

  let payload;
  try {
    payload = JSON.parse(await leerStdin());
  } catch (e) {
    process.stderr.write("Payload JSON inválido: " + e.message + "\n");
    return 2;
  }

  const documento = payload.documento;
  if (!documento || !documento.formato) {
    process.stderr.write("Falta 'documento' o su 'formato' en el payload\n");
    return 2;
  }
  const fuentes = payload.fuentes || documento.fuentes || {};

  registrarFuentes();
  // Tipografías propias de la marca: {familia: ruta} (frente D). Se registran tras el catálogo.
  for (const [familia, ruta] of Object.entries(payload.fuentes_extra || {})) {
    try { GlobalFonts.registerFromPath(ruta, familia); } catch { /* fuente ilegible: se ignora */ }
  }

  // Carga cada imagen referenciada por las capas (mapa objeto|media_id -> ruta_png).
  const imgs = {};
  for (const [clave, ruta] of Object.entries(payload.assets || {})) {
    imgs[clave] = await cargar(ruta);
  }

  // Opciones de EXPORT (formato/calidad/escala). La capa Python ya las valida y normaliza; aquí
  // las re-acotamos por robustez (el wrapper puede invocarse fuera de ese camino).
  const opciones = payload.opciones || {};
  let escala = Number(opciones.escala);
  if (!Number.isFinite(escala) || escala <= 0) escala = 1;
  escala = Math.min(4, Math.max(0.25, escala));
  const formato = String(opciones.formato || "png").toLowerCase() === "jpg"
    || String(opciones.formato || "").toLowerCase() === "jpeg"
    ? "jpg"
    : "png";

  const { w, h } = documento.formato;
  // Canvas en píxeles FINALES (w*escala × h*escala); escalamos el contexto para que el motor pinte
  // en coordenadas de documento (0..w, 0..h) sin saber nada de la escala.
  const canvas = createCanvas(Math.round(w * escala), Math.round(h * escala));
  const ctx = canvas.getContext("2d");
  if (escala !== 1) ctx.scale(escala, escala);

  dibujarDocumento(ctx, {
    documento,
    imgs,
    bindings: payload.bindings || {},
    familiaReal: (logica) => familiaReal(fuentes, logica),
    // Render del PÍXEL FINAL: `visible` es solo ayuda de edición; aquí se pintan TODAS las capas
    // (incluidas las de grupos ocultos). Solo la PREVIA del editor respeta `visible`.
    final: true,
  });

  let buffer;
  if (formato === "jpg") {
    let calidad = Number(opciones.calidad);
    if (!Number.isFinite(calidad)) calidad = 90;
    calidad = Math.min(100, Math.max(1, Math.round(calidad)));
    buffer = canvas.toBuffer("image/jpeg", calidad);
  } else {
    buffer = canvas.toBuffer("image/png");
  }
  writeFileSync(salida, buffer);
  process.stdout.write(
    "DATOS " + JSON.stringify({
      salida,
      formato,
      tamano: `${Math.round(w * escala)}x${Math.round(h * escala)}`,
      capas: (documento.capas || []).length,
    }) + "\n",
  );
  return 0;
}

main().then((c) => process.exit(c)).catch((e) => {
  process.stderr.write("Error de render: " + (e?.stack || e) + "\n");
  process.exit(1);
});
