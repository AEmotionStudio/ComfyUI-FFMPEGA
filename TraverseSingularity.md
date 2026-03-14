<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Wormhole</title>
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { overflow: hidden; background: #000; cursor: none; }
    canvas { display: block; }

    #overlay {
        position: fixed; inset: 0; pointer-events: none; z-index: 10;
        background: radial-gradient(ellipse at center,
            transparent 30%,
            rgba(0,0,0,0.45) 70%,
            rgba(0,0,0,0.85) 100%);
    }
    #scanlines {
        position: fixed; inset: 0; pointer-events: none; z-index: 11;
        background: repeating-linear-gradient(
            0deg,
            transparent,
            transparent 2px,
            rgba(0,0,0,0.03) 2px,
            rgba(0,0,0,0.03) 4px
        );
    }
    #grain {
        position: fixed; inset: 0; pointer-events: none; z-index: 12;
        opacity: 0.04;
        background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
    }
    #cursor {
        position: fixed; pointer-events: none; z-index: 100;
        width: 12px; height: 12px;
        border: 1.5px solid rgba(180,120,255,0.9);
        border-radius: 50%;
        transform: translate(-50%, -50%);
        transition: width 0.2s, height 0.2s, opacity 0.2s;
        box-shadow: 0 0 8px rgba(180,120,255,0.6), inset 0 0 4px rgba(180,120,255,0.3);
    }
    #cursor-dot {
        position: fixed; pointer-events: none; z-index: 101;
        width: 3px; height: 3px;
        background: rgba(220,160,255,1);
        border-radius: 50%;
        transform: translate(-50%, -50%);
        box-shadow: 0 0 6px rgba(220,160,255,1);
    }
    #hud {
        position: fixed; bottom: 38px; left: 50%; transform: translateX(-50%);
        pointer-events: none; z-index: 20;
        display: flex; flex-direction: column; align-items: center; gap: 8px;
    }
    #hud-label {
        font-family: 'Courier New', monospace;
        font-size: 10px; letter-spacing: 0.35em;
        color: rgba(180,130,255,0.5);
        text-transform: uppercase;
        animation: hudpulse 3s ease-in-out infinite;
    }
    #hud-bar {
        width: 120px; height: 1px;
        background: linear-gradient(90deg, transparent, rgba(180,130,255,0.5), transparent);
        animation: hudpulse 3s ease-in-out infinite;
    }
    @keyframes hudpulse {
        0%,100% { opacity: 0.4; }
        50%      { opacity: 1.0; }
    }

    #speed-lines {
        position: fixed; inset: 0; pointer-events: none; z-index: 9;
        opacity: 0;
        background: radial-gradient(ellipse at center,
            transparent 20%,
            rgba(120,60,220,0.03) 60%,
            transparent 100%);
        animation: speedpulse 2.5s ease-in-out infinite;
    }
    @keyframes speedpulse {
        0%,100% { opacity: 0; transform: scale(1); }
        50%      { opacity: 1; transform: scale(1.04); }
    }

    .ripple {
        position: fixed; pointer-events: none; z-index: 50;
        border-radius: 50%;
        transform: translate(-50%, -50%) scale(0);
        animation: rippleOut 0.9s cubic-bezier(0.1, 0.6, 0.3, 1) forwards;
    }
    @keyframes rippleOut {
        0%   { transform: translate(-50%,-50%) scale(0);   opacity: 1; }
        100% { transform: translate(-50%,-50%) scale(1);   opacity: 0; }
    }
    #boost-vignette {
        position: fixed; inset: 0; pointer-events: none; z-index: 8;
        background: radial-gradient(ellipse at center,
            transparent 25%, rgba(80,20,160,0.18) 65%, rgba(0,0,0,0.55) 100%);
        opacity: 0; transition: opacity 0.15s;
    }
</style>
<script type="importmap">
{
    "imports": {
        "three": "https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js",
        "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/"
    }
}
</script>

<div id="overlay"></div>
<div id="scanlines"></div>
<div id="grain"></div>
<div id="speed-lines"></div>
<div id="boost-vignette"></div>
<div id="cursor"></div>
<div id="cursor-dot"></div>
<div id="hud">
    <div id="hud-label">Traversing Singularity</div>
    <div id="hud-bar"></div>
</div>

<script type="module">
import * as THREE from 'three';

