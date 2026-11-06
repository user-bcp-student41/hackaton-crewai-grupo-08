# Plan de trabajo del hackathon

### Propuesta: seguimiento de aportes voluntarios para promociones escolares

## Objetivo de la planificación

Definir el alcance de la wallet, los roles del equipo y las actividades de los Sprint 1 y 2 para construir una demostración funcional.

La propuesta consiste en una aplicación de demostración para ayudar a organizar los aportes voluntarios de las familias para una promoción escolar en Perú. Permitirá simular aportes, consultar el estado de los pagos y visualizar el avance de la colecta.

Este plan se limita a las historias oficiales **HU-01 — Registro y activación** y **HU-02 — Confirmación de pagos de bajo monto**. De la épica solo incorporamos los objetivos, supuestos y requisitos transversales que corresponden a estas dos historias: onboarding de baja fricción, pago de bajo monto, confirmación clara, validación de límites por proveedor/canal e instrumentación de onboarding, checkout y activación. No incorporamos requisitos propios de otras historias. El panel de colecta será una funcionalidad adicional de nuestra aplicación.

\---

# 1\. Punto 1 — ¿Hasta dónde llega nuestro alcance de la wallet?

## 1.1 Problema que queremos resolver

En Perú, los padres de familia pueden organizar aportes voluntarios para financiar una actividad de promoción escolar, como una celebración de fin de año, los recuerdos de la promoción o una reunión de despedida.

El seguimiento de los aportes puede volverse difícil cuando la información está distribuida entre conversaciones de WhatsApp, transferencias y comprobantes enviados individualmente. La persona organizadora necesita saber qué aportes se han registrado, cuánto dinero se ha reunido y qué pagos aún están pendientes de confirmar.

**Problema propuesto:**

> La organización de una colecta para una promoción escolar puede resultar desordenada cuando no existe un lugar centralizado para registrar los aportes y consultar el estado de los pagos.

Esta es una **hipótesis de diseño que debemos validar** con al menos un padre o una madre que haya participado en la organización de una promoción. No afirmaremos que todas las familias tienen esta dificultad.

## 1.2 Usuario principal

**El padre o la madre que organiza los aportes voluntarios de la promoción escolar.**

Sus necesidades principales son:

* Registrar los aportes.
* Conocer el estado de los pagos.
* Consultar el monto reunido.
* Identificar los aportes pendientes de confirmación.

Los padres y madres que realizan los aportes serán usuarios secundarios.

## 1.3 Valor esperado

La solución debería permitir que la persona organizadora:

* Consulte los aportes registrados en un solo lugar.
* Distinga los pagos confirmados de los pendientes o rechazados.
* Conozca cuánto se ha reunido frente al objetivo de la colecta.
* Reduzca la necesidad de revisar manualmente conversaciones y comprobantes.

A los padres que aportan les permitirá consultar el resultado del pago y acceder al comprobante cuando esté disponible.

**Valor esperado:** mejorar la trazabilidad de los aportes voluntarios y facilitar el seguimiento de la colecta, sin manejar dinero real en el prototipo.

## 1.4 Ejemplo cotidiano para la demostración

Imaginemos que un grupo de familias organiza una promoción escolar y establece una meta ilustrativa de **S/ 3,000** para la celebración.

Una familia quiere realizar un aporte de **S/ 50**. La aplicación simula el pago, permite consultar su estado y, si queda confirmado como exitoso, muestra el comprobante. La persona organizadora ve el aporte registrado y el avance actualizado de la colecta.

Los montos son ficticios y sirven únicamente para la demostración.

## 1.5 Flujo principal alineado con HU-01 y HU-02

