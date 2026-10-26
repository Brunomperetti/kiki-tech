import type {EcommEditableFields,KikiAttribute,KikiMedia,KikiSource,KikiReadiness} from '../types/ecomm-app';
import '../commercial-backoffice.css';

export function assessCommercialReadiness(fields:EcommEditableFields):KikiReadiness{
  const keys:Array<keyof EcommEditableFields>= [
    'brand','title','short_title','short_description','description',
    'category','subcategory','presentation','seo_title','seo_description',
  ];
  const missing=keys.filter(k=>!String(fields[k]||'').trim()) as string[];
  if(!fields.attributes.some(x=>x.name.trim()&&x.value.trim()))missing.push('attributes');
  if(!fields.media.some(x=>x.kind==='IMAGE'&&x.url.startsWith('https://')))missing.push('images');
  if(!fields.sources.some(x=>x.kind==='FABRICANTE'||x.kind==='ETIQUETA'))missing.push('primary_source');
  if(!fields.seo_keywords.trim())missing.push('seo_keywords');
  const total=14;
  return {
    missing,ready:missing.length===0,completed:total-missing.length,
    total,percent:Math.round(100*(total-missing.length)/total),
    policy:'Completitud documental interna; las fuentes deben comprobarse y nada se publica.',
  };
}

type Props={
  fields:EcommEditableFields;
  onChange:<K extends keyof EcommEditableFields>(field:K,value:EcommEditableFields[K])=>void;
  readiness:KikiReadiness;
  categories:{name:string;count:number;subcategories:{name:string;count:number}[]}[];
};

