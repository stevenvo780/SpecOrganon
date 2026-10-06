import cut from '../native-dev8-progress-02.json';
export default function NativeDev8Progress(){
 const repo='https://github.com/stevenvo780/SpecOrganon';
 const base=repo+'/blob/main/goals/method-superiority-v1/evidence/';
 return <section aria-labelledby="piloto-dev8">
 <h5 id="piloto-dev8">Piloto público dev8: corte parcial de tres posiciones</h5>
 <p><strong>Corte documental del {cut.observed_utc}: 3 cierres de 6 posiciones originales.</strong> Dos failed y una review_ready; las otras tres no tienen resultado en este corte. El driver original seguía en ejecución al capturarlo. Registro prospectivo de seis posiciones N/S, 56 fuentes verificadas y cero reemplazos; esta foto no representa el estado vivo posterior.</p>
 <div style={{overflowX:'auto'}}><table><thead><tr><th>Posición</th><th>Método</th><th>Tarea</th><th>Estado original</th><th>Comprobaciones públicas</th><th>Paquete común / F externo</th></tr></thead><tbody>{cut.observations.map(row=><tr key={row.position}><td>{row.position}</td><td>{row.attempt.method}</td><td>{row.attempt.task}</td><td>{row.status}</td><td>{row.public_passed}/{row.public_cases}</td><td>Sin evidencia (null)</td></tr>)}</tbody></table></div>
 <p>La posición 01 pasó 115/115 comprobaciones pero falló en auditoría: el envoltorio del stream canónico Gemini produjo <strong>131246 bytes frente al límite 128000</strong>, con request 99333 y prompt 120174. La posición 02 falló en autoría de pruebas tras agotar su presupuesto. La posición 03, N LedgerFold, quedó <strong>review_ready con 104/104 comprobaciones</strong>; readiness no equivale a paquete completo ni a F externo.</p>
 <p><strong>334/334 comprobaciones públicas descriptivas</strong> en estas tres posiciones, sin convertirlas en 334 sujetos. common_complete y F externo son null en las tres; no se demuestra competencia, superioridad ni ranking. Los originales sellados conservan fallos, streams y cierres. No se ejecutaron retries ni se ampliaron límites para esta publicación.</p>
 <p>Un diagnóstico posterior <strong>offline y no implementado</strong> propone factorizar 14 subesquemas D/G idénticos mediante referencias Draft7: schema 19698→3575 bytes, prompt104051 y envoltorio113441, con nueve vectores de validación conservados. No fue source patch, instalación, retry ni llamada nativa; no cambia el fallo original ni acredita readiness posterior.</p>
 <div className="software-lab-downloads">
 <a className="text-link" href={repo+'/tree/main'}>Repositorio en main</a>
 <a className="text-link" href={base+'neutral-native-dev8-progress-02/index.json'}>Índice del corte 3/6</a>
 <a className="text-link" href={base+'neutral-native-dev8-progress-02/SHA256SUMS'}>Hashes del tercer original</a>
 <a className="text-link" href={base+'neutral-native-dev8-progress-01/index.json'}>Corte previo 2/6 inmutable</a>
 <a className="text-link" href={base+'neutral-native-dev8-progress-01/audit-envelope-diagnostic.json'}>Diagnóstico offline del envoltorio</a>
 <a className="text-link" href={repo+'/tree/main/goals/method-superiority-v1/evidence/neutral-native-dev8-progress-01/raw'}>RAW originales 01–02</a>
 <a className="text-link" href={repo+'/tree/main/goals/method-superiority-v1/evidence/neutral-native-dev8-progress-02/raw'}>RAW original 03</a>
 <a className="text-link" href={base+'neutral-native-dev8-admission-01/pilot-plan.json'}>Plan prospectivo original</a>
 <a className="text-link" href={base+'audit-schema-factoring-diagnostic-01/diagnostic.json'}>Propuesta offline de factorización, no implementada</a>
 <a className="text-link" href={base+'neutral-native-dev8-admission-01/admission-review.json'}>Admisión acotada N/S</a>
 </div></section>;
}
