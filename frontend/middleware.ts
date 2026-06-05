export const config = { matcher: '/api/:path*' };

export default async function middleware(request: Request): Promise<Response> {
  const backendUrl = process.env.BACKEND_URL;
  if (!backendUrl) {
    return new Response(JSON.stringify({ error: 'BACKEND_URL not configured' }), {
      status: 502,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const url = new URL(request.url);
  const target = `${backendUrl}${url.pathname.replace(/^\/api/, '')}${url.search}`;

  return fetch(target, {
    method: request.method,
    headers: request.headers,
    body: request.body,
    redirect: 'manual',
  });
}
