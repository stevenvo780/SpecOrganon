import data from '../software-engineering-06.json';
export default function NeutralControls(){
 return <section aria-labelledby="avance-dev6">
  <h5 id="avance-dev6">Hito inicial dev6: formatos neutrales y evidencia común</h5>
  <p>Este avance parcial prepara controles competentes de trabajo libre y SDD. El formato files-v1 permite aportar archivos y documentos sin fabricar pasos del motor, resultados o aprobaciones. La auditoría D/G admite notas en prosa de cualquiera de los métodos; las nueve fases H se evalúan aparte. Esta separación todavía no es un indicador común completo ni una comparación ejecutada.</p>
  <p>Los helpers capturan los bytes de un snapshot contra un manifiesto confiado al host, comprueban rutas, hashes y cadena de checkpoints, y enlazan los archivos actuales. Un archivo llamado receipt.json no demuestra ejecución: cada recibo declarado exige un verificador del transporte o diario host. Se conserva el juicio original; estos helpers no acreditan verdad semántica, precedencia de etapas, independencia real del revisor ni resultado funcional F. El operador host sigue siendo parte de la confianza.</p>
  <p><strong>{data.targeted_tests.passed} pruebas acotadas pasaron y {data.targeted_tests.skipped} quedaron omitidas</strong>. Las tres pruebas Docker antiguas requieren opt-in y no cuentan como aprobadas. Una prueba local de empaquetado comprobó los 34 módulos instalados por SHA y CLI --help con exit0. <strong>El wheel dev6 es local y no se libera; el último wheel público es dev5.</strong> No hay smoke MCP nuevo, generaciones dev6 ni suite global aprobada.</p>
  <p>La primera revisión de diseño rechazó reglas pendientes. La revisión de fuentes rechazó aceptar schema: 1.0; se corrigió con tipado exacto y nueve controles negativos. La aceptación posterior se limita a los helpers y es estática: no ejecutó tests ni aprobó el método completo. Los rechazos y errores intermedios permanecen descargables.</p>
  <p><strong>En este corte inicial faltaban controladores de etapas N/S, cronología y custodia de reparaciones, contabilidad efectiva de recursos y tiempo, verificación integrada de recibos, indicador común final y protocolo estadístico reservado.</strong> Después se deben congelar versión, adaptadores e imágenes, registrar y completar su propia cohorte fija de diez intentos y validar los controles libre/SDD en desarrollo público. Los avances posteriores se detallan más abajo; esta infraestructura no concede un ganador.</p>
  <p>La foto histórica del 6 de octubre a las 04:14:09 UTC conserva nueve cierres dev4, cuatro entregas, cinco fallos y el décimo intento en curso. El fallo 09 entregó JSON inválido del autor en validate: sus tests propios pasaron, pero el paquete quedó incompleto. Esa observación verificó las 45 fuentes congeladas y los recibos físicos sin nuevas llamadas; no es el cierre final ni un monitor en vivo.</p>
  <p>La meta permanece activa. Cero sujetos reservados, ninguna comparación ejecutada ni réplica; la superioridad sigue sin demostrar.</p>
  <div className="software-lab-downloads">
   <a className="text-link" href="/resultados/software/avance-dev6/ingenieria-parcial.json">Recibo de ingeniería parcial</a>
   <a className="text-link" href="/resultados/software/avance-dev6/infraestructura-parcial.md">Fuentes, pruebas y límites</a>
   <a className="text-link" href="/resultados/software/avance-dev6/protocolo-pendiente.md">Protocolo y puertas pendientes</a>
   <a className="text-link" href="/resultados/software/avance-dev6/evidencia-parcial-con-fallos.zip">Revisiones, logs y errores preservados</a>
   <a className="text-link" href="/resultados/software/avance-dev6/cohorte-dev4-observacion-03.json">Snapshot histórico dev4 de 04:14:09</a>
   <a className="text-link" href="/resultados/software/avance-dev6/descargas-sha256.json">SHA-256 de las nuevas descargas</a>
   <a className="text-link" href="https://github.com/stevenvo780/SpecOrganon/tree/main">Fuentes en desarrollo en main</a>
  </div>
 </section>;
}
