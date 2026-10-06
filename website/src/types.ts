export type Phase = {
  id: string; front: string; purpose: string; inputs: string;
  required: [string, number][]; exit_rule: string; review: string; stop_rule: string;
};
export type ProjectData = {
  published_at: string; reviewed_head: string; repository: string; repository_revision_note: string; scope: string;
  assessment: {basis:string;author:string;statement:string};
  metrics: {phases:number; operations:number; criteria_met:number; criteria_total:number; formal_executed:number; formal_planned:number; mechanical_runs:number; decisions:number};
  phases: Phase[];
  mvp: {ready:boolean; criteria:string[]; cases:{id:string;accepted_phases:number;artifacts:number;replay_applied:number;verdict:string}[]; tools:string[];paid_api_calls:number; regression_tests:number;new_tests:number;
    invalidation:{before_accepted_phases:number;after_accepted_phases:number;unjustified_advance_rejected:boolean;original_case_unchanged:boolean}};
  criteria: {number:number;title:string;verdict:string;evidence:string;gate:string;source:string}[];
  eras: {from:number;to:number;label:string;title:string;text:string;count:number}[];
  decisions: {id:string;number:number;title:string;date:string|null}[];
  cases: {id:string;title:string;subtitle:string;metric:string;unit:string;text:string;limit:string;visual:string;source:string}[];
  sources: {path:string;title:string;url:string|null}[];
};