const cursorEl    = document.getElementById('cursor');
const cursorDotEl = document.getElementById('cursor-dot');
const boostVig    = document.getElementById('boost-vignette');
let mouseX = innerWidth / 2, mouseY = innerHeight / 2;
let smoothX = mouseX, smoothY = mouseY;

let targetCamX = 0, targetCamY = 0;
let camX = 0, camY = 0;

let speedTarget  = 1.0;
let speedCurrent = 1.0;
let burstVal     = 0.0;

let prevMX = mouseX, prevMY = mouseY;
let velX = 0, velY = 0;
let warpX = 0, warpY = 0;

let isDragging    = false;
let dragStartX    = 0, dragStartY = 0;
let manualRotZ    = 0;
let dragVelZ      = 0;

let scrollBoost   = 0.0;
let lastPinchDist = 0;

function spawnRipple(x, y) {
    const colors = [
        ['rgba(120,60,255,0.9)',  'rgba(80,20,200,0.0)',   140],
        ['rgba(0,200,255,0.7)',   'rgba(0,120,200,0.0)',   200],
        ['rgba(255,40,160,0.6)',  'rgba(180,0,100,0.0)',   100],
    ];
    colors.forEach(([from, to, size], i) => {
        const el = document.createElement('div');
        el.className = 'ripple';
        el.style.cssText = `
            left:${x}px; top:${y}px;
            width:${size}px; height:${size}px;
            border: 1.5px solid ${from};
            box-shadow: 0 0 12px ${from}, inset 0 0 8px ${from};
            animation-delay: ${i * 0.08}s;
            animation-duration: ${0.75 + i * 0.12}s;
        `;
        document.body.appendChild(el);
        el.addEventListener('animationend', () => el.remove());
    });
}

document.addEventListener('mousemove', e => {
    prevMX = mouseX; prevMY = mouseY;
    mouseX = e.clientX; mouseY = e.clientY;
    velX = mouseX - prevMX;
    velY = mouseY - prevMY;
    targetCamX = (e.clientX / innerWidth  - 0.5) * 14.0;
    targetCamY = (e.clientY / innerHeight - 0.5) * -9.0;
});

document.addEventListener('click', e => {
    spawnRipple(e.clientX, e.clientY);
    burstVal    = 1.2;
    speedTarget = 3.5;
    setTimeout(() => { speedTarget = 1.0; }, 600);
});

document.addEventListener('contextmenu', e => {
    e.preventDefault();
    spawnRipple(e.clientX, e.clientY);
    speedTarget = -1.5;
    setTimeout(() => { speedTarget = 1.0; }, 700);
});

window.addEventListener('wheel', e => {
    scrollBoost += e.deltaY * 0.003;
    scrollBoost  = Math.max(-2.5, Math.min(4.0, scrollBoost));
}, { passive: true });

document.addEventListener('mousedown', e => {
    if (e.button === 0) { isDragging = true; dragStartX = e.clientX; dragStartY = e.clientY; dragVelZ = 0; }
});
document.addEventListener('mousemove', e => {
    if (isDragging) {
        const dx  = e.clientX - dragStartX;
        dragVelZ  = dx * 0.008;
        manualRotZ += dragVelZ;
        dragStartX = e.clientX; dragStartY = e.clientY;
    }
});
document.addEventListener('mouseup', () => { isDragging = false; });

document.addEventListener('touchstart', e => {
    if (e.touches.length === 1) {
        const t = e.touches[0];
        mouseX = t.clientX; mouseY = t.clientY;
        targetCamX = (t.clientX / innerWidth  - 0.5) * 14.0;
        targetCamY = (t.clientY / innerHeight - 0.5) * -9.0;
        spawnRipple(t.clientX, t.clientY);
        burstVal    = 1.2;
        speedTarget = 3.0;
        setTimeout(() => { speedTarget = 1.0; }, 500);
    }
    if (e.touches.length === 2) {
        lastPinchDist = Math.hypot(
            e.touches[0].clientX - e.touches[1].clientX,
            e.touches[0].clientY - e.touches[1].clientY
        );
    }
}, { passive: true });

document.addEventListener('touchmove', e => {
    if (e.touches.length === 1) {
        const t = e.touches[0];
        prevMX = mouseX; prevMY = mouseY;
        mouseX = t.clientX; mouseY = t.clientY;
        velX = mouseX - prevMX; velY = mouseY - prevMY;
        targetCamX = (t.clientX / innerWidth  - 0.5) * 14.0;
        targetCamY = (t.clientY / innerHeight - 0.5) * -9.0;
    }
    if (e.touches.length === 2) {
        const d = Math.hypot(
            e.touches[0].clientX - e.touches[1].clientX,
            e.touches[0].clientY - e.touches[1].clientY
        );
        const delta = d - lastPinchDist;
        scrollBoost  += delta * 0.04;
        scrollBoost   = Math.max(-2.5, Math.min(4.0, scrollBoost));
        lastPinchDist = d;
    }
}, { passive: true });

