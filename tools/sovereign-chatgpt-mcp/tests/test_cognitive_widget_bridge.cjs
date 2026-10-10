'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '..', 'sovereign_cognitive_widget.py'), 'utf8');
const script = source.match(/<script>\n([\s\S]*?)<\/script>/)[1];
function harness() {
  const elements = new Map();
  function element() {
    return {textContent:'',value:'',disabled:false,children:[],listeners:{},
      replaceChildren(){this.children=[];}, appendChild(x){this.children.push(x);},
      addEventListener(name,fn){this.listeners[name]=fn;}};
  }
  const messages=[], timers=new Map();
  let timerId=0, listener;
  const parent={postMessage(m){messages.push(m);}};
  const window={parent,addEventListener(name,fn){if(name==='message')listener=fn;}};
  const document={getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);},
    createElement:element};
  vm.runInNewContext(script,{window,document,Set,Map,Error,Number,Object,Array,
    setTimeout(fn){timers.set(++timerId,fn);return timerId;},clearTimeout(id){timers.delete(id);}});
  const receive=(m,from=parent)=>listener({source:from,data:m});
  const reply=(request,result)=>receive({jsonrpc:'2.0',id:request.id,result});
  const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
  const init=async()=>{reply(messages[0],{protocolVersion:'2026-01-26'});await flush();};
  const el=id=>document.getElementById(id);
  return {messages,timers,receive,reply,flush,init,el};
}
const status=(extra={})=>({ok:true,summary:'runtime receipt',status:'READY',
  manifest:{agents:[],doubleLoop:[],releaseMode:'draft_pr_only'},controlPlane:{status:'READY'},
  controllerRuns:{runs:[],latestRun:{}},draftPr:{ready:false},...extra});
test('initializes current protocol and sends initialized notification',async()=>{
  const h=harness();assert.equal(h.messages[0].method,'ui/initialize');
  await h.init();assert.equal(h.messages[1].method,'ui/notifications/initialized');
});
test('ignores foreign window and non JSON-RPC messages',async()=>{
  const h=harness();await h.init();
  h.receive({jsonrpc:'2.0',method:'ui/notifications/tool-result',params:{structuredContent:status()}},{});
  assert.equal(h.el('message').textContent,'');
  h.receive({method:'ui/notifications/tool-result',params:{structuredContent:status()}});
  assert.equal(h.el('message').textContent,'');
});
test('reads direct params structured tool result',async()=>{
  const h=harness();await h.init();
  h.receive({jsonrpc:'2.0',method:'ui/notifications/tool-result',params:{structuredContent:status()}});
  assert.equal(h.el('message').textContent,'runtime receipt');
});
test('refresh invokes only the registered read tool and recovers from host error',async()=>{
  const h=harness();await h.init();const done=h.el('refresh-runs').listeners.click();
  const request=h.messages.at(-1);assert.equal(request.method,'tools/call');
  assert.equal(request.params.name,'sovereign_cognitive_architecture_status');
  h.receive({jsonrpc:'2.0',id:request.id,error:{code:-1}});await done;
  assert.equal(h.el('refresh-runs').disabled,false);
  assert.match(h.el('message').textContent,/nicht aktualisiert/);
});
test('refresh times out and allows retry',async()=>{
  const h=harness();await h.init();const done=h.el('refresh-runs').listeners.click();
  for(const fn of h.timers.values())fn();await done;
  assert.equal(h.el('refresh-runs').disabled,false);assert.match(h.el('message').textContent,/Host-Antwort/);
});
test('rejects malformed PR hash and clears approval on failed status',async()=>{
  const h=harness();await h.init();
  h.receive({jsonrpc:'2.0',method:'ui/notifications/tool-result',params:{structuredContent:status({draftPr:{ready:true,number:12,headSha:'z'.repeat(40)}})}});
  assert.equal(h.el('approve').disabled,true);
  h.receive({jsonrpc:'2.0',method:'ui/notifications/tool-result',params:{structuredContent:status({draftPr:{ready:true,number:12,headSha:'a'.repeat(40)}})}});
  assert.equal(h.el('approve').disabled,false);
  h.receive({jsonrpc:'2.0',method:'ui/notifications/tool-result',params:{structuredContent:{ok:false,status:'BLOCKED'}}});
  // Incomplete status notifications must invalidate the previous approval.
  assert.equal(h.el('approve').disabled,true);
});
test('invalid workspace and PR inputs cause no host tool call',async()=>{
  const h=harness();await h.init();const before=h.messages.length;
  h.el('workspace-id').value='../other';await h.el('load-repository').listeners.click();
  h.el('pr-number').value='-2';await h.el('load-pr').listeners.click();
  assert.equal(h.messages.length,before);
});
test('PR CI must match full current head and renders untrusted labels as text',async()=>{
  const h=harness();await h.init();h.el('pr-number').value='2240';
  let done=h.el('load-pr').listeners.click();
  h.reply(h.messages.at(-1),{structuredContent:{ok:true,pr_number:2240,head_sha:'a'.repeat(40),
    checks:{head_sha:'b'.repeat(40),checks:[{name:'evil',status:'completed',conclusion:'success'}]}}});
  await done;assert.ok(h.el('pr-evidence').children.some(x=>/CI nicht verifiziert/.test(x.textContent)));
  assert.ok(!h.el('pr-evidence').children.some(x=>x.textContent.includes('evil')));
  done=h.el('load-pr').listeners.click();
  h.reply(h.messages.at(-1),{structuredContent:{ok:true,pr_number:2240,head_sha:'a'.repeat(40),
    checks:{head_sha:'a'.repeat(40),checks:[{name:'<img onerror=evil>',status:'completed',conclusion:'skipped'}]}}});
  await done;assert.ok(h.el('pr-evidence').children.some(x=>x.textContent.includes('<img onerror=evil>')&&x.textContent.includes('skipped')));
});
test('repository lookup preserves scope and separates deployed revision evidence',async()=>{
  const h=harness();await h.init();h.el('workspace-id').value='job-aadf79677712';
  const done=h.el('load-repository').listeners.click();const request=h.messages.at(-1);
  assert.equal(request.params.arguments.workspace_id,'job-aadf79677712');
  h.reply(request,{structuredContent:{ok:true,workspaceId:'job-aadf79677712',status:'RESOLVED',workspaceHeadSha:'a'.repeat(40),
    deployedMcpEvidence:{status:'FAILED',revision:'b'.repeat(40),revisionVerified:false,digestVerified:false}}});
  await done;assert.ok(h.el('deployment-evidence').children.some(x=>x.textContent==='revisionVerified: false'));
});

test('rejects cross-scope PR and workspace receipts',async()=>{
  const h=harness();await h.init();h.el('pr-number').value='2240';
  let done=h.el('load-pr').listeners.click();
  h.reply(h.messages.at(-1),{structuredContent:{ok:true,pr_number:999,head_sha:'a'.repeat(40)}});await done;
  assert.match(h.el('message').textContent,/anderen Scope/);
  h.el('workspace-id').value='job-aadf79677712';done=h.el('load-repository').listeners.click();
  h.reply(h.messages.at(-1),{structuredContent:{ok:true,workspaceId:'job-other'}});await done;
  assert.match(h.el('message').textContent,/anderen Scope/);
});
