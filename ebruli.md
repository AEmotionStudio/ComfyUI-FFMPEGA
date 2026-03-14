 <html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>three.js + Liquid Art Shader</title>
    <style>
      html, body { margin: 0; padding: 0; overflow: hidden; background: #111; }
      canvas { display: block; }
    </style>
  </head>
  <body>
    <script src="https://cdn.jsdelivr.net/npm/three@0.155.0/build/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/dat.gui@0.7.9/build/dat.gui.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/animejs@3.2.2/lib/anime.min.js"></script>

    <script>
      const renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setSize(window.innerWidth, window.innerHeight);
      document.body.appendChild(renderer.domElement);

      const scene = new THREE.Scene();
      const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10);
      camera.position.z = 1;
      const geometry = new THREE.PlaneGeometry(2, 2);

      const uniforms = {
        uTime: { value: 0 },
        uResolution: { value: new THREE.Vector2(window.innerWidth, window.innerHeight) },
        uTexAspect: { value: 1.0 },
        uScale: { value: 3.0 },     // Dalga ölçeği
        uSpeed: { value: 0.5 },     // Akış hızı
        uStrength: { value: 0.3 },  // Bükülme gücü
        uColorShift: { value: 0.1 },// Renk sapması
        uTex: { value: null }
      };

      const proxyUniforms = {
        uScale: uniforms.uScale.value,
        uSpeed: uniforms.uSpeed.value,
        uStrength: uniforms.uStrength.value,
        uColorShift: uniforms.uColorShift.value
      };

      const loader = new THREE.TextureLoader();
      // Soyut/Renkli bir görsel bu efektle daha iyi gider
      loader.load('https://images.unsplash.com/photo-1550684848-fac1c5b4e853', tex => {
        tex.minFilter = THREE.LinearFilter;
        tex.magFilter = THREE.LinearFilter;
        uniforms.uTex.value = tex;
        uniforms.uTexAspect.value = tex.image.width / tex.image.height;
      });

      const fragmentShader = `
      precision highp float;
      uniform sampler2D uTex;
      uniform vec2 uResolution;
      uniform float uTexAspect;
      uniform float uTime;
      uniform float uScale;
      uniform float uSpeed;
      uniform float uStrength;
      uniform float uColorShift;

      // Basit bir 2D Noise fonksiyonu
      vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
      vec2 mod289(vec2 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
      vec3 permute(vec3 x) { return mod289(((x*34.0)+1.0)*x); }

      float snoise(vec2 v) {
        const vec4 C = vec4(0.211324865405187, 0.366025403784439, -0.577350269189626, 0.024390243902439);
        vec2 i  = floor(v + dot(v, C.yy) );
        vec2 x0 = v -   i + dot(i, C.xx);
        vec2 i1;
        i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
        vec4 x12 = x0.xyxy + C.xxzz;
        x12.xy -= i1;
        i = mod289(i);
        vec3 p = permute( permute( i.y + vec3(0.0, i1.y, 1.0 )) + i.x + vec3(0.0, i1.x, 1.0 ));
        vec3 m = max(0.5 - vec3(dot(x0,x0), dot(x12.xy,x12.xy), dot(x12.zw,x12.zw)), 0.0);
        m = m*m ;
        m = m*m ;
        vec3 x = 2.0 * fract(p * C.www) - 1.0;
        vec3 h = abs(x) - 0.5;
        vec3 ox = floor(x + 0.5);
        vec3 a0 = x - ox;
        m *= 1.79284291400159 - 0.85373472095314 * ( a0*a0 + h*h );
        vec3 g;
        g.x  = a0.x  * x0.x  + h.x  * x0.y;
        g.yz = a0.yz * x12.xz + h.yz * x12.yw;
        return 130.0 * dot(m, g);
      }

      void main() {
        vec2 uv = gl_FragCoord.xy / uResolution;
        
        // Aspect ratio düzeltmesi
        float screenAspect = uResolution.x / uResolution.y;
        float texAspect = uTexAspect;
        vec2 scale = vec2(1.0);
        if (screenAspect > texAspect) scale.y = texAspect / screenAspect;
        else scale.x = screenAspect / texAspect;
        uv = (uv - 0.5) * scale + 0.5;

        // --- LIQUID LOGIC ---
        // Koordinatları noise ile büküyoruz (Domain Warping)
        float t = uTime * uSpeed;
        
        // 1. Katman Noise
        float n1 = snoise(uv * uScale + vec2(t * 0.1, t * 0.2));
        
        // 2. Katman Noise (Daha karmaşık akış için ilkiyle birleştiriyoruz)
        vec2 flowUV = uv + vec2(n1) * uStrength;
        float n2 = snoise(flowUV * uScale * 1.5 - t * 0.3);

        // Renk kanallarını (RGB) hafifçe farklı koordinatlardan alarak "Color Aberration" yapıyoruz
        float r = texture2D(uTex, flowUV + vec2(n2 * uColorShift, 0.0)).r;
        float g = texture2D(uTex, flowUV).g;
        float b = texture2D(uTex, flowUV - vec2(n2 * uColorShift, 0.0)).b;

        // Kenarları siyahlaştırma (Vignette) - Sonsuz tekrarı gizlemek için
        float vignette = 1.0 - smoothstep(0.5, 1.5, length((uv - 0.5) * 2.0));
        
        vec3 finalColor = vec3(r, g, b) * vignette;
        gl_FragColor = vec4(finalColor, 1.0);
      }
      `;

      const material = new THREE.ShaderMaterial({ uniforms, fragmentShader });
      const mesh = new THREE.Mesh(geometry, material);
      scene.add(mesh);

      // --- Resize & Loop ---
      window.addEventListener('resize', () => {
        renderer.setSize(window.innerWidth, window.innerHeight);
        uniforms.uResolution.value.set(window.innerWidth, window.innerHeight);
      });
      const clock = new THREE.Clock();
      renderer.setAnimationLoop(() => {
        uniforms.uTime.value = clock.getElapsedTime();
        renderer.render(scene, camera);
      });

      // --- GUI Controls ---
      const gui = new dat.GUI();
      const controls = {
        randomize: () => {
           anime({
            targets: proxyUniforms,
            easing: 'easeInOutQuad',
            duration: 1000,
            uScale: Math.random() * 5 + 1,
            uSpeed: Math.random() * 1.0 + 0.1,
            uStrength: Math.random() * 0.5 + 0.1,
            uColorShift: Math.random() * 0.1,
            update: () => {
              uniforms.uScale.value = proxyUniforms.uScale;
              uniforms.uSpeed.value = proxyUniforms.uSpeed;
              uniforms.uStrength.value = proxyUniforms.uStrength;
              uniforms.uColorShift.value = proxyUniforms.uColorShift;
            }
          });
        }
      };
      
      gui.add(controls, 'randomize').name('Random Flow');
      gui.add(proxyUniforms, 'uScale', 1, 10).onChange(v => uniforms.uScale.value = v);
      gui.add(proxyUniforms, 'uSpeed', 0, 2).onChange(v => uniforms.uSpeed.value = v);
      gui.add(proxyUniforms, 'uStrength', 0, 1).onChange(v => uniforms.uStrength.value = v);
      gui.add(proxyUniforms, 'uColorShift', 0, 0.2).onChange(v => uniforms.uColorShift.value = v);
      
      renderer.domElement.addEventListener('dblclick', controls.randomize);
    </script>
  </body>
</html>