1. El usuario inicia el onboarding y ve la secuencia de pasos y el paso actual (HU-01).
2. Si falta un dato obligatorio o un dato es inválido, el sistema bloquea el avance y muestra cómo corregirlo (HU-01).
3. Al finalizar correctamente, la wallet cambia a `ACTIVE` y el usuario accede al punto de entrada de pagos de bajo monto (HU-01).
4. Antes de confirmar el pago, la pantalla muestra claramente el destinatario y el monto; valida el límite aplicable al proveedor/canal antes de enviar (HU-02).
5. El sistema gestiona la respuesta del proveedor, incluidas las transiciones asíncronas, y comunica un resultado terminal por intento: exitoso, fallido o expirado (HU-02).
6. Si el pago es exitoso, se muestra la referencia y se conserva en el historial. Si falla o expira, se ofrecen acciones claras para reintentar o volver, evitando cargos duplicados (HU-02).
7. La aplicación registra los eventos analíticos requeridos por ambas historias. Como extensión propia, el panel de colecta suma únicamente pagos exitosos vinculados a ella.

## 1.6 Límite del alcance

### Incluido en el alcance

El alcance incluido toma de la **épica únicamente lo que corresponde a HU-01 y HU-02**. El flujo de la colecta escolar sirve como contexto de demostración, pero no reemplaza los requisitos originales de la wallet. Se utilizarán datos sintéticos y el mock/contrato disponible.

**A. Onboarding de la wallet — HU-01**

* Flujo guiado que muestre la secuencia de pasos requeridos y el paso actual en todo momento.
* Validación de información obligatoria y datos inválidos; bloquear el avance y explicar cómo corregirlos.
* Al completar el onboarding, cambiar el estado de la wallet a `ACTIVE` y habilitar la entrada a pagos de bajo monto.
* Registrar eventos de inicio del onboarding, finalización de cada paso y cierre del flujo.
* Preparar la instrumentación que permita medir la duración del onboarding, contar nuevos usuarios activos mensualmente y atribuir gasto de adquisición para calcular CAC.

**B. Pago de bajo monto a contacto — HU-02**

* Antes de confirmar, mostrar claramente la identidad del destinatario y el importe.
* Validar el límite de monto aplicable al proveedor/canal antes de enviar el pago. La regla concreta de “monto bajo” es una pregunta abierta para PO/Producto; no se inventará un umbral.
* Contemplar estados asíncronos: un estado como `PENDING` debe mostrarse como pendiente/procesando y no como resultado terminal.
* Comunicar un único resultado terminal por intento: exitoso, fallido o expirado. Las etiquetas serán provisionales hasta que Producto las valide.
* Si el pago es exitoso, mostrar la referencia de transacción y conservarlo en el historial.
* Si falla o expira, ofrecer una acción clara para reintentar o volver, sin crear cobros duplicados.
* Emitir el evento de activación del pagador tras una transacción exitosa y registrar los eventos necesarios para medir el funnel de checkout.

**C. Requisitos transversales de la épica que aplican a HU-01/HU-02**

* Priorizar baja fricción en el onboarding y claridad desde el inicio del pago hasta la confirmación.
* No asumir que todo el ecosistema procesa pagos por un único riel: para la demo se puede utilizar el mock asignado, documentando esa limitación técnica.
* Considerar que los límites pueden variar por proveedor/canal; la validación del importe debe ocurrir antes del envío.
* Representar correctamente las transiciones asíncronas y no comunicar como definitivo un pago que sigue pendiente, protegiendo la confianza del usuario y la expectativa operativa de pagos inmediatos con alias (24x7x365).
* Dejar instrumentación base para medir finalización de onboarding, caída en checkout y activación del pagador. Las metas de negocio requieren datos de cohorte posteriores al lanzamiento.

**D. Extensión propia del caso de uso: colecta escolar**

* Mostrar una colecta de demostración con una meta, aportes vinculados y total confirmado.
* Sumar al total solo los pagos exitosos asociados a esa colecta, sin contabilizar los pendientes o fallidos ni duplicar un pago.
* Calcular el porcentaje de avance de la meta. Esta extensión se implementará solo si no pone en riesgo los criterios oficiales de HU-01 y HU-02.

### Fuera del alcance

