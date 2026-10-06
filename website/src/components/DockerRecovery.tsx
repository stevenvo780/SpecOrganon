import engineering from '../software-engineering-05.json';
import cohort from '../native-cohort-02-observation-02.json';
const names: Record<string,string> = {rangeaudit:'RangeAudit',ledgerfold:'LedgerFold',topoplan:'TopoPlan'};
const statuses: Record<string,string> = {failed:'Fallido, cerrado',complete:'Entrega completa',in_progress:'En ejecución en esta foto',not_started:'Sin iniciar en esta foto'};
export default function DockerRecovery(){
 return <section aria-labelledby="avance-dev5">
  <h5 id="avance-dev5">Hito dev5: recuperar una creación Docker sin duplicarla</h5>
  <p>Ante una respuesta perdida de Docker, el transporte schema5 conserva el intento y un nonce antes de la única creación permitida. Sólo adopta el contenedor con nombre, etiqueta, imagen y fecha exactos, y prueba de que nunca arrancó. Guarda el identificador y el hash de la observación antes de iniciar; también verifica la evidencia histórica al leer un recibo cerrado. Una ejecución incierta no autoriza repetir la creación ni una llamada al modelo. No reanuda raíces schema4.</p>
  <p><strong>{engineering.host_targeted_tests} controles en el host y {engineering.installed_targeted_tests} en el wheel instalado</strong> pasaron, con 31 módulos coincidentes por SHA, CLI exit0 y 24 herramientas MCP por stdio real. La imagen verificada es local; no se afirma que esté publicada en un registry. La suite completa del host sigue sin estar aprobada.</p>
  <p><strong>Tres controles Docker reales con pérdida de respuesta inyectada</strong> comprobaron recuperación de un contenedor nunca iniciado, rechazo de uno ya ejecutado y reanudación tras interrumpir antes de guardar el identificador. Cada control creó un solo contenedor y el contador del programa quedó en 1. Corrieron sin red, con raíz de sólo lectura, sin perfiles ni nuevas llamadas a modelos. <strong>No reproducen el timeout natural de 15 segundos ni prueban fiabilidad nativa general.</strong></p>
  <p>Gemini rechazó el diseño inicial y Codex rechazó dos implementaciones; los errores, fuentes y correcciones permanecen archivados. La aceptación final de Codex es estática y declara tests_executed=false. Cada control Docker tiene un límite de 15 segundos; JobStore limita la admisión por 6000 segundos transcurridos, incluyendo preparación previa, y no garantiza un deadline estricto de extremo a extremo. La eficiencia debe usar el tiempo total de cada intento.</p>
  <h6>Cohorte dev4 02: observación histórica de 03:43:23</h6>
  <p>Foto del <time dateTime={cohort.at}>{new Date(cohort.at).toLocaleString('es-CO',{timeZone:'UTC'})} UTC</time>: <strong>{cohort.closed_attempts} intentos cerrados, {cohort.generation_complete} entregas completas, {cohort.planned_attempts} intentos fijados</strong>. LedgerFold pasó 104/104 comprobaciones públicas y TopoPlan 105/105, con nueve fases y recibos físicos verificados. Había cuatro fallos y cuatro intentos restantes. El observador comprobó las 45 fuentes congeladas y los cierres sin nuevas llamadas a modelos o tests; esta foto no es un monitor en vivo.</p>
  <div className="backup-table-wrap"><table><caption>Corte dev4 del 6 de octubre a las 03:43:23 UTC · sin resultados reservados</caption><thead><tr><th scope="col">Intento</th><th scope="col">Contrato</th><th scope="col">Estado</th></tr></thead><tbody>{cohort.rows.map(row=><tr key={row.attempt.id}><th scope="row">{row.attempt.id}</th><td>{names[row.attempt.task]}</td><td>{statuses[row.status]}</td></tr>)}</tbody></table></div>
  <p>Tres fallos fueron Docker control deadline exceeded. El cuarto agotó los dos autores de compare con paquetes de 6436 y 6150 bytes frente al límite de 6000. Se conservan los fallos sin reanudar ni sustituir esos intentos. <strong>El criterio de 9/10 ya es imposible en esta cohorte:</strong> incluso con éxito en los cuatro restantes, el máximo sería 6/10. Deben terminar los diez intentos originales antes de decidir cambios.</p>
  <p><strong>Dev5 todavía no tiene cohorte nativa.</strong> Su próxima prueba necesita congelar y registrar fuentes nuevas antes de generar, en otra ruta. El diseño de comparadores libre y SDD sólidos está publicado como propuesta pendiente de implementación y validación; no es una comparación ejecutada. La meta permanece activa: cero sujetos reservados, ninguna réplica y ninguna superioridad demostrada.</p>
  <div className="software-lab-downloads">
   <a className="text-link" href="/resultados/software/avance-dev5/ingenieria.json">Recibo de ingeniería dev5</a>
   <a className="text-link" href="/resultados/software/avance-dev5/specorganon-0.2.0rc3.dev5-py3-none-any.whl">Wheel final dev5</a>
   <a className="text-link" href="/resultados/software/avance-dev5/cohorte-dev4-observacion-02.json">Observación dev4 y recursos por intento</a>
   <a className="text-link" href="/resultados/software/avance-dev5/controles-docker-finales.json">Tres controles Docker y hashes</a>
   <a className="text-link" href="/resultados/software/avance-dev5/evidencia-dev5-con-fallos.zip">Fuentes, logs, revisiones y errores preservados</a>
   <a className="text-link" href="/resultados/software/avance-dev5/recuperacion-docker.md">Reproducción y límites</a>
   <a className="text-link" href="/resultados/software/avance-dev5/comparadores-solidos-diseno.md">Diseño pendiente de libre y SDD sólidos</a>
   <a className="text-link" href="/resultados/software/avance-dev5/descargas-sha256.json">SHA-256 de las nuevas descargas</a>
   <a className="text-link" href="https://github.com/stevenvo780/SpecOrganon/blob/main/examples/topoplan/PROVENANCE.md">Entrega TopoPlan dev4, sin reparación posterior</a>
   <a className="text-link" href="https://github.com/stevenvo780/SpecOrganon/tree/main">Código actual en main</a>
  </div>
 </section>;
}
