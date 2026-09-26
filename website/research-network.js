// A quiet, original research constellation using the locally pinned Three.js runtime.
const host = document.querySelector('.research-network');
const hero = document.querySelector('.hero');

async function createNetwork() {
  let renderer;
  try {
    const THREE = await import('./vendor/three-0.169.0.module.min.js');
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('webgl2', { alpha: true, antialias: true, powerPreference: 'low-power' });
    if (!context) return;
    renderer = new THREE.WebGLRenderer({ canvas, context, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
    renderer.setClearColor(0x000000, 0);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, .1, 50);
    camera.position.z = 8;
    const group = new THREE.Group();
    scene.add(group);
    const points = [];
    // Deterministic spiral bands suggest relationships between evidence, data and results.
    for (let index = 0; index < 210; index++) {
      const angle = index * 2.399963;
      const band = index % 3;
      const radius = 2.35 + band * .36 + Math.sin(index * 1.7) * .2;
      points.push(new THREE.Vector3(Math.cos(angle) * radius * 1.75, Math.sin(angle) * radius * .72, Math.sin(index * .53) * .9));
    }
    const positions = points.flatMap(point => [point.x, point.y, point.z]);
    const pointGeometry = new THREE.BufferGeometry();
    pointGeometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    const pointMaterial = new THREE.PointsMaterial({ color: 0xb3acff, size: .032, transparent: true, opacity: .85, blending: THREE.AdditiveBlending, depthWrite: false });
    group.add(new THREE.Points(pointGeometry, pointMaterial));
    const segments = [];
    points.forEach((point, i) => {
      points.slice(i + 1).forEach(other => {
        if (point.distanceTo(other) < .76) segments.push(point.x, point.y, point.z, other.x, other.y, other.z);
      });
    });
    const lineGeometry = new THREE.BufferGeometry();
    lineGeometry.setAttribute('position', new THREE.Float32BufferAttribute(segments, 3));
    const lineMaterial = new THREE.LineBasicMaterial({ color: 0x7a88d5, transparent: true, opacity: .23, blending: THREE.AdditiveBlending, depthWrite: false });
    group.add(new THREE.LineSegments(lineGeometry, lineMaterial));
    const orbitGeometry = new THREE.BufferGeometry().setFromPoints(Array.from({ length: 161 }, (_, i) => {
      const angle = i / 160 * Math.PI * 2;
      return new THREE.Vector3(Math.cos(angle) * 5.7, Math.sin(angle) * 1.95, Math.sin(angle) * .6);
    }));
    group.add(new THREE.Line(orbitGeometry, new THREE.LineBasicMaterial({ color: 0x9d8bf4, transparent: true, opacity: .24 })));
    host.append(canvas);
    hero.classList.add('network-ready');
    let frame = 0;
    let last = 0;
    let elapsed = 0;
    let visible = true;
    let lost = false;
    const pointer = { x: 0, y: 0 };
    function resize() {
      const { width, height } = host.getBoundingClientRect();
      if (!width || !height) return;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.render(scene, camera);
    }
    const canRun = () => visible && !document.hidden && !lost;
    function tick(now) {
      frame = 0;
      if (!canRun()) return;
      const delta = now - last;
      if (delta >= 1000 / 30) {
        elapsed += Math.min(delta, 50) / 1000;
        last = now;
        group.rotation.z = Math.sin(elapsed * .08) * .12 - .13;
        group.rotation.y += (pointer.x * .17 + Math.sin(elapsed * .12) * .12 - group.rotation.y) * .04;
        group.rotation.x += (pointer.y * .1 - group.rotation.x) * .04;
        renderer.render(scene, camera);
      }
      frame = requestAnimationFrame(tick);
    }
    function sync() {
      if (!canRun()) { cancelAnimationFrame(frame); frame = 0; }
      else if (!frame) { last = performance.now(); frame = requestAnimationFrame(tick); }
    }
    hero.addEventListener('pointermove', event => {
      if (event.pointerType === 'touch') return;
      const rect = hero.getBoundingClientRect();
      pointer.x = (event.clientX - rect.left) / rect.width - .5;
      pointer.y = (event.clientY - rect.top) / host.clientHeight - .5;
    }, { passive: true });
    hero.addEventListener('pointerleave', () => { pointer.x = 0; pointer.y = 0; });
    canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); lost = true; sync(); hero.classList.remove('network-ready'); });
    canvas.addEventListener('webglcontextrestored', () => { lost = false; hero.classList.add('network-ready'); resize(); sync(); });
    document.addEventListener('visibilitychange', sync);
    if ('IntersectionObserver' in window) new IntersectionObserver(entries => { visible = entries[0].isIntersecting; sync(); }).observe(host);
    if ('ResizeObserver' in window) new ResizeObserver(resize).observe(host);
    else addEventListener('resize', resize, { passive: true });
    resize();
    sync();
  } catch {
    renderer?.dispose();
    host.replaceChildren();
    hero.classList.remove('network-ready');
  }
}
createNetwork();
