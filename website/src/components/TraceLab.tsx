import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { ArrowRight, CircleCheck, FileCheck2, FileText, FlaskConical, GitBranch, Link2, RotateCcw, ShieldAlert, Sparkles, Target } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Reveal, SectionHead } from './Shared';

const items=[
  {id:'p1',name:'Problema',kind:'problem',icon:Target,text:'Retomar una tarea local conservando decisiones, criterios y contexto.',deps:[]},
  {id:'h1',name:'Hipótesis',kind:'hypothesis',icon:FlaskConical,text:'Un expediente versionado permite reanudar sin duplicar trabajo.',deps:['p1']},
  {id:'e1',name:'Evidencia',kind:'evidence',icon:FileText,text:'Resultados del experimento definido para contrastar la hipótesis.',deps:['h1']},
  {id:'d1',name:'Decisión',kind:'decision',icon:GitBranch,text:'Elegir el recorrido documentado tras comparar las alternativas.',deps:['e1']},
  {id:'r1',name:'Requisito',kind:'requirement',icon:FileCheck2,text:'Reanudar el mismo plan sin crear pasos ni eventos duplicados.',deps:['d1']},
  {id:'res1',name:'Resultado',kind:'result',icon:CircleCheck,text:'Observación del replay vinculada al criterio anterior a la ejecución.',deps:['r1']},
];
type Link={id:string;d:string;stale:boolean};

export default function TraceLab(){
  const [revised,setRevised]=useState(false),[active,setActive]=useState('h1'),[links,setLinks]=useState<Link[]>([]);
  const grid=useRef<HTMLDivElement>(null),reduced=useReducedMotion();
  useEffect(()=>{
    const root=grid.current;if(!root)return;
    const measure=()=>{
      const container=root.getBoundingClientRect();
      const boxes=items.map(item=>root.querySelector<HTMLElement>(`[data-trace-node="${item.id}"]`)!.getBoundingClientRect());
      const routes:Link[]=[];
      for(let index=1;index<boxes.length;index++){
        const from=boxes[index-1],to=boxes[index];let d;
        if(Math.abs(from.top-to.top)<8){const x1=from.right-container.left,y1=from.top-container.top+from.height/2,x2=to.left-container.left,y2=to.top-container.top+to.height/2;d=`M${x1},${y1} C${x1+20},${y1} ${x2-20},${y2} ${x2},${y2}`;}
        else{const x1=from.left-container.left+from.width/2,y1=from.bottom-container.top,x2=to.left-container.left+to.width/2,y2=to.top-container.top,mid=(y1+y2)/2;d=`M${x1},${y1} L${x1},${mid} L${x2},${mid} L${x2},${y2}`;}
        routes.push({id:`edge-${index}`,d,stale:revised&&index>=2});
      }
      setLinks(routes);
    };
    measure();const observer=new ResizeObserver(measure);observer.observe(root);
    return ()=>observer.disconnect();
  },[revised]);
  const selected=items.find(item=>item.id===active)!;
  const stale=revised&&items.findIndex(item=>item.id===active)>1;
  return <section className="section trace-section" id="trazabilidad">
    <SectionHead number="03" eyebrow="TRAZABILIDAD EN ACCIÓN" title="Una premisa cambia." accent="La historia permanece." description="Probá la lógica del grafo revisable. Esta demostración ilustra cómo una versión nueva exige revisar lo que dependía de la anterior; conserva el resultado previo y su contexto."/>
    <Reveal className="trace-lab"><div className="trace-lab-toolbar"><div><span className={`lab-status ${revised?'changed':''}`}/><span>{revised?'Hipótesis revisada · dependencias obsoletas':'Versiones vigentes · ejemplo ilustrativo'}</span></div><button className={`button ${revised?'secondary':'primary'}`} onClick={()=>{setRevised(!revised);setActive('h1');}}><RotateCcw size={15}/>{revised?'Restaurar el ejemplo':'Cambiar la hipótesis'}</button></div>
      <div className="trace-grid" ref={grid}><svg className="trace-connectors" aria-hidden="true"><defs><marker id="trace-arrow" viewBox="0 0 8 8" refX="6.5" refY="4" markerWidth="5" markerHeight="5" orient="auto"><path d="M1 1L6 4L1 7" fill="none" stroke="currentColor"/></marker></defs>{links.map(link=><motion.path key={link.id} d={link.d} fill="none" strokeWidth="1.25" strokeDasharray={link.stale?'4 4':undefined} className={link.stale?'stale':'valid'} markerEnd="url(#trace-arrow)" initial={reduced?false:{pathLength:0}} animate={{pathLength:1}} transition={{duration:.7}}/>)}</svg>
        {items.map((item,index)=>{const Icon=item.icon,obsolete=revised&&index>1,changed=revised&&index===1;return <motion.button layout key={item.id} data-trace-node={item.id} className={`trace-artifact ${active===item.id?'selected':''} ${obsolete?'obsolete':''} ${changed?'changed':''}`} onClick={()=>setActive(item.id)} aria-pressed={active===item.id} transition={{type:'spring',stiffness:260,damping:28}}><div className="trace-artifact-top"><Icon size={19}/><code>{item.id}</code><AnimatePresence mode="wait"><motion.span key={changed?'v2':'v1'} initial={{opacity:0,y:4}} animate={{opacity:1,y:0}} exit={{opacity:0,y:-4}} className="version">{changed?'v2':'v1'}</motion.span></AnimatePresence></div><strong>{item.name}</strong><span className="trace-kind">{item.kind}</span><div className={`trace-artifact-status ${obsolete?'obsolete':''}`}>{obsolete?<ShieldAlert size={11}/>:<CircleCheck size={11}/>}<span>{obsolete?'Requiere revisión':changed?'Nueva versión':'Vigente'}</span></div></motion.button>;})}
      </div>
      <AnimatePresence mode="wait"><motion.div className="trace-detail" key={`${active}-${revised}`} initial={reduced?false:{opacity:0,y:6}} animate={{opacity:1,y:0}} exit={{opacity:0,y:-4}} transition={{duration:.18}}><div><span className="mono">ARTEFACTO SELECCIONADO</span><h3>{selected.name}<code>{selected.id}:{revised&&active==='h1'?2:1}</code></h3></div><p>{stale?'La versión conservada sigue apuntando a dependencias anteriores. Su aceptación necesita reparar esas referencias y obtener una revisión vigente.':revised&&active==='h1'?'Se conserva h1:1 y se agrega h1:2. El cambio vuelve obsoletos los descendientes que dependían de la versión anterior.':selected.text}</p><div className="trace-deps"><Link2 size={13}/><span>{selected.deps.length?selected.deps.map(id=>`${id}:1`).join(' · '):'Raíz del problema'}</span></div></motion.div></AnimatePresence>
      <div className="trace-lab-footer"><Sparkles size={14}/><p>{revised?'La nueva versión no borra el resultado anterior. Reabrir el trabajo evita sostener una conclusión con premisas que ya cambiaron.':'Seleccioná un artefacto para inspeccionarlo. Cambiá la hipótesis para ver qué dependencias deben reabrirse.'}</p><ArrowRight size={15}/></div>
    </Reveal>
  </section>;
}
