/** Read-only, tightly allowlisted Remote Service inventory projection.
 * No arbitrary Core keys, credentials, admission inference, or runtime success.
 */
export type ServiceDetailField={label:string,value:string};
export type ServiceDetailSection={title:string,fields:ServiceDetailField[]};
type ServiceFields=Record<string,unknown>;
const FORBIDDEN_TEXT=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/g;

function object(value:unknown):ServiceFields{
 return value!==null&&typeof value==="object"&&!Array.isArray(value)
   ?value as ServiceFields:{};
}
function observedBool(value:unknown):boolean|null{
 if(value===true||value===1)return true;
 if(value===false||value===0)return false;
 return null;
}
/** SQLite may serialize booleans as 1/0. Missing evidence is not Disabled. */
export function serviceStateLabel(value:unknown):"Released"|"Enabled"|"Disabled"|"UNKNOWN"{
 const data=object(value);
 const released=observedBool(data.released),enabled=observedBool(data.enabled);
 if(released===true)return "Released";
 if(released!==false||enabled===null)return "UNKNOWN";
 return enabled?"Enabled":"Disabled";
}
function safeValue(data:ServiceFields,key:string):string{
 const raw=data[key];
 if(key==="target_port"||key==="public_port"){
   if(typeof raw!=="number"||!Number.isSafeInteger(raw)||raw<1||raw>65535)
     return "UNKNOWN";
   return String(raw);
 }
 if(typeof raw!=="string")return "UNKNOWN";
 const result=raw.replace(FORBIDDEN_TEXT," ").trim();
 return result?result.slice(0,140):"UNKNOWN";
}
/** Safe presentation identity shared by Service table and detail headings. */
export function serviceVisibleIdentity(value:unknown):{primary:string,secondary:string}{
 const data=object(value),id=safeValue(data,"id"),name=safeValue(data,"name");
 return {primary:name==="UNKNOWN"?id:name,secondary:id};
}

/** Identity and owning Host describe an inventory association, not connectivity. */
export function serviceDetailSections(value:unknown):ServiceDetailSection[]{
 const data=object(value);
 const name=safeValue(data,"name"),id=safeValue(data,"id");
 return [
  {title:"Service identity",fields:name==="UNKNOWN"&&id==="UNKNOWN"
    ?[{label:"Service identity",value:"UNKNOWN"}]
    :[{label:"Service name",value:name},{label:"Service ID",value:id}]},
  {title:"Owning Managed Host",fields:[
    {label:"Managed Host",value:safeValue(data,"managed_host")},
    {label:"Managed Host ID",value:safeValue(data,"managed_host_id")},
  ]},
  {title:"Published endpoint",fields:[
    {label:"Service type",value:safeValue(data,"service_type")},
    {label:"Target mode",value:safeValue(data,"target_mode")},
    {label:"Target Host",value:safeValue(data,"target_host")},
    {label:"Target port",value:safeValue(data,"target_port")},
    {label:"Public port",value:safeValue(data,"public_port")},
  ]},
  {title:"Service state",fields:[{label:"State",value:serviceStateLabel(data)}]},
 ];
}
