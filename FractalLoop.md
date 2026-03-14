<html lang="en">
    <script type="importmap">
        {
            "imports": {
                "three": "https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.js"
            }
        }
    </script>
    <script type="module">
        import * as THREE from 'three';
        let scene, camera, renderer, material, clock;
        const uniforms = {
            t: { value: 0.0 },
            r: { value: new THREE.Vector2(window.innerWidth, window.innerHeight) }
        };
        function init() {
            scene = new THREE.Scene();
            clock = new THREE.Clock();
           
            camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10);
            camera.position.z = 1;
            renderer = new THREE.WebGLRenderer();
            renderer.setSize(window.innerWidth, window.innerHeight);
            document.body.appendChild(renderer.domElement);
            const geometry = new THREE.PlaneGeometry(2, 2);
            material = new THREE.ShaderMaterial({
                uniforms: uniforms,
               
                vertexShader: `
                    varying vec2 vUv;
                    void main() {
                        vUv = uv;
                        gl_Position = vec4(position, 1.0);
                    }
                `,
               
                fragmentShader: `
                    uniform vec2 r;
                    uniform float t;
                    varying vec2 vUv;
                    mat2 rot(float a) {
                        float s = sin(a);
                        float c = cos(a);
                        return mat2(c, -s, s, c);
                    }
                    void main() {
                        vec2 uv = (vUv - 0.5) * 2.0;
                        uv.x *= r.x / r.y;
                        vec3 col = vec3(0.0);
                        float time = t * 0.1;
                        for (int i = 0; i < 5; i++) {
                            uv = abs(uv);
                           
                            uv = uv / dot(uv, uv);
                           
                            uv -= 0.7;
                            uv *= rot(time * 0.3 + float(i) * 0.5);
                        }
                        float d = length(uv);
                       
                        col.r = 0.5 + 0.5 * sin(d * 3.0 - time * 2.0);
                        col.g = 0.5 + 0.5 * sin(d * 3.5 - time * 1.5);
                        col.b = 0.5 + 0.5 * sin(d * 4.0 - time * 3.0);
                       
                        col /= (d * 0.8 + 1.0);
                        gl_FragColor = vec4(col, 1.0);
                    }
                `
            });
            const mesh = new THREE.Mesh(geometry, material);
            scene.add(mesh);
            window.addEventListener('resize', onWindowResize);
        }
        function onWindowResize() {
            renderer.setSize(window.innerWidth, window.innerHeight);
            uniforms.r.value.set(window.innerWidth, window.innerHeight);
        }
        function animate() {
            requestAnimationFrame(animate);
            uniforms.t.value = clock.getElapsedTime();
            renderer.render(scene, camera);
        }
        init();
        animate();
    </script>
    <style>
        body { margin: 0; background-color: #000; }
        canvas { display: block; width: 100%; height: 100%; }
    </style>
</html>