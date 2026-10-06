import data from '../software-engineering-03.json';

export default function BoundedAdmission(){
  return <section aria-labelledby="avance-dev3">
    <h5 id="avance-dev3">Candidato dev3: corrección de admisión dentro de la misma cuota</h5>
    <p>El controlador schema12 permite activar <code>admission_repair=True</code> en un run nuevo; permanece desactivado por defecto. Si un paquete de autor cerrado y válido falla únicamente en la admisión de recursos antes de escribir, se conserva el rechazo y el autor puede corregirlo dentro de los huecos que queden: dos autores por fase, tres en build y cuarenta roles totales. No se recorta contenido ni se eluden revisiones, compuertas o recibos.</p>
    <p>El adaptador reconoce sólo avisos exactos y ordenados de reconexión 1–5/5 dentro del mismo turno completado, con JSON final válido. Los errores arbitrarios y turnos incompletos siguen rechazados. El reanálisis de un transcript anterior valida el parser offline; no modifica el resultado histórico ni repite una petición al modelo. Las revisiones y aprobaciones de texto deben declarar <code>tests_executed=false</code>.</p>
    <p><strong>{data.host_tests_passed} controles en el host y {data.installed_tests_passed} en el wheel instalado</strong> pasaron. Docker comprobó la CLI y 24 herramientas MCP por stdio real, sin red, sesión ni llamadas a modelos. Todos los módulos instalados coinciden por SHA. Codex rechazó dos defectos en la primera revisión de texto y aceptó las correcciones; esa revisión no ejecutó tests.</p>
    <p>Los errores iniciales de preparación y el smoke vacío se conservan como intentos fallidos. La suite completa del host sigue sin estar validada. Esta es evidencia de ingeniería: <strong>dev3 no tiene todavía eficacia nativa medida</strong>, comparación reservada ni réplica.</p>
    <p>Main distribuye dev3; la cohorte en curso conserva su checkout dev2 y sus fuentes congeladas. Un clon nuevo no puede reanudar sus registros antiguos ni migrar runs schema11. Dev3 requiere una ruta y registro nuevos antes de una generación prospectiva.</p>
    <div className="software-lab-downloads">
      <a className="text-link" href="/resultados/software/avance-dev3/ingenieria.json">Verificación y límites de dev3</a>
      <a className="text-link" href="/resultados/software/avance-dev3/specorganon-0.2.0rc3.dev3-py3-none-any.whl">Wheel dev3</a>
      <a className="text-link" href="/resultados/software/avance-dev3/admission.md">Contrato de admisión y reproducción</a>
      <a className="text-link" href="/resultados/software/avance-dev3/parser-offline.json">Reanálisis offline, sin reemplazo</a>
      <a className="text-link" href="https://github.com/stevenvo780/SpecOrganon/tree/main">Fuentes actuales en main</a>
    </div>
  </section>;
}