function updateCursor() {
    smoothX += (mouseX - smoothX) * 0.12;
    smoothY += (mouseY - smoothY) * 0.12;
    cursorEl.style.left    = mouseX + 'px';
    cursorEl.style.top     = mouseY + 'px';
    cursorDotEl.style.left = smoothX + 'px';
    cursorDotEl.style.top  = smoothY + 'px';
    const s = Math.min(2.5, speedCurrent);
    cursorEl.style.width  = (12 + s * 6) + 'px';
    cursorEl.style.height = (12 + s * 6) + 'px';
    cursorEl.style.borderColor = speedCurrent > 1.5
        ? `rgba(100,220,255,${0.7 + burstVal * 0.3})`
        : `rgba(180,120,255,0.9)`;
}

const tunnelVert = `
    varying vec2  vUv;
    varying float vDepth;
    uniform float uTime;
    uniform float uSpeed;
    uniform float uWarpX;
    uniform float uWarpY;
    void main() {
        vUv = uv;
        vec3 pos = position;
        float warpTime = uTime * 0.35 * uSpeed;
        pos.x += sin(pos.z * 0.018 + warpTime) * (5.5 + uWarpX * 4.0);
        pos.y += cos(pos.z * 0.018 + warpTime) * (5.5 + uWarpY * 4.0);
        pos.x += sin(pos.z * 0.055 + warpTime * 1.7) * (1.8 + uWarpX * 2.0);
        pos.y += cos(pos.z * 0.055 + warpTime * 1.7) * (1.8 + uWarpY * 2.0);
        vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
        gl_Position = projectionMatrix * mvPosition;
        vDepth = -mvPosition.z;
    }
`;