* Despliegue multipaís amplio dentro de esta épica.
* Programas avanzados de lealtad o mecánicas de crecimiento no esenciales para el MVP.
* Paridad funcional completa entre todos los proveedores y bancos externos desde el primer día; se trabajará con los mocks y contratos disponibles para la demo.
* Exposición de APIs de pago abiertas y autoservicio para terceros.
* Gestión integral de la promoción escolar: presupuesto general, proveedores, contratos, gastos y rendición de cuentas.
* Administración de varias colectas con reglas, responsables y permisos avanzados; el prototipo se centrará en una colecta de demostración.
* Recordatorios automáticos, campañas masivas, votaciones, comentarios y otras funciones sociales de la promoción.
* Reportes contables avanzados, exportaciones contables y conciliación completa; se mostrará únicamente el resumen básico necesario para la demo.
* Automatizaciones de cobro, penalizaciones o clasificación de las familias según sus aportes.

### Decisiones pendientes con PO/Producto y mentor

* Confirmar el umbral de monto bajo por proveedor/canal.
* Confirmar la definición oficial de los eventos/timestamps de inicio y fin del onboarding y los eventos que delimitan el funnel de checkout.
* Validar las etiquetas visibles de estados terminales de pago.
* Confirmar por separado con el mentor el alcance general del reto para las otras historias. Este documento detalla solo HU-01 y HU-02 y no incorpora criterios de aceptación de las demás HUs.
* Confirmar qué datos estarán disponibles para instrumentar gasto de adquisición/CAC y el reporte mensual de MAU.

\---

# 2\. Punto 2 — ¿Qué roles vamos a tener?

El equipo trabajará con cinco roles: **PO, Arquitecto, AI Engineer, Testing y Security**. El AI Engineer asumirá tanto las tareas de desarrollo como las relacionadas con IA.

## 2.1 Product Owner (PO)

* Define el problema, el usuario principal y el valor esperado.
* Prioriza las historias y mantiene claro el alcance.
* Define y valida los criterios de aceptación con el equipo.
* Resuelve dudas funcionales y coordina las decisiones de alcance con el mentor.

## 2.2 Arquitecto

* Revisa el repositorio, la arquitectura existente y el contrato del mock.
* Define cómo se conectan la interfaz, el backend, la wallet, los pagos y el módulo de colecta.
* Establece decisiones técnicas y ayuda a evitar complejidad innecesaria.
* Verifica que la solución sea ejecutable y demostrable dentro del tiempo disponible.

## 2.3 AI Engineer (desarrollo e IA)

* Implementa la interfaz y la lógica funcional priorizada por el equipo.
* Integra los endpoints del mock según el contrato disponible.
* Desarrolla el flujo de onboarding, el pago a contacto y, si el flujo principal está estable, el panel básico de colecta.
* Utiliza herramientas de IA para apoyar la implementación, análisis y resolución de problemas.
* Prepara instrucciones y contexto claros para las tareas que se deleguen a la IA y revisa críticamente el código generado antes de integrarlo.
* Corrige errores y mantiene el código integrado y ejecutable.

## 2.4 Testing

* Diseña y ejecuta pruebas para los criterios de aceptación de HU-01 y HU-02.
* Valida el onboarding guiado, la validación de datos, la activación de la wallet y el acceso a pagos.
* Prueba los resultados exitoso, fallido y expirado, las transiciones asíncronas y las acciones de reintento o retorno.
* Comprueba que una misma operación no se contabilice dos veces.
* Registra evidencias reproducibles y verifica que solo los pagos exitosos se sumen al total de la colecta.

## 2.5 Security

* Revisa el manejo de datos y la configuración de la aplicación.
* Comprueba que no se incluyan credenciales, secretos ni datos personales reales.
* Revisa controles de acceso y validaciones relevantes para el alcance.
* Ayuda a revisar los riesgos de pagos duplicados, errores de estado y mensajes que puedan confundir al usuario.
* Verifica que los estados y errores no se presenten de forma engañosa.

## 2.6 Colaboración entre roles

* El PO define qué se debe construir y cómo se aceptará.
* El Arquitecto define la solución técnica y sus integraciones.
* El AI Engineer implementa las funcionalidades y utiliza IA como apoyo, revisando lo generado.
* Testing prueba cada incremento con base en los criterios de aceptación y registra evidencia.
* Security revisa los riesgos y controles durante el desarrollo.

