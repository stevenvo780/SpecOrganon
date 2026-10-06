import data from '../native-cohort-progress-02.json';

const names: Record<string,string> = {rangeaudit:'RangeAudit',ledgerfold:'LedgerFold',topoplan:'TopoPlan'};
const statuses: Record<string,string> = {failed:'Fallido, cerrado',complete:'Entrega completa',in_progress:'En ejecución',not_started:'Sin iniciar en esta foto'};
const base='https://github.com/stevenvo780/SpecOrganon/blob/main/';

export default function NativeCohortProgress(){
  return <section aria-labelledby="cohorte-nativa">
    <h5 id="cohorte-nativa">Cohorte nativa: diez intentos fijados, evaluación en curso</h5>
    <p>Después de la entrega anterior se registraron cuatro intentos de RangeAudit, tres de LedgerFold y tres de TopoPlan. La cohorte sigue en dev2 con sus fuentes congeladas y límites originales, con Codex como autor y Gemini como revisor. El caso anterior de <strong>115/115 queda fuera del denominador</strong>; la entrega del intento 04 sí pertenece a esta cohorte.</p>
    <p>Foto del <time dateTime={data.at}>{new Date(data.at).toLocaleString('es-CO',{timeZone:'UTC'})} UTC</time>: <strong>{data.closed_attempts} intentos cerrados, {data.generation_complete} generación completa, {data.planned_attempts} intentos fijados</strong>. Son cuatro fallos y una entrega RangeAudit de nueve fases con 115/115 comprobaciones públicas; TopoPlan seguía en ejecución en el intento 06. La foto puede quedar desactualizada; los intentos restantes no se cuentan como resultados cerrados.</p>
    <div className="backup-table-wrap"><table>
      <caption>Estado observado de la cohorte de desarrollo · sin evaluación reservada</caption>
      <thead><tr><th scope="col">Intento</th><th scope="col">Contrato</th><th scope="col">Estado</th><th scope="col">Fases aceptadas</th></tr></thead>
      <tbody>{data.rows.map(row=><tr key={row.attempt.id}><th scope="row">{row.attempt.id}</th><td>{names[row.attempt.task]}</td><td>{statuses[row.status]}</td><td>{row.accepted_phases ? `${row.accepted_phases.length}/9` : 'Sin cierre observado'}</td></tr>)}</tbody>
    </table></div>
    <p>Los intentos 01 y 05 excedieron la admisión de recursos en <code>compare</code>. El 02 cerró por el adaptador de transporte; su reanálisis offline no cambia ese fallo. El 03 no entregó el JSON exacto exigido para la aprobación. Se conservan los cinco resultados y sus sellos, sin sustituir ninguno.</p>
    <p><strong>El criterio de fiabilidad del 90% ya es imposible en esta cohorte:</strong> aunque los cinco intentos pendientes terminasen correctamente, el máximo sería {data.max_generation_complete_possible}/10. Se completarán los diez intentos originales. Dev3 se evalúa por separado y todavía no tiene una nueva cohorte nativa.</p>
    <p>La meta permanece activa. No hay comparación reservada con libre o SDD ni réplica independiente. El coste monetario y la equivalencia de tokens siguen desconocidos; la superioridad no está demostrada.</p>
    <div className="software-lab-downloads">
      <a className="text-link" href="/resultados/software/cohorte-nativa-02/progress-snapshot.json">Snapshot 02: cinco cierres y límites</a>
      <a className="text-link" href="/resultados/software/cohorte-nativa-02/verified-report-snapshot.json">Informe verificado y recursos</a>
      <a className="text-link" href="/resultados/software/cohorte-nativa-02/attempt-04-outcome.json">Entrega 04 y comprobaciones</a>
      <a className="text-link" href="/resultados/software/cohorte-nativa-02/descargas-sha256.json">Hashes de los cinco resultados</a>
      <a className="text-link" href="/resultados/software/cohorte-nativa-01/progress-snapshot.json">Snapshot 01 anterior, intacto</a>
      <a className="text-link" href={base+'goals/method-superiority-v1/development/NATIVE_COHORT.md'}>Protocolo en main</a>
      <a className="text-link" href={base+'goals/method-superiority-v1/development/registration-native-cohort-01.json'}>Registro previo en main</a>
      <a className="text-link" href={base+'scripts/native_reliability.py'}>Driver en main</a>
    </div>
  </section>;
}
