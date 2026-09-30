const assets=globalThis.__QUERYOTTER_ASSETS||{};
function serveAsset(request){
 const path=new URL(request.url).pathname;
 const item=assets[path==='/'?'/index.html':path];
 if(!item)return new Response('Not found',{status:404});
 if(!['GET','HEAD'].includes(request.method))return new Response('Method not allowed',{status:405});
 return new Response(request.method==='HEAD'?null:item.body,{headers:{'content-type':item.type,'cache-control':path.startsWith('/assets/')?'public, max-age=31536000, immutable':'no-cache','x-content-type-options':'nosniff','referrer-policy':'same-origin','content-security-policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"}});
}
export default {
 async fetch(request,env){
  const url=new URL(request.url);
  if(!url.pathname.startsWith('/api/')) return serveAsset(request);
  if(!env.CONNECTOR_URL||!env.SERVICE_TOKEN)return Response.json({detail:'Worker connector is offline. Published measured reports remain available.'},{status:503});
  if(!['GET','POST'].includes(request.method))return new Response('Method not allowed',{status:405});
  const origin=request.headers.get('origin');
  if(request.method==='POST'&&origin&&origin!==url.origin)return new Response('Cross-origin writes forbidden',{status:403});
  if(Number(request.headers.get('content-length')||0)>18000)return new Response('Request too large',{status:413});
  const route=url.pathname;
  if(!/^\/api\/(session|health|login|logout|examples|jobs(?:\/[a-f0-9]{32}(?:\/(?:cancel|report))?)?|connections|reports\/[a-z-]+)$/.test(route))return new Response('Not found',{status:404});
  const headers=new Headers();
  for(const key of ['content-type','cookie','origin'])if(request.headers.has(key))headers.set(key,request.headers.get(key));
  headers.set('x-service-token',env.SERVICE_TOKEN);headers.set('x-app-origin',url.origin);headers.set('x-forwarded-proto','https');
  try{
   const response=await fetch(new URL(route,new URL(env.CONNECTOR_URL)),{method:request.method,headers,body:request.method==='POST'?await request.text():undefined,redirect:'manual',signal:AbortSignal.timeout(10000)});
   const out=new Headers(response.headers);out.delete('server');out.set('cache-control','no-store');out.set('x-content-type-options','nosniff');
   return new Response(response.body,{status:response.status,headers:out});
  }catch{return Response.json({detail:'The local worker connector is unavailable. Published reports can still be explored.'},{status:503});}
 }
};
