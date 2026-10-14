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
/** A connect *template*, not a verified public hostname or current access grant.
 * Public server hostname/SSH account are not authoritative Service inventory fields.
 */
export function sshConnectionTemplate(value:unknown):string|null{
 const data=object(value);
 if(data.service_type!=="ssh"||serviceStateLabel(data)!=="Enabled")return null;
 const port=data.public_port;
 if(typeof port!=="number"||!Number.isSafeInteger(port)||port<1||port>65535)return null;
 return "ssh -p "+String(port)+" USERNAME@PUBLIC_SERVER_HOST";
}

export type ServiceUseAction={
 kind:"ssh"|"http"|"https"|"tcp",copyText:string,openUrl:string|null,note:string
};
function verifiedPublicEndpointHost(value:unknown):string|null{
 if(typeof value!=="string"||!value.trim()||value.length>253||FORBIDDEN_TEXT.test(value))return null;
 const host=value.trim();
 try{
   const probe=new URL("https://"+host+":443/");
   if(probe.username||probe.password||probe.pathname!=="/"||probe.search||probe.hash
     ||probe.hostname.replace(/^\[|\]$/g,"")!==host.replace(/^\[|\]$/g,""))return null;
   return host;
 }catch{return null}
}
/** UXR-2.7: protocol-specific use guidance from explicit Core Service facts.
 * PUBLIC_SERVER_HOST is intentionally a placeholder unless a separately verified
 * public endpoint host is supplied. No command is executed by this helper. */
export function serviceUseAction(value:unknown,publicHost?:unknown):ServiceUseAction|null{
 const data=object(value);
 if(serviceStateLabel(data)!=="Enabled")return null;
 const port=data.public_port,type=data.service_type;
 if(typeof port!=="number"||!Number.isSafeInteger(port)||port<1||port>65535
   ||typeof type!=="string"||!["ssh","http","https","tcp"].includes(type))return null;
 const verified=verifiedPublicEndpointHost(publicHost);
 if(type==="ssh")return {kind:"ssh",copyText:"ssh -p "+port+" USERNAME@"+(verified||"PUBLIC_SERVER_HOST"),openUrl:null,
   note:"Replace the account and any placeholder host with separately verified values."};
 if(type==="tcp")return {kind:"tcp",copyText:(verified||"PUBLIC_SERVER_HOST")+":"+port,openUrl:null,
   note:"Raw TCP endpoint template; application protocol and reachability are not inferred."};
 const scheme=type as "http"|"https";
 const copyText=scheme+"://"+(verified||"PUBLIC_SERVER_HOST")+":"+port+"/";
 return {kind:scheme,copyText,openUrl:verified?copyText:null,
   note:verified?"Public host was separately verified for this action.":"Open is unavailable until a public service host is separately verified."};
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
