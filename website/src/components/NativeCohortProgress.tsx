import data from '../native-cohort-progress-01.json';

const names: Record<string,string> = {rangeaudit:'RangeAudit',ledgerfold:'LedgerFold',topoplan:'TopoPlan'};
const statuses: Record<string,string> = {failed:'Fallido, cerrado',in_progress:'En ejecución',not_started:'Sin iniciar en esta foto'};
const base='https://github.com/stevenvo780/SpecOrganon/blob/main/';

export default function NativeCohortProgress(){
  const first=data.rows[0];
  return <section aria-labelledby="cohorte-nativa">
    <h5 id="cohorte-nativa">Cohorte nativa: diez intentos fijados, evaluación en curso</h5>
    <p>Después de la entrega anterior se registraron cuatro intentos de RangeAudit, tres de LedgerFold y tres de TopoPlan. Todos usan el mismo candidato y sus límites originales, con Codex como autor, Gemini como revisor y comprobaciones públicas independientes cuando exista entrega. El caso anterior de <strong>115/115 queda fuera del denominador</strong>.</p>
    <p>Foto del <time dateTime={data.at}>{new Date(data.at).toLocaleString('es-CO',{timeZone:'UTC'})} UTC</time>: <strong>{data.closed_attempts} intento cerrado, {data.generation_complete} generaciones completas, {data.planned_attempts} intentos fijados</strong>. LedgerFold seguía en ejecución. La foto puede quedar desactualizada; los intentos restantes no se cuentan como resultados cerrados.</p>
    <div className="backup-table-wrap"><table>
      <caption>Estado observado de la cohorte de desarrollo · sin evaluación reservada</caption>
      <thead><tr><th scope="col">Intento</th><th scope="col">Contrato</th><th scope="col">Estado</th><th scope="col">Fases aceptadas</th></tr></thead>
      <tbody>{data.rows.map(row=><tr key={row.attempt.id}><th scope="row">{row.attempt.id}</th><td>{names[row.attempt.task]}</td><td>{statuses[row.status]}</td><td>{row.accepted_phases ? `${row.accepted_phases.length}/9` : 'Sin cierre observado'}</td></tr>)}</tbody>
    </table></div>
    <p>El primer RangeAudit cerró con <code style={{overflowWrap:'anywhere'}}>{first.reason}</code>. Sus doce trabajos terminaron con código cero, pero el contenido excedió la admisión de recursos de <code>compare</code>; eso impidió completar la generación. No hubo programa final ni ejecución del comprobador público. Se conservaron el fallo y los sellos, sin sustituir el intento.</p>
    <p>Ese intento sumó {Math.round(first.job_seconds_sum ?? 0)} segundos de trabajos y {Math.round(first.wall_seconds ?? 0)} segundos transcurridos. El coste monetario y la equivalencia de tokens siguen desconocidos. La infraestructura pasó 158 pruebas y dos controles Docker con productos sintéticos inválidos; son controles del instrumento, separados de los resultados nativos.</p>
    <p>La meta permanece activa. Esta cohorte de desarrollo todavía no permite declarar fiabilidad y no compara con libre o SDD. La comparación reservada y la réplica independiente siguen pendientes.</p>
    <div className="software-lab-downloads">
      <a className="text-link" href="/resultados/software/cohorte-nativa-01/progress-snapshot.json">Foto fechada y límites</a>
      <a className="text-link" href="/resultados/software/cohorte-nativa-01/attempt-01-outcome.json">Primer fallo y recursos</a>
      <a className="text-link" href="/resultados/software/cohorte-nativa-01/attempt-01-outcome-closure.json">Sello del primer intento</a>
      <a className="text-link" href="/resultados/software/cohorte-nativa-01/descargas-sha256.json">Hashes de estas fuentes</a>
      <a className="text-link" href={base+'goals/method-superiority-v1/development/NATIVE_COHORT.md'}>Protocolo en main</a>
      <a className="text-link" href={base+'goals/method-superiority-v1/development/registration-native-cohort-01.json'}>Registro previo en main</a>
      <a className="text-link" href={base+'scripts/native_reliability.py'}>Driver en main</a>
    </div>
  </section>;
}
