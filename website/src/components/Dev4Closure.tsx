import data from '../native-cohort-terminal-02.json';
const names: Record<string,string> = {rangeaudit:'RangeAudit',ledgerfold:'LedgerFold',topoplan:'TopoPlan'};
export default function Dev4Closure(){
 return <section aria-labelledby="cohorte-dev4-cierre">
  <h5 id="cohorte-dev4-cierre">Cohorte dev4 cerrada: cinco entregas de diez intentos</h5>
  <p>Cierre verificado del <time dateTime={data.at}>{new Date(data.at).toLocaleString('es-CO',{timeZone:'UTC'})} UTC</time>: <strong>{data.closed_attempts} intentos cerrados, {data.generation_complete} entregas completas, {data.planned_attempts} intentos fijados</strong>. El proceso original y su lectura física final terminaron con exit0; se conservaron las 45 fuentes registradas, los diez intentos originales y todos los fallos, sin reemplazos ni nuevas llamadas del verificador.</p>
  <div className="backup-table-wrap"><table><caption>Resultado terminal dev4 · desarrollo público, sin comparación reservada</caption><thead><tr><th scope="col">Intento</th><th scope="col">Contrato</th><th scope="col">Estado</th><th scope="col">Comprobaciones públicas</th></tr></thead><tbody>{data.rows.map(row=><tr key={row.id}><th scope="row">{row.id}</th><td>{names[row.task]}</td><td>{row.status==='complete'?'Entrega completa':'Fallido, cerrado'}</td><td>{row.public_passed===null?'Sin paquete completo':`${row.public_passed}/${row.public_total}`}</td></tr>)}</tbody></table></div>
  <p>LedgerFold completó los intentos 05 y 08 con 104/104 comprobaciones cada uno; TopoPlan el 06 con 105/105; RangeAudit el 07 y el 10 con 115/115 cada uno. Son <strong>543/543 comprobaciones públicas en cinco entregas completas</strong> y tres tipos con nueve fases. Esas comprobaciones no son 543 unidades independientes para estimar fiabilidad: el denominador sigue siendo diez intentos.</p>
  <p><strong>Resultado: 50% (5/10); el criterio de 9/10 se incumplió.</strong> El intervalo Wilson del 95%, 23,66–76,34%, es descriptivo. Tres intentos fallaron por el límite de control Docker de 15 segundos, con contenedores creados que nunca arrancaron. El 02 agotó los dos autores de compare tras rechazar 6436 y 6150 bytes frente al límite de 6000; no agotó los cuarenta roles totales. El 09 pasó su test propio, pero la respuesta del autor en validate fue JSON inválido, exit2, y no produjo un paquete completo.</p>
  <p>Se conservaron 85 recibos de autor, 64 de revisión, 15 de mandato, seis tests propios y cinco verificaciones públicas. La suma histórica de wall_seconds, 4275,604 segundos, no incluye toda la preparación compartida o agregación y no se usa para declarar eficiencia comparativa. Coste monetario y equivalencia de tokens desconocidos.</p>
  <p>El archivo contiene resultados, cierres, entregas, diarios, salidas seleccionadas y una copia de las 45 fuentes congeladas. Sus rutas absolutas históricas permanecen: <strong>es evidencia inspeccionable, no un run reubicado o reanudable desde main.</strong> Se excluyen perfiles, credenciales, caches y copias repetidas. Las observaciones anteriores permanecen fechadas e intactas.</p>
  <p>Este resultado pertenece a dev4 y no valida dev5 ni la infraestructura parcial dev6. La meta permanece activa: sin sujetos reservados, comparación con libre/SDD ni réplica; la superioridad no está demostrada.</p>
  <div className="software-lab-downloads">
   <a className="text-link" href="/resultados/software/cohorte-dev4-terminal/summary.json">Resumen terminal dev4</a>
   <a className="text-link" href="/resultados/software/cohorte-dev4-terminal/report.json">Informe completo de los diez intentos</a>
   <a className="text-link" href="/resultados/software/cohorte-dev4-terminal/evidencia-cierre-dev4.zip">Evidencia original y fuentes congeladas</a>
   <a className="text-link" href="/resultados/software/cohorte-dev4-terminal/README.md">Fallos, contabilidad y custodia</a>
   <a className="text-link" href="/resultados/software/cohorte-dev4-terminal/manifest.sha256.json">Manifiesto del archivo original</a>
   <a className="text-link" href="/resultados/software/cohorte-dev4-terminal/descargas-sha256.json">SHA-256 de estas descargas</a>
   <a className="text-link" href="https://github.com/stevenvo780/SpecOrganon/tree/main">Repositorio en main</a>
  </div>
 </section>;
}
