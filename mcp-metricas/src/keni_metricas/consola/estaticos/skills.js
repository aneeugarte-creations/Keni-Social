// Feature Skills (Generar copy) — JS vanilla minimo, solo fetch local.
// Sin librerias ni red externa. Reusa los helpers globales de consola.js
// (fijarEstado, postJSON, marcarCargando); no los redefine.
"use strict";

// Muestra la descripcion del tipo de contenido elegido (de su data-desc).
function actualizarDescSkill() {
  const sel = document.getElementById("skills-skill");
  const desc = document.getElementById("skills-desc");
  if (!sel || !desc) return;
  const opcion = sel.options[sel.selectedIndex];
  desc.textContent = opcion ? opcion.getAttribute("data-desc") || "" : "";
}

// Texto del ultimo borrador generado (para copiar/descargar en cliente).
let ultimoBorrador = "";

// Envia el formulario, genera el borrador por debajo y pinta el resultado.
// Durante la espera marca el boton Generar como "cargando" (spinner) con el
// helper compartido marcarCargando() de consola.js.
async function generarSkill(form) {
  const estado = document.getElementById("skills-estado");
  const boton = document.getElementById("skills-generar");
  const wrap = document.getElementById("skills-resultado-wrap");
  const salida = document.getElementById("skills-resultado");
  const copiaEstado = document.getElementById("skills-copia-estado");

  const skill = form.querySelector("[name=skill]").value;
  const marca = form.querySelector("[name=marca]").value;
  const texto = form.querySelector("[name=texto]").value;

  if (!skill || !marca) {
    fijarEstado(estado, "Elige un tipo de contenido y una marca.", "error");
    return;
  }
  if (!texto.trim()) {
    fijarEstado(estado, "Pega una nota o transcripción.", "error");
    return;
  }

  marcarCargando(boton, true);
  if (wrap) wrap.hidden = true;
  if (copiaEstado) fijarEstado(copiaEstado, "", "");
  fijarEstado(estado, "Generando el borrador... esto puede tardar un poco.", "");

  const { ok, datos } = await postJSON("/api/skills/ejecutar", {
    skill: skill,
    marca: marca,
    texto: texto,
  });

  marcarCargando(boton, false);
  if (ok) {
    fijarEstado(estado, "Listo. Revisa el borrador antes de usarlo.", "ok");
    ultimoBorrador = datos.resultado || "";
    if (salida) salida.textContent = ultimoBorrador;
    if (wrap) {
      wrap.hidden = false;
      wrap.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } else {
    fijarEstado(estado, datos.error || "No se pudo generar el borrador.", "error");
  }
}

// Copia el borrador al portapapeles. Degrada con gracia si clipboard no esta
// disponible (contexto no seguro o navegador viejo): selecciona el texto y avisa.
async function copiarBorrador() {
  const estado = document.getElementById("skills-copia-estado");
  const salida = document.getElementById("skills-resultado");
  if (!ultimoBorrador) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(ultimoBorrador);
      fijarEstado(estado, "Copiado al portapapeles.", "ok");
      return;
    } catch (e) {
      // cae al modo manual de abajo
    }
  }
  // Sin clipboard: selecciona el texto para que el usuario copie a mano.
  if (salida && window.getSelection) {
    const rango = document.createRange();
    rango.selectNodeContents(salida);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(rango);
  }
  fijarEstado(estado, "Tu navegador no permite copiar solo; selecciona y copia (Ctrl/Cmd+C).", "error");
}

// Descarga el borrador como archivo .md generado en cliente con un Blob.
function descargarBorrador() {
  const estado = document.getElementById("skills-copia-estado");
  if (!ultimoBorrador) return;
  try {
    const blob = new Blob([ultimoBorrador], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "borrador-keni.md";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    fijarEstado(estado, "Descargado (borrador-keni.md).", "ok");
  } catch (e) {
    fijarEstado(estado, "No se pudo descargar el borrador.", "error");
  }
}

document.addEventListener("DOMContentLoaded", function () {
  const sel = document.getElementById("skills-skill");
  if (sel) {
    sel.addEventListener("change", actualizarDescSkill);
    actualizarDescSkill();
  }
  const form = document.getElementById("form-skills");
  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      generarSkill(form);
    });
  }
  const btnCopiar = document.getElementById("skills-copiar");
  if (btnCopiar) btnCopiar.addEventListener("click", copiarBorrador);
  const btnDescargar = document.getElementById("skills-descargar");
  if (btnDescargar) btnDescargar.addEventListener("click", descargarBorrador);
});
