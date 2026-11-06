/**
 * Ordo – Reloj de envíos (Apps Script de la planilla «Ordo – Panel de control»).
 *
 * GitHub lanza sus tareas programadas con horas de retraso. Este script revisa cada 5 minutos
 * si se acerca un envío y le ordena a GitHub ejecutar en ese momento (las órdenes manuales
 * arrancan en segundos). El sistema en GitHub espera hasta la hora exacta y no repite envíos.
 *
 * Instalación (una sola vez):
 *   1. Extensiones → Apps Script → pegar este código → Guardar.
 *   2. Configuración del proyecto (engranaje) → Propiedades de la secuencia de comandos →
 *      agregar  GITHUB_TOKEN  =  (la clave de GitHub).
 *   3. Elegir la función «instalar» → Ejecutar → autorizar con tu cuenta.
 *   4. Elegir la función «probarConexion» → Ejecutar. Debe decir «Conexión correcta».
 */

const REPO = 'lucasfelixjhs/ordo-telegram';
const WORKFLOW = 'publicar.yml';
const ZONA = 'America/Argentina/Buenos_Aires';

// Horarios de envío (hora local) y modo del sistema.
const HORARIOS = [
  { hora: '00:10', modo: 'publicar' },   // mensaje del día (+ Misa votiva)
  { hora: '12:00', modo: 'adelanto' },   // adelanto en el canal de control
  { hora: '18:00', modo: 'publicar' },   // I Vísperas (si corresponde)
];
const ANTES_MIN = 15;    // se ordena la ejecución hasta 15 min antes (el sistema espera la hora exacta)
const DESPUES_MIN = 90;  // si algo falló, se reintenta hasta 90 min después

function revisar() {
  const ahora = new Date();
  const props = PropertiesService.getScriptProperties();
  for (const h of HORARIOS) {
    for (const delta of [0, 1]) {               // el envío de las 00:10 se pide a las 23:55 del día anterior
      const dia = new Date(ahora.getTime() + delta * 86400000);
      const fecha = Utilities.formatDate(dia, ZONA, 'yyyy-MM-dd');
      const objetivo = parseFecha_(fecha, h.hora);
      const min = (objetivo.getTime() - ahora.getTime()) / 60000;
      const clave = 'disparo_' + fecha + '_' + h.hora;
      if (min <= ANTES_MIN && min >= -DESPUES_MIN && !props.getProperty(clave)) {
        const ok = disparar_(h.modo);
        if (ok) props.setProperty(clave, new Date().toISOString());
      }
    }
  }
  limpiar_(props);
}

function disparar_(modo) {
  const token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) throw new Error('Falta la propiedad GITHUB_TOKEN');
  const r = UrlFetchApp.fetch(
    'https://api.github.com/repos/' + REPO + '/actions/workflows/' + WORKFLOW + '/dispatches', {
      method: 'post',
      contentType: 'application/json',
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' },
      payload: JSON.stringify({ ref: 'main', inputs: { modo: modo } }),
      muteHttpExceptions: true,
    });
  const ok = r.getResponseCode() === 204;
  console.log((ok ? 'Ejecución pedida: ' : 'ERROR ' + r.getResponseCode() + ': ') + modo + ' ' + r.getContentText());
  return ok;
}

function parseFecha_(fecha, hora) {
  // Interpreta "AAAA-MM-DD HH:MM" en la zona horaria del canal.
  const iso = Utilities.formatDate(new Date(fecha + 'T12:00:00Z'), ZONA, "Z"); // p. ej. -0300
  return new Date(fecha + 'T' + hora + ':00' + iso.slice(0, 3) + ':' + iso.slice(3));
}

function limpiar_(props) {
  const limite = Date.now() - 3 * 86400000;
  const todo = props.getProperties();
  for (const k in todo) {
    if (k.startsWith('disparo_') && new Date(todo[k]).getTime() < limite) props.deleteProperty(k);
  }
}

/** Ejecutar una vez: crea el reloj que revisa cada 5 minutos. */
function instalar() {
  for (const t of ScriptApp.getProjectTriggers()) {
    if (t.getHandlerFunction() === 'revisar') ScriptApp.deleteTrigger(t);
  }
  ScriptApp.newTrigger('revisar').timeBased().everyMinutes(5).create();
  console.log('Reloj instalado: revisa cada 5 minutos.');
}

/** Comprueba que la clave de GitHub funciona (no publica nada). */
function probarConexion() {
  const token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) throw new Error('Falta la propiedad GITHUB_TOKEN');
  const r = UrlFetchApp.fetch('https://api.github.com/repos/' + REPO + '/actions/workflows/' + WORKFLOW, {
    headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' },
    muteHttpExceptions: true,
  });
  console.log(r.getResponseCode() === 200 ? 'Conexión correcta con GitHub.' :
              'ERROR ' + r.getResponseCode() + ': ' + r.getContentText());
}

/** Publica ya lo que esté pendiente (por si hiciera falta forzar un envío). */
function publicarAhora() {
  disparar_('publicar');
}
