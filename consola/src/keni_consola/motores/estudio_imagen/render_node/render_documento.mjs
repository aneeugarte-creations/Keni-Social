#!/usr/bin/env node
// Renderizador determinista de un DOCUMENTO de capas (editor profesional, @napi-rs/canvas).
//
// Lo invoca el back/worker por subproceso desde Python (dominio/estudio_imagen.py), igual que
// `componer.mjs`, pero sobre un documento de capas arbitrarias en vez del spec de slots fijos.
// Protocolo:
//   - argv: `--salida <out.png>`
//   - stdin: `{documento, assets:{<objeto|media_id>: ruta_png}, fuentes?, bindings?, fuentes_extra?}`
//   - salida: escribe el PNG en `out.png` (rc 0). En error: stderr + rc≠0.
//
// El render real lo hace `dibujar.mjs::dibujarDocumento` (única fuente de verdad, compartida con
// el editor). Aquí solo se registran fuentes, se cargan las imágenes de las capas y se vuelca el PNG.

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

  const { w, h } = documento.formato;
  const canvas = createCanvas(w, h);
  const ctx = canvas.getContext("2d");

  dibujarDocumento(ctx, {
    documento,
    imgs,
    bindings: payload.bindings || {},
    familiaReal: (logica) => familiaReal(fuentes, logica),
    // Render del PÍXEL FINAL: `visible` es solo ayuda de edición; aquí se pintan TODAS las capas
    // (incluidas las de grupos ocultos). Solo la PREVIA del editor respeta `visible`.
    final: true,
  });

  writeFileSync(salida, canvas.toBuffer("image/png"));
  process.stdout.write(
    "DATOS " + JSON.stringify({ salida, tamano: `${w}x${h}`, capas: (documento.capas || []).length }) + "\n",
  );
  return 0;
}

main().then((c) => process.exit(c)).catch((e) => {
  process.stderr.write("Error de render: " + (e?.stack || e) + "\n");
  process.exit(1);
});
