import { useState } from "react";
import "./user-guide.css";

const chapters = [
  {
    target: "catalog" as const,
    title: "1. Consultar y actualizar el catálogo",
    where: "Mi catálogo · Actualizar desde Ecomm-App",
    steps: [
      "Revisá la fecha de captura en la parte superior. Los datos de stock corresponden a esa captura, no al stock en vivo.",
      "Buscá por nombre, marca, SKU, EAN o Ecomm ID y pulsá Buscar. Usá Estado y siguiente paso para filtrar; podés combinar dos filtros.",
      "Si necesitás una nueva captura, guardá primero los cambios de cualquier ficha abierta. Pulsá Actualizar desde Ecomm-App y confirmá. Al finalizar, consultá la nueva fecha de captura.",
      "Cada fila representa una variante. Comprobá Ecomm ID y presentación antes de editar: un SKU o EAN repetido no identifica necesariamente el mismo producto.",
    ],
  },
  {
    target: "audit" as const,
    title: "2. Detectar productos que necesitan mejoras",
    where: "Auditoría real del inventario Ecomm-App · Mi catálogo",
    steps: [
      "Pulsá un indicador de códigos faltantes o repetidos, títulos breves u otras señales para ver los productos correspondientes.",
      "Desplegá Integridad de nombres, SKU y campos de origen para revisar inconsistencias de la captura.",
      "Abrí Campos pendientes en fichas editoriales iniciadas para localizar descripciones, categorías, atributos, imágenes, videos o SEO que requieren trabajo.",
      "Usá Limpiar filtro para volver al catálogo. Los indicadores pueden superponerse; no sumes sus cantidades como si fueran productos diferentes.",
    ],
  },
  {
    target: "Ficha" as const,
    title: "3. Editar y guardar una ficha comercial",
    where: "Mi catálogo → Ver ficha → Ficha",
    steps: [
      "Abrí Ver ficha en la variante elegida. Revisá Datos originales de Ecomm-App: son de solo lectura.",
      "En Ficha comercial editable de KIKI, completá los títulos, descripciones, detalles, características, presentación, marca, categoría, subcategoría y SEO que puedas respaldar.",
      "Registrá las referencias de imágenes o videos de esa misma variante y comprobá sus permisos de uso en Evidencias. Una URL pública no acredita una licencia.",
      "Pulsá Guardar borrador. Cuando termines de revisar, elegí el estado editorial correspondiente y pulsá Guardar estado editorial si está habilitado.",
      "Consultá Historial para comprobar la versión guardada. Estos cambios son internos: no modifican Ecomm-App ni publican en los canales.",
    ],
  },
  {
    target: "Evidencias" as const,
    title: "4. Incorporar y revisar información del fabricante",
    where: "Ver ficha → Evidencias → Documentos y evidencias",
    steps: [
      "Localizá una fuente oficial de la presentación exacta. Incorporá el original mediante las opciones de documento disponibles, o registrá su referencia para revisar.",
      "Compará el nombre, marca, presentación, código y tipo de venta con los datos originales de Ecomm-App. No reutilices automáticamente una fuente de otra variante o pack.",
      "Revisá procedencia e identidad en el expediente. Abrí Ver documento y ubicaciones verificables para comprobar el texto.",
      "Pulsá Extraer hechos del documento cuando esté disponible. Los candidatos quedan pendientes de revisión.",
      "Leé cada cita y usá Aprobar hecho solamente si la afirmación está respaldada y corresponde a la variante. Rechazá o dejá pendiente lo que no puedas comprobar.",
      "En Permisos de uso multimedia, registrá la autorización real de cada recurso. No inventes derechos ni datos ausentes.",
    ],
  },
  {
    target: "IA" as const,
    title: "5. Preparar textos y SEO desde evidencias",
    where: "Ver ficha → IA → Propuesta comercial desde evidencias",
    steps: [
      "Primero completá la revisión documental y aprobá los hechos verificables en Evidencias.",
      "Pulsá Generar propuesta respaldada. Este recorrido utiliza hechos aprobados vigentes sin necesidad de OpenAI.",
      "Compará cada propuesta con el valor actual y sus citas. Seleccioná únicamente los campos que quieras incorporar.",
      "Pulsá Guardar selección en ficha y confirmá. Los campos aceptados se guardan como borrador interno; no se publica.",
      "La opción Generar con IA desde hechos aprobados depende de la conexión con OpenAI y de la configuración autorizada. Si informa un error de autenticación, usá la propuesta respaldada y avisá al administrador.",
    ],
  },
  {
    target: "operations" as const,
    title: "6. Investigar fuentes y procesar lotes",
    where: "Mi catálogo → Seleccionar variantes → Operaciones",
    steps: [
      "Seleccioná hasta 20 variantes del mismo fabricante para un lote documental. Abrí Operaciones.",
      "Si está disponible, desplegá Preparar lote por URLs exactas (sin sitemap). Ingresá una línea por variante con Ecomm ID, URL HTTPS exacta y nota de procedencia, separados por punto y coma.",
      "Pulsá Guardar manifiesto de investigación. Este paso conserva la selección sin descargar páginas.",
      "Solo cuando las fuentes estén autorizadas y las descargas habilitadas, pulsá Procesar lote autorizado o Procesar siguiente fuente.",
      "Mantené abierto el panel para continuar el procesamiento. Podés Pausar después del paso actual, recuperar pasos vencidos sin descargar y reintentar fuentes cuando corresponda.",
      "Abrí el informe documental, revisá las excepciones y entrá en las evidencias de cada variante. Los hechos extraídos no se aprueban automáticamente; el guardado editorial sigue siendo individual.",
    ],
  },
  {
    target: "channels" as const,
    title: "7. Comparar Mercado Libre y Tiendanube",
    where: "Cobertura por canal · Ver ficha → Canales",
    steps: [
      "Consultá los indicadores de cobertura por canal y las diferencias de captura desde el dashboard.",
      "Abrí Ver análisis detallado y exportaciones por canal para consultar coincidencias, faltantes y discrepancias.",
      "En la ficha, entrá en Canales para revisar la evidencia disponible y confirmar que corresponde a esa variante.",
      "Sin evidencia del canal significa que KIKI no pudo acreditar una coincidencia en la captura disponible. No demuestra que el producto no exista en ese canal.",
      "Usá Preparación interna para publicar (requiere validación) para localizar fichas preparadas. No equivale a una publicación efectiva.",
    ],
  },
  {
    target: "history" as const,
    title: "8. Revisar cambios y mantener el catálogo",
    where: "Historial · Operaciones · Configuración",
    steps: [
      "Desde Historial o la pestaña Historial de una ficha, consultá los guardados y sus versiones.",
      "Revisá periódicamente los indicadores de cobertura, las fichas pendientes y las excepciones documentales; priorizá cambios de identidad, fuentes revocadas y revisiones vencidas.",
      "Usá las opciones de exportación disponibles para compartir pendientes con el equipo. Una exportación no certifica una revisión comercial.",
      "En Configuración o Conexiones, consultá el estado de las integraciones. Si una opción está deshabilitada, no fuerces el proceso: puede depender de permisos o configuración.",
    ],
  },
];

