# Enmienda de bindings antes del freeze final

Revisión independiente detectó que hashear archivos vivos permite cambiar la
fuente antes del build y llamarla «original». Se fijan 12 SHA de Git
98a1403ea972f328a86a114f207716978fd98a98: GOAL, protocolo, core y nueve inputs
de D-F/D-E. Todos se verifican antes de crear salida y los inputs nuevamente
al copiar. Alterar CSV, core o protocolo en copias públicas debe fallar antes
de crear bundle. Un cambio legítimo requiere otro contrato y versión explícita.

También se ligan precio declarado y topes de solicitudes/costo en los dos
runners directos, antes de mkdir/claims, para no depender sólo del builder.
Un plan DEV con roles distintos de leader se rechaza: el calendario declara
solo. Reducciones de topes se permiten, nunca reposición ni aumento.

La primera integración mostró que init con nodes supported se rechaza porque
el wrapper exige todos pending; se corrige el fixture y las instrucciones.
La siguiente mostró EPERM en fchmod del wrapper dentro del sandbox. Se
elimina esa llamada redundante y se comprueba el modo0600 creado; el builder
fuera del sandbox conserva chmod0500. No se flexibiliza syscall ni core.
Los originales y negativos están conservados antes de la reparación.

`phase_status=accepted` que producen review/advance significa aceptación
mecánica del prototipo, sin aprobación humana ni autoridad normativa. El
driver no expone approve. Precios, esfuerzo e identidad siguen declarados;
ningún token/costo fake puede convertirse en factura o evidencia de un modelo.
