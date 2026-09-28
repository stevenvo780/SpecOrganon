# Despacho medido de una solicitud de desarrollo

`scripts/run_managed_response.py` ofrece una ruta **de desarrollo** para una
solicitud de texto a OpenAI Responses. Usa el endpoint de
[conteo de entrada](https://developers.openai.com/api/docs/guides/token-counting)
antes del envío y fija `max_output_tokens`, que según la documentación de
OpenAI incluye salida visible y razonamiento. El ledger privado
`scripts/managed_token_ledger.py` reserva la suma antes de enviar, comparte
el tope entre roles que usan la misma carpeta y conserva la reserva cuando
el resultado es incierto.

`scripts/run_managed_conversation.py` compone esa ruta en una corrida de **2 a
32 turnos de texto del mismo modelo**. Prepara un plan privado, conserva cada
solicitud, respuesta y recibo, y usa un único ledger y un plazo activo local
para toda la conversación. Con `store:false`, reenvía los elementos completos
de `response.output`, incluidos razonamiento cifrado y `phase`, siguiendo la
[guía oficial de estado de conversación](https://developers.openai.com/api/docs/guides/conversation-state).
Si aparece una respuesta incompleta, no textual o sin razonamiento preservable,
termina `truncated`; una salida incierta deja `indeterminate` y bloquea la
reejecución. No llama herramientas.

## Contrato local

1. El operador crea **una sola** carpeta de ledger por corrida, fuera del
   workspace visible al modelo. Fija el máximo de tokens y de solicitudes.
2. Cada agente entrega un ID de solicitud único, su rol y un JSON con
   `model`, `input`, `max_output_tokens` y opcionalmente `instructions` y
   `reasoning: {"effort": "..."}`. El ejecutor rechaza herramientas y otros
   campos: todavía no coordina llamadas de herramienta ni conversaciones.
3. El transportador solicita al proveedor el conteo de esa entrada. El ledger
   reserva, bajo un lock entre procesos, entrada contada más el techo de salida. Si no cabe,
   no se llama a `/responses`. Solo puede quedar una solicitud pendiente a la
   vez por ledger; una muerte del proceso tras reservar impide enviar otra
   hasta revisar ese intento.
4. Tras el envío se guarda el JSON completo de respuesta en un archivo nuevo
   bajo una carpeta privada. Solo entonces se concilian
   `input_tokens + output_tokens = total_tokens`; el caché está incluido en
   entrada y el razonamiento en salida, sin volver a sumarlos.
5. Si el envío, la escritura o la telemetría fallan, la reserva queda retenida
   y el ledger impide otras solicitudes hasta revisión. No hay reintento
   automático. Una respuesta `incomplete` con uso válido se concilia y el
   orquestador puede enviar otra solicitud; la política del estudio debe decidir
   cuándo una corrida está truncada e impedir sustituirla por una favorable.

La preparación local no llama al proveedor:

```sh
python3 scripts/run_managed_response.py init /ruta/privada/corrida-01/ledger \
  --limit-tokens 80000 --max-requests 100
```

Para una conversación, crear primero un JSON privado como este:

```json
{
  "schema": 1,
  "model": "gpt-6-luna",
  "instructions": "Examina la evidencia aportada y declara incertidumbres.",
  "reasoning": {"effort": "low"},
  "turns": [
    {"user": "Resume el problema y las fuentes que faltan.", "max_output_tokens": 300},
    {"user": "Revisa tu respuesta anterior y señala supuestos refutables.", "max_output_tokens": 300}
  ]
}
```

```sh
python3 scripts/run_managed_conversation.py prepare plan.json /ruta/privada/corrida-02 \
  --limit-tokens 80000 --active-limit-seconds 5400
python3 scripts/run_managed_conversation.py status /ruta/privada/corrida-02
```

`prepare` y `status` son locales y no facturan. `execute` requiere
`--allow-paid-requests` y `OPENAI_API_KEY`; solo debe usarse después de la
autorización humana y de fijar también tarifas y techo de gasto. El temporizador
monotónico del proceso cubre conteo, envíos y escritura local mientras la
ejecución está activa. No pausa esperas humanas y una interrupción mata la
posibilidad de continuar esa misma corrida automáticamente. Una carpeta nueva
no sustituye el resultado truncado o incierto en un estudio registrado.
Un transporte que ignore indefinidamente la alarma del proceso puede impedir
un corte duro; la comprobación monotónica posterior evita continuar o marcar
`completed` si finalmente devuelve el control. Ese límite requiere aislamiento
externo antes de usar la ruta como presupuesto confirmatorio.

El subcomando `send` requiere `--allow-paid-request` y `OPENAI_API_KEY`, además
del ledger, JSON de solicitud, archivo nuevo de respuesta, ID y rol. **Esa
bandera no acredita autorización humana ni impone un límite de dólares.** No
se ejecutó `send` contra un proveedor para este desarrollo. Las pruebas usan
un transporte falso y un servidor HTTP local, sin gasto ni credenciales.

## Límite de la evidencia

Estos controles cubren únicamente las solicitudes que pasan por estos
ejecutores y comparten el mismo ledger. Rechazan redirecciones HTTP con la
clave adjunta.
La CLI opaca de `run_development_arm.py` sigue analizando uso al terminar y no
adopta este control. El ledger, el temporizador y los recibos son locales, sin
custodia independiente ni recibo de factura. El plazo nuevo solo cubre la
conversación secuencial de un proceso y no agrega varios agentes. Faltan
herramientas compartidas, tarifa y techo de gasto,
versiones exactas de modelo, agentes coordinados, familias adicionales,
reservas, jueces ciegos y evaluación de campo. Hasta integrar y verificar
esas condiciones, el piloto facturable y el criterio 4 continúan **NO-GO / no
demostrado**. El máximo de 80 000 tokens procede del
[protocolo prospectivo](protocolo_experimental.md#3-brazos-panel-y-comparabilidad);
no es por sí mismo una autorización para consumirlo.

Las pruebas del ledger cubren muerte del proceso y reapertura local. Las de
conversación usan transporte falso: dos turnos, razonamiento cifrado preservado,
límites, fallo de envío, muerte del proceso hijo durante `send` y alteración de
un archivo. No ensayan apagón del host,
plazo largo real ni garantías del dispositivo de almacenamiento. El journal
tampoco tiene custodia externa frente a cambios coherentes del mismo usuario.
