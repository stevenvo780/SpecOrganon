export default function NativePilotProgress(){
 const repo='https://github.com/stevenvo780/SpecOrganon';
 const evidence=repo+'/blob/main/goals/method-superiority-v1/evidence/neutral-native-pilot-dev7-01/';
 return <section aria-labelledby="piloto-dev7">
 <h5 id="piloto-dev7">Piloto público dev7: corte parcial de dos cierres</h5>
 <p><strong>Corte documental parcial report-01: 2 cierres de 6 posiciones fijadas; las otras 4 no tienen resultado terminal en este corte.</strong> El piloto está en curso según el checkpoint de este corte; esta página no es un monitor en vivo. Se conserva el plan original N/S, tres tipos, sin reemplazos ni reparaciones de intentos cerrados.</p>
 <div style={{overflowX:'auto'}}><table><thead><tr><th>Posición</th><th>Método / tarea</th><th>Gate</th><th>Prueba pública</th><th>Recursos cobrados</th></tr></thead><tbody>
 <tr><td>01</td><td>N / RangeAudit</td><td>FAILED: solicitud excede presupuesto</td><td>115/115</td><td>2 autores, 1 feedback, 1 medida propia</td></tr>
 <tr><td>02</td><td>S / RangeAudit</td><td>FAILED: solicitud excede presupuesto</td><td>115/115</td><td>1 plan, 1 revisión de plan, 1 programa; 0 medidas propias</td></tr>
 </tbody></table></div>
 <p><strong>Ambos fallaron y no acreditan auditoría D/G final ni paquete común completo.</strong> Los programas pasaron 115/115 comprobaciones públicas de desarrollo cada uno; eso no convierte los intentos en completos, no es F reservado ni demuestra competencia o superioridad. El denominador permanece seis y los pendientes quedan aparte; no hay ranking entre N y S.</p>
 <p>El diagnóstico offline del primer pedido reconstruyó <strong>131968 bytes frente al límite 110000</strong>. Archivos actuales 14924 bytes y documentos 5768 están dentro de sus límites. El historial incorpora 89938 bytes antes de escapar JSON externo: paquetes de rol 30947 y capturas 58708, además de estructura; repite contenido ya presente en archivos/documentos. Esta serialización compartida explica la parada observada, sin concluir eficacia causal del método.</p>
 <p>El diagnóstico midió en un proceso aparte las cuatro generaciones cerradas, omitiendo el guard solo en memoria para contar bytes. <strong>No hubo retry, dispatch ni modificación de fuentes, driver, registros o cuotas.</strong> No se ejecutó el programa generado. Los 504 archivos sellados originales y su índice SHA conservan outcomes, closures, recibos y errores; los logs mutables posteriores no forman parte de este corte.</p>
 <p>La corrección futura debe deduplicar pedidos de N/S conservando información útil y originales físicos, verificar recuperación y usar otra versión y registro prospectivo. <strong>No ampliar este presupuesto ni sustituir estas posiciones.</strong> Competencia, integración T común, F externo, freeze completo, calificación T propia y comparación reservada con réplica siguen pendientes. La meta permanece activa. Wheel e imágenes locales, último wheel público dev5 y 94 descargas históricas intactas.</p>
 <div className="software-lab-downloads">
 <a className="text-link" href={repo+'/tree/main'}>Repositorio actual en main</a>
 <a className="text-link" href={evidence+'README.md'}>Corte parcial y límites</a>
 <a className="text-link" href={evidence+'report-01.stdout'}>Informe original de dos cierres</a>
 <a className="text-link" href={evidence+'first-request-diagnostic.json'}>Diagnóstico offline de bytes</a>
 <a className="text-link" href={evidence+'closed-raw-index-01.json'}>Índice SHA de originales sellados</a>
 <a className="text-link" href={repo+'/tree/main/goals/method-superiority-v1/evidence/neutral-native-pilot-dev7-01/closed-raw'}>Archivos originales de los dos cierres</a>
 <a className="text-link" href={repo+'/blob/main/goals/method-superiority-v1/evidence/neutral-native-admission-01/pilot-plan.json'}>Plan prospectivo original</a>
 <a className="text-link" href={repo+'/blob/main/goals/method-superiority-v1/evidence/neutral-native-admission-01/admission-review.json'}>Admisión acotada a seis posiciones</a>
 </div>
 </section>;
}
