import * as THREE from '../../three.module.js';

const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const ease = v => { const t = clamp(v); return t * t * (3 - 2 * t); };
const mix = (a, b, t) => a + (b - a) * t;

async function textureFor(item, logo = false) {
  const canvas = document.createElement('canvas');
  canvas.width = 384;
  canvas.height = item.kind === 'show' ? 576 : 384;
  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;
  ctx.beginPath();
  if (item.kind === 'provider' && !logo) ctx.arc(w / 2, h / 2, w / 2 - 2, 0, Math.PI * 2);
  else ctx.roundRect(2, 2, w - 4, h - 4, logo ? 82 : 34);
  ctx.clip();
  ctx.fillStyle = item.kind === 'provider' ? '#fff' : '#202b38';
  ctx.fillRect(0, 0, w, h);
  try {
    const image = await new Promise((resolve, reject) => {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      const timeout = setTimeout(() => reject(new Error('Image timed out')), 12000);
      img.onload = () => { clearTimeout(timeout); resolve(img); };
      img.onerror = () => { clearTimeout(timeout); reject(new Error('Image unavailable')); };
      img.src = item.image;
    });
    const contain = item.kind === 'provider' && !logo;
    const scale = (contain ? Math.min(w / image.width, h / image.height) * .78 : Math.max(w / image.width, h / image.height));
    ctx.drawImage(image, (w - image.width * scale) / 2, (h - image.height * scale) / 2, image.width * scale, image.height * scale);
  } catch {
    ctx.fillStyle = item.kind === 'provider' ? '#192331' : '#fff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = '600 34px sans-serif';
    const words = (item.title || 'Seasons').split(' ');
    words.slice(0, 4).forEach((word, index) => ctx.fillText(word, w / 2, h / 2 + (index - (Math.min(words.length, 4) - 1) / 2) * 43, w - 30));
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

/** The only animation input is normalized page scroll. No perpetual render loop. */
export async function createScene(container, items, logoURL) {
  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'low-power' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x000000, 0);
  renderer.domElement.setAttribute('aria-hidden', 'true');
  renderer.domElement.style.cssText = 'display:block;width:100%;height:100%;pointer-events:none';
  container.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-8, 8, 5, -5, .1, 100);
  camera.position.z = 30;
  let height = 10, pixelHeight = 800, mobile = false, previousProgress = 0, previousVariant = 'A';
  const resources = [];
  const textures = await Promise.all(items.map(item => textureFor(item)));
  const makeMesh = (texture, width, height) => {
    const geometry = new THREE.PlaneGeometry(width, height);
    const material = new THREE.MeshBasicMaterial({ map: texture, transparent: true, side: THREE.DoubleSide, depthWrite: false });
    const mesh = new THREE.Mesh(geometry, material);
    scene.add(mesh);
    resources.push(geometry, material, texture);
    return mesh;
  };
  const cards = items.map((item, i) => makeMesh(textures[i], item.kind === 'provider' ? 1.04 : 1.2, item.kind === 'provider' ? 1.04 : 1.8));
  const logo = makeMesh(await textureFor({ title: 'Seasons', image: logoURL, kind: 'logo' }, true), 2.3, 2.3);
  logo.renderOrder = 100;

  function update(progress, variant = 'A') {
    previousProgress = clamp(progress);
    previousVariant = variant;
    const p = previousProgress;
    const mode = typeof variant === 'number' ? variant : Math.max(0, 'ABCDE'.indexOf(String(variant).toUpperCase()));
    // Reserve the actual copy and navigation regions, including card extents.
    const safeTop = mobile ? pixelHeight * .44 : Math.max(pixelHeight * .46, 325);
    const safeBottom = Math.max(safeTop + 80, pixelHeight - 145);
    const unitsPerPixel = height / pixelHeight;
    const cy = height / 2 - (safeTop + safeBottom) / 2 * unitsPerPixel;
    const safeHalf = (safeBottom - safeTop) / 2 * unitsPerPixel;
    const visualScale = mobile ? 1.5 : .78;
    const spanY = Math.max(.2, safeHalf - 1.05 * visualScale);
    const sideLayout = mode === 3 && !mobile;
    const centerX = sideLayout ? 3.2 : 0;
    const fitX = sideLayout ? .52 : 1;
    const convergence = ease((p - .12) / .37);
    const logoPulse = Math.sin(clamp((p - .28) / .38) * Math.PI);
    logo.position.set(centerX, cy, 2);
    logo.scale.setScalar((mix(1, .7, ease((p - .57) / .18)) + logoPulse * .14) * Math.min(visualScale, safeHalf / 1.4));
    logo.material.opacity = 1 - ease((p - .7) / .15);
    logo.rotation.z = mode === 1 ? -.12 * Math.sin(p * Math.PI) : 0;

    cards.forEach((card, i) => {
      const count = cards.length;
      const angle = i * 2.399963;
      const ring = .45 + .55 * Math.sqrt((i + 1) / count);
      let x = Math.cos(angle) * 6.7 * ring;
      let y = Math.sin(angle) * spanY * ring;
      let z = Math.sin(i * 7.3) * 2;
      let rotation = Math.sin(i * 3.1) * .23;
      let ry = Math.sin(i * 2.1) * .25;
      if (mode === 0) {
        // The supplied sketch: a broad cloud drawn down into the app.
        y = Math.sin(angle) * spanY;
      } else if (mode === 1) {
        const orbit = angle + p * 2.2;
        x = Math.cos(orbit) * (3.7 + ring * 2.9);
        y = Math.sin(orbit) * spanY;
        z = Math.sin(orbit) * 3;
        rotation = Math.sin(orbit) * .4;
      } else if (mode === 2) {
        x = ((i % 9) - 4) * 1.65 - p * 2;
        y = (Math.floor(i / 9) - .5) * spanY * 2;
        rotation = -.08;
        ry = -.22;
      } else if (mode === 3) {
        x = ((i % 6) - 2.5) * 2.3 + Math.sin(i * 3) * .45;
        y = (Math.floor(i / 6) - 1) * spanY;
        rotation = Math.sin(i * 2) * .36;
      } else {
        const orbit = angle + p * 1.3;
        x = Math.cos(orbit) * (2.4 + ring * 4.4);
        y = Math.sin(orbit) * spanY;
        z = -i * .3;
        rotation = orbit * .14;
        ry = Math.cos(orbit) * .52;
      }

      const intake = ease((p - .13 - (i / count) * .105) / .29);
      const release = ease((p - .57 - (i / count) * .23) / .16);
      const columns = mobile ? 6 : 9;
      const rows = Math.ceil(count / columns);
      let tx = ((i % columns) - (columns - 1) / 2) * (mobile ? 2.15 : 1.55);
      let ty = ((rows - 1) / 2 - Math.floor(i / columns)) * (mobile ? 2.35 : 2.15);
      let targetScale = mobile ? 1.05 : .9;
      if (mode === 1) {
        const col = i % 6, row = Math.floor(i / 6);
        tx = (col - 2.5) * 2.2;
        ty = (1 - row) * 1.7;
        targetScale = .8;
      } else if (mode === 2) {
        tx = ((i % 9) - 4) * 1.55;
        ty = (Math.floor(i / 9) === 0 ? 1.05 : -1.05);
        targetScale = .85;
      } else if (mode === 3) {
        tx = ((i % 6) - 2.5) * 2.15;
        ty = (1 - Math.floor(i / 6)) * 1.85;
        targetScale = .83;
      } else if (mode === 4) {
        tx = ((i % 6) - 2.5) * 2.1;
        ty = (1 - Math.floor(i / 6)) * 1.85;
        targetScale = .84;
      }
      // Hold cards beneath the mark before releasing them in their stable order.
      const finalRows = mode === 2 || (mode === 0 && !mobile) ? 2 : 3;
      const finalScale = Math.min(targetScale * visualScale * (sideLayout ? .63 : 1), safeHalf * 2 / (finalRows * 2.1));
      const row = Math.floor(i / (count / finalRows));
      ty = ((finalRows - 1) / 2 - row) * (finalScale * 1.8 + .2);
      const sx = mix(x, 0, intake), sy = mix(y, 0, intake);
      card.position.set(centerX + mix(sx, tx, release) * fitX, cy + mix(sy, ty, release), mix(z, 0, Math.max(convergence, release)));
      const tiny = mix(1, .06, intake);
      // Orthographic framing with explicit perspective magnification for the tunnel.
      const depthScale = mode === 4 ? mix(1 / (1 + i * .065), 1, Math.max(intake, release)) : 1;
      card.scale.setScalar(mix(tiny * (sideLayout ? .63 : 1) * visualScale, finalScale, release) * depthScale);
      card.rotation.set(0, ry * (1 - intake) * (1 - release), rotation * (1 - intake) * (1 - release));
      const halfExtent = (items[i].kind === 'provider' ? .74 : 1.1) * card.scale.x;
      card.position.y = cy + clamp(card.position.y - cy, -Math.max(0, safeHalf - halfExtent), Math.max(0, safeHalf - halfExtent));
      card.material.opacity = Math.max(1 - ease((intake - .7) / .3), release);
      card.renderOrder = i;
    });
    renderer.render(scene, camera);
  }

  function resize() {
    const width = Math.max(container.clientWidth, 1);
    pixelHeight = Math.max(container.clientHeight, 1);
    height = 16 * pixelHeight / width;
    mobile = width < 650;
    camera.left = -8;
    camera.right = 8;
    camera.top = height / 2;
    camera.bottom = -height / 2;
    camera.updateProjectionMatrix();
    renderer.setSize(width, pixelHeight, false);
    update(previousProgress, previousVariant);
  }
  resize();
  return { update, resize, dispose() {
    resources.forEach(resource => resource.dispose());
    renderer.dispose();
    renderer.domElement.remove();
  } };
}