Los roles pueden colaborar en una misma tarea, pero cada uno debe tener una responsabilidad principal clara.
---

# 3\. Punto 3 — Actividades del Sprint 1 y Sprint 2

Según el cronograma del Día 5:

* **Sprint 1:** 10:15–12:30.
* **Sprint 2:** 13:45–15:15.

## 3.1 Sprint 1 — Construir el flujo principal

**Horario:** 10:15–12:30

**Objetivo:** construir el recorrido funcional principal de HU-01 y HU-02 respetando sus criterios, sin intentar todavía resolver todos los indicadores de negocio de un lanzamiento real.

|Actividad|Responsable principal|Entregable|
|-|-|-|
|Revisar repositorio, historias, contrato y URL del mock|Arquitecto + PO|Contrato y alcance confirmados|
|Definir pasos de onboarding, validaciones y eventos analíticos|PO + AI Engineer|Flujo HU-01 especificado|
|Implementar onboarding guiado, paso actual y errores accionables|AI Engineer|HU-01: el usuario sabe en qué paso está y cómo corregir datos inválidos|
|Activar wallet al completar el onboarding y habilitar entrada a pagos|AI Engineer|HU-01: wallet `ACTIVE` y entrada a pagos habilitada|
|Implementar pantalla previa al pago con destinatario y monto|AI Engineer|HU-02: destino y monto visibles antes de confirmar|
|Conectar pago a contacto, consultar estado, referencia e historial|AI Engineer|HU-02: flujo de pago conectado al mock|
|Ejecutar pruebas de la ruta feliz y registrar evidencias|Testing + Security|Evidencia de aceptación funcional|

### Entregable al terminar el Sprint 1

Una versión ejecutable que permita:

1. Mostrar los pasos del onboarding y el paso actual.
2. Bloquear datos obligatorios ausentes o inválidos y explicar cómo corregirlos.
3. Completar el onboarding, dejar la wallet en `ACTIVE` y habilitar el acceso a pagos de bajo monto.
4. Mostrar el destinatario y el monto antes de confirmar una transferencia.
5. Crear un pago simulado y consultar su estado; cuando sea exitoso, mostrar la referencia y conservarlo en el historial.

La prioridad es lograr primero un recorrido funcional alineado con los criterios principales de HU-01 y HU-02. La instrumentación analítica, los límites por proveedor/canal y los casos de excepción se completarán y probarán en el Sprint 2. Las demás HUs no se incorporan a este alcance detallado.

## 3.2 G2 — Scope Check

**Horario:** 13:30–13:45

Antes de iniciar el segundo sprint, revisaremos:

* Si el flujo W1 → W2 funciona de principio a fin.
* Si el alcance sigue siendo viable.
* Qué errores o bloqueos debemos resolver.
* Si el mentor exige alguna cobertura adicional de otras historias fuera de este plan de HU-01/HU-02.
* Qué funcionalidades adicionales pueden completarse sin poner en riesgo la demo.

## 3.3 Sprint 2 — Robustecer, completar y preparar la demostración

**Horario:** 13:45–15:15

**Objetivo:** completar la instrumentación analítica y cubrir los estados, validaciones y errores definidos por HU-01/HU-02. El panel de colecta es secundario frente a esos requisitos oficiales.

|Actividad|Responsable principal|Entregable|
|-|-|-|
|Registrar inicio de onboarding, finalización de cada paso y cierre del flujo|AI Engineer|Eventos HU-01 disponibles para analítica|
|Definir y probar las marcas de tiempo de inicio/fin del onboarding|PO + Testing|Definición documentada de medición; frontera pendiente de confirmar con producto|
|Validar la regla de monto bajo por proveedor/canal antes del envío|AI Engineer + Arquitecto|Validación previa al pago y regla configurable/documentada|
|Manejar transiciones asíncronas hasta el resultado terminal|AI Engineer|Pago con estado final comunicado correctamente|
|Probar resultado exitoso, fallido y expirado|Testing|Evidencia de un único resultado terminal por intento|
|Validar referencia e historial para pago exitoso|Testing|Prueba HU-02 de referencia e historial persistido|
|Validar acción clara de reintentar/volver sin duplicar cargos|AI Engineer + Testing + Security|Pruebas de fallo/expiración e idempotencia|
|Emitir evento de activación del pagador tras transacción exitosa|AI Engineer|Evento requerido para MAU instrumentado|
|Implementar panel de colecta si los criterios oficiales están estables|AI Engineer + PO|Meta y total de pagos exitosos vinculados a la colecta|
|Actualizar documentación y evidencias|PO + Arquitecto + Testing|README, decisiones y resultados de pruebas|

