import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { ArrowRight, ArrowUpRight, CircleCheck, FileStack, GitBranch, ScanEye, ShieldAlert } from 'lucide-react';
import { useState } from 'react';
import type { KeyboardEvent } from 'react';
import { fronts, phaseNames, artifactNames, phaseExamples } from '../content';
import type { Phase } from '../types';
import { Reveal, SectionHead } from './Shared';

export default function MethodExplorer({phases}:{phases:Phase[]}){
  const [selected,setSelected]=useState('frame'), reduced=useReducedMotion();
  const phase=phases.find(item=>item.id===selected)||phases[0];
  const front=fronts.find(item=>item.id===phase.front)!, Icon=front.icon;
  const position=phases.findIndex(item=>item.id===phase.id);
  function onTabKey(event:KeyboardEvent<HTMLButtonElement>,items:string[],index:number){
    if(!['ArrowRight','ArrowLeft','ArrowDown','ArrowUp','Home','End'].includes(event.key))return;
    event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?items.length-1:(index+(['ArrowRight','ArrowDown'].includes(event.key)?1:-1)+items.length)%items.length;
    const id=items[next];setSelected(id);requestAnimationFrame(()=>document.getElementById(`phase-${id}`)?.focus({preventScroll:true}));
  }
  return <section className="section method-section" id="metodo">
    <SectionHead number="02" eyebrow="EL ESTÁNDAR OPERATIVO" title="Cuatro frentes." accent="Un recorrido conectado." description="Cada fase tiene un propósito, insumos, artefactos y una condición de salida. Explorá los contratos reales del toolkit y cómo se aplican en un proyecto local."/>
    <Reveal className="front-switcher"><div className="front-switcher-inner" aria-label="Seleccionar frente del método">{fronts.map(item=>{const FrontIcon=item.icon;return <button key={item.id} onClick={()=>setSelected(phases.find(p=>p.front===item.id)!.id)} className={front.id===item.id?'selected':''} aria-pressed={front.id===item.id}>{front.id===item.id&&<motion.span className="front-pill" layoutId="front-pill" transition={{type:'spring',stiffness:320,damping:32}}/>}<FrontIcon size={16}/><span>{item.name}</span></button>;})}</div></Reveal>
    <Reveal className="method-workbench"><aside className="phase-navigation"><div className="workbench-label"><GitBranch size={13}/><span>EL RECORRIDO</span><small>09</small></div><div role="tablist" aria-label="Nueve fases del método" aria-orientation="vertical">{phases.map((item,index)=>{const FIcon=fronts.find(f=>f.id===item.front)!.icon;return <button key={item.id} id={`phase-${item.id}`} role="tab" aria-controls="phase-contract" aria-selected={item.id===selected} tabIndex={item.id===selected?0:-1} className={`phase-nav ${item.id===selected?'selected':''}`} onClick={()=>setSelected(item.id)} onKeyDown={event=>onTabKey(event,phases.map(p=>p.id),index)}>{item.id===selected&&<motion.span layoutId="phase-highlight" className="phase-highlight" transition={{type:'spring',stiffness:300,damping:30}}/>}<span className="phase-order">{String(index+1).padStart(2,'0')}</span><FIcon size={15}/><span className="phase-nav-name">{phaseNames[item.id]}<small>{item.id}</small></span><ArrowRight size={13} className="phase-nav-arrow"/></button>;})}</div><div className="phase-navigation-note"><span className="small-ring"/><p>Las dependencias pueden reabrir fases ya avanzadas.</p></div></aside>
      <div className="phase-main" role="tabpanel" id="phase-contract" aria-labelledby={`phase-${phase.id}`}>
        <AnimatePresence mode="wait"><motion.div key={phase.id} initial={reduced?false:{opacity:0,y:10}} animate={{opacity:1,y:0}} exit={{opacity:0,y:-7}} transition={{duration:.23}}>
          <div className="phase-main-meta"><span className={`front-label ${front.color}`}><Icon size={13}/>{front.name}</span><span className="mono">FASE {String(position+1).padStart(2,'0')} / 09</span></div>
          <h3>{phaseNames[phase.id]}<span>{phase.id}</span></h3><p className="phase-purpose">{phase.purpose}</p>
          <div className="phase-input"><ArrowRight size={14}/><span>Parte de</span><p>{phase.inputs}</p></div>
          <div className="phase-artifacts"><div className="contract-label"><FileStack size={14}/>ARTEFACTOS MÍNIMOS</div><div>{phase.required.map(([kind,count])=><span key={kind}><strong>{artifactNames[kind]||kind}</strong><small>{kind}</small><i>×{count}</i></span>)}</div></div>
          <div className="phase-rules"><div><span className="contract-label"><CircleCheck size={14}/>PARA AVANZAR</span><p>{phase.exit_rule}</p></div><div><span className="contract-label"><ScanEye size={14}/>REVISIÓN</span><p>{phase.review}</p></div></div>
          <div className="phase-stop"><ShieldAlert size={15}/><div><strong>Cuándo detenerse</strong><p>{phase.stop_rule}</p></div></div>
          <div className="phase-example"><span className="mono">EJEMPLO ILUSTRATIVO / PROYECTO LOCAL</span><p>{phaseExamples[phase.id]}</p></div>
        </motion.div></AnimatePresence>
        <div className="phase-footer"><span>{front.title}</span><button onClick={()=>setSelected(phases[(position+1)%phases.length].id)}>{position===8?'Volver al inicio':'Siguiente fase'}<ArrowRight size={14}/></button></div>
      </div>
    </Reveal>
    <Reveal className="method-afterword"><div><ShieldAlert size={15}/><p>Las compuertas comprueban contratos y referencias. La revisión debe corresponder al caso y a la política de confianza elegida.</p></div><a href="/diagrams/recorrido.html" target="_blank" rel="noopener noreferrer"><span>Mapa explorable del recorrido<small>Controles del mapa en inglés</small></span><ArrowUpRight size={15}/></a></Reveal>
  </section>;
}
