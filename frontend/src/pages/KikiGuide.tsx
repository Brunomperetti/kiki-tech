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
      'Ingresá a Catálogo por API y mirá la fecha de la última captura completa de Ecomm-App.',
      'Si necesitás datos recientes, elegí «Actualizar catálogo ahora», confirmá y observá el progreso; no hace falta abrir GitHub.',
      'La renovación automática está prevista dos veces por día. Mercado Libre y Tiendanube se actualizan por separado.',
      'Si un dato no figura en la copia API, no asumas que falta en el producto real.'
    ],
    check:'Puedo identificar qué dato proviene de la API y qué dato es histórico.',
    caution:'El botón actualiza solamente la copia Ecomm-App en KIKI, nunca productos del proveedor. El stock no es en tiempo real.',
    action:'Abrir Catálogo por API',to:'/pilot'
  },
  {
    heading:'Encontrá qué productos necesitan trabajo',icon:'chart',
    intro:'Cola de mejoras combina las variantes de Ecomm-App API con candidatos de Mercado Libre API y Tiendanube CSV. Las fichas comerciales que KIKI todavía no empezó NO están vacías.',
    directions:[
      'Abrí Cola de mejoras y probá «Candidatos en TN», «Candidatos en ML» y «Conflictos de canales para verificar».',
      'Buscá por SKU, ID o nombre; mirá el motivo, cuántas filas comparten SKU y las referencias de cada canal.',
      'Una coincidencia por SKU es un candidato: compará producto, presentación, combo y fuentes antes de considerarla válida.'
    ],
    check:'Puedo encontrar un SKU y distinguir candidato, conflicto y falta de coincidencia en la copia.',
    caution:'«Sin SKU exacto en copia» NO significa «no publicado»; las capturas pueden estar desactualizadas.',
    action:'Abrir Cola de mejoras',to:'/queue'
  },
  {
    heading:'Prepará un lote pequeño sin gastar IA',icon:'layers',
    intro:'La primera etapa admite hasta tres productos simples por lote. Los packs y los casos de identidad ambigua requieren verificación específica antes de generar contenido.',
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
      'Revisá cuántas solicitudes nuevas se harían y el cupo diario antes de confirmar el consumo de IA.',
      'La IA puede reutilizar una propuesta vigente sin volver a consumir una solicitud.',
      'Cuando finaliza, el resultado muestra un enlace «Revisar propuesta» para cada SKU.'
    ],
    check:'Sé distinguir «Propuesta generada» de «Ficha comercial guardada».',
    caution:'No confíes automáticamente en ingredientes, beneficios, marcas, envases o cantidades. KIKI bloquea algunos errores, pero no reemplaza la verificación.',
    action:'Ver generación por lotes',to:'/queue'
  },
  {
    heading:'Revisá y corregí la ficha del producto',icon:'check',
    intro:'El Backoffice de productos guarda título completo y corto, descripciones, detalles, atributos, presentación, categorías, SEO, multimedia y fuentes originales. El ID y SKU de Ecomm-App quedan como referencia.',
    directions:[
      'Abrí una ficha desde la cola o buscala por SKU/ID dentro de Backoffice de productos.',
      'Revisá marca sugerida por evidencia y la propuesta KIKI AI. Usá cada título o descripción solo si coincide con datos verificables.',
      'Completá los seis bloques: identidad, contenido, posicionamiento, características, multimedia y fuentes.',
      'Adjuntá los enlaces oficiales de fabricante o documentá la etiqueta comprobada; nunca inventes un EAN.'
    ],
    check:'Separé los datos corroborados de las sugerencias de IA.',
    caution:'Copiar el texto sugerido al formulario NO lo guarda. No inventes GTIN ni contenido de packs.',
    action:'Abrir Mejorar productos',to:'/workspace'
  },
  {
    heading:'Guardá de verdad y comprobá el historial',icon:'check',
    intro:'Todo el contenido de una ficha se conserva en PostgreSQL cuando guardás. También podés dejarla «Lista para canales» cuando se completen los requisitos documentales.',
    directions:[
      'Elegí «Guardar borrador» si necesitás continuar otro día.',
      'Usá «Enviar a revisión interna» solo cuando la ficha tenga suficiente evidencia y esté lista para que otra persona la controle.',
      'Cuando se completen los controles editoriales, usá «Dejar lista para canales». Esa condición sigue siendo interna.',
      'Verificá el mensaje de guardado y el «Historial de ediciones». Podés cerrar y recuperar todos los campos.'
    ],
    check:'Veo el estado de la ficha, el porcentaje documental y una versión en su historial.',
    caution:'«Lista para canales» no publica automáticamente; la veracidad de las fuentes sigue requiriendo comprobación humana. Los cambios sin guardar se pierden.',
    action:'Abrir mis fichas guardadas',to:'/workspace'
  },
  {
    heading:'Retomá el trabajo sin repetirlo',icon:'clock',
    intro:'Al regresar, no tenés que comenzar desde cero: KIKI conserva las ediciones guardadas en PostgreSQL y las propuestas IA generadas como objetos separados.',
    directions:[
      'En Mejorar productos, seleccioná «Fichas guardadas» y filtrá por SKU, nombre o estado.',
      'En Cola de mejoras, usá «Borradores» para continuar el trabajo.',
      'Si ya generaste IA pero todavía no guardaste la ficha, abrí «Propuestas IA guardadas» y recuperala sin consumir otra solicitud.'
    ],
    check:'Puedo reabrir una ficha guardada y encontrar el texto y el historial.',
    caution:'Las propuestas IA pendientes no aparecen como «borradores» hasta que se copian, revisan y guarda la ficha.',
    action:'Recuperar propuestas IA generadas',to:'/propuestas-ia'
  },
  {
    heading:'Consultá canales sin confundir estados',icon:'store',
    intro:'La cobertura cruza Ecomm-App API, la última copia de Mercado Libre API y el CSV importado de Tiendanube. Ninguna coincidencia confirma por sí sola una publicación.',
    directions:[
      'Entrá a Canales de venta y revisá fechas y estado de las fuentes; una captura vieja sirve para investigar, no para confirmar ausencias actuales.',
      'La autorización de Mercado Libre debe hacerla el titular. Cuando esté conectada, usá «Actualizar publicaciones por API» para renovar la copia.',
      'Tiendanube usa el CSV importado y Ecomm-App únicamente su API. Guardar una ficha en KIKI no modifica los canales externos.'
    ],
    check:'Sé cuándo una comparación usa datos históricos y cuándo debo pedir una captura nueva.',
    caution:'No se puede publicar, modificar stock o sincronizar fichas hacia los canales desde este piloto.',
    action:'Abrir Canales de venta',to:'/channels'
  }
];

