import { Compass, FlaskConical, Layers3, ScanLine } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export const REPOSITORY = 'https://github.com/stevenvo780/SpecOrganon/tree/main';
export const fronts: {id:string;name:string;title:string;description:string;color:string;icon:LucideIcon}[] = [
  {id:'philosophy',name:'Filosofía',title:'Definir qué problema merece una solución.',description:'Conceptos, actores, supuestos y fines. Las decisiones sobre lo deseable se hacen explícitas y vuelven a la persona competente.',color:'sage',icon:Compass},
  {id:'science',name:'Ciencia',title:'Convertir afirmaciones en investigación.',description:'Preguntas, hipótesis, protocolos e indicadores antes de observar. Evidencia, inferencia e incertidumbre conservan su lugar.',color:'blue',icon:FlaskConical},
  {id:'engineering',name:'Ingeniería',title:'Elegir, especificar y construir con una razón.',description:'Comparar alternativas y riesgos. Ligar cada requisito con su justificación y cada prueba con un criterio previo.',color:'sand',icon:Layers3},
  {id:'validation',name:'Validación',title:'Volver al problema y comprobar el resultado.',description:'Línea base, efectos y límites. El veredicto conserva el alcance de la evidencia e incorpora costes y posibles daños.',color:'rose',icon:ScanLine},
];
export const phaseNames: Record<string,string> = {frame:'Enmarcar',critique:'Criticar',study:'Estudiar',observe:'Observar',explain:'Explicar',compare:'Comparar',specify:'Especificar',build:'Construir',validate:'Validar'};
export const artifactNames: Record<string,string> = {problem:'Problema',actor:'Actor',boundary:'Frontera',concept:'Concepto',assumption:'Supuesto',frame_option:'Formulación alternativa',norm:'Compromiso normativo',question:'Pregunta',hypothesis:'Hipótesis',protocol:'Protocolo',indicator:'Indicador',evidence:'Evidencia',inference:'Inferencia',synthesis:'Síntesis',uncertainty:'Incertidumbre',option:'Alternativa',comparison:'Comparación',risk:'Riesgo',decision:'Decisión',requirement:'Requisito',criterion:'Criterio',implementation:'Implementación',test:'Prueba',baseline:'Línea base',result:'Resultado',assessment:'Evaluación'};
export const phaseExamples: Record<string,string> = {
  frame:'¿Cómo hacer que un equipo pueda retomar una tarea local sin perder sus decisiones?',
  critique:'Distinguir velocidad de continuidad. El dueño define qué acciones puede ejecutar el agente.',
  study:'Hipótesis: un expediente versionado permite reanudar con los mismos criterios. Fijar cómo comprobarlo.',
  observe:'Conservar los comandos realmente ejecutados, sus resultados y las fuentes utilizadas.',
  explain:'Separar lo observado de lo inferido. Identificar qué incertidumbre sigue abierta.',
  compare:'Comparar notas libres con un expediente estructurado bajo las mismas restricciones.',
  specify:'Requisito: reanudar sin duplicar pasos. Criterio previo: replay terminal con cero eventos nuevos.',
  build:'Construir la entrada local y ejecutar pruebas. Registrar argv, resultado y streams de la ejecución.',
  validate:'Comprobar la reanudación y emitir un veredicto técnico local con sus límites explícitos.',
};

export const principles = [
  {title:'Un problema explícito',text:'Actores, contexto, frontera y fines antes de elegir una solución.',icon:Compass},
  {title:'Evidencia con procedencia',text:'Fuente, fecha, alcance, unidades e incertidumbre para cada afirmación.',icon:FlaskConical},
  {title:'Una especificación justificada',text:'Alternativas y criterios previos que expliquen cada requisito.',icon:Layers3},
  {title:'Un resultado revisable',text:'Pruebas, revisión y contexto persistente para poder continuar.',icon:ScanLine},
];
