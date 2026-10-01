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

## Revisión estática inicial del runner

Fuentes originales preservadas byteexactas en `static_review_initial/`:
runner `06f51998b8bb7f80ed2b016380e5465a819dc6caf559fcb71650d20f3bf9cc45`,
test `fa4e821f3ab043ba27bd11abe3754f27db485ffb80e1771b4f2d3fb05da15bbd`.
El revisor señaló otros dos P2 antes de pytest:

- El validador proyectaba solo los dos primeros segmentos al bridge. Validar
  cada segmento antes de crear directorios/claim evita gastar en un plan cuyo
  tercer segmento ya era inválido.
- El claim se publicaba antes de completar preparación y contexto. Cambiar
  a admisión al comenzar el primer segmento, dentro del plazo activo, antes
  del primer conteo. La preparación incompleta no adquiere claim. Dos copias
  pueden prepararse, pero solo el dueño admitido puede contactar al proveedor.
  No se liberan claims ni se recuperan automáticamente segmentos activos.

Es una enmienda prospectiva de la política de preparación; la fuente original
permanece disponible. No constituye todavía cierre de la revisión integrada.

## Seam de herramienta autorizada antes de integración

El runner detectó que `_invoke_tool` validaba y reservaba antes de su llamada
interna a `call_tool`, con guard solo exterior. Root amplía ese helper con
keyword opcional `guard=None`, comprobado inmediatamente antes y después del
lanzamiento. El runner de equipo lo suministra; el bridge v1 conserva su
comportamiento por omisión. No se instala un hook global ni se sustituye la
función de otro módulo en runtime. Ownership de esa ampliación: root.

Esto cambia deliberadamente el helper del bridge respecto de los 36 pines
iniciales; los otros 35, producción y wheel deben permanecer intactos. Las
fuentes anteriores siguen en Git `053894a`; los gates finales fijan también
el helper ampliado y verifican compatibilidad de v1.

## Revisión integrada exploratoria

La captura `unit_team_checks/attempt_01` registra 25 pruebas aprobadas en
Python 3.11 y 51.60 segundos reportados, con cuatro fuentes byteestables.
Es exploratoria: el revisor confirmó las dos correcciones del runner y
detectó un P2 posterior en el contexto `29765a4d094b6b8ad49090ce951a0d7731bf26f696e2e0bef3c9ee5f160a54a1`.

`_end` comprobaba deadline y luego tomaba otra muestra de tiempo para
acumularlo. Si esa segunda muestra cruzaba el límite, podía guardar
active_seconds superior al máximo; la compensación indeterminate conservaba
ese valor y el lector rechazaba el estado. Decidir con una muestra validada,
mantener estado legible y retención conservadora, y probar el borde antes
del freeze final. El contexto original está preservado en la captura citada.

El negativo `unit_context_checks/attempt_01` ejecuta las dos variantes contra
ese contexto original: 2 fallos/8 deselected, exit1 esperado, bytes antes y
después idénticos. La corrección `522df24e5d33dbe4898bef4005c62246c3df23995f7fb7239fcdfa6e33d5ae41`
usa una muestra validada y estado previo válido para compensar. El marcador
durable `.closing` bloquea resume/status exitoso si falla la publicación.
Tests `fd15f6e4add42fcfcfaa6c871911c1230ce2cdd4c7da60898b5140516ca19d5d`:
10 passed en 3.11/3.12 (0.49/0.54s), fuentes guardadas antes y después.
El revisor independiente cierra estáticamente el P2 sin otro P1/P2 confirmado
en el parche acotado; resta la captura integrada de root sobre el freeze.