### Entregable al terminar el Sprint 2

Una demo que permita verificar:

* HU-01: onboarding guiado; paso actual visible; validación de datos incompletos/incorrectos con mensajes accionables; wallet activa y entrada a pagos al completar; eventos de analítica del flujo.
* HU-02: identidad del destinatario y monto visibles antes de confirmar; validación de monto antes del envío; transición de estado contemplada; resultado terminal único (exitoso, fallido o expirado); referencia e historial en caso exitoso; acción de reintento o retorno sin duplicar cargos en fallo/expiración.
* Eventos analíticos necesarios para inicio/pasos/cierre del onboarding, funnel de checkout y activación del pagador, con estructura revisable para el reporte.
* Panel básico de la colecta únicamente si no compromete los criterios oficiales de la épica y HU-01/HU-02.
* Pruebas y evidencias reproducibles de cada criterio funcional incluido en la demo.



## 3.4 Freeze

Antes del freeze debemos tener:

* Una versión estable del código.
* README actualizado.
* Arquitectura e instrucciones para ejecutar la solución.
* Evidencias de las pruebas.
* Una demo reproducible sin depender de cambios de último minuto.

\---

# 4\. Criterios de aceptación y éxito alineados con la épica, HU-01 y HU-02

Es importante separar **criterios funcionales verificables durante el hackathon** de **indicadores de éxito de negocio que solo pueden medirse tras el lanzamiento**. No afirmaremos haber logrado las metas de tres meses con una demo de un día; en el hackathon verificaremos el comportamiento funcional y que la instrumentación necesaria esté implementada o claramente documentada.

## 4.1 HU-01 — Registro y activación del MVP de wallet

|ID|Criterio de aceptación de HU-01|Cómo lo probaremos en la demo|Evidencia esperada|
|-|-|-|-|
|HU1-AC1|El onboarding muestra la secuencia de pasos requeridos y el paso actual en todo momento.|Avanzar paso por paso y comprobar que la interfaz identifica el paso activo.|Captura o vídeo del recorrido y prueba de UI.|
|HU1-AC2|Si falta información obligatoria o hay datos inválidos, se bloquea el avance y se muestra un mensaje accionable.|Omitir un campo obligatorio e ingresar un dato inválido.|La pantalla no avanza y explica qué corregir.|
|HU1-AC3|Al finalizar correctamente, la wallet cambia a activa y el usuario puede acceder al punto de entrada de pagos de bajo monto.|Completar el onboarding con datos de prueba y abrir el acceso a pagos.|Estado `ACTIVE` y acceso a pagos visible/funcional.|
|HU1-AC4|Se registran eventos de inicio, finalización de cada paso y cierre del onboarding.|Ejecutar un onboarding completo y revisar los eventos/logs generados.|Eventos de inicio, pasos completados y cierre presentes con marca de tiempo.|
|HU1-AC5|La mediana de finalización baja de 8 minutos a 3 minutos en el trimestre posterior al lanzamiento.|No es medible con una única demo; comprobar que pueden capturarse los tiempos necesarios.|Instrumentación y definición del cálculo documentadas; resultado real pendiente de datos de cohorte.|
|HU1-AC6|La analítica mensual permite contar nuevos usuarios activos y atribuir gasto de adquisición para verificar MAU 1,000–2,000 y CAC de PEN 10 en los primeros 3 meses.|Revisar que el esquema de eventos y el reporte incluyan los campos/fuentes necesarios, sin afirmar resultados reales.|Estructura del reporte y fuentes necesarias documentadas.|

**Contexto y supuestos a respetar en HU-01**