const tunnelFrag = `
    uniform float uTime;
    uniform float uSpeed;
    uniform float uBurst;
    varying vec2  vUv;
    varying float vDepth;

    vec3 mod289v3(vec3 x){return x-floor(x*(1./289.))*289.;}
    vec4 mod289v4(vec4 x){return x-floor(x*(1./289.))*289.;}
    vec4 permute(vec4 x){return mod289v4(((x*34.)+10.)*x);}
    vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
    float snoise(vec3 v){
        const vec2 C=vec2(1./6.,1./3.);
        const vec4 D=vec4(0.,.5,1.,2.);
        vec3 i=floor(v+dot(v,C.yyy));
        vec3 x0=v-i+dot(i,C.xxx);
        vec3 g=step(x0.yzx,x0.xyz);
        vec3 l=1.-g;
        vec3 i1=min(g.xyz,l.zxy);
        vec3 i2=max(g.xyz,l.zxy);
        vec3 x1=x0-i1+C.xxx;
        vec3 x2=x0-i2+C.yyy;
        vec3 x3=x0-D.yyy;
        i=mod289v3(i);
        vec4 p=permute(permute(permute(
            i.z+vec4(0.,i1.z,i2.z,1.))
            +i.y+vec4(0.,i1.y,i2.y,1.))
            +i.x+vec4(0.,i1.x,i2.x,1.));
        float n_=0.142857142857;
        vec3 ns=n_*D.wyz-D.xzx;
        vec4 j=p-49.*floor(p*ns.z*ns.z);
        vec4 x_=floor(j*ns.z);
        vec4 y_=floor(j-7.*x_);
        vec4 x=x_*ns.x+ns.yyyy;
        vec4 y=y_*ns.x+ns.yyyy;
        vec4 h=1.-abs(x)-abs(y);
        vec4 b0=vec4(x.xy,y.xy);
        vec4 b1=vec4(x.zw,y.zw);
        vec4 s0=floor(b0)*2.+1.;
        vec4 s1=floor(b1)*2.+1.;
        vec4 sh=-step(h,vec4(0.));
        vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;
        vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
        vec3 p0=vec3(a0.xy,h.x);
        vec3 p1=vec3(a0.zw,h.y);
        vec3 p2=vec3(a1.xy,h.z);
        vec3 p3=vec3(a1.zw,h.w);
        vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
        p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
        vec4 m=max(0.5-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.);
        m=m*m;
        return 42.*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
    }
    float fbm(vec3 p){
        float f=0.; float a=0.5;
        for(int i=0;i<6;i++){ f+=a*snoise(p); p*=2.02; a*=0.5; }
        return f;
    }
    float ridge(float h){ h=abs(h); h=1.-h; return h*h; }

    void main() {
        float t = uTime * 0.9 * uSpeed;

        float z     = vUv.y * 14.0 - t * 3.5;
        float angle = vUv.x * 6.2831853;
        angle += sin(z * 0.18) * 2.2 + cos(z * 0.08) * 1.1;

        vec3 p = vec3(cos(angle), sin(angle), z);

        vec3 color = vec3(0.0);

        float nBase = snoise(p * 0.35 + vec3(0., 0., t * 0.18));
        vec3 baseA  = vec3(0.01, 0.005, 0.06);
        vec3 baseB  = vec3(0.06, 0.02,  0.18);
        color += mix(baseA, baseB, nBase * 0.5 + 0.5);

        vec3 pFib = vec3(cos(angle)*4.5, sin(angle)*4.5, z * 0.13);
        float nFib = snoise(pFib + vec3(0., 0., t * 1.1));
        float nFib2= snoise(pFib * 1.5 - vec3(0., 0., t * 0.7));
        float fib  = pow(smoothstep(0.32, 0.82, nFib),  2.2);
        float fib2 = pow(smoothstep(0.38, 0.88, nFib2), 2.0);
        color += vec3(0.0, 0.85, 1.0) * fib  * 2.2;
        color += vec3(1.0, 0.12, 0.72) * fib2 * 2.0;
        color += vec3(0.65, 0.25, 1.0) * fib * fib2 * 2.8;

        float zD1   = z * 2.6 + snoise(p * 1.4 - vec3(0., 0., t)) * 2.2;
        float zD2   = z * 3.8 + snoise(p * 2.0 + vec3(0., 0., t * 1.3)) * 1.5;
        float rings1 = smoothstep(0.94, 1.0, abs(sin(zD1)));
        float rings2 = smoothstep(0.96, 1.0, abs(sin(zD2)));
        rings1 *= smoothstep(0.2, 1.0, snoise(p*2.0+vec3(t))*0.5+0.5);
        rings2 *= smoothstep(0.3, 1.0, snoise(p*2.5-vec3(t*0.8))*0.5+0.5);
        color += vec3(1.0, 0.75, 0.25) * rings1 * 2.5;
        color += vec3(0.15, 1.0, 0.82) * rings2 * 2.2;

        float rings = rings1 + rings2;

        float betweenMask = 1.0 - smoothstep(0.01, 0.20, rings);
        betweenMask *= 1.0 - smoothstep(0.03, 0.28, fib + fib2);
        betweenMask = clamp(betweenMask, 0.0, 1.0);

        float cloud1 = fbm(vec3(cos(angle)*1.3, sin(angle)*1.3, z*0.40 - t*0.07));
        float cloud2 = fbm(vec3(cos(angle*2.)*2.2, sin(angle*2.)*2.2, z*0.90 + t*0.04));
        float clouds = smoothstep(-0.18, 0.72, cloud1*0.65 + cloud2*0.35);
        vec3 cloudCol = mix(vec3(0.02, 0.01, 0.07), vec3(0.10, 0.04, 0.20), clouds);
        cloudCol = mix(cloudCol, vec3(0.04, 0.06, 0.22), smoothstep(0.5, 1.0, clouds));
        cloudCol += vec3(0.0, 0.04, 0.12) * smoothstep(0.6, 1.0, clouds);
        color += cloudCol * betweenMask * 0.7;

        float fil1 = ridge(snoise(vec3(cos(angle)*3.5, sin(angle)*3.5, z*0.70 - t*0.4)));
        float fil2 = ridge(snoise(vec3(cos(angle)*7.0, sin(angle)*7.0, z*1.30 + t*0.16)));
        float fil3 = ridge(snoise(vec3(cos(angle)*12., sin(angle)*12., z*2.20 - t*0.55)));
        float filaments = smoothstep(0.68, 0.90, fil1*0.5 + fil2*0.32 + fil3*0.18);
        vec3 filCol = mix(
            vec3(0.3, 0.1, 0.8),
            vec3(0.0, 0.8, 1.0),
            0.5 + 0.5*sin(z*0.7 - t*0.45)
        );
        filCol = mix(filCol, vec3(1.0, 0.3, 0.7), 0.5+0.5*cos(z*0.5 + t*0.3));
        color += filCol * filaments * betweenMask * 0.38;

        float dustA = snoise(vec3(cos(angle)*20., sin(angle)*20., z*4.5 - t*2.8));
        float dustB = snoise(vec3(cos(angle)*32., sin(angle)*32., z*7.0 + t*3.2));
        float dustC = snoise(vec3(cos(angle*3.)*15., sin(angle*3.)*15., z*5.5 - t*1.9));
        float dustSpark = smoothstep(0.88, 0.99, dustA) + smoothstep(0.90, 0.99, dustB) * 0.6
                        + smoothstep(0.91, 0.99, dustC) * 0.4;
        vec3 sparkCol = mix(vec3(1.0, 0.7, 0.3), vec3(0.5, 0.9, 1.0), fract(angle + z * 0.2));
        color += sparkCol * dustSpark * betweenMask * 0.65;

        float nS  = snoise(p * 28.0 - vec3(0., 0., t * 4.5));
        float nS2 = snoise(p * 42.0 + vec3(0., 0., t * 6.0));
        color += vec3(0.88, 0.92, 1.0) * smoothstep(0.90, 1.0, nS)  * 1.4;
        color += vec3(1.0,  0.72, 0.88) * smoothstep(0.92, 1.0, nS2) * 1.1;

        float edgeGlow = smoothstep(0.88, 0.97, abs(sin(zD1 + 0.05)));
        color += vec3(0.0, 1.0, 0.9) * edgeGlow * 0.5;

        float radial = 1.0 - abs(vUv.x - 0.5) * 1.8;
        radial = max(radial, 0.0);
        color += vec3(0.05, 0.02, 0.12) * radial * 0.5;

        color = max(color, 0.0);
        color = pow(color, vec3(1.08));
        float lum = dot(color, vec3(0.2126, 0.7152, 0.0722));
        color = mix(vec3(lum), color, 1.25);

        float fog = smoothstep(18.0, 140.0, vDepth);
        color = mix(color, vec3(0.0), fog);

        color += vec3(0.7, 0.5, 1.0) * uBurst * (1.0 - fog) * 0.9;

        gl_FragColor = vec4(color, 1.0);
    }
`;

