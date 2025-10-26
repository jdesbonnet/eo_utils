
// ===== Map setup =====
const map = L.map('map', { preferCanvas: true }).setView([53.269914, -9.057045], 20); // Salthouse
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors',
maxNativeZoom:18,
maxZoom:22,
}).addTo(map);

const buildingsLayer = L.geoJSON(null, {
  style: { color: '#1d4ed8', weight: 1, fillOpacity: 0.2 },
  onEachFeature: (f, layer) => {
    const h = getHeightMeters(f);
    layer.bindTooltip(`Height: ${h != null ? h + ' m' : 'n/a'}`);
  }
}).addTo(map);

const shadowsLayer = L.geoJSON(null, { style: { color: '#111827', weight: 0, fillOpacity: 0.35 } }).addTo(map);
const sunLayer = L.layerGroup().addTo(map);

// ===== App state =====
let allFeatures = []; // normalized polygon features with heights
let lastWfsUrl = null;

// ===== Utilities =====
function zeroPad(n){ return (n<10? '0'+n: String(n)); }
function minutesToHHMM(m){ const hh = Math.floor(m/60), mm = m%60; return `${zeroPad(hh)}:${zeroPad(mm)}`; }
function todayLocalISO(){ const d=new Date(); return `${d.getFullYear()}-${zeroPad(d.getMonth()+1)}-${zeroPad(d.getDate())}`; }

function getHeightMeters(feature){
  const p = (feature && feature.properties) || {};
  const keys = ['height','Height','building:height','HGT','hgt'];
  for (const k of keys){ if (p[k] != null){ const v=Number(String(p[k]).replace(/m$/i,'')); if (isFinite(v)) return v; }}
  return null;
}

function featureIntersectsView(f){
  const bounds = map.getBounds();
  const [minx, miny, maxx, maxy] = turf.bbox(f);
  const fbounds = L.latLngBounds(L.latLng(miny, minx), L.latLng(maxy, maxx));
  return bounds.intersects(fbounds);
}

function turfTranslate(geo, meters, bearing){ return turf.transformTranslate(geo, meters, bearing, { units: 'meters' }); }

function computeShadowPolygon(feature, azimuthDegFromNorth, elevationDeg, mode='accurate'){
  const h = getHeightMeters(feature);
  if (!h || elevationDeg <= 0) return null;
  const shadowLen = h / Math.tan(elevationDeg * Math.PI/180);
  if (!isFinite(shadowLen) || shadowLen <= 0) return null;
  const shadowBearing = (azimuthDegFromNorth + 180) % 360; // direction of shadow on ground

  const geom = feature.geometry;
  if (!geom || (geom.type!=='Polygon' && geom.type!=='MultiPolygon')) return null;

  const polygons = (geom.type==='Polygon') ? [geom.coordinates] : geom.coordinates;
  const out = [];

  for (const ringSet of polygons){
    const poly = { type: 'Feature', properties: feature.properties || {}, geometry: { type: 'Polygon', coordinates: ringSet } };
    const translated = turfTranslate(poly, shadowLen, shadowBearing);
    if (mode==='fast'){
      const pts=[]; turf.coordEach(poly, c=>pts.push(turf.point(c))); turf.coordEach(translated, c=>pts.push(turf.point(c)));
      const hull = turf.concave(turf.featureCollection(pts), { maxEdge: Math.max(5, shadowLen*2) }) || turf.convex(turf.featureCollection(pts));
      if (hull) out.push(hull);
      continue;
    }
    // accurate-ish: union of edge quads + translated footprint
    const outer = ringSet[0];
    const quads=[];
    for (let i=0;i<outer.length-1;i++){
      const a = outer[i], b = outer[i+1];
      const aT = turf.getCoords(turfTranslate(turf.point(a), shadowLen, shadowBearing));
      const bT = turf.getCoords(turfTranslate(turf.point(b), shadowLen, shadowBearing));
      quads.push(turf.polygon([[a,b,bT,aT,a]]));
    }
    let acc = translated;
    for (const q of quads){ try { acc = turf.union(acc, q) || acc; } catch(_){} }
    if (acc) out.push(turf.feature(acc.geometry, { source:'shadow' }));
  }
  if (!out.length) return null;
  if (out.length===1) return out[0];
  // merge multiparts
  try { return turf.union(...out); } catch(_) { return turf.featureCollection(out); }
}

