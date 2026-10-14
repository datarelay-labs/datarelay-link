/** G-35: original operator-private Saved Views first-100 *local* pagination.
 * Core already scoped and loaded the list; no server totals or next cursors.
 * This is NOT authorization, Core paging or a persistent Saved View setting.
 */
export type LoadedSavedViewPage<T extends Record<string,unknown>>={
  items:T[],total:number,from:number,to:number,pageIndex:number,pageCount:number
};
const PAGE_SIZE=25;
export function paginateLoadedSavedViews<T extends Record<string,unknown>>(
  rows:unknown,pageIndex:unknown
):LoadedSavedViewPage<T>|null{
  if(!Array.isArray(rows)||rows.length>100||
     !Number.isSafeInteger(pageIndex)||(pageIndex as number)<0||
     rows.some(row=>!row||typeof row!=="object"||Array.isArray(row)))return null;
  const count=rows.length,pageCount=Math.ceil(count/PAGE_SIZE);
  // Server refresh can shrink an already-filtered local page; clamp in
  // presentation rather than inventing unloaded Core rows or an empty page.
  const current=pageCount===0?0:Math.min(pageIndex as number,pageCount-1);
  const from=count===0?0:current*PAGE_SIZE+1;
  const to=count===0?0:Math.min(count,(current+1)*PAGE_SIZE);
  return {
    items:rows.slice(count===0?0:from-1,to) as T[],
    total:count,from,to,pageIndex:current,pageCount
  };
}