* Los requisitos de KYC y documentos deben ser definidos por Cumplimiento y Producto antes de implementación. Para el hackathon se utilizarán únicamente los escenarios y datos de prueba disponibles en el mock; no inventaremos requisitos de KYC adicionales.
* Las metas MAU de 1,000–2,000 y CAC de PEN 10 fueron definidas por el PO; son indicadores de negocio y no un criterio que podamos declarar cumplido por la demo.
* La HU deja abierta la frontera oficial para medir duración del onboarding. Producto debe definir qué eventos/timestamps representan inicio y fin. Hasta entonces, la instrumentación se documentará como propuesta, no como definición aprobada.

## 4.2 HU-02 — Confirmación de pagos de bajo monto

|ID|Criterio de aceptación de HU-02|Cómo lo probaremos en la demo|Evidencia esperada|
|-|-|-|-|
|HU2-AC1|Antes de confirmar, la pantalla muestra la identidad del destino y el monto de la transferencia.|Preparar un pago y detenerse en la pantalla previa a confirmar.|Destinatario e importe visibles antes de ejecutar el pago.|
|HU2-AC2|El pagador recibe un único resultado terminal por intento: exitoso, fallido o expirado.|Ejecutar escenarios disponibles del mock y revisar cómo se muestran los resultados.|Cada intento termina con un único estado terminal comunicado al usuario. Un estado intermedio, como pendiente, no se trata como terminal.|
|HU2-AC3|Si el pago es exitoso, se muestra una referencia de transacción y queda persistido en el historial.|Ejecutar un pago exitoso y revisar el detalle y el historial.|Referencia visible y pago recuperable desde el historial.|
|HU2-AC4|Si el pago falla o expira, se muestra una siguiente acción clara (reintentar o volver) sin crear cobros duplicados.|Simular fallo/expiración y probar el camino de reintento o retorno.|Acción clara; reutilización de clave idempotente cuando se reintenta la misma operación; no aparece un segundo cargo.|
|HU2-AC5|La caída de checkout baja de 30% a 8% durante el trimestre posterior al lanzamiento.|No es medible en la demo sin una cohorte real; comprobar que se registren eventos/datos para calcular el indicador.|Eventos y definición de checkout documentados; resultado real pendiente de datos posteriores al lanzamiento.|
|HU2-AC6|Las transacciones exitosas emiten el evento de activación del pagador usado para calcular MAU (objetivo 1,000–2,000 en meses 1–3).|Completar una transacción exitosa y revisar el evento emitido.|Evento de activación del pagador presente y documentado. MAU real pendiente de datos de cohorte.|

**Contexto y supuestos a respetar en HU-02**

* El límite de monto puede variar por proveedor/canal. La validación del importe debe ocurrir antes de enviar la solicitud. La regla concreta de “monto bajo” por proveedor/canal sigue siendo una pregunta abierta para Producto/PO y no se debe inventar.
* La confirmación debe contemplar transiciones asíncronas. Un estado intermedio como `PENDING` debe mostrarse como pendiente/procesando y no como resultado terminal; cuando se resuelva, comunicar el resultado final correspondiente.
* Las etiquetas finales visibles al usuario quedan por definir con Producto. Para la demo se pueden usar etiquetas provisionales —exitoso, fallido y expirado— claramente identificadas como pendientes de validación por Producto.
* Los objetivos MAU de 1,000–2,000 y CAC de PEN 10 fueron definidos por el PO. HU-02 exige emitir el evento de activación del pagador; no significa que la demo deba demostrar por sí sola el cumplimiento de la meta MAU.

## 4.3 Requisitos transversales de la épica aplicables solo a HU-01 y HU-02

La épica establece objetivos y restricciones que se conectan directamente con el onboarding (HU-01) y la confirmación de pagos de bajo monto (HU-02). No se incluyen aquí requisitos de QR/comercios ni de otras historias.

