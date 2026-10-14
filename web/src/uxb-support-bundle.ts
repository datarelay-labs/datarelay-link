/** M2/R6: product-owned display-only projection for Core's sanitized
 * server-side Support Bundle. No Web download or archive-content exposure.
 * The real Core/CSRF/role authority and file-custody checks are unchanged.
 */
export type ObservedCoreSupportBundleReceipt={
 status:"CREATED",path:string,size_bytes:number,sha256:string,
 sanitized:true,download_exposed:false,authoritative_mutation:false
};
const SUPPORT=/^\/var\/lib\/drlink\/support-bundles\/drlink-support-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}\.tar\.gz$/;
const DIGEST=/^[a-f0-9]{64}$/;
export function observedCoreSupportBundleReceipt(value:unknown):
 ObservedCoreSupportBundleReceipt|null{
 if(value===null||typeof value!=="object"||Array.isArray(value))return null;
 const source=value as Record<string,unknown>;
 if(source.status!=="CREATED"||source.protected_artifact!==false
   ||source.sanitized!==true||source.download_exposed!==false
   ||source.authoritative_mutation!==false
   ||typeof source.path!=="string"||!SUPPORT.test(source.path)
   ||!Number.isSafeInteger(source.size_bytes)||Number(source.size_bytes)<1
   ||typeof source.sha256!=="string"||!DIGEST.test(source.sha256))
   return null;
 return {status:"CREATED",path:source.path,size_bytes:source.size_bytes as number,
   sha256:source.sha256,sanitized:true,download_exposed:false,
   authoritative_mutation:false};
}
