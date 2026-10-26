import {useState} from 'react';
import {Link} from 'react-router-dom';
import {KikiIcon} from '../components/KikiIcon';
import '../guide.css';

type JourneyStep={
  heading:string;intro:string;action:string;to:string;icon:'home'|'layers'|'chart'|'sparkles'|'check'|'clock'|'store';
  directions:string[];check:string;caution:string;
};

const steps:JourneyStep[]=[
  {
    heading:'Entendé desde dónde lee KIKI',icon:'home',
    intro:'La fuente principal de identidad es una copia completa obtenida por API de Ecomm-App. La copia muestra la fecha de captura, no stock en vivo.',
    directions:[
      'Ingresá a Inicio y mirá el estado de Ecomm-App API y la fecha de captura.',
      'Los indicadores de Mercado Libre corresponden a una copia anterior mientras el titular no autorice una nueva conexión.',
      'Si un dato no figura en la copia API, no asumas que falta en el producto real.'
    ],
    check:'Puedo identificar qué dato proviene de la API y qué dato es histórico.',
    caution:'No uses el stock capturado como confirmación de inventario actual.',
    action:'Ir a Inicio',to:'/'
  },
  {
    heading:'Encontrá qué productos necesitan trabajo',icon:'chart',
    intro:'Cola de mejoras organiza las variantes de Ecomm-App y las ediciones guardadas en KIKI. Es un diagnóstico: los motivos se pueden superponer.',
    directions:[
      'Abrí Cola de mejoras y probá los filtros «Borradores» y «Simples aptos para IA».',
      'Usá el buscador por SKU, ID Ecomm o nombre. Cada resultado muestra por qué fue incluido.',
      'Podés seleccionar varios casos y exportar CSV para seguimiento; seleccionar NO guarda ni aprueba.'
    ],
    check:'Puedo localizar un producto o un borrador por SKU y abrir su ficha.',
    caution:'«GTIN no disponible en copia API» NO significa que el artículo carezca de EAN.',
    action:'Abrir Cola de mejoras',to:'/queue'
  },
  {
    heading:'Prepará un lote pequeño sin gastar IA',icon:'layers',
    intro:'La primera etapa admite hasta tres productos simples por lote. Los packs y los casos de identidad ambigua se excluyen de este piloto.',
    directions:[
      'En Cola de mejoras elegí «Ver solo productos simples aptos para IA».',
      'Marcá entre uno y tres productos, o usá «Elegir 3 simples de esta página».',
      'Pulsá «Preparar selección · sin costo IA». Revisá si hay propuestas reutilizables y cuántas solicitudes nuevas consumirías.'
    ],
    check:'Veo la cantidad de solicitudes y las fichas antes de decidir si genero.',
    caution:'Preparar no consume IA ni deja el lote aprobado. El límite actual es de 10 intentos por día UTC, contando errores.',
    action:'Preparar mi selección',to:'/queue'
  },
  {
    heading:'Generá propuestas IA (solo cuando haga falta)',icon:'sparkles',
    intro:'Cuando confirmás la generación, KIKI guarda propuestas de título y descripción. No las incorpora todavía a la ficha comercial.',
    directions:[
      'Leé el costo estimado del lote y confirmá únicamente si querés consumir esas solicitudes.',
      'La IA puede reutilizar una propuesta vigente sin volver a consumir una solicitud.',
      'Cuando finaliza, el resultado muestra un enlace «Revisar propuesta» para cada SKU.'
    ],
    check:'Sé distinguir «Propuesta generada» de «Ficha comercial guardada».',
    caution:'No confíes automáticamente en ingredientes, beneficios, marcas, envases o cantidades. KIKI bloquea algunos errores, pero no reemplaza la verificación.',
    action:'Ver generación por lotes',to:'/queue'
  },
  {
    heading:'Revisá y corregí la ficha del producto',icon:'check',
    intro:'Mejorar productos permite editar marca, título, descripción, GTIN propuesto y observaciones. El ID y SKU de Ecomm-App permanecen como referencia.',
    directions:[
      'Abrí una ficha desde la cola o buscala por SKU/ID dentro de Mejorar productos.',
      'Revisá marca sugerida por evidencia y la propuesta KIKI AI. Usá cada título o descripción solo si coincide con datos verificables.',
      'Dejá en «Observaciones y evidencia» lo que confirmaste y lo que falta comprobar.'
    ],
    check:'Separé los datos corroborados de las sugerencias de IA.',
    caution:'Copiar el texto sugerido al formulario NO lo guarda. No inventes GTIN ni contenido de packs.',
    action:'Abrir Mejorar productos',to:'/workspace'
  },
  {
    heading:'Guardá de verdad y comprobá el historial',icon:'check',
    intro:'Este es el paso más importante: los campos solo quedan persistidos en PostgreSQL al pulsar «Guardar borrador» o «Enviar a revisión interna».',
    directions:[
      'Elegí «Guardar borrador» si necesitás continuar otro día.',
      'Usá «Enviar a revisión interna» solo cuando la ficha tenga suficiente evidencia y esté lista para que otra persona la controle.',
      'Verificá el mensaje de guardado y el «Historial de ediciones». Podés cerrar, volver a entrar y recuperar los datos.'
    ],
    check:'Veo el estado «Borrador guardado» o «Lista para revisión» y una versión en el historial.',
    caution:'«Lista para revisión» NO significa aprobada ni publicada. Si cerrás sin guardar, perderás los cambios recientes.',
    action:'Abrir mis fichas guardadas',to:'/workspace'
  },
  {
    heading:'Retomá el trabajo sin repetirlo',icon:'clock',
    intro:'Al regresar, no tenés que comenzar desde cero: KIKI conserva las ediciones guardadas en PostgreSQL y las propuestas IA generadas como objetos separados.',
    directions:[
      'En Mejorar productos, seleccioná «Fichas guardadas» y filtrá por SKU, nombre o estado.',
      'En Cola de mejoras, usá «Borradores» para continuar el trabajo.',
      'Si ya generaste IA pero todavía no guardaste la ficha, buscá de nuevo el SKU y revisá la propuesta IA antes de usarla.'
    ],
    check:'Puedo reabrir una ficha guardada y encontrar el texto y el historial.',
    caution:'Las propuestas IA pendientes no aparecen como «borradores» hasta que se copian, revisan y guarda la ficha.',
    action:'Buscar fichas guardadas',to:'/workspace'
  },
  {
    heading:'Consultá canales sin confundir estados',icon:'store',
    intro:'Canales de venta muestra la situación de Mercado Libre y Tiendanube. La integración de escritura masiva aún no está habilitada.',
    directions:[
      'En Canales de venta distinguí la copia API de ML de la información Tiendanube importada por CSV.',
      'Los módulos de «Herramientas y datos históricos» siguen basados en importaciones antiguas y están separados del flujo nuevo por API.',
      'La publicación y los cambios de stock/precio requerirán integraciones y autorizaciones adicionales.'
    ],
    check:'Sé qué está preparado en KIKI y qué NO cambió en las tiendas.',
    caution:'No interpretes una coincidencia de SKU como publicación confirmada ni una propuesta de ficha como exportación lista.',
    action:'Abrir Canales de venta',to:'/channels'
  }
];