|ID|Requisito aplicable|Cómo lo probaremos en el hackathon|Evidencia esperada|
|-|-|-|-|
|EP-HU1\_2-01|La experiencia debe reducir fricción en onboarding y checkout.|Recorrer el onboarding y el pago con datos de prueba; documentar los pasos y tiempos medidos en la demo, sin extrapolarlos a una cohorte de lanzamiento.|Secuencia funcional, errores accionables y medición de duración/funnel instrumentada.|
|EP-HU1\_2-02|Los límites de monto pueden variar por proveedor/canal y deben validarse antes del envío.|Probar un monto admitido y, si el mock/contrato permite, uno rechazado por límite; si la regla no está definida, dejar el punto documentado para PO/Producto.|Validación previa al envío y regla/configuración documentada o pregunta abierta explícita.|
|EP-HU1\_2-03|No asumir un único riel de procesamiento en la arquitectura.|Revisar que la lógica de pago esté separada del adaptador/mock y que la demo declare qué mock usa.|Decisión de arquitectura documentada; no se afirma paridad completa de proveedores.|
|EP-HU1\_2-04|Las transiciones asíncronas deben comunicarse claramente, respetando la expectativa de pagos inmediatos.|Simular un estado intermedio y verificar que se presenta como pendiente/procesando hasta recibir resultado final.|La UI no muestra éxito/fallo definitivo mientras el pago siga pendiente.|
|EP-HU1\_2-05|La instrumentación base permite medir onboarding, checkout y activación.|Revisar eventos de onboarding y evento de activación tras el pago exitoso; comprobar la disponibilidad de datos para métricas.|Eventos y estructura de reporte documentados; las metas de negocio quedan pendientes de datos posteriores al lanzamiento.|

La épica fija para el lanzamiento los objetivos de bajar la mediana del onboarding de 8 a 3 minutos, reducir la caída en checkout del 30% al 8%, mantener MAU entre 1,000 y 2,000 y conseguir CAC de PEN 10. En un hackathon de un día no se pueden declarar cumplidos esos resultados trimestrales: se demuestra la funcionalidad y se deja preparada la instrumentación para medirlos.

## 4.4 Criterios propios de la extensión “colecta escolar”

Estos criterios **no pertenecen a las HU-01 ni HU-02**. Son una extensión del prototipo y se implementarán solo después de cubrir los criterios oficiales priorizados.

|ID|Criterio de la extensión|Prueba|Evidencia esperada|
|-|-|-|-|
|COL-01|La persona organizadora puede ver la meta de la colecta y los aportes registrados.|Abrir el panel con datos sintéticos.|Meta y listado/resumen visibles.|
|COL-02|Solo los pagos confirmados como exitosos se suman al total reunido.|Comparar el total antes y después de pagos exitosos, pendientes y fallidos.|Pendientes/fallidos no incrementan el total; éxito lo incrementa una sola vez.|
|COL-03|El porcentaje de avance se calcula usando total exitoso/meta.|Probar con valores conocidos (p. ej., S/ 1,200 de S/ 3,000).|Se muestra 40% con cálculo verificable.|

## 4.5 Criterios de éxito del hackathon

La demo se considerará exitosa si podemos mostrar y adjuntar evidencia de:

1. **HU-01 funcional:** pasos del onboarding y paso actual visibles; validación bloqueante con mensajes accionables; wallet en `ACTIVE` y acceso a pagos tras finalizar correctamente.
2. **HU-01 instrumentada:** eventos de inicio, finalización de cada paso y cierre del onboarding; estructura para medir la duración y el reporte mensual de nuevos usuarios activos/atribución de adquisición.
3. **HU-02 funcional:** destinatario y monto visibles antes de confirmar; validación de monto antes del envío; manejo de estados asíncronos; un único resultado terminal por intento; referencia e historial cuando el pago sea exitoso; opción clara de reintentar o volver ante fallo/expiración sin duplicar el cargo.
4. **HU-02 instrumentada:** evento de activación del pagador después de una transacción exitosa y datos/eventos suficientes para calcular la caída en checkout.
5. **Épica aplicada solo a HU-01/HU-02:** se documenta que la arquitectura no debe asumir un único riel, que el límite por proveedor/canal se valida antes del envío y que los estados asíncronos no se presentan como definitivos.
6. **Instrumentación del MVP:** están disponibles y verificables los eventos de onboarding, funnel de checkout y activación del pagador necesarios para calcular duración de onboarding, caída en checkout, MAU y CAC.
7. **Metas de negocio correctamente tratadas:** las metas de 8→3 minutos, checkout 30%→8%, MAU 1,000–2,000 y CAC PEN 10 se documentan como métricas de lanzamiento/primer trimestre, no como logros probados por la demo.
8. **Extensión escolar:** si queda tiempo después de cubrir HU-01, HU-02 y los requisitos de épica que les aplican, se pueden cumplir COL-01 a COL-03.

