# Revisión prospectiva independiente y enmienda D-111

`source_gate_review`, agente nativo existente, revisó `plan.md` en commit
7ea1cd5 antes de la fuente estable. No ejecutó pruebas ni efectos externos.
Modelo/esfuerzo del revisor no autenticados. Dos riesgos P2 de contrato:

1. El claim identifica un intento, no un segmento. La instancia que ejecuta
   debe poseer la revisión/lease activa; cada count, send, herramienta y
   transición pause/finish/abort exige esa misma instancia. Pausar/finalizar
   revoca el lease. Una instancia anterior no puede actuar ni abortar el
   siguiente segmento. `abort` exige ownership vigente incluso tras vencer
   el deadline, sin permitir que un antiguo segmento altere otro.
2. Comprobar deadline antes y después de I/O y al pausar/finalizar. Una
   operación tardía o transporte que captura el timeout deja incertidumbre;
   no debe dar estado paused/completed ni restaurar presupuesto.

Se incorporan ambas precisiones al contrato antes de las pruebas de aceptación
del nuevo runner. El plan original queda preservado. Las pruebas deben
incluir instancia antigua tras relevo y transporte que retorna tarde.
