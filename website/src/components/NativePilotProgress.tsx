export default function NativePilotProgress(){
 const repo='https://github.com/stevenvo780/SpecOrganon';
 const evidence=repo+'/blob/main/goals/method-superiority-v1/evidence/neutral-native-pilot-dev7-final-01/';
 const previous=repo+'/blob/main/goals/method-superiority-v1/evidence/neutral-native-pilot-dev7-01/';
 const rows=[['01','N','RangeAudit','115/115'],['02','S','RangeAudit','115/115'],['03','N','LedgerFold','104/104'],['04','S','LedgerFold','104/104'],['05','N','TopoPlan','105/105'],['06','S','TopoPlan','105/105']];
 return <section aria-labelledby="piloto-dev7">
 <h5 id="piloto-dev7">Piloto público dev7 cerrado: seis gates fallidos</h5>
 <p><strong>Cierre original del 6 de octubre de 2026 a las 08:56:26 UTC: 6 cierres de 6 posiciones fijadas, 6 gates fallidos y 0/6 gates completos.</strong> N/S en tres tipos, sin reemplazos ni cambios de fuentes o presupuestos. El driver terminó exit0 porque produjo el informe terminal; ese exit0 no significa entregas completas. Esta página publica el cierre verificado, sin reabrir intentos.</p>
 <div style={{overflowX:'auto'}}><table><thead><tr><th>Posición</th><th>Método</th><th>Tarea</th><th>Gate</th><th>Comprobaciones públicas</th></tr></thead><tbody>{rows.map(([id,method,task,checks])=><tr key={id}><td>{id}</td><td>{method}</td><td>{task}</td><td>FAILED: exact canonical request exceeds budget</td><td>{checks}</td></tr>)}</tbody></table></div>
 <p><strong>648/648 comprobaciones públicas descriptivas aprobadas</strong>: RangeAudit115 por brazo, LedgerFold104 y TopoPlan105. La unidad sigue siendo seis intentos; no son 648 sujetos ni tamaño inferencial. <strong>Los seis carecen de auditoría D/G final y paquete común acreditado.</strong> common_complete y F externo siguen sin evidencia (null), sin imputar éxito. No demuestra competencia, superioridad ni ranking entre N y S: el fallo compartido de transporte impide esa interpretación.</p>
 <p>Los tiempos whole_attempt suman <strong>1830,455 segundos</strong>, una suma observada sin ratio comparativo ni costo monetario/tokens comparables. Los recibos distinguen <strong>19 lanzamientos nativos de roles: 13 autores y 6 revisores</strong>, más 3 mediciones propias. Los 22 contenedores de controlador quedaron exited, ninguno running, retenidos según protocolo; no se hizo cleanup ni reinicio para esta publicación.</p>
 <p>El <strong>corte parcial report-01 de 2/6 permanece inmutable e histórico</strong>. Sus 504 archivos originales sellados se enlazan con los 1080 nuevos de posiciones03–06 (22.311.295 bytes); el índice final fija los seis, outcomes, closures y hashes. El manifiesto final conserva 1087 entradas. Los fallos y RAW mantienen sus bytes; las comprobaciones públicas posteriores no retornaron al autor.</p>
 <p>El diagnóstico previo del primer pedido reconstruyó <strong>131968 bytes frente al límite 110000</strong>: historial89938 antes de escapar JSON externo, paquetes de rol30947 y capturas58708; archivos14924 y documentos5768 dentro de sus límites. Fue diagnóstico offline, no retry ni dispatch, sin cambiar fuentes/cuotas. <strong>No ampliar el presupuesto, sustituir o reparar estas posiciones.</strong> La deduplicación lossless posterior se publica como ingeniería parcial dev8, sin nuevo piloto ni admisión; no altera este cierre.</p>
 <p>Competencia de controles, integración T común, F independiente, freeze completo, calificación T propia y comparación reservada con réplica siguen pendientes. La meta permanece activa, cero sujetos reservados y sin superioridad demostrada. Wheel e imágenes locales; último wheel público dev5 y 94 descargas históricas intactas.</p>
 <div className="software-lab-downloads">
 <a className="text-link" href={repo+'/tree/main'}>Repositorio actual en main</a>
 <a className="text-link" href={evidence+'summary.json'}>Informe terminal de seis posiciones</a>
 <a className="text-link" href={evidence+'README.md'}>Cierre, fallos y límites</a>
 <a className="text-link" href={evidence+'closed-raw-index.json'}>Índice SHA final de originales</a>
 <a className="text-link" href={repo+'/tree/main/goals/method-superiority-v1/evidence/neutral-native-pilot-dev7-final-01/closed-raw'}>Originales sellados de posiciones03–06</a>
 <a className="text-link" href={evidence+'terminal-containers.json'}>Roles, mediciones y contenedores terminales</a>
 <a className="text-link" href={evidence+'SHA256SUMS'}>SHA-256 del archivo final</a>
 <a className="text-link" href={previous+'report-01.stdout'}>Corte parcial report-01 inmutable:2/6</a>
 <a className="text-link" href={previous+'first-request-diagnostic.json'}>Diagnóstico offline original de bytes</a>
 <a className="text-link" href={repo+'/blob/main/goals/method-superiority-v1/evidence/neutral-native-admission-01/pilot-plan.json'}>Plan original sin cambios</a>
 <a className="text-link" href={repo+'/blob/main/goals/method-superiority-v1/evidence/neutral-native-admission-01/admission-review.json'}>Admisión acotada a las seis posiciones</a>
 </div>
 </section>;
}