export type GuideTarget = (typeof chapters)[number]["target"];

export function UserGuide({ onNavigate }: { onNavigate: (target: GuideTarget) => void }) {
  const [query, setQuery] = useState("");
  const normalize = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const term = normalize(query.trim());
  const visible = chapters.filter(chapter =>
    normalize([chapter.title, chapter.where, ...chapter.steps].join(" ")).includes(term)
  );
  return (
    <details className="k-user-guide" id="guia-de-uso">
      <summary>Guía de uso · Aprendé a utilizar KIKI Tech 2.0</summary>
      <div className="k-user-guide-body">
        <p>Encontrá cada función, dónde está y cómo aplicarla. Podés abrir o cerrar esta guía sin cambiar la ficha ni el catálogo.</p>
        <label className="k-user-guide-search">
          Buscar en la guía
          <input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Ej.: SEO, EAN, lotes, imágenes" />
        </label>
        <div className="k-user-guide-grid">
          {visible.map(chapter => (
            <details key={chapter.title} className="k-user-guide-chapter">
              <summary>{chapter.title}</summary>
              <div className="k-user-guide-steps">
                <p><strong>Dónde:</strong> {chapter.where}</p>
                <ol>{chapter.steps.map(step => <li key={step}>{step}</li>)}</ol>
                <button type="button" className="k-user-guide-link" onClick={() => onNavigate(chapter.target)}>
                  {["Ficha", "Evidencias", "IA"].includes(chapter.target) ? "Ir al producto · seleccionar variante" : "Ir a esta función"}
                </button>
              </div>
            </details>
          ))}
        </div>
        {!visible.length && <p role="status">No encontramos ese término. Probá con otra palabra.</p>}
        <p className="k-user-guide-note"><strong>Importante:</strong> las acciones dependen de tus permisos y de las funciones habilitadas. Los lotes documentales requieren validación con productos reales; la revisión masiva de fichas, la IA a escala y la ejecución autónoma siguen en desarrollo. No hay publicación automática.</p>
      </div>
    </details>
  );
}