const glossary=[
  ['Catálogo por API','Consultar productos, SKU, ID y stock a la fecha de captura de Ecomm-App. No edita Ecomm-App.','/pilot'],
  ['Cola de mejoras','Ordenar pendientes, buscar, filtrar y seleccionar. El CSV es una lista de seguimiento, no una carga masiva.','/queue'],
  ['Mejorar productos','Cambiar datos editoriales dentro de KIKI, guardar borradores y consultar el historial.','/workspace'],
  ['KIKI AI','Proponer títulos/descripciones. Una propuesta queda almacenada, pero no modifica la ficha hasta que la revisás y guardás.','/workspace'],
  ['Casos para revisar','Diagnóstico entre capturas de Ecomm y Mercado Libre; no confirma vínculos ni publicaciones.','/cases'],
  ['Canales de venta','Ver fuentes de ML/Tiendanube. El CSV de TN y la copia ML no equivalen a sincronización en vivo.','/channels'],
  ['Herramientas y datos históricos','Módulos del sistema anterior basados en Excel/CSV. Mantenerlos separados del nuevo trabajo de Ecomm por API.','/']
];

export function KikiGuide(){
  const [active,setActive]=useState(0);
  const step=steps[active];
  return <div className="kiki-guide">
    <header className="kiki-home-header">
      <div><p className="eyebrow">KIKI TECH · GUÍA INTERACTIVA</p>
        <h1>Aprendé KIKI mientras trabajás</h1>
        <p>Un recorrido sencillo para Guillermo y Mercedes: de encontrar un producto a
          guardar las mejoras y recuperarlas otro día.</p>
      </div>
      <Link className="kiki-guide-home-link" to="/"><KikiIcon name="home" size={16}/> Ir a Inicio</Link>
    </header>

    <section className="kiki-guide-essential">
      <KikiIcon name="shield" size={25}/>
      <div><strong>Lo principal: el trabajo queda guardado cuando confirmás la ficha.</strong>
        <p>«Generar propuesta IA» guarda una propuesta interna; «Usar este título»
          solo la copia al formulario. <b>«Guardar borrador» o «Enviar a revisión interna»
          son los botones que conservan los campos de la ficha en PostgreSQL.</b>
          No se publica ni se modifica el inventario externo.</p>
      </div>
    </section>

    <section className="kiki-guide-wizard" aria-label="Recorrido interactivo">
      <div className="kiki-guide-step-heading">
        <div><p className="eyebrow">RECORRIDO GUIADO</p><h2>Seguí estos pasos</h2>
          <p>Elegí cualquier paso para ver cómo usar esa función.</p></div>
        <span>Paso {active+1} de {steps.length}</span>
      </div>
      <div className="kiki-guide-stepper" role="group" aria-label="Pasos de la guía">
        {steps.map((item,i)=><button type="button" key={item.heading}
          className={i===active?'active':''} aria-pressed={active===i}
          onClick={()=>setActive(i)}>
          <span>{i+1}</span>{item.heading}
        </button>)}
      </div>
      <article className="kiki-guide-current">
        <div className="kiki-guide-current-title">
          <span className="kiki-guide-current-icon"><KikiIcon name={step.icon} size={24}/></span>
          <div><p>ETAPA {active+1}</p><h3>{step.heading}</h3></div>
        </div>
        <p className="kiki-guide-intro">{step.intro}</p>
        <ol>{step.directions.map(item=><li key={item}>{item}</li>)}</ol>
        <div className="kiki-guide-verify"><KikiIcon name="check" size={18}/>
          <div><strong>Cómo sé que lo entendí</strong><p>{step.check}</p></div>
        </div>
        <div className="kiki-guide-warning"><KikiIcon name="alert" size={18}/>
          <div><strong>Atención</strong><p>{step.caution}</p></div>
        </div>
        <div className="kiki-guide-step-actions">
          <Link to={step.to} className="kiki-guide-step-open">{step.action}
            <KikiIcon name="arrow-right" size={17}/></Link>
          <div>
            <button type="button" disabled={active===0} onClick={()=>setActive(x=>x-1)}>Anterior</button>
            <button type="button" disabled={active===steps.length-1} onClick={()=>setActive(x=>x+1)}>
              Siguiente paso</button>
          </div>
        </div>
        <p className="kiki-guide-disclaimer">Este recorrido es una ayuda visual: no marca
          fichas como completadas ni guarda decisiones por vos.</p>
      </article>
    </section>

    <section className="kiki-guide-reference" aria-label="Qué hace cada función">
      <div><p className="eyebrow">CONSULTA RÁPIDA</p><h2>¿Para qué sirve cada sección?</h2>
        <p>Abrí cada explicación y entrá a la función cuando la necesites.</p></div>
      <div className="kiki-guide-reference-list">{glossary.map(([name,detail,path])=>
        <details key={name}><summary>{name}</summary>
          <p>{detail}</p>
          <Link to={path}>Abrir sección <KikiIcon name="arrow-right" size={14}/></Link>
        </details>)}</div>
    </section>
    <section className="kiki-guide-finish">
      <KikiIcon name="clock" size={24}/>
      <div><h2>Una forma simple de trabajar todos los días</h2>
        <p>Buscar en la cola → verificar fuente → obtener sugerencias si sirven →
          corregir → guardar borrador → comprobar historial → continuar otro día.
          No hace falta terminar todo el catálogo para empezar.</p></div>
      <Link to="/queue">Empezar a trabajar <KikiIcon name="arrow-right" size={15}/></Link>
    </section>
  </div>
}