function updateUIAzEl(azDeg, elDeg){
  document.getElementById('az').textContent = azDeg.toFixed(1);
  document.getElementById('el').textContent = elDeg.toFixed(1);
}

function drawSunRay(center, azDeg, elDeg, len=200){
  sunLayer.clearLayers();
  if (elDeg <= 0) return;
  const bearing = (azDeg + 180) % 360;
  const end = turf.destination([center.lng, center.lat], len, bearing, { units:'meters' }).geometry.coordinates;
  L.polyline([[center.lat, center.lng],[end[1], end[0]]], { weight:2, dashArray:'4 4' }).addTo(sunLayer);
  L.circleMarker([center.lat, center.lng], { radius:4 }).addTo(sunLayer);
}

// Local (browser) timezone interpretation for date + time
function getSelectedWhen(){
  const dateStr = document.getElementById('date').value;
  const mins = Number(document.getElementById('time').value || 0);
  const [Y,M,D] = dateStr.split('-').map(Number);
  const hh = Math.floor(mins/60), mm = mins%60;
  return new Date(Y, M-1, D, hh, mm, 0); // local time
}

function computeSun(){
  const when = getSelectedWhen();
  const c = map.getCenter();
  const pos = SunCalc.getPosition(when, c.lat, c.lng);
  const az = (pos.azimuth * 180/Math.PI + 180) % 360; // from north clockwise
  const el = pos.altitude * 180/Math.PI;
  return { when, center:c, az, el };
}

function redrawShadows(){
  const { az, el, center } = computeSun();
  updateUIAzEl(az, el);
  const showSun = document.getElementById('showSun').checked;
  if (showSun) drawSunRay(center, az, el); else sunLayer.clearLayers();

  shadowsLayer.clearLayers();
  if (!allFeatures.length || el <= 0) return;

  const clip = document.getElementById('clipToView').checked;
  const mode = document.getElementById('shadowMode').value;
  const feats = clip ? allFeatures.filter(featureIntersectsView) : allFeatures;

  const out=[];
  for (const f of feats){
    const s = computeShadowPolygon(f, az, el, mode);
    if (s) out.push(s);
  }
  if (out.length){ shadowsLayer.addData({ type:'FeatureCollection', features: out.map(g=>({type:'Feature', properties:{}, geometry: g.geometry||g})) }); }
}

function loadGeoJSON(geojson, fit=true){
  buildingsLayer.clearLayers();
  shadowsLayer.clearLayers();
  allFeatures = [];
  if (!geojson) return;
  const fc = geojson.type==='FeatureCollection' ? geojson : { type:'FeatureCollection', features:[geojson] };
  for (const f of fc.features){
    if (!f || !f.geometry) continue;
    const h = getHeightMeters(f);
    if (h==null || !isFinite(h) || h<=0) continue; // keep only features with positive height
    if (['Polygon','MultiPolygon'].includes(f.geometry.type)) allFeatures.push(f);
  }
  buildingsLayer.addData({ type:'FeatureCollection', features: allFeatures });
  if (fit && buildingsLayer.getLayers().length) map.fitBounds(buildingsLayer.getBounds(), { padding:[20,20] });
  redrawShadows();
}