const geoVert = `
    varying vec2 vUv; varying vec3 vPos;
    void main() { vUv=uv; vPos=position; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }
`;

const knotFrag = `
    uniform float uTime;
    varying vec2 vUv;
    void main() {
        float t = uTime;
        float band  = sin(vUv.x * 55.0 - t * 6.0) * 0.5 + 0.5;
        float band2 = sin(vUv.x * 23.0 + t * 3.5) * 0.5 + 0.5;
        float band3 = sin(vUv.x * 8.0  - t * 1.2) * 0.5 + 0.5;
        float rim   = pow(abs(sin(vUv.y * 3.14159)), 2.5);
        float pulse = 0.55 + 0.45 * sin(t * 2.8);
        vec3 c1 = vec3(0.0,  0.85, 1.0);
        vec3 c2 = vec3(0.95, 0.10, 0.80);
        vec3 c3 = vec3(1.00, 0.80, 0.20);
        vec3 c4 = vec3(0.40, 0.15, 1.0);
        vec3 col = mix(c1, c2, band);
        col = mix(col, c3, band2 * 0.45);
        col = mix(col, c4, band3 * 0.3);
        col += vec3(1.0) * rim * pulse * 2.5;
        col *= 0.8 + 0.4 * pulse;
        gl_FragColor = vec4(col, 1.0);
    }
`;

const ringFrag = `
    uniform float uTime;
    uniform vec3  uColor;
    varying vec2  vUv;
    void main() {
        float rim   = pow(abs(sin(vUv.y * 3.14159)), 2.2);
        float pulse = 0.5 + 0.5 * sin(uTime * 2.2 + vUv.x * 12.0);
        float shimmer = 0.5 + 0.5 * sin(uTime * 5.0 + vUv.x * 40.0);
        vec3 col    = uColor * (2.0 + 0.8 * pulse) + uColor * shimmer * 0.4;
        float alpha = rim * (0.65 + 0.35 * pulse);
        gl_FragColor = vec4(col, alpha);
    }
`;

