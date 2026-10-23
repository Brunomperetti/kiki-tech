/** Consistent lightweight line icons, shipped locally (no icon font/CDN). */
import type {ReactNode} from 'react';
type GlyphName='home'|'layers'|'search'|'chart'|'store'|'archive'|'check'|
  'shield'|'link'|'arrow-right'|'clock'|'alert'|'help'|'refresh'|'sparkles'|'box';
const glyphs:Record<GlyphName,ReactNode>={
  home:<><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/><path d="M9 21v-8h6v8"/></>,
  layers:<><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 8h10M7 12h10M7 16h6"/></>,
  search:<><circle cx="10.8" cy="10.8" r="7"/><path d="m16 16 5 5"/></>,
  chart:<><path d="M4 20V10m6 10V4m6 16v-8m5 8H3"/></>,
  store:<><path d="M3 10l2-6h14l2 6M4 10v10h16V10M9 20v-7h6v7"/><path d="M3 10c0 3 4 3 4 0 0 3 5 3 5 0 0 3 5 3 5 0 0 3 4 3 4 0"/></>,
  archive:<><rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v11h14V9M10 13h4"/></>,
  check:<><circle cx="12" cy="12" r="9"/><path d="m7.5 12.5 3 3 6-7"/></>,
  shield:<><path d="m12 2 9 4v6c0 5-3.2 8.5-9 10-5.8-1.5-9-5-9-10V6z"/><path d="m8.5 12 2.5 2.5 4.5-5"/></>,
  link:<><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2"/><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2"/></>,
  'arrow-right':<><path d="M5 12h14m-6-6 6 6-6 6"/></>,
  clock:<><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/></>,
  alert:<><path d="M12 3 2 20h20z"/><path d="M12 9v5m0 3v.5"/></>,
  help:<><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.7 2.7 0 0 1 5 1c0 2-2.5 2.4-2.5 4M12 17h.01"/></>,
  refresh:<><path d="M20 7v5h-5M4 17v-5h5"/><path d="M5.5 9A7 7 0 0 1 19 7l1 5M4 12l1 5a7 7 0 0 0 13.5-2"/></>,
  sparkles:<><path d="m12 2 2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5z"/></>,
  box:<><path d="m12 2 9 5-9 5-9-5zM3 7v10l9 5 9-5V7M12 12v10"/></>,
};
export function KikiIcon({name,size=20,className=''}:{
  name:GlyphName;size?:number;className?:string;
}){
  return <svg className={className} xmlns="http://www.w3.org/2000/svg" width={size}
    height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
    aria-hidden="true" focusable="false">{glyphs[name]}</svg>;
}
