# Ejecutores v3 candidatos: aún no registrados ni iniciados

registration.py valida el registro completo, sus fuentes/contratos/tests/lock,
modelo público y medium, imágenes y perfiles originales, revisión nativa completa
con juicio/manifest/job/provider/model/time ligados y el mapping privado original
SHA33e47d210e98909c81fbe3df099cf4d7994faba7c205703dcb251f9d6d448245.
Deriva cell-01..42 en el orden original, nunca genera nuevos IDs/seed/tareas.
El primerT sigue FractionMix/Codex/r1. Verifica también que módulos ejecutados
provengan del checkout registrado. Un label draft o scoped accept no admite autores.

campaign.py conecta RunJournal, N/S/T/A, DockerRoles y NativeEvidence. Cada éxito
se valida físicamente antes de cerrar el outcome de presupuesto. Sólo un fracaso
de bridge con recibo/handle cerrado verificado puede cerrar fracaso: diagnósticos
exactos de formato dan generation_failed; otros fallos preservan causa account/
quota desconocida y detienen campaña sin fallback/reinicio. Un handle live/missing
o captura sin cierre permanece UncertainJob; no se inventa un resultado terminal.

Un job reservado pero aún no iniciado vuelve a comprobar cuota y plazo original
antes de arrancar el mismo handle. No renueva contadores/relojes. Un job iniciado
se reconcilia mediante sus mismos records; el transporte no lo vuelve a iniciar.
La cuota Gemini desconocida/vencida retiene admisiones; Codex desactivado conserva
unknown explícito, sin declarar disponibilidad o activar polling. Una lectura
actual de ambos perfiles originales con edad<=600s se liga a cada admisión.

Los exports contienen sólo schema/opaque_id/task/files/delivery_sha256; método,
modelo, proceso e historia quedan en terminal-snapshot privado. Cada cierre liga
la entrega y todas las admisiones. No se repara ninguna entrega tras la revisión
final. Una auditoría final nativa negativa real es fracaso del hito; evidencia
desconocida permanece inconclusa. Las observaciones inconclusas del hito se
conservan antes de actualizarse por una lectura concluyente, sin nuevos autores.

evaluation.py exige todas42generaciones terminales y el gate físico T9 antes de
crear Subjects. Congela manifests de los42exports y libera una sola evaluación.
Cada recipe usa su mismo handle/recibo; un resultado perdido puede releerse, nunca
reejecutarse. Programme ausente sólo se puntúa0 cuando se habilitó evaluación,
sin fingir que se ejecutó un sujeto. Si el hito falla, F permanece no evaluado
con [0,1]; si el hito es inconcluso, no se sella informe final ni falso fracaso.

El informe reutiliza la auditoría final ya cargada al budget y liga su recibo
nativo/files/locators. Presenta F,D,G,H separados, intervalos por desconocidos,
12pares T-N/T-S y6pares T-A, sin H impuesto a N ni p-values/causalidad general.
Además conserva estratos por tarea (4pares N/S,2A) y familia (6pares N/S,3A),
con todos los bloques y los intervalos desconocidos, sin seleccionar victorias.
Conserva llamadas/bytes/tests/tiempos y uso declarado por job, sin normalizar
quantidades desconocidas a tokens ni inventar dinero. El evaluador automatizado
no recibe labels de método/modelo; las entregas pueden autoidentificarse en su
propio contenido, por lo que no se afirma ceguera absoluta o criptográfica.

CLI candidata (PYTHONPATH=src:. y Python3.12 en este checkout):

python -m experiments.software_comparison_v3.campaign validate --source CHECKOUT --registration REGISTRO
python -m experiments.software_comparison_v3.campaign status --source CHECKOUT --registration REGISTRO
python -m experiments.software_comparison_v3.campaign step --source CHECKOUT --registration REGISTRO --quota SNAPSHOT
python -m experiments.software_comparison_v3.campaign gate --source CHECKOUT --registration REGISTRO --quota SNAPSHOT
python -m experiments.software_comparison_v3.campaign evaluate-step --source CHECKOUT --registration REGISTRO --quota SNAPSHOT
python -m experiments.software_comparison_v3.campaign report --source CHECKOUT --registration REGISTRO --quota SNAPSHOT

validate/status no crean un diario de campaña ni llaman modelos/sujetos. step
ejecuta una acción máxima; el coordinador actualiza cuota para la siguiente acción.
El registro completo, revisión conjunta y comprobaciones físicas del ejecutor
están pendientes. Los controles sintéticos no sustituyen una campaña oT9 reales.
No hay autores ni sujetos de esta cohorte; release final y publicación pendientes.

PROVENANCE_STATUS.md describe la revisión anterior del verificador en7cb78818.
Los cambios posteriores de failed_role/MilestoneRejected/runner no pertenecen a
aquella aceptación. Se requiere revisar el nuevo snapshot antes de registro.