const discFrag = `
    uniform float uTime;
    varying vec2 vUv;
    void main() {
        vec2 uv = vUv * 2.0 - 1.0;
        float r = length(uv);
        float a = atan(uv.y, uv.x);
        float t = uTime;
        float petals  = pow(cos(a * 16.0 - t * 0.9) * 0.5 + 0.5, 3.5);
        float petals2 = pow(cos(a * 7.0  + t * 1.3) * 0.5 + 0.5, 4.0);
        float rings   = smoothstep(0.78, 1.0, abs(sin(r * 24.0 - t * 3.0)));
        float mask    = smoothstep(1.0, 0.82, r) * smoothstep(0.0, 0.10, r);
        vec3 c1 = vec3(0.0,  0.8, 1.0);
        vec3 c2 = vec3(1.0,  0.2, 0.9);
        vec3 c3 = vec3(1.0,  0.9, 0.3);
        vec3 col = mix(c1, c2, r);
        col = mix(col, c3, petals2 * 0.35);
        col += vec3(1.0, 0.85, 0.5) * rings * 3.0;
        col *= (petals * 0.6 + petals2 * 0.4) * mask;
        float alpha = (petals * 0.5 + petals2 * 0.3 + rings * 1.1) * mask;
        gl_FragColor = vec4(col, alpha);
    }
`;

const haloFrag = `
    uniform float uTime;
    varying vec2 vUv;
    void main() {
        vec2 uv  = vUv * 2.0 - 1.0;
        float r  = length(uv);
        float a  = atan(uv.y, uv.x);
        float p1 = 0.5 + 0.5 * sin(uTime * 1.6 + a * 3.0);
        float p2 = 0.5 + 0.5 * sin(uTime * 2.4 - a * 5.0);
        float glow = exp(-r * 2.8) * (0.5 + 0.5 * p1);
        float rim  = exp(-(r - 0.78) * (r - 0.78) * 40.0) * (0.6 + 0.4 * p2);
        vec3 colA = vec3(0.1, 0.05, 0.9);
        vec3 colB = vec3(0.0, 0.8,  1.0);
        vec3 colC = vec3(1.0, 0.15, 0.7);
        vec3 col  = mix(colA, colB, r * 0.8);
        col = mix(col, colC, p2 * 0.4);
        float alpha = (glow + rim) * 0.7;
        gl_FragColor = vec4(col * (glow + rim), alpha);
    }
`;

const particleVert = `
    attribute float aSpeed;
    attribute float aSize;
    attribute vec3  aColor;
    uniform float uTime;
    uniform float uSpeed;
    varying vec3  vColor;
    varying float vAlpha;
    void main() {
        vColor = aColor;
        vec3 pos = position;
        float z = mod(pos.z + uTime * aSpeed * 60.0 * uSpeed, 220.0) - 110.0;
        pos.z = z;
        float alpha = 1.0 - smoothstep(0.0, 30.0, abs(z + 50.0));
        vAlpha = alpha * 0.9;
        vec4 mv = modelViewMatrix * vec4(pos, 1.0);
        gl_PointSize = aSize * (280.0 / -mv.z) * (0.8 + uSpeed * 0.5);
        gl_Position  = projectionMatrix * mv;
    }
`;
const particleFrag = `
    varying vec3  vColor;
    varying float vAlpha;
    void main() {
        vec2  uv   = gl_PointCoord * 2.0 - 1.0;
        float dist = length(uv);
        float glow = exp(-dist * dist * 3.0);
        float hard = smoothstep(0.8, 0.2, dist);
        gl_FragColor = vec4(vColor, (glow + hard * 0.4) * vAlpha);
    }
`;

const scene = new THREE.Scene();
scene.fog   = new THREE.FogExp2(0x000000, 0.0045);

const camera = new THREE.PerspectiveCamera(72, innerWidth / innerHeight, 0.1, 1000);
camera.position.set(0, 0, 50);

const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
renderer.setSize(innerWidth, innerHeight);
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.88;
document.body.appendChild(renderer.domElement);

const tunnelGeo = new THREE.CylinderGeometry(13, 13, 260, 80, 160, true);
tunnelGeo.rotateX(Math.PI / 2);
tunnelGeo.translate(0, 0, -55);

const tunnelMat = new THREE.ShaderMaterial({
    vertexShader: tunnelVert,
    fragmentShader: tunnelFrag,
    uniforms: {
        uTime:       { value: 0 },
        uSpeed:      { value: 1.0 },
        uWarpX:      { value: 0.0 },
        uWarpY:      { value: 0.0 },
        uBurst:      { value: 0.0 },
    },
    side: THREE.BackSide
});

