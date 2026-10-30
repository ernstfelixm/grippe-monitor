(function(){
  'use strict';
  const DAY=86400000, START=Date.UTC(2003,9,1), END=Date.UTC(2004,8,30);
  const label=y=>`${y}/${String(y+1).slice(2)}`;
  const color=(y,current)=>y===current?'#d70005':y===current-1?'#ed716f':'#d3d3d3';
  const position=w=>{const d=new Date(w.date+'T00:00:00Z'),m=d.getUTCMonth();return Date.UTC(m>=9?2003:2004,m,d.getUTCDate());};
  const fmt=n=>new Intl.NumberFormat('de-DE',{maximumFractionDigits:0}).format(n);
  const stamp=s=>new Intl.DateTimeFormat('de-AT',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(s));
  function validate(d){
    if(d?.version!==1||d.metric!=='AUFNAHMEN'||!Array.isArray(d.weeks)||d.weeks.length<3||d.weeks.length>2000||!Number.isFinite(Date.parse(d.retrievedAt)))throw Error('Ungültiger Datenstand');
    let previous;
    d.weeks.forEach((w,i)=>{
      const t=Date.parse(w.date+'T00:00:00Z'),date=new Date(t),month=date.getUTCMonth();
      const jan4=new Date(Date.UTC(w.year,0,4)),monday=+jan4-((jan4.getUTCDay()+6)%7)*DAY;
      if(!Number.isFinite(t)||date.getUTCDay()!==4||date.getUTCFullYear()!==w.year||1+Math.round((t-3*DAY-monday)/(7*DAY))!==w.week||w.season!==(month>=9?w.year:w.year-1)||!Number.isSafeInteger(w.value)||w.value<0||w.provisional!==(i>=d.weeks.length-2)||(previous!==undefined&&t-previous!==7*DAY))throw Error('Ungültige Wochenwerte');
      previous=t;
    });return d;
  }
  function accept(next,previous){validate(next);if(previous&&(next.weeks.at(-1).date<previous.weeks.at(-1).date||Date.parse(next.retrievedAt)<Date.parse(previous.retrievedAt)))throw Error('Älterer Datenstand');return next;}
  function stale(d,now=Date.now()){return now-Date.parse(d.retrievedAt)>3*DAY||now-(Date.parse(d.weeks.at(-1).date)+3*DAY)>21*DAY;}
  if(typeof module!=='undefined'&&module.exports){module.exports={validate,accept,position,color,stale};return;}
  const root=document.getElementById('kurier-sari-title');
  if(!root||root.dataset.initialized)return;root.dataset.initialized='true';
  const svg=root.querySelector('svg'),plot=root.querySelector('.kst-plot'),legend=root.querySelector('.kst-legend'),status=root.querySelector('.kst-status'),tip=root.querySelector('.kst-tooltip');
  const ns='http://www.w3.org/2000/svg',hidden=new Set();
  const el=(tag,attrs={},text)=>{const n=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;return n;};
  let data,external=false,failed=false,busy=false,timer,resizeFrame=0;
  function series(){const current=data.weeks.at(-1).season;return [...new Set(data.weeks.map(w=>w.season))].sort((a,b)=>a-b).map(year=>({year,rows:data.weeks.filter(w=>w.season===year),color:color(year,current)}));}
  function updateStatus(){
    const w=data.weeks.at(-1),warnings=[];
    if(failed)warnings.push('Aktualisierung fehlgeschlagen; der zuletzt verfügbare Stand bleibt sichtbar.');
    if(stale(data))warnings.push('Der verfügbare Datenstand ist möglicherweise veraltet.');
    status.textContent=`${external?'Datenabruf':'Gespeicherter Datenstand'}: ${stamp(data.retrievedAt)} · Enthalten bis KW ${w.week}/${w.year}. Die jüngsten zwei Wochen sind unvollständig und werden nachgemeldet. ${warnings.join(' ')}`;
  }
  function updateLegend(){
    const focus=document.activeElement?.dataset?.season;
    legend.replaceChildren();
    [...series()].reverse().forEach(s=>{const button=document.createElement('button'),key=document.createElement('i');
      button.type='button';button.dataset.season=s.year;button.setAttribute('aria-pressed',String(!hidden.has(s.year)));button.setAttribute('aria-label',`Saison ${label(s.year)} ein- oder ausblenden`);
      key.className='kst-key';key.style.borderColor=s.color;key.setAttribute('aria-hidden','true');button.append(key,document.createTextNode(label(s.year)));
      button.addEventListener('click',()=>{hidden.has(s.year)?hidden.delete(s.year):hidden.add(s.year);draw();});legend.append(button);
    });
    if(focus)legend.querySelector(`[data-season="${focus}"]`)?.focus();
  }
  function valuesAt(target){return [...series()].reverse().filter(s=>!hidden.has(s.year)).map(s=>{
    const w=s.rows.reduce((a,b)=>Math.abs(position(a)-target)<Math.abs(position(b)-target)?a:b);
    return Math.abs(position(w)-target)<=4*DAY?`${label(s.year)} · KW ${w.week}/${w.year}: ${fmt(w.value)} Aufnahmen${w.provisional?' (unvollständig)':''}`:`${label(s.year)}: keine Daten`;
  });}
  function draw(){
    if(!data||!root.isConnected)return;
    const all=series(),visible=all.filter(s=>!hidden.has(s.year)),current=data.weeks.at(-1).season;
    const style=getComputedStyle(root),font=parseFloat(style.fontSize)||16,width=plot.clientWidth;
    if(width<1)return;
    const ctx=document.createElement('canvas').getContext('2d');ctx.font=style.font||`${style.fontSize} ${style.fontFamily}`;
    // Keep the scale fixed while toggling a legend item, preserving comparisons.
    const max=Math.max(1,...data.weeks.map(w=>w.value)),raw=max/4,power=10**Math.floor(Math.log10(raw));
    const step=Math.max(1,[1,2,2.5,5,10].find(x=>x*power>=raw)*power),top=Math.ceil(max/(step/2))*(step/2);
    const left=Math.ceil(ctx.measureText(fmt(top)).width)+font*.75,right=font*.8,height=Math.max(280,Math.min(490,width*.57)),upper=font*.7,bottom=font*1.9;
    const pw=width-left-right,ph=height-upper-bottom,X=x=>left+(x-START)/(END-START)*pw,Y=v=>upper+ph-v/top*ph;
    svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.setAttribute('height',height);
    svg.replaceChildren(el('title',{id:'kst-chart-title'},'Schwere Atemwegsinfektionen im Saisonvergleich'),el('desc',{id:'kst-chart-desc'},`Österreich: absolute wöchentliche Krankenhausaufnahmen. Saisonachse Oktober bis September. Aktuelle Saison ${label(current)} rot, Vorjahr hellrot, ältere Saisonen grau. Alle verfügbaren Wochen sind enthalten, die letzten beiden sind unvollständig. Exakte Werte stehen in der Datentabelle.`));
    for(let n=0;n<=top;n+=step){svg.append(el('line',{x1:left,x2:width-right,y1:Y(n),y2:Y(n),stroke:'currentColor','stroke-opacity':.08}),el('text',{x:left-font*.55,y:Y(n),'text-anchor':'end','dominant-baseline':'middle'},fmt(n)));}
    svg.append(el('line',{x1:left,x2:left,y1:upper,y2:Y(0),stroke:'currentColor','stroke-opacity':.08}));
    const months=['Okt','Nov','Dez','Jan','Feb','Mär','Apr','Mai','Jun','Jul','Aug','Sep'];
    const ids=pw<330?[0,3,7,11]:pw<600?[0,2,4,6,8,11]:months.map((_,i)=>i);
    ids.forEach((i,j)=>{const t=Date.UTC(i<3?2003:2004,(i+9)%12,1);svg.append(el('text',{x:X(t),y:height-font*.4,'text-anchor':j===0?'start':'middle'},months[i]));});
    visible.forEach(s=>{
      const d=s.rows.map((w,i)=>`${i?'L':'M'}${X(position(w))},${Y(w.value)}`).join(' ');
      if(s.rows.length>1)svg.append(el('path',{d,fill:'none',stroke:s.color,'stroke-width':2.4,'stroke-linecap':'round','stroke-linejoin':'round','data-season':s.year}));
      const w=s.rows.at(-1);svg.append(el('circle',{cx:X(position(w)),cy:Y(w.value),r:3.2,fill:s.color,'data-endpoint':s.year}));
    });
    const guide=el('line',{x1:0,x2:0,y1:upper,y2:Y(0),stroke:'currentColor','stroke-opacity':.3,visibility:'hidden'});svg.append(guide);
    const hit=el('rect',{x:left,y:upper,width:Math.max(1,pw),height:ph,fill:'transparent'});svg.append(hit);tip.hidden=true;
    let pinned=false;
    const show=e=>{
      const rect=svg.getBoundingClientRect(),x=Math.max(left,Math.min(width-right,(e.clientX-rect.left)*width/rect.width));
      const target=START+(x-left)/pw*(END-START);guide.setAttribute('x1',x);guide.setAttribute('x2',x);guide.setAttribute('visibility','visible');tip.replaceChildren();
      valuesAt(target).forEach(text=>{const p=document.createElement('p');p.textContent=text;tip.append(p);});
      tip.style.left=Math.max(0,Math.min(x+12,width-350))+'px';tip.style.top='0px';tip.hidden=false;
    };
    hit.addEventListener('pointermove',e=>{if(e.pointerType!=='touch'&&!pinned)show(e);});
    hit.addEventListener('click',e=>{pinned=!pinned;if(pinned)show(e);else{tip.hidden=true;guide.setAttribute('visibility','hidden');}});
    hit.addEventListener('pointerleave',()=>{if(!pinned){tip.hidden=true;guide.setAttribute('visibility','hidden');}});
    updateLegend();updateStatus();
    const tbody=root.querySelector('tbody');tbody.replaceChildren();
    [...data.weeks].reverse().filter(w=>!hidden.has(w.season)).forEach(w=>{const tr=document.createElement('tr');[label(w.season),`KW ${w.week}/${w.year}${w.provisional?' (unvollständig)':''}`,fmt(w.value)].forEach(t=>{const td=document.createElement('td');td.textContent=t;tr.append(td);});tbody.append(tr);});
    const range=root.querySelector('.kst-explore');root.querySelector('.kst-keyboard').textContent=valuesAt(START+Number(range.value)*DAY).join(' · ');
  }
  async function refresh(){
    if(busy||!root.dataset.source||!root.isConnected)return;busy=true;
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),12000);
    try{
      const response=await fetch(root.dataset.source,{cache:'no-store',signal:controller.signal,credentials:'omit'});
      if(!response.ok)throw Error('HTTP '+response.status);
      const text=await response.text();if(text.length>1_000_000)throw Error('Daten zu groß');
      data=accept(JSON.parse(text),data);external=true;failed=false;
    }catch(e){failed=true;}finally{clearTimeout(timeout);busy=false;draw();}
  }
  function init(){
    try{data=validate(JSON.parse(document.getElementById('kst-data').textContent));}
    catch(e){status.textContent='Die Daten konnten nicht geprüft werden. Bitte nutzen Sie die verlinkten Quelldaten.';return;}
    draw();
    const observer=new ResizeObserver(()=>{cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(draw);});observer.observe(plot);
    if(document.fonts)document.fonts.ready.then(draw);
    root.querySelector('.kst-explore').addEventListener('input',e=>{root.querySelector('.kst-keyboard').textContent=valuesAt(START+Number(e.target.value)*DAY).join(' · ');});
    refresh();
    const visibility=()=>{if(!document.hidden)refresh();};document.addEventListener('visibilitychange',visibility);
    timer=setInterval(()=>{if(!root.isConnected){clearInterval(timer);observer.disconnect();document.removeEventListener('visibilitychange',visibility);}else if(!document.hidden)refresh();},15*60*1000);
  }
  init();
})();
