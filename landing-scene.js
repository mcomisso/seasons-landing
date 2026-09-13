import * as THREE from './three.module.js';

const clamp=(value,min=0,max=1)=>Math.min(max,Math.max(min,value));
const ease=value=>{const t=clamp(value);return t*t*(3-2*t)};
const mix=(start,end,amount)=>start+(end-start)*amount;

async function makeTexture(item,isLogo=false){
  const canvas=document.createElement('canvas');canvas.width=384;canvas.height=item.kind==='show'?576:384;
  const context=canvas.getContext('2d'),width=canvas.width,height=canvas.height;
  context.beginPath();
  if(item.kind==='provider'&&!isLogo)context.arc(width/2,height/2,width/2-2,0,Math.PI*2);else context.roundRect(2,2,width-4,height-4,isLogo?82:34);
  context.clip();context.fillStyle=item.kind==='provider'?'#f8fafc':'#17151f';context.fillRect(0,0,width,height);
  try{
    const image=await new Promise((resolve,reject)=>{const source=new Image();source.crossOrigin='anonymous';const timer=setTimeout(()=>reject(Error('Image timeout')),10000);source.onload=()=>{clearTimeout(timer);resolve(source)};source.onerror=()=>{clearTimeout(timer);reject(Error('Image unavailable'))};source.src=item.image});
    const contain=item.kind==='provider'&&!isLogo;const scale=(contain?Math.min(width/image.width,height/image.height)*.78:Math.max(width/image.width,height/image.height));
    context.drawImage(image,(width-image.width*scale)/2,(height-image.height*scale)/2,image.width*scale,image.height*scale);
  }catch{context.fillStyle='#f8fafc';context.textAlign='center';context.textBaseline='middle';context.font='600 32px sans-serif';context.fillText(item.title||'Seasons',width/2,height/2,width-30)}
  const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;return texture;
}

export async function createOrbitScene(container,items){
  const renderer=new THREE.WebGLRenderer({alpha:true,antialias:true,powerPreference:'low-power'});renderer.setPixelRatio(Math.min(devicePixelRatio||1,2));renderer.setClearColor(0,0);container.append(renderer.domElement);
  const scene=new THREE.Scene(),camera=new THREE.OrthographicCamera(-8,8,5,-5,.1,100);camera.position.z=30;
  let sceneHeight=10,pixelHeight=800,mobile=false,lastProgress=0;const resources=[];
  const textures=await Promise.all(items.map(makeTexture));
  const mesh=(texture,width,height)=>{const geometry=new THREE.PlaneGeometry(width,height);const material=new THREE.MeshBasicMaterial({map:texture,transparent:true,side:THREE.DoubleSide,depthWrite:false});const object=new THREE.Mesh(geometry,material);scene.add(object);resources.push(geometry,material,texture);return object};
  const cards=items.map((item,index)=>mesh(textures[index],item.kind==='provider'?1.04:1.2,item.kind==='provider'?1.04:1.8));
  const logo=mesh(await makeTexture({title:'Seasons',image:'seasonslogo.png',kind:'logo'},true),2.3,2.3);logo.renderOrder=100;

  function update(progress){
    lastProgress=clamp(progress);const p=lastProgress,count=cards.length;
    const safeTop=mobile?pixelHeight*.44:Math.max(pixelHeight*.46,325),safeBottom=Math.max(safeTop+80,pixelHeight-145),unitsPerPixel=sceneHeight/pixelHeight;
    const centreY=sceneHeight/2-(safeTop+safeBottom)/2*unitsPerPixel,safeHalf=(safeBottom-safeTop)/2*unitsPerPixel,visualScale=mobile?1.5:.78,spanY=Math.max(.2,safeHalf-1.05*visualScale);
    const convergence=ease((p-.12)/.37),logoPulse=Math.sin(clamp((p-.28)/.38)*Math.PI);
    logo.position.set(0,centreY,2);logo.scale.setScalar((mix(1,.7,ease((p-.57)/.18))+logoPulse*.14)*Math.min(visualScale,safeHalf/1.4));logo.material.opacity=1-ease((p-.7)/.15);logo.rotation.z=-.12*Math.sin(p*Math.PI);
    cards.forEach((card,index)=>{
      const seed=index*2.399963,ring=.45+.55*Math.sqrt((index+1)/count),orbit=seed+p*2.2;
      const sourceX=Math.cos(orbit)*(3.7+ring*2.9),sourceY=Math.sin(orbit)*spanY,sourceZ=Math.sin(orbit)*3;
      const intake=ease((p-.13-index/count*.105)/.29),release=ease((p-.57-index/count*.23)/.16);
      const columns=6,rows=3,column=index%columns,row=Math.floor(index/columns),targetScale=Math.min(.8*visualScale,safeHalf*2/(rows*2.1));
      const targetX=(column-2.5)*(mobile?2.2:2.05),targetY=((rows-1)/2-row)*(targetScale*1.8+.2);
      const gatheredX=mix(sourceX,0,intake),gatheredY=mix(sourceY,0,intake);
      card.position.set(mix(gatheredX,targetX,release),centreY+mix(gatheredY,targetY,release),mix(sourceZ,0,Math.max(convergence,release)));
      const tiny=mix(visualScale,.06,intake);card.scale.setScalar(mix(tiny,targetScale,release));
      card.rotation.set(0,Math.sin(seed)*.25*(1-intake)*(1-release),Math.sin(orbit)*.4*(1-intake)*(1-release));
      const extent=(items[index].kind==='provider'?.74:1.1)*card.scale.x;card.position.y=centreY+clamp(card.position.y-centreY,-Math.max(0,safeHalf-extent),Math.max(0,safeHalf-extent));
      card.material.opacity=Math.max(1-ease((intake-.7)/.3),release);card.renderOrder=index;
    });renderer.render(scene,camera);
  }
  function resize(){const width=Math.max(container.clientWidth,1);pixelHeight=Math.max(container.clientHeight,1);sceneHeight=16*pixelHeight/width;mobile=width<650;camera.top=sceneHeight/2;camera.bottom=-sceneHeight/2;camera.updateProjectionMatrix();renderer.setSize(width,pixelHeight,false);update(lastProgress)}
  resize();return{update,resize,dispose(){resources.forEach(resource=>resource.dispose());renderer.dispose();renderer.domElement.remove()}};
}