scene.add(new THREE.Mesh(tunnelGeo, tunnelMat));

const PARTICLE_COUNT = 4200;
const pPositions = new Float32Array(PARTICLE_COUNT * 3);
const pSpeeds    = new Float32Array(PARTICLE_COUNT);
const pSizes     = new Float32Array(PARTICLE_COUNT);
const pColors    = new Float32Array(PARTICLE_COUNT * 3);

const palette = [
    [0.0, 0.85, 1.0],
    [1.0, 0.15, 0.72],
    [0.7, 0.3,  1.0],
    [1.0, 0.75, 0.25],
    [0.15, 1.0, 0.75],
    [1.0, 1.0,  1.0],
];

for (let i = 0; i < PARTICLE_COUNT; i++) {
    const r   = 3.0 + Math.random() * 9.5;
    const ang = Math.random() * Math.PI * 2;
    pPositions[i*3+0] = Math.cos(ang) * r;
    pPositions[i*3+1] = Math.sin(ang) * r;
    pPositions[i*3+2] = (Math.random() - 0.5) * 220;
    pSpeeds[i]        = 0.3 + Math.random() * 0.9;
    pSizes[i]         = 1.5 + Math.random() * 3.5;
    const c = palette[Math.floor(Math.random() * palette.length)];
    pColors[i*3+0] = c[0]; pColors[i*3+1] = c[1]; pColors[i*3+2] = c[2];
}

const pGeo = new THREE.BufferGeometry();
pGeo.setAttribute('position', new THREE.BufferAttribute(pPositions, 3));
pGeo.setAttribute('aSpeed',   new THREE.BufferAttribute(pSpeeds, 1));
pGeo.setAttribute('aSize',    new THREE.BufferAttribute(pSizes, 1));
pGeo.setAttribute('aColor',   new THREE.BufferAttribute(pColors, 3));

const pMat = new THREE.ShaderMaterial({
    vertexShader: particleVert,
    fragmentShader: particleFrag,
    uniforms: { uTime: { value: 0 }, uSpeed: { value: 1.0 } },
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    vertexColors: true
});

scene.add(new THREE.Points(pGeo, pMat));

const energyGroup = new THREE.Group();
energyGroup.position.set(0, 0, -165);
scene.add(energyGroup);

const knotMat = new THREE.ShaderMaterial({
    vertexShader: geoVert, fragmentShader: knotFrag,
    uniforms: { uTime: { value: 0 } }, side: THREE.DoubleSide
});
const knotMesh = new THREE.Mesh(new THREE.TorusKnotGeometry(9.5, 0.85, 320, 32, 3, 5), knotMat);
energyGroup.add(knotMesh);

const outerKnotMat = new THREE.ShaderMaterial({
    vertexShader: geoVert, fragmentShader: knotFrag,
    uniforms: { uTime: { value: 1.2 } },
    side: THREE.DoubleSide, transparent: true,
    blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0.45
});
const outerKnot = new THREE.Mesh(new THREE.TorusKnotGeometry(12.0, 0.5, 260, 24, 2, 7), outerKnotMat);
energyGroup.add(outerKnot);

function makeRing(radius, tube, hexColor, rx, ry) {
    const mat = new THREE.ShaderMaterial({
        vertexShader: geoVert, fragmentShader: ringFrag,
        uniforms: { uTime: { value: 0 }, uColor: { value: new THREE.Color(hexColor) } },
        transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide
    });
    const m = new THREE.Mesh(new THREE.TorusGeometry(radius, tube, 8, 160), mat);
    m.rotation.x = rx; m.rotation.y = ry;
    return m;
}

const rings = [
    makeRing(14.0, 0.10, 0x00d8ff,  0,              0),
    makeRing(14.0, 0.10, 0xff20c8,  Math.PI/2,      0),
    makeRing(14.0, 0.10, 0xffc832,  Math.PI/4,      Math.PI/4),
    makeRing(10.5, 0.08, 0x6a50ff,  0,              Math.PI/3),
    makeRing(17.5, 0.07, 0x20ffcc,  Math.PI/3,      Math.PI/6),
    makeRing(17.5, 0.07, 0xff4060,  Math.PI*0.6,    Math.PI/5),
];
rings.forEach(r => energyGroup.add(r));

const discMat = new THREE.ShaderMaterial({
    vertexShader: geoVert, fragmentShader: discFrag,
    uniforms: { uTime: { value: 0 } },
    transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide
});
const discMesh = new THREE.Mesh(new THREE.PlaneGeometry(38, 38), discMat);
discMesh.position.z = -1.0;
energyGroup.add(discMesh);

