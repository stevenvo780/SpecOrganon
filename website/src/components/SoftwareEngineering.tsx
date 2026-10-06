import data from '../software-engineering-02.json';
import NativeCohortProgress from './NativeCohortProgress';
import BoundedAdmission from './BoundedAdmission';
import NativeSyntax from './NativeSyntax';
import DockerRecovery from './DockerRecovery';
import NeutralControls from './NeutralControls';
import Dev4Closure from './Dev4Closure';

export default function SoftwareEngineering(){
  const native=data.native_development;
  return <section aria-labelledby="avance-rc3">
    <h4 id="avance-rc3">Avance posterior: candidato 0.2.0rc3.dev2</h4>
    <p>Este bloque conserva el hito anterior de dev2. Las fuentes y descargas originales permanecen disponibles; los avances históricos dev3/dev4/dev5 y la infraestructura parcial dev6 se detallan más abajo.</p>
    <p>El toolkit ya ensambla el manifiesto a partir del contenido tipado del autor. Conserva el paquete original, el manifiesto derivado y sus hashes; comprueba el snapshot y rechaza campos extra o contenido vacío. Se mantienen las nueve fases, las revisiones y los recibos reales de pruebas.</p>
    <p>La verificación del candidato pasó <strong>{data.host_tests_passed} pruebas y {data.host_subtests_passed} subpruebas</strong>. La instalación en Docker comprobó la CLI y el MCP por stdio, con {data.installed_runtime.MCP_tools_discovered} herramientas. La revisión estática de Gemini aceptó el código; esa revisión no ejecutó las pruebas.</p>
    <h5>RangeAudit: primera entrega nativa de esta versión</h5>
    <p>Una CLI de biblioteca estándar para fusionar intervalos enteros y detectar huecos. Completó <strong>{native.accepted_phases.length}/9 fases</strong>, con {native.author_calls_completed} llamadas de Codex, {native.phase_reviews_completed} revisiones de Gemini y {native.mandate_checks_completed} comprobaciones del mandato. Una corrección de validación quedó contabilizada; el programa y su documentación se sellaron antes de generar las pruebas.</p>
    <p>Las pruebas generadas pasaron en el ejecutor aislado. Después, una comprobación pública separada pasó <strong>115/115 casos</strong>, con un oráculo de ocupación de celdas enteras, límites de entrada y rechazo atómico. Son comprobaciones de desarrollo posteriores a la generación, sin cegamiento ni comparación con otros métodos.</p>
    <p>Los trabajos aislados de este intento sumaron {Math.round(native.sum_isolated_job_seconds)} segundos; desde el registro hasta la entrega transcurrieron {Math.round(native.registration_to_completion_seconds)} segundos, incluidas las esperas de coordinación. Estos tiempos describen una ejecución. No demuestran eficiencia comparativa ni beneficio de campo.</p>
    <NativeCohortProgress/>
    <BoundedAdmission/>
    <NativeSyntax/>
    <DockerRecovery/>
    <NeutralControls/>
    <Dev4Closure/>
    <h5 id="meta-mejor-metodo">Meta activa: demostrar que mejora la entrega</h5>
    <p>Codex tiene asignada la mejora y su validación. Para cerrar la meta, el candidato deberá satisfacer criterios fijados antes de las nuevas evaluaciones:</p>
    <ul>
      <li>Al menos 90% de generaciones completas en diez o más intentos de desarrollo y tres tipos de problema.</li>
      <li>Mejorar en al menos diez puntos porcentuales las entregas completas frente a libre y SDD, bajo un contrato común.</li>
      <li>Funcionalidad no inferior, con margen máximo de cinco puntos porcentuales; tiempo medio total no mayor que el doble de cada alternativa.</li>
      <li>Tareas reservadas, incertidumbre simultánea del 95% y una réplica independiente de la misma versión.</li>
    </ul>
    <p>El progreso incluye ingeniería verificada, una entrega anterior completa y la cohorte dev2 cerrada con tres entregas y siete fallos, y la cohorte dev4 cerrada con cinco entregas de diez, separada de los controles de ingeniería dev5 y los helpers parciales dev6. La cohorte cerrada incumplió el criterio de fiabilidad. La superioridad continúa sin demostrar. La campaña v3, sus 42 celdas y sus puntajes permanecen cerrados.</p>
    <div className="software-lab-downloads">
      <a className="text-link" href="/resultados/software/candidato-rc3-dev2-verificacion.json">Verificación y consumo observado</a>
      <a className="text-link" href="/resultados/software/specorganon-candidate-0.2.0rc3.dev2.zip">Fuentes del candidato</a>
      <a className="text-link" href="/resultados/software/specorganon-0.2.0rc3.dev2-py3-none-any.whl">Wheel del candidato</a>
      <a className="text-link" href="/resultados/software/rc3-dev2-evidencia-ingenieria.zip">Pruebas, revisiones y fallos iniciales</a>
      <a className="text-link" href="/resultados/software/rangeaudit-desarrollo-01-entrega.zip">Entrega RangeAudit y comprobaciones</a>
      <a className="text-link" href="/resultados/software/rangeaudit-desarrollo-01-contrato.md">Contrato de desarrollo</a>
      <a className="text-link" href="/resultados/software/meta-mejor-metodo.md">Meta y criterios de cierre</a>
    </div>
  </section>;
}
