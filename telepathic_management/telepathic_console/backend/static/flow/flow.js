/* Browser-local, illustrative playback. No prompt is submitted to Grace. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const NS = 'http://www.w3.org/2000/svg';
  const modules = {
    user: {name:'Your browser', icon:'♡', type:'http', kind:'Console frontend', x:105,y:115, subtitle:'WebUI · frontend', location:'The web browser on your device', description:'The frontend of Console: the page where you enter prompts and see Grace’s replies. It sends requests to the Console backend. In this preview, everything stays in your browser.', input:'Your text, or a Canvas request', output:'HTTP chat request / Canvas WebSocket'},
    console: {name:'Console backend',icon:'▣',type:'http',kind:'Console backend process',x:105,y:285,subtitle:'Python web server',location:'telepathic_console · outside Grace',description:'The server side of Console, separate from the browser frontend. It serves the WebUI, encodes outgoing prompts, and relays rosbridge events. It decodes response text before forwarding it to the browser.',input:'/api/telepathic/send or /api/canvas/ws',output:'Encoded stimulus; decoded response events'},
    cypher: {name:'Cypher',icon:'◇',type:'python',kind:'Shared Python codec',x:285,y:115,subtitle:'Encode / decode',location:'Imported by Console and the receptor',description:'Converts text to and from ternary_utf8_v1 signals. This is reversible encoding. The same library is used on both sides of ROS transport.',input:'UTF-8 text or encoded signal',output:'Signal bytes + pulse, or decoded text'},
    bridge: {name:'rosbridge',icon:'⌁',type:'ros',kind:'ROS 2 bridge',x:285,y:285,subtitle:'WebSocket ↔ ROS 2',location:'/rosbridge_websocket + /rosapi',description:'Connects the external Console to Grace’s ROS graph. Stimulus and response events cross this bridge in opposite directions.',input:'WebSocket publish / subscribe envelopes',output:'/telepathic/stimulus · /telepathic/response'},
    receptor: {name:'Telepathy',icon:'✦',type:'ros',kind:'ROS 2 node',x:480,y:405,subtitle:'Grace’s receptor',location:'/telepathy_receptor · AIVA',description:'Grace’s entry point. Decodes the stimulus, dispatches chat or Canvas requests, and encodes text in response events. The conversation and memory libraries run inside this process.',input:'TelepathicSignal on /telepathic/stimulus',output:'JSON std_msgs/String on /telepathic/response'},
    interactive: {name:'Interactive',icon:'✳',type:'python',kind:'In-process Python library',x:690,y:320,subtitle:'Conversation engine',location:'Inside the telepathy_receptor process',description:'Assembles persona, current time, recent exchanges, and the new prompt. Calls the model, streams response deltas, then saves the completed conversation turn.',input:'Decoded prompt + request identifier',output:'Model request; start / delta / done events'},
    persona: {name:'Persona',icon:'☷',type:'python',kind:'Configuration context',x:665,y:115,subtitle:'Soul & user profile',location:'Shell persona/SOUL.md + user profile',description:'Grace’s persona and the user profile provide context for conversation. This is configuration read by the engine, rather than an independent ROS service.',input:'Configured persona and profile files',output:'Context for the model’s messages'},
    model: {name:'Model server',icon:'✧',type:'http',kind:'Separate model service',x:865,y:150,subtitle:'Inference endpoint',location:'Configured OpenAI-compatible endpoint',description:'Generates streaming text for conversation, or structured tool actions for Canvas. The actual endpoint and model depend on AIVA’s configuration.',input:'POST /v1/chat/completions',output:'Text deltas or Canvas tool actions'},
    memory: {name:'Memory',icon:'▤',type:'python',kind:'In-process Python library',x:865,y:470,subtitle:'SQLite · recent turns',location:'agi-memory · receptor process',description:'Loads the configured recent conversation window and persists completed turns in SQLite. The current chat flow uses recent history; it does not perform semantic recall.',input:'Load recent exchanges / persist turn',output:'Recent messages; saved conversation history'},
    canvas: {name:'Canvas',icon:'✎',type:'python',kind:'Python capability + orchestration',x:680,y:555,subtitle:'Actions & visual feedback',location:'Receptor orchestration + grace-canvas',description:'Plans and validates drawing actions, publishes them for browser replay, and requests snapshots for visual review when the configured model supports vision.',input:'Drawing prompt, objects, and screenshots',output:'Canvas actions / snapshot requests / replies'},
    imaging: {name:'Imaging',icon:'◩',type:'http',kind:'Optional painting capability',x:455,y:555,subtitle:'Optional MOSS sidecar',optional:true,location:'Imaging library + moss-server sidecar',description:'Generates raster artwork for explicit image requests when MOSS is installed. Default tool drawing does not invoke this branch. This preview’s Canvas scenario demonstrates vector tools.',input:'An explicit image action and painting prompt',output:'Bitmap published in a canvas_image event'},
    logs: {name:'Health & logs',icon:'≋',type:'ros',kind:'ROS 2 monitoring node',x:160,y:500,subtitle:'Passive observation',location:'/agi_log_collector',description:'Collects ROS logs, stores rotating JSONL files, and publishes /agi/logs. This is an observation branch, rather than a required hop for a prompt.',input:'ROS log records',output:'/agi/logs + local log files'}
  };
  // The same connection can be traversed in either direction.
  const links = [
    ['user','console','http'],['console','cypher','python'],['console','bridge','http'],
    ['bridge','receptor','ros'],['receptor','interactive','python'],['persona','interactive','python'],
    ['interactive','model','http'],['interactive','memory','python'],['receptor','canvas','python'],
    ['canvas','model','http'],['canvas','memory','python'],['canvas','imaging','http'],['bridge','logs','ros']
  ];
  const paths = new Map();
  for (const [from,to,type] of links) {
    const path=document.createElementNS(NS,'path');
    path.dataset.from=from;path.dataset.to=to;
    path.setAttribute('class',`edge ${type}`);
    $('edges').append(path);paths.set(`${from}:${to}`,{path,reverse:false,type});paths.set(`${to}:${from}`,{path,reverse:true,type});
  }
  const nodeElements = {};
  for (const [id,m] of Object.entries(modules)) {
    const button=document.createElement('button');button.type='button';
    button.dataset.module=id;
    button.className=`node ${m.type}${m.optional?' optional':''}`;
    button.style.left=`${m.x/10}%`;button.style.top=`${m.y/6.5}%`;
    button.setAttribute('aria-pressed','false');button.setAttribute('aria-label',`${m.name}: ${m.kind}`);
    const top=document.createElement('span');top.className='node-top';
    const icon=document.createElement('span');icon.className='node-icon';icon.textContent=m.icon;icon.setAttribute('aria-hidden','true');
    const name=document.createElement('span');name.className='node-name';name.textContent=m.name;
    const subtitle=document.createElement('span');subtitle.className='node-type';subtitle.textContent=m.subtitle;
    top.append(icon,name);button.append(top,subtitle);button.addEventListener('click',()=>inspect(id));
    $('nodes').append(button);nodeElements[id]=button;
  }
  function layoutConnections() {
    // Match SVG units to CSS pixels. A fixed 1000×650 viewBox letterboxed
    // when the responsive map changed aspect ratio, detaching its edges.
    const map=$('constellation');
    $('connections').setAttribute('viewBox',`0 0 ${map.clientWidth} ${map.clientHeight}`);
    const bounds=(id)=>{
      const node=nodeElements[id];
      return {x:node.offsetLeft,y:node.offsetTop,w:node.offsetWidth,h:node.offsetHeight};
    };
    for(const [from,to] of links) {
      const a=bounds(from),b=bounds(to),dx=b.x-a.x,dy=b.y-a.y;
      let d;
      if(from==='canvas'&&to==='model') {
        // Route the long model connection outside Memory and Interactive.
        const x1=a.x+a.w/2,y1=a.y,x2=b.x+b.w/2,y2=b.y;
        const lane=Math.max(x1,x2)+24;
        d=`M${x1},${y1} C${lane},${y1} ${lane},${y1} ${lane},${y1-24} L${lane},${y2+24} Q${lane},${y2} ${x2},${y2}`;
      } else if(Math.abs(dx)>Math.abs(dy)) {
        const direction=Math.sign(dx),x1=a.x+direction*a.w/2,x2=b.x-direction*b.w/2;
        const bend=Math.max(24,Math.abs(x2-x1)*.5);
        d=`M${x1},${a.y} C${x1+direction*bend},${a.y} ${x2-direction*bend},${b.y} ${x2},${b.y}`;
      } else {
        const direction=Math.sign(dy),y1=a.y+direction*a.h/2,y2=b.y-direction*b.h/2;
        const bend=Math.max(24,Math.abs(y2-y1)*.5);
        d=`M${a.x},${y1} C${a.x},${y1+direction*bend} ${b.x},${y2-direction*bend} ${b.x},${y2}`;
      }
      paths.get(`${from}:${to}`).path.setAttribute('d',d);
    }
    if(activeLink)positionPacket(Math.min(elapsed/duration,1));
  }
  function inspect(id) {
    const m=modules[id];
    for(const [key,button] of Object.entries(nodeElements)){button.classList.toggle('selected',key===id);button.setAttribute('aria-pressed',String(key===id));}
    for(const [element,value] of Object.entries({inspectIcon:m.icon,inspectKind:m.kind,inspectTitle:m.name,inspectDescription:m.description,inspectLocation:m.location,inspectInput:m.input,inspectOutput:m.output})) $(element).textContent=value;
  }
  // These are source-informed scenarios, not a trace of a running system.
  const event=(from,to,title,detail)=>({from,to,title,detail});
  function makeSteps(scenario,prompt) {
    const start=[
      event('user','console','A thought arrives',`Simulated prompt: “${prompt}”`),
      event('console','cypher','Encode the request','Cypher converts UTF-8 text to ternary_utf8_v1 signal bytes.'),
      event('cypher','console','Signal is ready','Console receives encoded bytes and pulse metadata.'),
      event('console','bridge','Cross the bridge','Console publishes a TelepathicSignal through rosbridge.'),
      event('bridge','receptor','Grace receives the signal','/telepathic/stimulus reaches the receptor, which decodes the request.')
    ];
    const back=[
      event('receptor','bridge','A response leaves Grace','The receptor encodes response text and publishes /telepathic/response.'),
      event('bridge','console','Return through rosbridge','Console receives the ROS event and decodes its text content.'),
      event('console','user','The journey comes full circle','The browser displays the simulated response. A real session streams many events along this route.')
    ];
    if(scenario==='canvas') return [...start,
      event('receptor','canvas','Open the artist’s toolkit','Canvas orchestration combines the drawing request, document objects, and screenshot.'),
      event('canvas','model','Plan the drawing','The model receives the Canvas tool schema and, when supported, a view of the artwork.'),
      event('model','canvas','A plan becomes actions','Illustrative tool result: background, moon, foliage, and small glowing flowers.'),
      event('canvas','receptor','Validate and publish','Validated Canvas actions are sent as structured response events.'),
      ...back.slice(0,2),
      event('console','user','Watch the drawing unfold','The browser replays strokes and shapes on its local canvas.'),
      event('user','console','A fresh look at the artwork','Illustrative visual review: the browser sends a fresh screenshot when requested.'),
      event('console','bridge','Send the snapshot','Console publishes the snapshot on /aiva/canvas_snapshot.'),
      event('bridge','receptor','Snapshot reaches Grace','The receptor matches the screenshot to the pending drawing request.'),
      event('receptor','canvas','Review the result','A vision-capable configuration can compare the rendered artwork with the request.'),
      event('canvas','model','Refine with visual context','Illustrative review pass using the latest screenshot. Actual passes depend on model support.'),
      event('model','canvas','Finish the study','The simulated review completes. Real requests may produce additional edits.'),
      event('canvas','receptor','Artwork is ready','Publish completion and a reply to the requesting Canvas page.'),...back];
    return [...start,
      event('receptor','interactive','Begin a conversation','The receptor calls the Interactive conversation engine with the decoded prompt.'),
      event('persona','interactive','Bring her personality','The engine assembles persona, user profile, and current time.'),
      event('interactive','memory','Look at recent history','Load the configured recent window; the default is up to eight exchanges.'),
      event('memory','interactive','Context comes together','Recent exchanges join the persona and current prompt. No semantic search is simulated.'),
      event('interactive','model','Time to think','Send the assembled messages to the configured /v1/chat/completions endpoint.'),
      event('model','interactive','Words begin to form','Illustrative stream of response deltas. This preview does not call a model.'),
      event('interactive','receptor','Stream her words','The engine emits text deltas; the receptor publishes encoded response events.'),
      ...back,
      event('interactive','memory','Keep this exchange','After the model stream completes, persist the finished conversation turn in SQLite.'),
      event('interactive','receptor','Mark the turn complete','The engine emits done after saving the completed exchange.'),
      event('receptor','bridge','Publish completion','A done event travels on /telepathic/response.'),
      event('bridge','console','Relay completion','Console relays the final event to the browser.'),
      event('console','user','A new shared moment','The simulated turn is complete. Her next prompt can include this exchange in recent history.')];
  }
  let scenario='chat',steps=[],index=-1,playing=false,elapsed=0,lastTime=null,frameId=null,activeLink=null;
  const duration=1600;
  const reducedMotion=window.matchMedia('(prefers-reduced-motion: reduce)');
  function revealModule(id) {
    const viewport=document.querySelector('.map-scroll');
    const center=modules[id].x/1000*$('constellation').clientWidth;
    viewport.scrollTo({left:center-viewport.clientWidth/2,behavior:'instant'});
  }
  function updateControls() {
    $('play').textContent=playing?'Ⅱ Pause':index===steps.length-1 && index>=0?'↺ Replay':index>=0?'▶ Continue':'▶ Simulate prompt';
    $('step').disabled=index>=0 && index===steps.length-1;
    $('prompt').disabled=index>=0;
    $('progress').max=Math.max(steps.length,1);$('progress').value=index+1;
    $('stepCount').textContent=index<0?'Ready':`${index+1} / ${steps.length}`;
  }
  function positionPacket(fraction) {
    if(!activeLink)return;
    const length=activeLink.path.getTotalLength();
    const point=activeLink.path.getPointAtLength(length*(activeLink.reverse?1-fraction:fraction));
    $('packet').setAttribute('cx',point.x);$('packet').setAttribute('cy',point.y);
    $('packet').toggleAttribute('hidden',reducedMotion.matches);
  }
  function showStep(next) {
    index=next;elapsed=0;
    const step=steps[index];activeLink=paths.get(`${step.from}:${step.to}`);
    document.querySelectorAll('.edge.current').forEach(p=>{p.classList.remove('current');p.classList.add('traversed');});
    activeLink.path.classList.add('current');
    for(const [id,node] of Object.entries(nodeElements))node.classList.toggle('active',id===step.from||id===step.to);
    inspect(step.to);positionPacket(0);revealModule(step.to);
    $('graceState').textContent=scenario==='chat'?'A conversation in motion':'A little creative spark';
    $('currentEvent').textContent=`${step.title}. ${step.detail}`;
    if(index===0)$('journal').replaceChildren();
    const row=document.createElement('li');row.textContent=step.title;
    const meta=document.createElement('small');meta.textContent=`${String(index+1).padStart(2,'0')} · ${modules[step.from].name} → ${modules[step.to].name}`;row.append(meta);$('journal').append(row);$('journal').scrollTop=$('journal').scrollHeight;
    $('eventCount').textContent=`${index+1} events`;updateControls();
  }
  function stop() {playing=false;lastTime=null;if(frameId!==null)cancelAnimationFrame(frameId);frameId=null;updateControls();}
  function reset() {
    stop();index=-1;steps=[];elapsed=0;activeLink=null;
    document.querySelectorAll('.edge').forEach(p=>p.classList.remove('current','traversed'));
    Object.values(nodeElements).forEach(n=>n.classList.remove('active'));
    $('packet').setAttribute('hidden','');$('journal').replaceChildren();
    const empty=document.createElement('li');empty.className='empty-journal';empty.textContent='Your prompt’s story will unfold here.';$('journal').append(empty);
    $('eventCount').textContent='0 events';$('currentEvent').textContent='Ready when you are. Press play or step through the journey.';
    $('graceState').textContent='A world of connections';inspect('receptor');updateControls();
  }
  function ensureSteps() {
    if(steps.length)return true;
    const prompt=$('prompt').value.trim();
    if(!prompt){$('currentEvent').textContent='Add a prompt to begin the simulation.';$('prompt').focus();return false;}
    steps=makeSteps(scenario,prompt);return true;
  }
  function tick(now) {
    if(!playing)return;
    if(lastTime!==null)elapsed+=Math.min(now-lastTime,100)*Number($('speed').value);
    lastTime=now;positionPacket(Math.min(elapsed/duration,1));
    if(elapsed>=duration){
      if(index<steps.length-1)showStep(index+1);
      else{stop();$('packet').setAttribute('hidden','');$('graceState').textContent='A journey, complete';return;}
    }
    frameId=requestAnimationFrame(tick);
  }
  $('play').addEventListener('click',()=>{
    if(playing){stop();return;}
    if(index>=0 && index===steps.length-1)reset();
    if(!ensureSteps())return;
    if(index<0)showStep(0);
    playing=true;lastTime=null;updateControls();frameId=requestAnimationFrame(tick);
  });
  $('step').addEventListener('click',()=>{stop();if(!ensureSteps())return;if(index<steps.length-1){showStep(index+1);positionPacket(1);}if(index===steps.length-1){$('graceState').textContent='A journey, complete';$('packet').setAttribute('hidden','');}});
  $('reset').addEventListener('click',reset);
  document.querySelectorAll('[data-scenario]').forEach(button=>button.addEventListener('click',()=>{
    if(scenario===button.dataset.scenario)return;
    scenario=button.dataset.scenario;reset();
    document.querySelectorAll('[data-scenario]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
    $('scenarioLabel').textContent=scenario==='chat'?'CONVERSATION':'CANVAS · TOOL DRAWING';
    $('prompt').value=scenario==='chat'?'Grace, what do you remember about our last conversation?':'Grace, draw a little moonlit garden with glowing flowers.';
    $('scenarioNote').textContent=scenario==='chat'?'A simulated chat turn: recent memory, model inference, and a reply.':'A simulated vector drawing with visual review. Requires vision in a real session; MOSS is optional.';
  }));
  // Do not skip through the story while the browser tab is hidden.
  document.addEventListener('visibilitychange',()=>{lastTime=null;});
  reducedMotion.addEventListener('change',()=>{$('packet').toggleAttribute('hidden',reducedMotion.matches||index<0||(!playing&&index===steps.length-1));});
  layoutConnections();
  const layoutObserver=new ResizeObserver(layoutConnections);
  layoutObserver.observe($('constellation'));
  Object.values(nodeElements).forEach(node=>layoutObserver.observe(node));
  reset();
  revealModule('receptor');
})();