const fieldNames:Record<string,string>={
  brand:'Marca comercial',title:'Título principal',short_title:'Título corto',
  short_description:'Descripción corta',description:'Descripción larga',
  category:'Categoría',subcategory:'Subcategoría',
  presentation:'Presentación',attributes:'Características técnicas',
  images:'Imagen del producto',primary_source:'Fuente primaria del fabricante o etiqueta',
  seo_title:'Título SEO',seo_description:'Metadescripción SEO',
  seo_keywords:'Palabras clave',
};
export function CommercialBackofficeFields({fields,onChange,readiness,categories}:Props){
  const editAttribute=(idx:number,key:keyof KikiAttribute,value:string)=>{
    onChange('attributes',fields.attributes.map((a,i)=>i===idx?{...a,[key]:value}:a));
  };
  const editMedia=(idx:number,key:keyof KikiMedia,value:string)=>{
    onChange('media',fields.media.map((a,i)=>i===idx?{...a,[key]:value}:a) as KikiMedia[]);
  };
  const editSource=(idx:number,key:keyof KikiSource,value:string)=>{
    onChange('sources',fields.sources.map((a,i)=>i===idx?{...a,[key]:value}:a) as KikiSource[]);
  };
  return <div className="kiki-commercial">
    <div className="kiki-commercial-overview" role="status">
      <div><strong>Ficha comercial central de KIKI</strong>
        <p>Todos los campos se guardan en KIKI y quedan asociados al ID de variante de Ecomm-App.
          No se envían a ningún canal hasta que exista un proceso de publicación autorizado.</p></div>
      <div className="kiki-commercial-score"><strong>{readiness.percent}%</strong><span>Completitud documental</span></div>
      <div className="kiki-commercial-meter" aria-label={readiness.percent+'% de la ficha completa'}>
        <span style={{width:readiness.percent+'%'}}/>
      </div>
    </div>

    <section className="kiki-commercial-section">
      <div className="kiki-commercial-section-head"><span>01</span><div><h3>Identidad y presentación</h3>
        <p>Nombre comercial y presentación exacta. No se infiere la composición de packs por familia SKU.</p></div></div>
      <div className="kiki-commercial-grid">
        <label>Marca comercial
          <input maxLength={120} placeholder="Marca comprobada del fabricante" value={fields.brand}
            onChange={e=>onChange('brand',e.target.value)}/></label>
        <label>Fabricante / responsable
          <input maxLength={120} placeholder="Razón o marca declarada" value={fields.manufacturer}
            onChange={e=>onChange('manufacturer',e.target.value)}/></label>
        <label className="wide">Título completo
          <input maxLength={180} placeholder="Producto, marca, variedad y presentación confirmadas"
            value={fields.title} onChange={e=>onChange('title',e.target.value)}/></label>
        <label>Título corto
          <input maxLength={100} placeholder="Nombre breve para listados"
            value={fields.short_title} onChange={e=>onChange('short_title',e.target.value)}/></label>
        <label>Presentación comercial y packs
          <textarea rows={2} maxLength={750} placeholder="Contenido neto, formato y composición comprobados"
            value={fields.presentation} onChange={e=>onChange('presentation',e.target.value)}/></label>
        <label className="wide">GTIN/EAN sugerido (si existe)
          <input maxLength={14} inputMode="numeric" placeholder="8, 12, 13 o 14 dígitos, confirmar en envase"
            value={fields.proposed_gtin} onChange={e=>onChange('proposed_gtin',e.target.value)}/></label>
      </div>
    </section>

    <section className="kiki-commercial-section">
      <div className="kiki-commercial-section-head"><span>02</span><div><h3>Contenido comercial y detalles</h3>
        <p>Textos expresivos, específicos y sustentados en documentación. Sin atributos inventados ni promesas médicas.</p></div></div>
      <div className="kiki-commercial-grid">
        <label className="wide">Descripción corta
          <textarea rows={3} maxLength={500} placeholder="Resumen que se entienda al primer vistazo"
            value={fields.short_description} onChange={e=>onChange('short_description',e.target.value)}/></label>
        <label className="wide">Descripción larga
          <textarea rows={6} maxLength={5000} placeholder="Información verificada del producto para su futura publicación"
            value={fields.description} onChange={e=>onChange('description',e.target.value)}/></label>
        <label className="wide">Detalles, uso y aclaraciones
          <textarea rows={5} maxLength={5000} placeholder="Uso y precauciones solo cuando estén documentados"
            value={fields.details} onChange={e=>onChange('details',e.target.value)}/></label>
      </div>
    </section>

    <section className="kiki-commercial-section">
      <div className="kiki-commercial-section-head"><span>03</span><div><h3>Categorías y posicionamiento SEO</h3>
        <p>Organización interna maestra. Las categorías específicas de cada canal se mapearán al publicar.</p></div></div>
      <div className="kiki-commercial-grid">
        <label>Categoría principal
          <input maxLength={160} list="kiki-category-options" placeholder="Ej.: Alimentos y bebidas" value={fields.category}
            onChange={e=>onChange('category',e.target.value)}/></label>
        <label>Subcategoría
          <input maxLength={160} list="kiki-subcategory-options" placeholder="Ej.: Aderezos y salsas" value={fields.subcategory}
            onChange={e=>onChange('subcategory',e.target.value)}/></label>
        <label className="wide">Título SEO
          <input maxLength={180} placeholder="Búsqueda natural + producto + presentación verificada"
            value={fields.seo_title} onChange={e=>onChange('seo_title',e.target.value)}/></label>
        <label className="wide">Descripción para buscadores
          <textarea rows={3} maxLength={320} placeholder="Metadescripción clara, sin atributos no comprobados"
            value={fields.seo_description} onChange={e=>onChange('seo_description',e.target.value)}/></label>
        <label className="wide">Palabras clave / términos relevantes
          <input maxLength={1000} placeholder="Separá términos con comas, sin repetir palabras"
            value={fields.seo_keywords} onChange={e=>onChange('seo_keywords',e.target.value)}/></label>
      </div>
      <datalist id="kiki-category-options">{categories.map(cat=><option key={cat.name} value={cat.name}/>)}</datalist>
      <datalist id="kiki-subcategory-options">{categories
        .filter(cat=>cat.name.toLocaleLowerCase()===fields.category.toLocaleLowerCase())
        .flatMap(cat=>cat.subcategories).map(sub=><option key={sub.name} value={sub.name}/>)}</datalist>
      <p className="kiki-commercial-hint">Se sugieren categorías que ya existen en KIKI para mantener nombres consistentes. Podés crear una nueva escribiéndola.</p>
    </section>

    <section className="kiki-commercial-section">
      <div className="kiki-commercial-section-head"><span>04</span><div><h3>Características y especificaciones</h3>
        <p>Agregá pares atributo/valor (por ejemplo contenido neto, sabor, formato) únicamente con respaldo documental.</p></div></div>
      <div className="kiki-commercial-list">
        {fields.attributes.map((a,i)=><div className="kiki-commercial-array" key={'attribute'+i}>
          <label>Atributo
            <input maxLength={90} value={a.name} placeholder="Ej.: Contenido neto"
              onChange={e=>editAttribute(i,'name',e.target.value)}/></label>
          <label>Valor comprobado
            <input maxLength={450} value={a.value} placeholder="Ej.: 500 g"
              onChange={e=>editAttribute(i,'value',e.target.value)}/></label>
          <button type="button" aria-label={'Quitar característica '+(i+1)}
            onClick={()=>onChange('attributes',fields.attributes.filter((_,n)=>n!==i))}>Quitar</button>
        </div>)}
        {fields.attributes.length<40&&<button type="button" className="kiki-commercial-add"
          onClick={()=>onChange('attributes',[...fields.attributes,{name:'',value:''}])}>+ Agregar característica</button>}
      </div>
    </section>

    <section className="kiki-commercial-section">
      <div className="kiki-commercial-section-head"><span>05</span><div><h3>Fotografías, gráficas y videos</h3>
        <p>Biblioteca de enlaces multimedia HTTPS con origen y descripción. No se descargan ni suben archivos al servidor.</p></div></div>
      <div className="kiki-commercial-list">
        {fields.media.map((m,i)=><div className="kiki-commercial-array kiki-commercial-media" key={'media'+i}>
          <label>Tipo
            <select value={m.kind} onChange={e=>editMedia(i,'kind',e.target.value)}>
              <option value="IMAGE">Fotografía / gráfica</option><option value="VIDEO">Video</option>
            </select></label>
          <label>URL HTTPS del archivo o video
            <input maxLength={1000} type="url" placeholder="https://fabricante.com/imagen.jpg"
              value={m.url} onChange={e=>editMedia(i,'url',e.target.value)}/></label>
          <label>Descripción / texto alternativo
            <input maxLength={180} placeholder="Ej.: Frente del envase" value={m.alt}
              onChange={e=>editMedia(i,'alt',e.target.value)}/></label>
          <label>Fuente original del recurso
            <input maxLength={1000} type="url" placeholder="https://fabricante.com/producto"
              value={m.source_url} onChange={e=>editMedia(i,'source_url',e.target.value)}/></label>
          <button type="button" aria-label={'Quitar recurso '+(i+1)}
            onClick={()=>onChange('media',fields.media.filter((_,n)=>n!==i))}>Quitar</button>
          {m.url.startsWith('https://')&&<div className="kiki-commercial-media-preview">
            {m.kind==='IMAGE'&&<img alt={m.alt||'Vista previa comercial'} src={m.url} loading="lazy" referrerPolicy="no-referrer"/>}
            <a href={m.url} target="_blank" rel="noopener noreferrer">Abrir recurso multimedia</a>
          </div>}
        </div>)}
        {fields.media.length<30&&<button type="button" className="kiki-commercial-add"
          onClick={()=>onChange('media',[...fields.media,{kind:'IMAGE',url:'',alt:'',source_url:''}])}>+ Agregar imagen o video</button>}
      </div>
    </section>

    <section className="kiki-commercial-section">
      <div className="kiki-commercial-section-head"><span>06</span><div><h3>Fuentes y control editorial</h3>
        <p>Registrá fabricante, ficha oficial, etiqueta o documentación concreta. Un EAN no garantiza que el contenido público coincida con esta variante.</p></div></div>
      <div className="kiki-commercial-list">
        {fields.sources.map((src,i)=><div className="kiki-commercial-array kiki-commercial-media" key={'source'+i}>
          <label>Tipo de evidencia
            <select value={src.kind} onChange={e=>editSource(i,'kind',e.target.value)}>
              <option value="FABRICANTE">Sitio del fabricante</option><option value="ETIQUETA">Etiqueta / envase verificado</option>
              <option value="DISTRIBUIDOR">Distribuidor</option><option value="OTRO">Otra fuente</option>
            </select></label>
          <label>Nombre de la fuente
            <input maxLength={180} placeholder="Ej.: Marca · ficha oficial" value={src.name}
              onChange={e=>editSource(i,'name',e.target.value)}/></label>
          <label>Enlace HTTPS (obligatorio para fabricante/distribuidor)
            <input maxLength={1000} type="url" placeholder="https://fabricante.com/producto" value={src.url}
              onChange={e=>editSource(i,'url',e.target.value)}/></label>
          <label>Verificación, fecha o evidencia en envase
            <textarea rows={2} maxLength={500} placeholder="Qué dato se verificó y cómo" value={src.note}
              onChange={e=>editSource(i,'note',e.target.value)}/></label>
          <button type="button" onClick={()=>onChange('sources',fields.sources.filter((_,n)=>n!==i))}
            aria-label={'Quitar fuente '+(i+1)}>Quitar</button>
          {src.url.startsWith('https://')&&<a href={src.url} target="_blank" rel="noopener noreferrer">Abrir fuente</a>}
        </div>)}
        {fields.sources.length<20&&<button type="button" className="kiki-commercial-add"
          onClick={()=>onChange('sources',[...fields.sources,{kind:'FABRICANTE',name:'',url:'',note:''}])}>+ Registrar fuente verificable</button>}
      </div>
      <label className="kiki-commercial-note">Observaciones y pendientes
        <textarea maxLength={1800} rows={3} value={fields.note}
          placeholder="Qué debe comprobarse y qué quedó pendiente, sin completar con suposiciones"
          onChange={e=>onChange('note',e.target.value)}/></label>
    </section>
    <section className="kiki-commercial-checklist" aria-live="polite">
      <strong>{readiness.ready?'Ficha documentalmente completa para preparar canales':'Datos pendientes para completar la ficha'}</strong>
      <p>La calidad y autenticidad de fuentes deben ser comprobadas por el operador; este control valida presencia y estructura, no verdad externa.</p>
      {readiness.missing.length>0&&<ul>{readiness.missing.map(key=><li key={key}>{fieldNames[key]||key}</li>)}</ul>}
      {readiness.ready&&<p>Guardar como «Lista para canales» fija esta versión interna. Nada se publica automáticamente.</p>}
    </section>
  </div>;
}