> \*\*No declarar como logrados durante el hackathon\*\* el lanzamiento del MVP dentro de un trimestre ni los objetivos de negocio (mediana de onboarding de 8→3 minutos, caída de checkout de 30%→8%, MAU de 1,000–2,000 y CAC de PEN 10). Son resultados que se evalúan durante el lanzamiento y los primeros tres meses posteriores; durante el hackathon debemos dejar preparada la instrumentación y documentadas las definiciones de medición.

\---

# 5\. Preguntas para el mentor en el G1

1. ¿Cuál es la regla inicial de monto bajo por proveedor/canal que debemos aplicar en HU-02?
2. ¿Qué eventos o timestamps definen oficialmente el inicio y fin del onboarding y las etapas del funnel de checkout?
3. ¿Qué etiquetas finales deben mostrarse para los estados terminales exitoso, fallido y expirado?
4. ¿Qué datos estarán disponibles para atribuir gasto de adquisición y calcular CAC?
5. ¿Podemos implementar la gestión de la colecta como una extensión propia después de completar los criterios de HU-01 y HU-02?
6. ¿Qué cobertura de las demás historias requiere el reto general? La respuesta se registrará por separado y no se incorporará automáticamente a este alcance de HU-01/HU-02.

\---

# 6\. Checklist para el G1

* \[ ] Alcance alineado solo con la parte de la épica aplicable a HU-01 y HU-02: onboarding de baja fricción, pagos de bajo monto, estados claros, límites por proveedor/canal e instrumentación.
* \[ ] No se incorporan requisitos de QR ni de otras HUs en el alcance o en los criterios de aceptación de este documento.
* \[ ] Extensión de colecta identificada como funcionalidad secundaria, posterior a los criterios oficiales de HU-01 y HU-02.
* \[ ] Fuera de alcance identificado: despliegue multipaís, lealtad avanzada, paridad completa entre proveedores, APIs abiertas y gestión escolar integral.
* \[ ] Preguntas al mentor preparadas sobre el límite de monto, los eventos analíticos, las etiquetas de estado y la medición de métricas.
* \[ ] Roles y responsabilidades asignados.
* \[ ] Actividades y entregables del Sprint 1 definidos.
* \[ ] Actividades y entregables del Sprint 2 definidos.
* \[ ] Metas de negocio diferenciadas de los criterios funcionales que sí pueden verificarse durante la demo.

\---

# 7\. Guion breve para explicar la propuesta al mentor

> Nuestro caso de uso de demostración es una colecta voluntaria para una promoción escolar. Este plan cubre solo HU-01 y HU-02 y toma de la épica los requisitos que les corresponden: onboarding de baja fricción, pago de bajo monto, confirmación clara de estados, validación de límites por proveedor/canal e instrumentación de onboarding, checkout y activación. El panel de colecta será una extensión si no pone en riesgo esos criterios oficiales. No estamos incorporando aquí requisitos de las otras historias.
>
> Hemos definido los roles y dividido el trabajo en dos sprints: primero construiremos el flujo de extremo a extremo; después reforzaremos las excepciones, las pruebas, la documentación y la demo. Cualquier requisito global adicional del reto se registrará por separado y no se incorporará automáticamente al alcance ni a los criterios de HU-01 y HU-02.

## Recomendación final

No intentemos construir una billetera completa y una plataforma de recaudación compleja al mismo tiempo. Primero aseguremos el flujo funcional de registro y pago; después conectemos ese pago al panel de la colecta. Así tendremos una demo más coherente, comprobable y fácil de explicar.

