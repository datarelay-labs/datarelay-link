/** G-08: UTC-only, edit-only Audit time range shortcuts.
 * Use the caller's single click-time snapshot. Never infer Core retention.
 */
const HOURS=new Set([1,3,24,168]);
const MAX_UTC_MS=253402300799999; // Last supported four-digit ISO calendar year.
export function auditUtcPresetRange(hours:unknown,nowMs:unknown):{start:string,end:string}|null{
  if(typeof hours!=="number"||!Number.isSafeInteger(hours)||!HOURS.has(hours))return null;
  if(typeof nowMs!=="number"||!Number.isSafeInteger(nowMs)||
     nowMs<0||nowMs>MAX_UTC_MS)return null;
  const endMs=Math.floor(nowMs/1000)*1000;
  const startMs=endMs-hours*60*60*1000;
  if(startMs<0)return null;
  const utc=(ms:number)=>new Date(ms).toISOString().replace(/\.\d{3}Z$/,"Z");
  return {start:utc(startMs),end:utc(endMs)};
}
