'use strict';
const $ = id => document.getElementById(id);
const source = document.createElement('canvas');
const sourceContext = source.getContext('2d', {willReadFrequently: true});
const before = $('before'), after = $('after');
let effect = 'film', ready = false, loadVersion = 0, imageLabel = 'Chocolate Labrador';
const descriptions = {
  film: 'Muted color, lifted shadows, and a restrained warm cast.',
  sepia: 'Cocoa shadows and cream highlights, like a warm photographic print.',
  duotone: 'A restrained palette of deep blue-green and warm sand.',
  vignette: 'A soft falloff at the edges draws attention to the center.',
  segments: 'Six color clusters simplify the image into regions. This groups colors, not objects; foreground cutout is in the desktop app.',
  primary: 'A graphic, eight-color palette. Each channel becomes either 0 or 255.',
  halftone: 'The original two-by-two dot patterns, re-created in your browser.',
  edge: 'Trace changes in luminance. Lower the threshold to reveal finer edges.',
  mirror: 'Look at the familiar from the other direction. A horizontal flip.',
  rotate: 'A complete change of perspective: rotate your image by 180 degrees.'
};
function apply() {
  if (!ready) return;
  const w=source.width,h=source.height;
  after.width=w;after.height=h;
  const context=after.getContext('2d');
  if(effect==='mirror'||effect==='rotate') {
    context.translate(w,effect==='rotate'?h:0);
    context.scale(-1,effect==='rotate'?-1:1);
    context.drawImage(source,0,0);
  } else {
    const input=sourceContext.getImageData(0,0,w,h);
    const output=context.createImageData(w,h),src=input.data,dst=output.data;
    const lum=i=>.299*src[i]+.587*src[i+1]+.114*src[i+2];
    if(effect==='segments') {
      const samples=[];for(let i=0;i<src.length;i+=4*Math.max(1,Math.floor(w*h/2500)))samples.push([src[i],src[i+1],src[i+2]]);
      const centers=Array.from({length:6},(_,i)=>samples[Math.floor(i*samples.length/6)].slice());
      const nearest=p=>{let best=0,distance=Infinity;centers.forEach((c,k)=>{const d=(p[0]-c[0])**2+(p[1]-c[1])**2+(p[2]-c[2])**2;if(d<distance){distance=d;best=k;}});return best;};
      for(let iteration=0;iteration<10;iteration++){const sums=centers.map(()=>[0,0,0,0]);for(const p of samples){const k=nearest(p);for(let c=0;c<3;c++)sums[k][c]+=p[c];sums[k][3]++;}sums.forEach((sum,k)=>{if(sum[3])centers[k]=sum.slice(0,3).map(v=>v/sum[3]);});}
      for(let i=0;i<src.length;i+=4){const c=centers[nearest([src[i],src[i+1],src[i+2]])];dst[i]=c[0];dst[i+1]=c[1];dst[i+2]=c[2];dst[i+3]=src[i+3];}
    } else if(effect==='halftone') {
      for(let y=0;y<h;y+=2)for(let x=0;x<w;x+=2){
        let tone=0;
        for(let dy=0;dy<2;dy++)for(let dx=0;dx<2;dx++)tone+=lum((Math.min(y+dy,h-1)*w+Math.min(x+dx,w-1))*4)/4;
        const pattern=tone>223?[255,255,255,255]:tone>159?[255,255,0,255]:tone>95?[255,0,0,255]:tone>32?[0,0,255,0]:[0,0,0,0];
        for(let dy=0;dy<2;dy++)for(let dx=0;dx<2;dx++)if(x+dx<w&&y+dy<h){const i=((y+dy)*w+x+dx)*4;dst[i]=dst[i+1]=dst[i+2]=pattern[dy*2+dx];dst[i+3]=src[i+3];}
      }
    } else for(let y=0;y<h;y++)for(let x=0;x<w;x++){
      const i=(y*w+x)*4;
      if(effect==='film'){const gray=lum(i);[25,20,16].forEach((offset,c)=>dst[i+c]=(.72*src[i+c]+.28*gray)*.88+offset);}
      else if(effect==='sepia'||effect==='duotone'){const low=effect==='sepia'?[48,32,21]:[22,54,56],high=effect==='sepia'?[247,231,198]:[239,212,164],t=lum(i)/255;for(let c=0;c<3;c++)dst[i+c]=low[c]+(high[c]-low[c])*t;}
      else if(effect==='vignette'){const nx=2*x/Math.max(1,w-1)-1,ny=2*y/Math.max(1,h-1)-1,factor=Math.max(.35,1-.35*(nx*nx+ny*ny));for(let c=0;c<3;c++)dst[i+c]=src[i+c]*factor;}
      else if(effect==='primary'){for(let c=0;c<3;c++)dst[i+c]=src[i+c]>127?255:0;}
      else {const threshold=Number($('threshold').value);const v=x<w-1&&y>0&&(Math.abs(lum(i)-lum(i+4))>threshold||Math.abs(lum(i)-lum(i-w*4))>threshold)?255:0;dst[i]=dst[i+1]=dst[i+2]=v;}
      dst[i+3]=src[i+3];
    }
    context.putImageData(output,0,0);
  }
  $('download').disabled=false;
}
function selectEffect(key){
  effect=key;
  document.querySelectorAll('[data-effect]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.effect===key)));
  $('effect-description').textContent=descriptions[key];
  $('threshold-control').hidden=key!=='edge';
  apply();
}
async function loadImage(url,label){
  const version=++loadVersion;
  $('demo-status').textContent='Opening image…';
  try {
    const image=new Image();image.src=url;await image.decode();
    if(version!==loadVersion)return;
    const scale=Math.min(1,1600/Math.max(image.naturalWidth,image.naturalHeight));
    source.width=Math.max(1,Math.round(image.naturalWidth*scale));source.height=Math.max(1,Math.round(image.naturalHeight*scale));
    sourceContext.drawImage(image,0,0,source.width,source.height);
    before.width=source.width;before.height=source.height;before.getContext('2d').drawImage(source,0,0);
    $('compare-stage').style.aspectRatio=`${source.width} / ${source.height}`;
    $('dimensions').textContent=`${source.width.toLocaleString()} × ${source.height.toLocaleString()} PX${scale<1?' · RESIZED PREVIEW':''}`;
    imageLabel=label;$('image-name').textContent=label;
    ready=true;apply();
    $('demo-status').textContent='Ready. Ten browser effects; all twenty-four in the desktop app.';
  }catch(error){if(version===loadVersion)$('demo-status').textContent='Could not read that image. Try a PNG, JPG, or WebP file.';}
}
document.querySelectorAll('[data-effect]').forEach(button=>button.addEventListener('click',()=>selectEffect(button.dataset.effect)));
document.querySelectorAll('[data-effect]').forEach((button,index)=>button.firstChild.textContent=String(index+1).padStart(2,'0')+' ');
document.querySelectorAll('[data-sample]').forEach(button=>button.addEventListener('click',async()=>{
  await loadImage('samples/'+button.dataset.sample,button.dataset.label);
  document.querySelectorAll('[data-sample]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));
  $('playground').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
}));
$('comparison').addEventListener('input',event=>$('compare-stage').style.setProperty('--split',`${event.target.value}%`));
$('threshold').addEventListener('input',event=>{$('threshold-value').value=event.target.value;apply();});
$('photo-input').addEventListener('change',async event=>{
  const file=event.target.files[0];if(!file)return;
  if(file.size>25*1024*1024){$('demo-status').textContent='Please choose a file under 25 MB for this browser demo.';return;}
  const url=URL.createObjectURL(file);try{await loadImage(url,file.name);}finally{URL.revokeObjectURL(url);event.target.value='';}
});
$('reset').addEventListener('click',()=>{selectEffect('film');document.querySelector('.effect-list').scrollTop=0;$('comparison').value=50;$('compare-stage').style.setProperty('--split','50%');document.querySelectorAll('[data-sample]').forEach(item=>item.setAttribute('aria-pressed',String(item.dataset.sample==='cheerful-puppy.png')));loadImage('samples/cheerful-puppy.png','Cheerful Labrador puppy · Generated sample');});
$('download').addEventListener('click',()=>{
  if(!ready)return;
  after.toBlob(blob=>{if(!blob)return;const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`${imageLabel.replace(/\.[^.]*$/,'').replace(/[^a-z0-9_-]+/gi,'-')}-${effect}.png`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);},'image/png');
});
loadImage('samples/cheerful-puppy.png','Cheerful Labrador puppy · Generated sample');