const icoMesh = new THREE.Mesh(
    new THREE.IcosahedronGeometry(5.5, 1),
    new THREE.MeshBasicMaterial({
        color: 0xaaffff, wireframe: true,
        blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, opacity: 0.5
    })
);
energyGroup.add(icoMesh);

const octaMesh = new THREE.Mesh(
    new THREE.OctahedronGeometry(7.5, 1),
    new THREE.MeshBasicMaterial({
        color: 0xff80ff, wireframe: true,
        blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, opacity: 0.35
    })
);
energyGroup.add(octaMesh);

const haloMat = new THREE.ShaderMaterial({
    vertexShader: geoVert, fragmentShader: haloFrag,
    uniforms: { uTime: { value: 0 } },
    transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide
});
const haloMesh = new THREE.Mesh(new THREE.PlaneGeometry(80, 80), haloMat);
haloMesh.position.z = -4.0;
energyGroup.add(haloMesh);

const allUniforms = [
    knotMat, outerKnotMat, discMat, haloMat,
    ...rings.map(r => r.material)
];

const clock = new THREE.Clock();

function animate() {
    requestAnimationFrame(animate);
    const t   = clock.getElapsedTime();
    const dt  = Math.min(clock.getDelta(), 0.05);

    updateCursor();

    scrollBoost  *= 0.93;
    const rawSpeed = speedTarget + scrollBoost;
    speedCurrent  += (rawSpeed - speedCurrent) * 0.06;

    burstVal *= 0.93;

    warpX += (velX * 0.012 - warpX) * 0.08;
    warpY += (velY * 0.012 - warpY) * 0.08;
    velX  *= 0.85; velY *= 0.85;

    camera.position.x = 0;
    camera.position.y = 0;
    const zBoost = Math.max(0, speedCurrent - 1.0) * 6.0;
    camera.position.z = 50 - zBoost + Math.sin(t * 0.22) * 4.0;
    camera.lookAt(0, 0, 0);

    const vigOpacity = Math.min(1, Math.max(0, speedCurrent - 1.2) * 0.5);
    boostVig.style.opacity = vigOpacity;

    tunnelMat.uniforms.uTime.value  = t;
    tunnelMat.uniforms.uSpeed.value = Math.max(0.1, speedCurrent);
    tunnelMat.uniforms.uWarpX.value = warpX;
    tunnelMat.uniforms.uWarpY.value = warpY;
    tunnelMat.uniforms.uBurst.value = burstVal;

    pMat.uniforms.uTime.value  = t;
    pMat.uniforms.uSpeed.value = Math.max(0.1, speedCurrent);

    const tMesh = scene.children.find(c => c.material === tunnelMat);
    if (tMesh) tMesh.rotation.z = t * 0.04 * speedCurrent;

    allUniforms.forEach((m, i) => {
        m.uniforms.uTime.value = t + i * 0.15;
    });

    if (!isDragging) dragVelZ *= 0.92;
    manualRotZ += dragVelZ;

    const spinMult = 0.8 + speedCurrent * 0.5;
    energyGroup.rotation.z = manualRotZ + t * 0.08 * spinMult;
    energyGroup.rotation.x = Math.sin(t * 0.14) * (0.14 + Math.abs(warpY) * 0.5);
    energyGroup.rotation.y = Math.cos(t * 0.10) * (0.14 + Math.abs(warpX) * 0.5);

    knotMesh.rotation.z   =  t * 0.28 * spinMult;
    outerKnot.rotation.z  = -t * 0.18 * spinMult;
    outerKnot.rotation.x  =  t * 0.10;

    icoMesh.rotation.x  =  t * 0.50 * spinMult;
    icoMesh.rotation.y  =  t * 0.35;
    octaMesh.rotation.x = -t * 0.42 * spinMult;
    octaMesh.rotation.z =  t * 0.28;

    rings[0].rotation.z =  t * 0.20 * spinMult;
    rings[1].rotation.z = -t * 0.17 * spinMult;
    rings[2].rotation.z =  t * 0.13;
    rings[3].rotation.z = -t * 0.25 * spinMult;
    rings[4].rotation.z =  t * 0.09;
    rings[5].rotation.z = -t * 0.11 * spinMult;

    renderer.render(scene, camera);
}

animate();

window.addEventListener('resize', () => {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
});
</script>