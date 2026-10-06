import raw from '../software-diagnosis-v3.json';

export default function SoftwareDiagnosis(){
  return <section aria-labelledby="diagnostico-campana-v3">
    <h4 id="diagnostico-campana-v3">Por qué falló la campaña y qué vamos a mejorar</h4>
    <p>El diagnóstico conserva los motivos de parada de las <strong>42 celdas originales</strong>: seis generaciones completas y 36 fallidas. Trabajo libre obtuvo más funcionalidad media (75%); SpecOrganon obtuvo 16,7%, con dos paquetes completos. SDD y la ablación obtuvieron 0% bajo este protocolo. Corregir los fallos del ejecutor puede mejorar la entrega, pero su efecto todavía no está medido.</p>
    <div className="backup-table-wrap"><table><caption>Motivos de parada registrados · no equivalen a una causa profunda demostrada</caption><thead><tr><th scope="col">Motivo</th><th scope="col">Libre</th><th scope="col">SDD</th><th scope="col">SpecOrganon</th><th scope="col">Ablación</th></tr></thead><tbody>{raw.failure_groups.map(group=><tr key={group.reason}><th scope="row">{group.label}</th>{(['N','S','T','A'] as const).map(method=><td key={method}>{group.counts[method]}</td>)}</tr>)}</tbody></table></div>
    <p>Cuatro intentos de SpecOrganon terminaron por manifiestos inválidos, tres por registros de artefactos que no cumplían el contrato, dos por presupuesto de roles agotado y uno por el límite de especificación. No se ha comprobado que resolver esas incidencias baste para superar a los otros métodos. Las nueve fases, el contenido sustantivo, las revisiones y los recibos de pruebas siguen siendo requisitos.</p>
    <details><summary>Mejoras propuestas, todavía sin resultados</summary>{raw.priorities.map(priority=><div key={priority.title}><h5>{priority.title}</h5><p>{priority.proposal}</p></div>)}</details>
    <p>La siguiente validación utilizará tareas nuevas reservadas y criterios comunes de funcionalidad, documentación, trazabilidad, pruebas y recursos. La adherencia a las nueve fases se informará por separado. El protocolo y la regla de parada se fijarán antes de generar; se conservarán los resultados adversos. La campaña v3 permanece cerrada.</p>
    <div className="software-lab-downloads"><a className="text-link" href="/resultados/software/campana-v3-diagnostico.md">Diagnóstico y propuestas</a><a className="text-link" href="/resultados/software/campana-v3-diagnostico.json">Motivos de parada de las 42 celdas</a></div>
  </section>;
}
