/**
 * Cloudflare Worker 反向代理脚本 (解决浏览器跨域 CORS 限制)
 * 部署在 Cloudflare Worker (免费版每天 10 万次请求)
 */
export default {
  async fetch(request, env, ctx) {
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "*",
      "Access-Control-Max-Age": "86400"
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    const url = new URL(request.url);
    // 从 query 或 body 获取目标激活链接
    let targetUrl = url.searchParams.get("url");
    let cookie = request.headers.get("x-google-cookie") || "";

    if (!targetUrl && request.method === "POST") {
      try {
        const body = await request.json();
        targetUrl = body.url;
        if (body.cookie) cookie = body.cookie;
      } catch (e) {}
    }

    if (!targetUrl) {
      return new Response(JSON.stringify({ error: "Missing target URL" }), {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }

    // 规范化 URL 到 one.google.com
    if (targetUrl.includes("serviceactivation.google.com/subscription/new/")) {
      targetUrl = targetUrl.replace("serviceactivation.google.com/subscription/new/", "one.google.com/activate-plan/subscription/new/");
    }

    const fetchHeaders = {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
      "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
      "Upgrade-Insecure-Requests": "1"
    };
    if (cookie) {
      fetchHeaders["Cookie"] = cookie;
    }

    try {
      const response = await fetch(targetUrl, {
        method: "GET",
        headers: fetchHeaders,
        redirect: "follow"
      });

      const text = await response.text();
      const finalUrl = response.url;
      const statusCode = response.status;

      return new Response(JSON.stringify({
        status: statusCode,
        final_url: finalUrl,
        html: text
      }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    } catch (err) {
      return new Response(JSON.stringify({ error: err.message }), {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }
  }
};
