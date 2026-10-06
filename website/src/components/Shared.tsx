import { animate, motion, useInView, useReducedMotion } from 'motion/react';
import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { ArrowUpRight } from 'lucide-react';
import { REPOSITORY } from '../content';

export function Reveal({children,className='',delay=0}: {children:ReactNode;className?:string;delay?:number}) {
  const reduced = useReducedMotion();
  return <motion.div className={className} initial={reduced?false:{opacity:0,y:24}} whileInView={{opacity:1,y:0}} viewport={{once:true,amount:0.12}} transition={{duration:.65,delay,ease:[.22,1,.36,1]}}>{children}</motion.div>;
}
export function SectionHead({number,eyebrow,title,accent,description}: {number:string;eyebrow:string;title:string;accent:string;description?:string}) {
  return <Reveal className="section-head"><div><p className="eyebrow"><span>{number}</span>{eyebrow}</p><h2>{title}<br/><em>{accent}</em></h2></div>{description&&<p className="section-description">{description}</p>}</Reveal>;
}
export function RepoLink({className='',children='Explorar el repositorio'}:{className?:string;children?:ReactNode}) {
  return <a className={className} href={REPOSITORY} target="_blank" rel="noopener noreferrer">{children}<ArrowUpRight size={16}/></a>;
}
export function Count({value}:{value:number}) {
  const ref=useRef<HTMLSpanElement>(null), visible=useInView(ref,{once:true}), reduced=useReducedMotion();
  const [display,setDisplay]=useState(reduced?value:0);
  useEffect(()=>{
    if(!visible)return;
    if(reduced){setDisplay(value);return;}
    const control=animate(0,value,{duration:1.3,ease:'easeOut',onUpdate:latest=>setDisplay(Math.round(latest))});
    return ()=>control.stop();
  },[visible,value,reduced]);
  return <span ref={ref} aria-label={String(value)}>{display}</span>;
}
export function Logo({light=false}:{light?:boolean}) {
  return <a href="#inicio" className={`logo ${light?'light':''}`} aria-label="SpecOrganon, volver al inicio"><svg width="34" height="34" viewBox="0 0 34 34" aria-hidden="true"><rect x="1" y="1" width="32" height="32" rx="10" fill="currentColor"/><path d="M10 11C10 7 19 7 19 11S10 13 10 18S19 22 19 18" stroke="var(--logo-line)" strokeWidth="1.7" fill="none" strokeLinecap="round"/><circle cx="23" cy="15" r="5.5" stroke="var(--logo-line)" strokeWidth="1.5" fill="none"/></svg><span>SpecOrganon<small>INDAGACIÓN → INTERVENCIÓN</small></span></a>;
}
