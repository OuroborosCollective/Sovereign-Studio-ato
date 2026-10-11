"""Native SSH-session projection; credential entry stays on the owner HTTPS page."""
from mcp.server.fastmcp import FastMCP
URI = "ui://sovereign/owner_ssh_console.html"
DOMAIN = "https://sovereign-backend.arelorian.de"
TOOL_META = {"ui": {"resourceUri": URI, "visibility": ["model", "app"]},
             "openai/outputTemplate": URI,
             "openai/ui": {"entrypoints": [{"type": "global"}, {"type": "thread"}]}}
HTML = r"""<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sovott VPS-Konsole</title><style>body{font:16px system-ui;margin:16px;color:CanvasText;background:Canvas}section{border:1px solid #64748b;border-radius:14px;padding:18px}button,a{display:inline-block;padding:12px;margin:6px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style></head><body>
<section><h1>VPS-Konsole über SSH</h1><p>VPS anmelden, selbst im Konsolenmenü arbeiten und Hilfe für diese Verbindung freigeben.</p>
<a id="ownerLink" href="https://sovereign-backend.arelorian.de/owner-ssh" target="_blank" rel="noopener noreferrer">Geschützte SSH-Konsole öffnen</a>
<p>Zugangsdaten werden ausschließlich auf der geschützten Owner-Seite eingegeben. Die Freigabe dort ist zeitlich begrenzt und widerrufbar.</p>
<pre id="status" role="status" aria-live="polite">Keine bestätigte Sitzungsinformation.</pre></section>
<script>
'use strict';
function render(value){const node=document.getElementById('status');if(!value||value.ok!==true){node.textContent='Keine bestätigte Sitzungsinformation.';return;}
node.textContent='Status: '+String(value.status||'unbekannt')+(value.sessionId?'\nSitzung: '+value.sessionId:'')+(value.host?'\nVPS: '+value.host:'')+'\nAssistenz: '+(value.assistantGrantActive===true?'freigegeben':'keine aktive Freigabe');}
window.addEventListener('message',event=>{if(event.source!==window.parent||!event.data||event.data.jsonrpc!=='2.0')return;const m=event.data;if(m.method==='ui/notifications/tool-result'){const p=m.params||{};render(p.structuredContent||p);}});
if(window.openai&&window.openai.toolOutput)render(window.openai.toolOutput);
window.parent.postMessage({jsonrpc:'2.0',id:'ssh-init',method:'ui/initialize',params:{protocolVersion:'2026-01-26',appInfo:{name:'Sovott SSH-Konsole',version:'1.0.0'},appCapabilities:{}}},'*');
window.addEventListener('message',event=>{if(event.source===window.parent&&event.data&&event.data.jsonrpc==='2.0'&&event.data.id==='ssh-init'&&event.data.result)window.parent.postMessage({jsonrpc:'2.0',method:'ui/notifications/initialized',params:{}},'*');});
</script></body></html>"""
def register_owner_ssh_widget(mcp: FastMCP):
    @mcp.resource(URI, mime_type="text/html;profile=mcp-app",
                  meta={"ui": {"domain": DOMAIN, "csp": {"connectDomains": [], "resourceDomains": [], "frameDomains": []}},
                        "openai/widgetDomain": DOMAIN,
                        "openai/widgetCSP": {"connect_domains": [], "resource_domains": [], "frame_domains": [],
                                             "redirect_domains": [DOMAIN]}})
    def owner_ssh_widget():
        return HTML
