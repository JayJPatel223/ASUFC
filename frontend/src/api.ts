export type Program={code:string;name:string};
export type Funding={id:number;name:string;academic_year:string;kind:'cash'|'credit';expected_cents:number;received_cents:number;remaining_cents:number;unallocated_cents:number;expiry:string|null;eligible_program:string|null;eligible_supplier:string|null};
export type Budget={id:number;funding_id:number;funding_name:string;program_code:string;academic_year:string;kind:string;cents:number;remaining:number;expiry:string|null};
export type Transaction={id:number;purchase_date:string;supplier:string;purchase_type:string;description:string;cents:number;allocations:{budget_id:number;program:string;funding:string;kind:string;academic_year:string;cents:number}[]};
export type Dashboard={funding:{kind:string;received:number;expected:number;spent:number}[];programs:{program_code:string;allocated:number;spent:number}[]};
export type Api=<T>(path:string,method?:string,body?:unknown)=>Promise<T>;
export function makeApi(user:string,password:string):Api {
 const bytes=new TextEncoder().encode(user+':'+password);
 const credential=btoa(Array.from(bytes,b=>String.fromCharCode(b)).join(''));
 return async <T>(path:string,method='GET',body?:unknown):Promise<T>=>{
  const response=await fetch('/api'+path,{method,headers:{Authorization:'Basic '+credential,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
  if(!response.ok){const error=await response.json().catch(()=>null);throw new Error(typeof error?.detail==='string'?error.detail:response.status===401?'Invalid staff credentials':'Request failed ('+response.status+')');}
  return response.json() as Promise<T>;
 };
}
export function cents(value:string):number {
 if(!/^\d+(\.\d{1,2})?$/.test(value))throw new Error('Enter a valid dollar amount with at most two decimal places.');
 const [whole,fraction='']=value.split('.');
 const n=Number(whole)*100+Number(fraction.padEnd(2,'0'));
 if(!Number.isSafeInteger(n)||n>1e12)throw new Error('Amount is too large.');
 return n;
}
export const money=(n:number)=>new Intl.NumberFormat('en-CA',{style:'currency',currency:'CAD'}).format(n/100);
