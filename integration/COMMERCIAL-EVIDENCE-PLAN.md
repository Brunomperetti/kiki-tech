# KIKI — Plan comercial por evidencias (PR #187)

Esta fase conecta **documentación revisada** con la operación comercial
para grupos de hasta 20 variantes provenientes exclusivamente de Ecomm-App API.

## Función nueva

**Mi catálogo → Operaciones → Plan comercial desde evidencias**

- Selecciona entre 1 y 20 Ecomm ID existentes en la captura API completa.
- KIKI aplica el MISMO control de evidencias, identidad, contradicciones y
  revisiones de la cola editorial que ya existe.
- Informa, por variante: siguiente tarea prioritaria, hechos aprobados vigentes,
  nombres de campos comerciales que pueden recibir una propuesta, campos
  sin respaldo suficiente, revisión mensual vencida y bloqueos documentales.
- Los estados priorizan: **resolver identidad** → **buscar fuente** →
  **revalidar** → **aprobar hechos** → **generar propuesta respaldada** →
  **revisar contenido y multimedia**.
- Abre directamente la ficha o el expediente documental de cada producto.
- Es una vista **sin escrituras**: no genera borradores, no aprueba hechos,
  no usa OpenAI ni publica cambios en Ecomm-App, ML o Tiendanube.

## Mejora del generador existente

Cuando **nombre y presentación estén aprobados**, KIKI puede construir
también descripción corta, descripción larga y meta-descripción SEO básicas,
usando solo esos fragmentos documentados. Antes la ausencia de atributos
impedía generar cualquiera de estos textos. La propuesta queda en borrador
y requiere revisión humana para su aceptación.

La nueva descripción no inventa beneficios, ingredientes, salud, tamaños,
categorías o medios. Si no existen características verificadas, el motor
muestra expresamente que la redacción es básica y debe enriquecerse.
Se mantiene el límite de caracteres y las referencias a hechos originales.

**No es un generador IA de redacción expresiva avanzada.** La futura
generación con IA requiere un contrato de contenido, cuotas limitadas,
verificación de frases contra evidencia aprobada y consentimiento expreso
antes de cualquier uso de API paga.

## Falta para el alcance contractual completo

1. Confirmar sitemap/autorización de al menos un fabricante real.
2. Aplicar la migración de la cola documental tras respaldo restaurable
   y validar piloto de incorporación; flags continúan apagados.
3. Desarrollar extracción fiable de características, ingredientes,
   formatos, taxonomía y medios con derechos de uso.
4. Generar propuestas expresivas (eventualmente con IA) **solo** desde
   hechos aprobados y con controles de gasto por lote.
5. Aprobación por operador, preparación por canal y auditoría mensual.

## Validación

- `backend/tests/test_documental_commercial_plan.py` comprueba
  la redacción estrictamente respaldada, prioridad de bloqueos,
  límites de selección, liberación del contexto y cero escrituras.
- CI completa backend/frontend y PostgreSQL 18.
- Sin migraciones ni variables nuevas para esta función.