// ===== WFS helpers =====
function buildWfsUrl(baseUrl, useBbox){
  try{
    const u = new URL(baseUrl);
    if (!u.searchParams.has('srsName')) u.searchParams.set('srsName', 'EPSG:4326'); // Return coordinates in lng,lat
    if (!u.searchParams.has('outputFormat')) u.searchParams.set('outputFormat', 'application/json');
    if (useBbox){
      const b = map.getBounds();
      const minx=b.getWest().toFixed(6), miny=b.getSouth().toFixed(6), maxx=b.getEast().toFixed(6), maxy=b.getNorth().toFixed(6);
      u.searchParams.set('bbox', `${minx},${miny},${maxx},${maxy},EPSG:4326`);
    } else {
      u.searchParams.delete('bbox');
    }
    return u.toString();
  }catch{
    return baseUrl;
  }
}

async function fetchWfsAndLoad(){
  const base = document.getElementById('wfsUrl').value.trim();
  const useBbox = document.getElementById('wfsBbox').checked;
  if (!base){ alert('Enter a WFS GetFeature URL'); return; }
  const url = buildWfsUrl(base, useBbox);
  lastWfsUrl = base;
  try{
    const res = await fetch(url);
    const ctype = res.headers.get('content-type')||'';
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (ctype.includes('json')){
      const gj = await res.json();
      loadGeoJSON(gj);
    } else {
      const text = await res.text();
      try { loadGeoJSON(JSON.parse(text)); }
      catch { throw new Error('Server did not return JSON. Ensure outputFormat=application/json and CORS is enabled.'); }
    }
  }catch(err){ alert('WFS load failed: ' + err.message); }
}

// ===== Wire-up UI =====
const dateInput = document.getElementById('date');
const timeInput = document.getElementById('time');
const timeLabel = document.getElementById('timeLabel');

dateInput.value = todayLocalISO();
timeInput.value = (new Date()).getHours()*60 + (new Date()).getMinutes();
function updateTimeLabel(){ timeLabel.textContent = minutesToHHMM(Number(timeInput.value)); }
updateTimeLabel();

['input','change'].forEach(evt => {
  timeInput.addEventListener(evt, () => { updateTimeLabel(); redrawShadows(); });
  dateInput.addEventListener(evt, () => redrawShadows());
  document.getElementById('shadowMode').addEventListener(evt, () => redrawShadows());
  document.getElementById('clipToView').addEventListener(evt, () => redrawShadows());
  document.getElementById('showSun').addEventListener(evt, () => redrawShadows());
});

// File loader
DocumentFileInput = document.getElementById('file');
DocumentFileInput.addEventListener('change', async (e) => {
  const f = e.target.files[0]; if (!f) return;
  const text = await f.text();
  try{ loadGeoJSON(JSON.parse(text)); } catch(err){ alert('Invalid GeoJSON: '+err.message); }
});

// Demo button
DocumentDemoBtn = document.getElementById('demoBtn');
DocumentDemoBtn.addEventListener('click', () => {
  const demo = {
    type:'FeatureCollection',
    features:[
      //turf.feature(turf.polygon([[[-9.1625,53.2497],[-9.1620,53.2497],[-9.1620,53.2499],[-9.1625,53.2499],[-9.2625,53.2497]]]).geometry, { height: 20, name:'Block A' })
      //turf.feature(turf.polygon([[[-6.2615,53.3495],[-6.2609,53.3495],[-6.2609,53.3498],[-6.2615,53.3498],[-6.2615,53.3495]]]).geometry, { height: 35, name:'Block B' }),
      //turf.feature(turf.polygon([[[-6.2605,53.3496],[-6.2599,53.3496],[-6.2599,53.34985],[-6.2605,53.34985],[-6.2605,53.3496]]]).geometry, { height: 12, name:'Block C' })
    ]
  };
  loadGeoJSON(demo);
});

// WFS button
DocumentWfsBtn = document.getElementById('wfsBtn');
DocumentWfsBtn.addEventListener('click', fetchWfsAndLoad);

// Recompute/refresh on map move
let moveTimer=null;
map.on('moveend zoomend', () => {
  clearTimeout(moveTimer);
  moveTimer = setTimeout(() => {
    redrawShadows();
    if (document.getElementById('wfsAuto').checked && lastWfsUrl) fetchWfsAndLoad();
  }, 120);
});

// Initial demo load
DocumentDemoBtn.click();


