export default function RequestContentEngineering(){
 const repo='https://github.com/stevenvo780/SpecOrganon';
 const evidence=repo+'/blob/main/goals/method-superiority-v1/evidence/request-content-dev8-01/';
 return <section aria-labelledby="avance-dev8">
 <h5 id="avance-dev8">Dev8: contexto íntegro con referencias compartidas</h5>
 <p><strong>Ingeniería parcial verificada, 0.2.0rc3.dev8.</strong> N y S comparten un codec de referencias a cadenas repetidas: conserva archivos, documentos, historial completo, capturas y metadatos. La auditoría conserva localizadores físicos y criterios originales; JSON sólo se trata como canónico cuando coincide exactamente con sus bytes, y el resto conserva su texto UTF-8. No se recorta el contexto ni se amplían los presupuestos.</p>
 <p><strong>156 pruebas seleccionadas aprobadas</strong> en el recibo de ingeniería. La revisión Codex inicial rechazó dos problemas de asignación de recursos; las correcciones cuentan cadenas en bloques acotados y verifican límites particulares y expansión antes de copiar. La revisión posterior acepta sólo esas correcciones. Se conservan el rechazo, la aceptación Gemini del corte anterior y un timeout sin resultado.</p>
 <div style={{overflowX:'auto'}}><table><thead><tr><th>Comprobación offline</th><th>Resultado observado</th><th>Alcance</th></tr></thead><tbody><tr><td>Seis pedidos históricos reconstruidos</td><td>58663–84841 bytes; límite 110000</td><td>Roundtrip exacto del contexto; sin retry ni dispatch</td></tr><tr><td>Tres auditorías hipotéticas N</td><td>78620 / 83870 / 105480 bytes</td><td>Nunca enviadas; localizadores, criterios y metadatos íntegros</td></tr><tr><td>Prompts de las tres hipótesis</td><td>95429 / 100553 / 122863 bytes</td><td>Límite original 128000 conservado</td></tr></tbody></table></div>
 <p>Wheel privado del host e imágenes Docker <strong>locales verifican 41 módulos byte iguales</strong>; CLI, <strong>MCP real de 24 herramientas</strong>, intérprete exacto del bridge, features desactivadas y medición offline con replay sin segunda ejecución. El manifiesto sella <strong>380 entradas SHA-256</strong>, incluidos snapshots históricos conservados. <strong>No hay wheel público dev8, registry ni nueva release.</strong> El último wheel descargable sigue siendo dev5 y las 94 descargas históricas mantienen sus hashes.</p>
 <p><strong>Cero nuevos intentos nativos en este hito; sin admisión, freeze completo, calificación, competencia ni superioridad.</strong> Las hipótesis no entran en ningún ranking ni denominador experimental. El piloto dev7 permanece cerrado con seis gates FAILED de seis y 648/648 comprobaciones públicas descriptivas, sin D/G final ni paquete común acreditado. La meta sigue activa: faltan nuevo registro y admisión independientes, controles competentes N/S, integración común de T y evaluación reservada con réplica.</p>
 <div className="software-lab-downloads">
 <a className="text-link" href={repo+'/tree/main'}>Repositorio actual en main</a>
 <a className="text-link" href={evidence+'engineering-receipt.json'}>Informe de ingeniería dev8</a>
 <a className="text-link" href={evidence+'README.md'}>Fuentes, fallos y límites</a>
 <a className="text-link" href={evidence+'codex-resource-source-review.json'}>Rechazo y aceptación acotada Codex</a>
 <a className="text-link" href={evidence+'source-resource-final-pins.json'}>12 fuentes fijadas</a>
 <a className="text-link" href={evidence+'request-regression.json'}>Reconstrucción offline de seis pedidos</a>
 <a className="text-link" href={evidence+'audit-context-regression.json'}>Tres auditorías hipotéticas sin dispatch</a>
 <a className="text-link" href={evidence+'SHA256SUMS'}>380 hashes de evidencia</a>
 <a className="text-link" href={repo+'/blob/main/goals/method-superiority-v1/development/REQUEST_CONTENT_V1.md'}>Contrato lossless del contexto</a>
 </div>
 </section>;
}
