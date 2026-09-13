import {createOrbitScene} from './landing-scene.js';

const journey=document.querySelector('.orbit-journey'),sceneHost=document.querySelector('#orbit-scene'),title=document.querySelector('#orbit-title'),description=document.querySelector('#orbit-description');
let scene,pending=false,phase=-1,data;
const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
const copy=[
  ['Your streaming universe.<br><span>One centre.</span>','Seasons tells you exactly when to subscribe and cancel, so you only pay for what you love.','Gather your favourites'],
  ['Everything revolves<br><span>around you.</span>','Your shows and streaming services come together in one clear view.','Bring them into Seasons'],
  ['Less searching.<br><span>More looking forward.</span>','See what you want to watch, then plan when each subscription is worth keeping.','Build your watch plan']
];
const progress=()=>clamp(scrollY/Math.max(1,journey.offsetHeight-innerHeight));
const clamp=value=>Math.max(0,Math.min(1,value));
function render(){pending=false;const value=reduced?1:progress(),next=value<.31?0:value<.76?1:2;if(next!==phase){phase=next;title.innerHTML=copy[phase][0];description.textContent=copy[phase][1];document.querySelector('#phase-label').textContent=copy[phase][2];document.querySelector('#phase-count').textContent=`${phase+1} of 3`;document.querySelector('.scroll-cue').childNodes[0].textContent=['Scroll to bring it together ','Keep scrolling ','Explore what Seasons does '][phase]}document.querySelector('.progress i').style.width=`${value*100}%`;scene?.update(value)}
function schedule(){if(!pending){pending=true;requestAnimationFrame(render)}}
function staticOrbit(items){const group=document.createElement('div');group.className='static-orbit';items.slice(0,13).forEach((item,index)=>{if(index===6){const logo=document.createElement('img');logo.src='seasonslogo.png';logo.alt='';logo.className='logo';group.append(logo)}const image=document.createElement('img');image.src=item.image;image.alt='';image.className=item.kind;group.append(image)});sceneHost.replaceChildren(group)}
function renderTrending(){const grid=document.querySelector('#trending-grid');grid.replaceChildren();data.shows.slice(0,12).forEach(show=>{const card=document.createElement('article');card.className='show';const image=document.createElement('img');image.src=show.poster;image.alt='';image.loading='lazy';const heading=document.createElement('h3');heading.textContent=show.title;const rank=document.createElement('p');rank.textContent=`Trending · ${show.rank}`;card.append(image,heading,rank);grid.append(card)});const updated=new Date(data.updatedAt);document.querySelector('#freshness').textContent=`Updated ${updated.toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'})} · TMDB`}
try{
  data=await fetch('./trending-shows.json').then(response=>{if(!response.ok)throw Error(response.status);return response.json()});renderTrending();
  const items=[];data.shows.slice(0,12).forEach((show,index)=>{items.push({title:show.title,image:show.poster,kind:'show'});if(index%2===0&&data.providers[index/2]){const provider=data.providers[index/2];items.push({title:provider.name,image:provider.logo,kind:'provider'})}});
  if(reduced){document.body.classList.add('reduced-motion');staticOrbit(items)}else{try{scene=await createOrbitScene(sceneHost,items)}catch(error){document.body.classList.add('reduced-motion');staticOrbit(items);console.warn('Interactive artwork unavailable',error)}}
}catch(error){document.body.classList.add('reduced-motion');staticOrbit([]);document.querySelector('#freshness').textContent='Trending artwork is temporarily unavailable.';console.warn('Landing artwork unavailable',error)}
addEventListener('scroll',schedule,{passive:true});addEventListener('resize',()=>{scene?.resize();schedule()});render();