const glossary=[
  ['Catálogo por API','Consultar productos, SKU, ID y stock a la fecha de captura de Ecomm-App. No edita Ecomm-App.','/pilot'],
  ['Cola de mejoras','Encontrar candidatos ML/TN, conflictos entre canales y fichas comerciales pendientes. Un SKU coincidente no es un vínculo aprobado; el CSV exportado sirve solo para seguimiento.','/queue'],
  ['Backoffice comercial de productos','Crear fichas maestras completas: textos, atributos, categorías, SEO, imágenes/videos por URL y fuentes; guardar e historizar.','/workspace'],
  ['KIKI AI','Proponer títulos/descripciones. Una propuesta queda almacenada, pero no modifica la ficha hasta que la revisás y guardás.','/workspace'],
  ['Propuestas IA guardadas','Bandeja para recuperar lo generado, aunque hayas salido del lote. Entrá al editor para revisar y guardar los campos.','/propuestas-ia'],
  ['Casos para revisar','Diagnóstico entre capturas de Ecomm y Mercado Libre; no confirma vínculos ni publicaciones.','/cases'],
  ['Canales de venta','El titular conecta Mercado Libre, actualiza su copia API y consulta Tiendanube CSV. No se escribe a tiendas.','/channels#mercado-libre'],
  ['Herramientas y datos históricos','Legado separado; Ecomm-App trabaja exclusivamente por API, sin recurrir al Excel anterior.','/']
];

export function KikiGuide(){
  const [active,setActive]=useState(0);
  const step=steps[active];
  return <div className="kiki-guide">
    <header className="kiki-home-header">
      <div><p className="eyebrow">KIKI TECH · GUÍA INTERACTIVA</p>
        <h1>Aprendé KIKI mientras trabajás</h1>
        <p>Empezá con los datos disponibles, verificá coincidencias entre canales y
          guardá mejoras en KIKI. La generación con IA es opcional.</p>
      </div>
      <Link className="kiki-guide-home-link" to="/"><KikiIcon name="home" size={16}/> Ir a Inicio</Link>
    </header>

    <section className="kiki-guide-essential">
      <KikiIcon name="shield" size={25}/>
      <div><strong>Lo principal: el trabajo queda guardado cuando confirmás la ficha.</strong>
        <p>«Generar propuesta IA» conserva una propuesta interna y «Usar este título» solo
          la copia al formulario. <b>Para conservar los cambios de una ficha, pulsá
          «Guardar borrador», «Enviar a revisión interna» o «Dejar lista para canales».</b>
          Ninguna de estas acciones publica ni modifica el inventario externo.</p>
      </div>
    </section>

    <section className="kiki-guide-start" aria-label="Primera prueba en tres pasos">
      <div>
        <p className="eyebrow">PRIMERA PRUEBA · SIN COSTO DE IA NI PUBLICACIONES</p>
        <h2>Empezá por acá: tres acciones simples</h2>
        <p>No hace falta revisar todo el catálogo. Probá un producto y comprobá cómo KIKI conserva el trabajo.</p>
      </div>
      <div className="kiki-guide-start-grid">
        <Link to="/channels" className="kiki-guide-start-card">
          <span>01 · FUENTES</span><strong>Revisá de dónde salen los datos</strong>
          <small>Ecomm por API, última copia ML y CSV Tiendanube. Mirá las fechas.</small>
          <KikiIcon name="arrow-right" size={16}/>
        </Link>
        <Link to="/queue" className="kiki-guide-start-card">
          <span>02 · COINCIDENCIAS</span><strong>Elegí un caso real</strong>
          <small>Filtrá candidatos o conflictos y verificá SKU, presentación y canal.</small>
          <KikiIcon name="arrow-right" size={16}/>
        </Link>
        <Link to="/workspace" className="kiki-guide-start-card">
          <span>03 · GUARDADO</span><strong>Completá y guardá una ficha</strong>
          <small>Guardá un borrador, volvé a entrar y comprobá el historial.</small>
          <KikiIcon name="arrow-right" size={16}/>
        </Link>
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
        <p>Buscar en la cola → verificar fuentes → completar ficha y multimedia →
          guardar borrador → controlar completitud → dejar lista para canales → consultar historial.
          No hace falta terminar todo el catálogo para empezar.</p></div>
      <Link to="/queue">Empezar a trabajar <KikiIcon name="arrow-right" size={15}/></Link>
    </section>
  </div>
}
