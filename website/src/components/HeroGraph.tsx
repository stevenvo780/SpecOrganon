import { AnimatePresence, motion, useMotionValue, useReducedMotion, useSpring, useTransform } from 'motion/react';
import { ArrowUpRight, GitBranch, MousePointer2 } from 'lucide-react';
import { useState } from 'react';

const nodes=[
  {id:'problem',label:'Problema',type:'problem',x:100,y:110,width:122,note:'Delimitar actores, contexto y límites. Una solución empieza por saber qué problema estamos formulando.'},
  {id:'evidence',label:'Evidencia',type:'evidence',x:391,y:123,width:129,note:'Fuentes, hipótesis y observaciones con procedencia. La incertidumbre forma parte del expediente.'},
  {id:'decision',label:'Decisión',type:'decision',x:400,y:351,width:120,note:'Comparar opciones y conservar la razón de la elección. Las decisiones normativas vuelven al dueño.'},
  {id:'requirement',label:'Requisito',type:'requirement',x:106,y:360,width:127,note:'Cada requisito remite a su problema, compromisos y evidencia; su criterio se fija antes del resultado.'},
  {id:'result',label:'Resultado',type:'result',x:36,y:236,width:121,note:'La evaluación contrasta el resultado y su línea base, conserva los límites y puede reabrir lo afectado.'},
];

export default function HeroGraph(){
  const [active,setActive]=useState('evidence'), reduced=useReducedMotion();
  const mx=useMotionValue(0),my=useMotionValue(0);
  const rx=useSpring(useTransform(my,[-.5,.5],[4,-4]),{stiffness:110,damping:24});
  const ry=useSpring(useTransform(mx,[-.5,.5],[-4,4]),{stiffness:110,damping:24});
  const selected=nodes.find(node=>node.id===active)!;
  return <div className="hero-graph-wrap" onPointerMove={event=>{if(event.pointerType==='touch')return;const r=event.currentTarget.getBoundingClientRect();mx.set((event.clientX-r.left)/r.width-.5);my.set((event.clientY-r.top)/r.height-.5);}} onPointerLeave={()=>{mx.set(0);my.set(0);}}>
    <motion.div className="hero-graph" style={reduced?undefined:{rotateX:rx,rotateY:ry}}>
      <div className="graph-topline"><span><GitBranch size={12}/> UN EXPEDIENTE CONECTADO</span><span className="graph-pill">Esquema del método</span></div>
      <svg viewBox="0 0 570 470" className="constellation" role="img" aria-labelledby="constellation-title"><title id="constellation-title">El problema, la evidencia, la decisión, el requisito y el resultado forman un grafo revisable.</title>
        <defs><linearGradient id="orb-grad" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stopColor="#d8eea6" stopOpacity=".07"/><stop offset="100%" stopColor="#d8eea6" stopOpacity="0"/></linearGradient><marker id="conn-arrow" viewBox="0 0 8 8" refX="5.5" refY="4" markerWidth="6" markerHeight="6" orient="auto"><path d="M1 1L6 4L1 7" fill="none" stroke="#779983" strokeWidth="1"/></marker></defs>
        <circle cx="289" cy="235" r="164" fill="url(#orb-grad)"/>
        <motion.circle cx="289" cy="235" r="180" className="orbit-dashes" animate={reduced?undefined:{rotate:360}} transition={{duration:150,repeat:Infinity,ease:'linear'}} style={{transformOrigin:'289px 235px'}}/>
        <circle cx="289" cy="235" r="127" className="orbit-inner"/>
        {['M222 132C282 132 330 145 386 145','M456 178L456 345','M391 377C315 377 251 386 233 386','M108 358L108 282','M124 236L151 164'].map((d,index)=><motion.path key={d} d={d} className="constellation-link" markerEnd="url(#conn-arrow)" initial={reduced?false:{pathLength:0,opacity:0}} animate={{pathLength:1,opacity:1}} transition={{delay:.25+index*.15,duration:1.2}}/>) }
        <motion.path d="M424 347C445 253 335 53 221 123" className="constellation-feedback" initial={reduced?false:{pathLength:0}} animate={{pathLength:1}} transition={{delay:1.2,duration:1.8}}/>
        <text className="graph-center-word" x="289" y="221">Una razón</text><text className="graph-center-word italic" x="289" y="254">para cada paso.</text><text className="graph-center-meta" x="289" y="282">VERSIONES · EVIDENCIA · REVISIÓN</text>
        {nodes.map((node,index)=><motion.g key={node.id} className={`constellation-node ${active===node.id?'active':''} ${node.id==='result'?'result':''}`} initial={reduced?false:{opacity:0,y:10}} animate={{opacity:1,y:0}} transition={{delay:.3+index*.13,duration:.65}} role="button" tabIndex={0} aria-label={`${node.label}: ${node.note}`} onPointerEnter={()=>setActive(node.id)} onFocus={()=>setActive(node.id)} onClick={()=>setActive(node.id)} onKeyDown={event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();setActive(node.id);}}}>
          <rect x={node.x} y={node.y} width={node.width} height="51" rx="10"/>
          <circle cx={node.x+16} cy={node.y+26} r="3"/>
          <text x={node.x+29} y={node.y+24} className="constellation-label">{node.label}</text><text x={node.x+29} y={node.y+39} className="constellation-type">{node.type} · v1</text>
        </motion.g>)}
        {!reduced&&<motion.circle r="3" fill="#d6eca6" animate={{cx:[226,276,328,386],cy:[133,135,141,145],opacity:[0,1,1,0]}} transition={{duration:3.8,repeat:Infinity,delay:1,ease:'linear'}}/>}
      </svg>
      <div className="graph-inspector"><div className="inspector-label"><MousePointer2 size={12}/><span>EXPLORÁ UNA CONEXIÓN</span><ArrowUpRight size={13}/></div><AnimatePresence mode="wait"><motion.div key={active} initial={reduced?false:{opacity:0,y:5}} animate={{opacity:1,y:0}} exit={{opacity:0,y:-4}} transition={{duration:.18}}><strong>{selected.label}</strong><p>{selected.note}</p></motion.div></AnimatePresence></div>
    </motion.div>
  </div>;
}
