# Enmienda preventiva — separación del análisis

Registrada después de plan2063a05 y antes de cualquier gate final. El worker
detectó que ejecutar código de un participante in-process concede acceso a
globals, imports y al mismo work que contiene method_state.json/proposal.json.
Allowlist del wrapper o chequeo posterior de hashes no impiden manipulación
transitoria ni reemplazo de la propia verificación. No es barrera suficiente.

El punto5 del plan se corrige: este driver **rechaza analyze sin efectos**.
Permite entregar analysis.py, report.md y sources.json en chunks y ejecutar
operaciones del núcleo original; no ejecuta código escrito por el modelo.
El análisis necesitará un carril cuyo estado del método sea read-only y cuyas
salidas no compartan esa capacidad de escritura. No se amplía el sandbox ni
se habilita fork/red. Los tests deben comprobar el rechazo y estado intacto.

Es una omisión material explícita de este adaptador preparatorio, por lo que
no habilita todavía una celda formal completa. Tampoco C pasa a tener
paralelismo real, ni se considera resuelto el acceso común a pasajes PDF.
El objetivo completo y los 24 ensayos siguen pendientes, sin redefinición.
