/** G-12: purely local Host display filter affordance. No Core or storage calls.
 * Unknown/invalid local state must expose a way to reset, not hide it.
 */
export function hostDisplayFilterResetAvailable(
  text:unknown,admission:unknown,connection:unknown
):boolean{
  if(typeof text!=="string"||typeof admission!=="string"||
    typeof connection!=="string")return true;
  return !!text.trim()||admission!=="all"||connection!=="all";
}
