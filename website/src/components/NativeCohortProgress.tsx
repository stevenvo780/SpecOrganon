import data from '../native-cohort-terminal-01.json';
const names: Record<string,string> = {rangeaudit:'RangeAudit',ledgerfold:'LedgerFold',topoplan:'TopoPlan'};
const statuses: Record<string,string> = {failed:'Fallido, cerrado',complete:'Entrega completa'};
const base='https://github.com/stevenvo780/SpecOrganon/blob/main/';
export default function NativeCohortProgress(){
 return <section aria-labelledby="cohorte-nativa">
  <h5 id="cohorte-nativa">Cohorte dev2 cerrada: tres entregas de diez intentos</h5>
  <p>Se completaron los diez intentos fijados: cuatro RangeAudit, tres LedgerFold y tres TopoPlan, con Codex como autor y Gemini como revisor. Se mantuvieron el código dev2 congelado y las cuotas originales, sin reemplazos. El caso anterior de <strong>115/115 queda fuera del denominador</strong>.</p>
  <p>Cierre verificado del <time dateTime={data.at}>{new Date(data.at).toLocaleString('es-CO',{timeZone:'UTC'})} UTC</time>: <strong>{data.closed_attempts} intentos cerrados, {data.generation_complete} entregas completas, {data.planned_attempts} intentos fijados</strong>. Siete fallos y tres entregas de nueve fases: RangeAudit en los intentos 04 y 10, con 115/115 comprobaciones públicas cada uno; LedgerFold en el 08, con 104/104.</p>
  <div className="backup-table-wrap"><table><caption>Resultados terminales de desarrollo · sin evaluación reservada</caption><thead><tr><th scope="col">Intento</th><th scope="col">Contrato</th><th scope="col">Estado</th><th scope="col">Comprobaciones públicas</th><th scope="col">Motivo de cierre fallido</th></tr></thead>
   <tbody>{data.rows.map(row=><tr key={row.attempt.id}><th scope="row">{row.attempt.id}</th><td>{names[row.attempt.task]}</td><td>{statuses[row.status]}</td><td>{row.public_report ? `${row.public_report.passed}/${row.public_report.cases}` : 'Sin entrega completa'}</td><td>{row.reason ?? 'Entrega y controles completos'}</td></tr>)}</tbody></table></div>
  <p><strong>El criterio de fiabilidad del 90% se incumplió: 3/10, un 30%.</strong> El intervalo Wilson del 95% es descriptivo, aproximadamente 10,8–60,3%; no prueba superioridad. Se conservan fallos de admisión, formato y transporte, streams, cierres y hashes. El reanálisis offline de un fallo de transporte no lo transforma en éxito.</p>
  <p>La meta permanece activa. No hay comparación reservada con libre o SDD ni réplica independiente. El coste monetario y la equivalencia de tokens siguen desconocidos; la superioridad no está demostrada.</p>
  <div className="software-lab-downloads">
   <a className="text-link" href="/resultados/software/avance-dev4/cohorte-dev2-terminal.json">Resumen terminal: diez cierres</a>
   <a className="text-link" href="/resultados/software/avance-dev4/cohorte-dev2-evidencia.zip">Evidencia completa y manifiesto de hashes</a>
   <a className="text-link" href="/resultados/software/avance-dev4/ledgerfold-entrega-08.zip">Entrega LedgerFold 08, sin reparación posterior</a>
   <a className="text-link" href="/resultados/software/cohorte-nativa-02/progress-snapshot.json">Snapshot 02 histórico, intacto</a>
   <a className="text-link" href="/resultados/software/cohorte-nativa-01/progress-snapshot.json">Snapshot 01 histórico, intacto</a>
   <a className="text-link" href={base+'goals/method-superiority-v1/development/NATIVE_COHORT.md'}>Protocolo en main</a>
   <a className="text-link" href={base+'goals/method-superiority-v1/development/registration-native-cohort-01.json'}>Registro original en main</a>
  </div>
 </section>;
}
