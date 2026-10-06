import cut from '../native-dev8-terminal-01.json';
export default function NativeDev8Progress(){
 const repo='https://github.com/stevenvo780/SpecOrganon';
 const base=repo+'/blob/main/goals/method-superiority-v1/evidence/';
 return <section aria-labelledby="piloto-dev8">
 <h5 id="piloto-dev8">Piloto público dev8 cerrado: cuatro fallos y dos review_ready</h5>
 <p><strong>Seis posiciones originales cerradas de seis, cuatro failed y dos review_ready.</strong> El mismo driver terminó el {cut.driver_terminal_at}, exit0: informe terminal producido, no gate ni paquete común completo. No se reemplazaron posiciones ni se modificaron fuentes o presupuestos. Este cierre conserva los seis outcomes y sus sellos; T no participó.</p>
 <div style={{overflowX:'auto'}}><table><thead><tr><th>Posición</th><th>Método</th><th>Tarea</th><th>Estado original</th><th>Comprobaciones públicas</th><th>Paquete común / F externo</th></tr></thead><tbody>{cut.observations.map(row=><tr key={row.position}><td>{row.position}</td><td>{row.attempt.method}</td><td>{row.attempt.task}</td><td>{row.status}</td><td>{row.public_passed}/{row.public_cases}</td><td>Sin evidencia (null)</td></tr>)}</tbody></table></div>
 <p>01 N RangeAudit pasó115/115 y falló en auditoría: envoltorio canónico Gemini <strong>131246 bytes frente al límite128000</strong>, request99333 y prompt120174.02 S RangeAudit agotó admisión durante autoría de pruebas (mapa de archivos/documentos excedía su presupuesto).04 S LedgerFold propuso BATTERY.md y BATTERY_ADDITION.md cuando la etapa de pruebas prohibía añadir documentos; agotó las propuestas de esa etapa.06 S TopoPlan agotó admisión de pruebas por el mapa completo de archivos/documentos.</p>
 <p>03 N LedgerFold y05 N TopoPlan quedaron <strong>review_ready</strong>, con104/104 y105/105 comprobaciones respectivamente. <strong>common_complete y F externo son null en los seis</strong>: readiness no equivale a paquete completo, competencia ni calificación. Los brazos S también conservan sus comprobaciones públicas posteriores; no revierten sus fallos de generación.</p>
 <p><strong>648/648 comprobaciones públicas descriptivas</strong>:115 por cada RangeAudit,104 por cada LedgerFold y105 por cada TopoPlan. La unidad son seis generaciones, no648 sujetos. No demuestra superioridad ni ranking N/S, ni resultado de T. Los tiempos whole_attempt suman2553,186 segundos; preparación compartida, coste monetario, tokens comparables y ratio comparativo siguen desconocidos.</p>
 <p>Los RAW01/02 y03 permanecen inmutables en sus cortes anteriores; el cierre añade <strong>1171 archivos RAW de04–06,25.903.964 bytes</strong> y un manifiesto de <strong>1180 entradas</strong>. Se verificaron2513 hashes sellados del runtime, seis outcomes iguales al informe terminal y56 fuentes originales. Se omiten sólo locks vacíos del nuevo RAW, conservando sus hashes; no hay perfiles, autenticación ni sesiones transferidos. Los cortes2/6 y3/6 se conservan históricos.</p>
 <p>El diagnóstico de factorización sigue siendo una <strong>propuesta offline no implementada</strong>:14 subesquemas D/G mediante Draft7 refs, schema19698→3575, prompt104051 y envoltorio113441, nueve vectores conservados. No hubo patch, instalación, retry ni llamada nativa: no cambia retroactivamente el fallo01. Dev9 permanece ingeniería parcial de T; la meta continúa activa.</p>
 <div className="software-lab-downloads">
 <a className="text-link" href={repo+'/tree/main'}>Repositorio compartible en main</a>
 <a className="text-link" href={base+'neutral-native-dev8-final-01/summary.json'}>Resumen terminal6/6</a>
 <a className="text-link" href={base+'neutral-native-dev8-final-01/report.json'}>Informe original del driver</a>
 <a className="text-link" href={base+'neutral-native-dev8-final-01/pilot-run-terminal.json'}>Recibo de terminación exit0</a>
 <a className="text-link" href={base+'neutral-native-dev8-final-01/archive-verification.json'}>Custodia y verificación del archivo</a>
 <a className="text-link" href={base+'neutral-native-dev8-final-01/verify_archive.py'}>Verificador offline del archivo</a>
 <a className="text-link" href={base+'neutral-native-dev8-final-01/SHA256SUMS'}>1180 hashes del cierre</a>
 <a className="text-link" href={base+'neutral-native-dev8-progress-02/index.json'}>Corte3/6 histórico inmutable</a>
 <a className="text-link" href={base+'neutral-native-dev8-progress-01/index.json'}>Corte2/6 histórico inmutable</a>
 <a className="text-link" href={base+'neutral-native-dev8-progress-01/audit-envelope-diagnostic.json'}>Diagnóstico del fallo original01</a>
 <a className="text-link" href={repo+'/tree/main/goals/method-superiority-v1/evidence/neutral-native-dev8-final-01/raw'}>RAW originales04–06</a>
 <a className="text-link" href={repo+'/tree/main/goals/method-superiority-v1/evidence/neutral-native-dev8-progress-01/raw'}>RAW originales01–02</a>
 <a className="text-link" href={repo+'/tree/main/goals/method-superiority-v1/evidence/neutral-native-dev8-progress-02/raw'}>RAW original03</a>
 <a className="text-link" href={base+'neutral-native-dev8-admission-01/pilot-plan.json'}>Plan prospectivo original</a>
 <a className="text-link" href={base+'neutral-native-dev8-admission-01/admission-review.json'}>Admisión acotada N/S</a>
 <a className="text-link" href={base+'audit-schema-factoring-diagnostic-01/diagnostic.json'}>Factorización propuesta offline</a>
 </div></section>;
}
