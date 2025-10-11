
(function(){
  // Map init
  const map = L.map('map').setView([53.3498,-6.2603], 6);

  // Base layers
  const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    crossOrigin: true,
    attribution: '&copy; OpenStreetMap'
  }).addTo(map);

  const esri = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19,
    crossOrigin: true,
    attribution: 'Tiles &copy; Esri'
  });

  const baseLayers = { 'OSM': osm, 'ESRI World Imagery': esri };
  const overlays = {};
  L.control.layers(baseLayers, overlays, { collapsed: true }).addTo(map);

  // Screenshoter
  const screenshoter = L.simpleMapScreenshoter({ hidden: false, preventDownload:false, position:'topleft' });
  screenshoter.addTo(map);

  // Geoman controls
  map.pm.addControls({
    position: 'topleft',
    drawCircle: false,
    drawCircleMarker: false
  });

  // A group to hold user features
  const drawn = L.featureGroup().addTo(map);

  // Selected layer
  let selected = null;
  const selectLayer = (layer)=>{
    selected = layer;
    // sync UI from selected, where possible
    try{
      if(layer instanceof L.Marker){
        // nop
      } else if (layer instanceof L.Polyline){
        const oc = layer.options.color || '#ff4757';
        const fc = layer.options.fillColor || '#2ed573';
        document.getElementById('strokeColor').value = tinycolor(oc).toHexString();
        document.getElementById('fillColor').value = tinycolor(fc).toHexString();
        document.getElementById('opacity').value = layer.options.opacity ?? 0.7;
        const da = layer.options.dashArray;
        document.getElementById('lineType').value = da ? (da === '1, 6' ? 'dot' : 'dash') : 'solid';
      }
      const tt = layer?.getTooltip?.();
      document.getElementById('labelText').value = tt ? tt.getContent() : '';
      const pp = layer?.getPopup?.();
      document.getElementById('popupText').value = pp ? pp.getContent() : '';
    }catch(e){}
  };

  // Utility: tinycolor fallback (very small util)
  function tinycolor(c){
    const ctx = document.createElement('canvas').getContext('2d');
    ctx.fillStyle = c; // lets the browser parse
    const computed = ctx.fillStyle; // normalized like rgb(r,g,b)
    // convert to hex
    const m = computed.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    if(!m) return { toHexString:()=> '#000000' };
    const [r,g,b] = [parseInt(m[1]),parseInt(m[2]),parseInt(m[3])];
    const hex = '#' + [r,g,b].map(v=> v.toString(16).padStart(2,'0')).join('');
    return { toHexString:()=>hex };
  }

  // Click to select logic for all created layers
  function attachCommon(layer){
    layer.addTo(drawn);
    layer.on('click', ()=> selectLayer(layer));
  }

  // Geoman create hooks to style & attach
  map.on('pm:create', e => {
    const layer = e.layer;
    attachCommon(layer);
    ensureLayerId(layer);

    if(layer instanceof L.Marker){
      // default awesome marker
      setMarkerIcon(layer, document.getElementById('markerIcon').value);
    } else if (layer instanceof L.Polyline){
      applyStyle(layer);
    }
    // default label/popup from inputs
    applyText(layer);
    selectLayer(layer);
  });

  // Style application helpers
  function applyStyle(layer){
    const stroke = document.getElementById('strokeColor').value;
    const fill = document.getElementById('fillColor').value;
    const op = parseFloat(document.getElementById('opacity').value);
    const lt = document.getElementById('lineType').value;
    const dash = lt==='dash' ? '6, 8' : (lt==='dot' ? '1, 6' : null);

    if(layer instanceof L.Polyline){
      const opts = { color: stroke, opacity: op, weight: 3, dashArray: dash };
      if(layer instanceof L.Polygon){
        opts.fillColor = fill; opts.fillOpacity = op; opts.fill = true;
      }
      layer.setStyle(opts);
    }
  }

  // Marker icons via AwesomeMarkers
  function setMarkerIcon(marker, value){
    const [iconName, color] = value.split(',');
    const icon = L.AwesomeMarkers.icon({ icon: iconName.replace('fa-',''), prefix:'fa', markerColor: getColorName(color), iconColor: 'white' });
    marker.setIcon(icon);
    marker.options._am = { iconName, color };// store for export
  }
  // Map a hex to closest awesome marker color name (simple)
  function getColorName(hex){
    const palette = {
      '#d33':'red', '#f1c40f':'orange', '#3498db':'blue', '#2ecc71':'green', '#9b59b6':'purple'
    };
    return palette[hex?.toLowerCase()] || 'cadetblue';
  }

  // Text bindings
  function applyText(layer){
    const label = document.getElementById('labelText').value.trim();
    const popup = document.getElementById('popupText').value.trim();

    if(label){
      const tooltipOpts = { permanent: true, direction:'center', className:'feature-label' };
      layer.bindTooltip(label, tooltipOpts).openTooltip();
    } else if(layer.getTooltip()){
      layer.unbindTooltip();
    }

    if(popup){
      layer.bindPopup(popup);
    } else if(layer.getPopup()){
      layer.unbindPopup();
    }
  }

  document.getElementById('applyText').addEventListener('click', ()=>{
    if(!selected) return alert('Select a feature first.');
    if(selected instanceof L.Polyline) applyStyle(selected);
    if(selected instanceof L.Marker) setMarkerIcon(selected, document.getElementById('markerIcon').value);
    applyText(selected);
  });

  // Update style live when UI changes if a layer is selected
  ['strokeColor','fillColor','opacity','lineType','markerIcon'].forEach(id=>{
    document.getElementById(id).addEventListener('input', ()=>{
      if(!selected) return;
      if(selected instanceof L.Polyline) applyStyle(selected);
      if(selected instanceof L.Marker && id==='markerIcon') setMarkerIcon(selected, document.getElementById('markerIcon').value);
    })
  });


  //
  // Stylus related functions
  //


  // Freehand (stylus-friendly) polyline drawing
  let fhEnabled = false;
  let fhDrawing = false;
  let fhPointerId = null;
  let fhPts = [];
  let fhTemp = null;

  function setFreehandEnabled(on){
    fhEnabled = !!on;  // cast truthy/falsy to hard boolean value
    const btn = document.getElementById('fhEnableBtn');
    if(btn){ 
	btn.textContent = fhEnabled ? 'Freehand Enabled' : 'Enable Freehand'; 
    }
    // TODO why !on and not !fhEnabled?
    if(!on){
      if(fhDrawing){ 
	endFreehand(true); 
      }
    }
  }

  function startFreehand(e){
    if(!fhEnabled) return;
    const penOnly = document.getElementById('fhPenOnly').value === 'yes';
    if(penOnly && e.pointerType && e.pointerType !== 'pen') return;

    fhDrawing = true;
    fhPointerId = e.pointerId;
    fhPts = [];

    if(map.dragging && map.dragging.disable) map.dragging.disable();

    const ll = map.mouseEventToLatLng(e);
    fhPts.push(ll);
    fhTemp = L.polyline(fhPts, { color: document.getElementById('strokeColor').value, opacity: parseFloat(document.getElementById('opacity').value) || 0.7, weight: 3 });
    fhTemp.addTo(map);
  }

  function moveFreehand(e){
    if(!fhDrawing || e.pointerId !== fhPointerId) return;
    const minDist = Math.max(0, parseFloat(document.getElementById('fhMinDist').value) || 0);
    const ll = map.mouseEventToLatLng(e);
    const last = fhPts[fhPts.length - 1];
    if(!last || map.distance(last, ll) >= minDist){
      fhPts.push(ll);
      if(fhTemp) fhTemp.setLatLngs(fhPts);
    }
  }

  function endFreehand(cancel){
    if(!fhDrawing) return;
    fhDrawing = false;

    if(map.dragging && map.dragging.enable) map.dragging.enable();

    if(fhTemp){ fhTemp.remove(); fhTemp = null; }

    if(!cancel && fhPts.length > 1){
      const line = L.polyline(fhPts);
      attachCommon(line);
      applyStyle(line);
      applyText(line);
      selectLayer(line);
      if (typeof snapshot === 'function') snapshot();
    }
    fhPts = [];
    fhPointerId = null;
  }

  const container = map.getContainer();
  container.addEventListener('pointerdown', startFreehand);
  container.addEventListener('pointermove', moveFreehand);
  container.addEventListener('pointerup', function(e){ if(e.pointerId===fhPointerId) endFreehand(false); });
  container.addEventListener('pointercancel', function(e){ if(e.pointerId===fhPointerId) endFreehand(true); });

  document.getElementById('fhEnableBtn').onclick = function(){ setFreehandEnabled(true); };
  document.getElementById('fhDisableBtn').onclick = function(){ setFreehandEnabled(false); };

  // Undo/Redo History
  let undoStack = [];
  let redoStack = [];
  let isRestoring = false;
  const HISTORY_LIMIT = 100;

  function snapshot(){
    if(isRestoring) return;
    try{
      const fc = collectGeoJSON();
      const state = JSON.stringify(fc);
      undoStack.push(state);
      if(undoStack.length > HISTORY_LIMIT) undoStack.shift();
      redoStack.length = 0;
      updateUndoRedoUI();
    }catch(e){}
  }
  function loadState(geojson){
    isRestoring = true;
    try{
      drawn.clearLayers();
      map.eachLayer(l=>{ if(l instanceof L.GeoJSON) map.removeLayer(l); });
      restoreFromGeoJSON(geojson);
    } finally {
      isRestoring = false;
      updateUndoRedoUI();
    }
  }
  function canUndo(){ return undoStack.length > 1; }
  function canRedo(){ return redoStack.length > 0; }
  function undo(){ if(!canUndo()) return; const curr = undoStack.pop(); redoStack.push(curr); const prev = JSON.parse(undoStack[undoStack.length-1]); loadState(prev); }
  function redo(){ if(!canRedo()) return; const state = redoStack.pop(); undoStack.push(state); loadState(JSON.parse(state)); }
  function updateUndoRedoUI(){
    const u = document.getElementById('undoBtn');
    const r = document.getElementById('redoBtn');
    if(u){ u.disabled = !canUndo(); u.classList.toggle('disabled', u.disabled); }
    if(r){ r.disabled = !canRedo(); r.classList.toggle('disabled', r.disabled); }
  }
  function initHistory(){
    map.on('pm:create', ()=> snapshot());
    map.on('pm:remove', ()=> snapshot());
    map.on('pm:edit', ()=> snapshot());
    map.on('pm:dragend', ()=> snapshot());
    const importEl = document.getElementById('importFile');
    if(importEl){ importEl.addEventListener('change', ()=> setTimeout(()=> snapshot(), 50)); }
    // Also snapshot after adding pin by lat/lon
    const addLL = document.getElementById('addLatLonBtn');
    if(addLL){ addLL.addEventListener('click', ()=> setTimeout(()=> snapshot(), 0)); }
    snapshot(); // initial
  }
  document.getElementById('undoBtn').onclick = undo;
  document.getElementById('redoBtn').onclick = redo;
  document.addEventListener('keydown', (e)=>{
    const z = e.key==='z' || e.key==='Z';
    const y = e.key==='y' || e.key==='Y';
    if((e.ctrlKey||e.metaKey) && z && !e.shiftKey){ e.preventDefault(); undo(); }
    else if((e.ctrlKey||e.metaKey) && (y || (z && e.shiftKey))){ e.preventDefault(); redo(); }
  });
  let snapshotTimer = null; function scheduleSnapshot(){ clearTimeout(snapshotTimer); snapshotTimer = setTimeout(()=> snapshot(), 400); }
  document.getElementById('applyText').addEventListener('click', ()=> snapshot());
  ;['strokeColor','fillColor','opacity','lineType','markerIcon'].forEach(id=>{ const el = document.getElementById(id); if(el) el.addEventListener('change', scheduleSnapshot); });
  setTimeout(initHistory, 0);

  // Collaboration — simple WebSocket transport
  let isRemoteApplying = false;
  function uuidv4(){
    if(window.crypto && crypto.getRandomValues){
      const a = crypto.getRandomValues(new Uint8Array(16));
      a[6] = (a[6] & 0x0f) | 0x40; a[8] = (a[8] & 0x3f) | 0x80;
      const b = [...a].map((x,i)=> (i===4||i===6||i===8||i===10?'-'+('0'+x.toString(16)).slice(-2):('0'+x.toString(16)).slice(-2))).join('');
      return b;
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c=>{
      const r = Math.random()*16|0, v = c==='x'?r:(r&0x3|0x8); return v.toString(16);
    });
  }
  function colorFromName(name){ let h=0; for(let i=0;i<name.length;i++) h=(h*31+name.charCodeAt(i))>>>0; h=h%360; return `hsl(${h} 70% 55%)`; }
  function ensureLayerId(layer){ if(!layer.options._id) layer.options._id='f_'+uuidv4(); }
  function setMetaOnCreate(layer){ ensureLayerId(layer); const now = new Date().toISOString(); layer.options._meta = { createdBy: collab.my.name, createdAt: now, updatedBy: collab.my.name, updatedAt: now }; }
  function updateMetaOnEdit(layer){ const now = new Date().toISOString(); layer.options._meta = Object.assign({}, layer.options._meta||{}, { updatedBy: collab.my.name, updatedAt: now }); }
  function toSingleGeoJSON(layer){ const gj = layer.toGeoJSON(); const props = gj.properties || (gj.properties={}); props._id = layer.options._id || ('f_'+uuidv4()); const m = layer.options._meta||{}; props._createdBy = m.createdBy||collab.my.name; props._createdAt = m.createdAt||new Date().toISOString(); props._updatedBy = m.updatedBy||props._createdBy; props._updatedAt = m.updatedAt||props._createdAt; if(layer instanceof L.Polyline){ props.stroke = layer.options.color || '#ff4757'; props.opacity = layer.options.opacity ?? 0.7; props.dashArray = layer.options.dashArray || null; if(layer instanceof L.Polygon){ props.fill = layer.options.fillColor || '#2ed573'; } } const tt = layer.getTooltip && layer.getTooltip(); if(tt) props.label = tt.getContent(); const pp = layer.getPopup && layer.getPopup(); if(pp) props.popup = pp.getContent(); if(layer instanceof L.Marker && layer.options._am){ props._am = layer.options._am; }
      // metadata
      props._id = layer.options._id || ('f_'+uuidv4());
      const mm = layer.options._meta || {};
      if(mm.createdBy) props._createdBy = mm.createdBy;
      if(mm.createdAt) props._createdAt = mm.createdAt;
      if(mm.updatedBy) props._updatedBy = mm.updatedBy;
      if(mm.updatedAt) props._updatedAt = mm.updatedAt; return gj; }

  function createCursorIcon(name, color){ 
	return L.divIcon({ 
		className: '', 
/*		html: `<div class=\"remote-cursor\" style=\"border-color:${'`'}+color+{'`'}\"><div class=\"dot\" style=\"background:${'`'}+color+{'`'}\"></div><span>${'`'}+name+{'`'}</span></div>`, 	iconSize:[10,10], iconAnchor:[0,0] }); } */
		html: `<div class=\"remote-cursor\" style=\"border-color:${color}\"><div class=\"dot\" style=\"background:${color}\"></div><span>${name}</span></div>`,
 		iconSize:[10,10], 
		iconAnchor:[0,0] 
		}); 
  }


  function createCollab(map, drawn){
    const presenceEl = document.getElementById('presence');
    const nameInput = document.getElementById('collabName');
    const roomInput = document.getElementById('collabRoom');
    const serverInput = document.getElementById('collabServer');
    const followSelect = document.getElementById('followUser');
    const broadcastView = document.getElementById('broadcastView');

    const my = { id: uuidv4(), name: localStorage.getItem('qm_name')||'Guest-'+String(Math.random()).slice(2,6), color: '#7cf' };
    my.color = colorFromName(my.name); nameInput.value = my.name;

    const participants = new Map();
    function renderPresence(){ presenceEl.innerHTML=''; participants.set(my.id,{name:my.name,color:my.color,self:true}); const frag=document.createDocumentFragment(); followSelect.innerHTML='<option value="">(none)</option>'; for(const [id,p] of participants){ const d=document.createElement('div'); d.className='avatar'; d.title=p.name; d.style.color='#fff'; d.style.outline=`2px solid ${p.color}`; d.textContent=p.name.slice(0,2).toUpperCase(); frag.appendChild(d); if(id!==my.id){ const o=document.createElement('option'); o.value=id; o.textContent=p.name; followSelect.appendChild(o);} } presenceEl.appendChild(frag); }

    let ws=null, connected=false, room='';
    function connect(){ 
	const url = serverInput.value.trim(); 
	room = roomInput.value.trim()||'default'; 
	my.name = nameInput.value.trim()||my.name; 
	my.color = colorFromName(my.name); 
	localStorage.setItem('qm_name', my.name); 
	try{ if(ws) ws.close(); }catch(_){ } 
	ws = new WebSocket(url); 
	ws.onopen=()=>{ 
		connected=true; 
		send('hello',{}); 
		send('presence',{}); 
		renderPresence(); 
	}; 
	ws.onmessage=evt=>{ 
		let msg; 
		try{ msg=JSON.parse(evt.data);}catch(_){return;} 
		if(msg.room && msg.room!==room) return; 
		if(msg.user && msg.user.id===my.id) return; 
		handle(msg); 
	}; 
	ws.onclose=()=>{ connected=false; for(const [id,p] of [...participants]){ if(!p.self){ if(p.cursor) map.removeLayer(p.cursor); participants.delete(id);} } renderPresence(); };
 	ws.onerror=()=>{}; 
    }



    function disconnect(){ if(ws){ try{ ws.close(); }catch(_){ } ws=null; connected=false; } }
    function isConnected(){ return connected; }

    function send(type,payload){
	console.log("attempting to send message: type=" +type + " payload="+payload);
	if(!connected) return; 
	const msg=Object.assign({type,room,user:{id:my.id,name:my.name,color:my.color}},payload||{}); 
	try{ ws.send(JSON.stringify(msg)); }catch(_){ } 
    }

    // Handle incoming collaboration message
    function handle(msg){ 
        const {type,user}=msg; 
        if(!user||!user.id) return;
        let p = participants.get(user.id)||{name:user.name,color:user.color};
        p.name=user.name;
        p.color=user.color;
        participants.set(user.id,p);
        if(type==='presence'||type==='hello'){
            renderPresence(); 
            return;
        }
        if(type==='cursor'&&msg.latlng){
            if(!p.cursor){
                p.cursor=L.marker(msg.latlng,{zIndexOffset:10000,icon:createCursorIcon(p.name,p.color)}).addTo(map); 
            } else { 
                p.cursor.setLatLng(msg.latlng);
            } return;
        }
        if(type==='view'&&msg.center&&typeof msg.zoom==='number'){
            p.lastView={center:msg.center,zoom:msg.zoom};
            return;
        }
        if(type==='feature:add'&&msg.feature){
            isRemoteApplying=true;
            try{ 
                addFeatureFromRemote(msg.feature);
            } finally {
                isRemoteApplying=false; 
            } 
            return;
        }
        if(type==='feature:edit'&&msg.feature){
            isRemoteApplying=true; 
            try{
                editFeatureFromRemote(msg.feature);
            } finally {
                isRemoteApplying=false; 
            } return; 
        } if(type==='feature:remove'&&msg.id){
            isRemoteApplying=true; 
            try{
                removeFeatureById(msg.id);
            } finally {
                isRemoteApplying=false;
            } 
            return; 
        }
    } // end function handle()

    function findLayerById(id){ let found=null; drawn.eachLayer(l=>{ if(l.options && l.options._id===id) found=l; }); return found; }
    function addFeatureFromRemote(feat){ L.geoJSON(feat,{ pointToLayer:(feature,latlng)=>{ const m=L.marker(latlng); if(feature.properties&&feature.properties._am){ const v=`${feature.properties._am.iconName},${feature.properties._am.color||'#d33'}`; setMarkerIcon(m,v);} return m; }, onEachFeature:(feature,layer)=>{ attachCommon(layer);
    ensureLayerId(layer); ensureLayerId(layer); const p=feature.properties||{}; layer.options._id=p._id||layer.options._id; layer.options._meta={createdBy:p._createdBy,createdAt:p._createdAt,updatedBy:p._updatedBy,updatedAt:p._updatedAt}; if(layer instanceof L.Polyline){ const opts={color:p.stroke||'#ff4757',opacity:p.opacity ?? 0.7,weight:3,dashArray:p.dashArray||null}; if(layer instanceof L.Polygon){ opts.fillColor=p.fill||'#2ed573'; opts.fillOpacity=p.opacity ?? 0.7; opts.fill=true;} layer.setStyle(opts);} if(p.label){ layer.bindTooltip(p.label,{permanent:true,direction:'center',className:'feature-label'}).openTooltip(); } if(p.popup){ layer.bindPopup(p.popup);} } }).addTo(map); }


    function editFeatureFromRemote(feat) {
        const id=feat.properties&&feat.properties._id; 
        if(!id) return addFeatureFromRemote(feat); 
        const layer=findLayerById(id); 
        if(!layer){ addFeatureFromRemote(feat); return;} 
        const g=feat.geometry; 
        if(layer.setLatLngs && g){ 
            if(g.type==='LineString'){ 
                layer.setLatLngs(L.GeoJSON.coordsToLatLngs(g.coordinates,0)); 
            } else if(g.type==='Polygon'){ 
                layer.setLatLngs(L.GeoJSON.coordsToLatLngs(g.coordinates,1)); 
            } 
        } 
        const p=feat.properties||{}; 
        if(layer instanceof L.Polyline){ 
            const opts={color:p.stroke||'#ff4757',opacity:p.opacity ?? 0.7,weight:3,dashArray:p.dashArray||null}; 
            if(layer instanceof L.Polygon){ 
                opts.fillColor=p.fill||'#2ed573'; 
                opts.fillOpacity=p.opacity ?? 0.7; 
                opts.fill=true;
            } 
            layer.setStyle(opts);
        } 
        if(p.label){ 
            layer.bindTooltip(p.label,{permanent:true,direction:'center',className:'feature-label'}).openTooltip(); } 
        else if(layer.getTooltip()) layer.unbindTooltip(); if(p.popup){ layer.bindPopup(p.popup);} 
        else if(layer.getPopup()) layer.unbindPopup(); 
        layer.options._meta={createdBy:p._createdBy,createdAt:p._createdAt,updatedBy:p._updatedBy,updatedAt:p._updatedAt}; 
    }
    function removeFeatureById(id){ const l=findLayerById(id); if(l) drawn.removeLayer(l); }

    function sendCursor(latlng){ send('cursor',{latlng}); }
    function sendView(){ const c=map.getCenter(); send('view',{center:[c.lat,c.lng],zoom:map.getZoom()}); }
    function sendAdd(layer){ if(isRemoteApplying) return; ensureLayerId(layer); setMetaOnCreate(layer); send('feature:add',{feature:toSingleGeoJSON(layer)}); }
    function sendEdit(layer){ if(isRemoteApplying) return; if(!layer) return; updateMetaOnEdit(layer); send('feature:edit',{feature:toSingleGeoJSON(layer)}); }
    function sendRemove(layer){ if(isRemoteApplying) return; if(!layer) return; const id=layer.options&&layer.options._id; if(id) send('feature:remove',{id}); }

    document.getElementById('collabConnect').onclick=connect;
    document.getElementById('collabDisconnect').onclick=disconnect;
    document.getElementById('jumpToUser').onclick=()=>{ const id=followSelect.value; if(!id) return; const p=participants.get(id); if(p&&p.lastView){ map.setView(p.lastView.center,p.lastView.zoom);} };

    let lastCursorSent=0; map.getContainer().addEventListener('pointermove',(e)=>{ if(!connected) return; const now=performance.now(); if(now-lastCursorSent<50) return; lastCursorSent=now; const ll=map.mouseEventToLatLng(e); sendCursor([ll.lat,ll.lng]); });
    map.on('moveend',()=>{ if(connected && broadcastView.value==='yes') sendView(); });

    map.on('pm:create',e=>{ if(connected) sendAdd(e.layer); });
    map.on('pm:edit',e=>{ if(connected) sendEdit(e.layer); });
    map.on('pm:dragend',e=>{ if(connected) sendEdit(e.layer); });
    map.on('pm:remove',e=>{ if(connected) sendRemove(e.layer); });

    return { connect, disconnect, isConnected, sendAdd, sendEdit, sendRemove, my, participants };
  }

  const collab = createCollab(map, drawn);

  // Basemap switching buttons
  document.getElementById('osmBtn').onclick = ()=>{ if(!map.hasLayer(osm)) { esri.remove(); osm.addTo(map);} };
  document.getElementById('esriBtn').onclick = ()=>{ if(!map.hasLayer(esri)) { osm.remove(); esri.addTo(map);} };

  // Custom tile layer
  document.getElementById('addTileBtn').onclick = ()=>{
    const url = document.getElementById('customTileUrl').value.trim();
    if(!url) return;
    const custom = L.tileLayer(url, { maxZoom: 22, crossOrigin: true, attribution: 'Custom' }).addTo(map);
    overlays[`Custom ${Object.keys(overlays).length+1}`] = custom;
  };

  // GeoTIFF from URL
  document.getElementById('addTiffUrl').onclick = async ()=>{
    const url = document.getElementById('tiffUrl').value.trim();
    if(!url) return;
    await addGeoTiff(url);
  };

  // GeoTIFF from file
  document.getElementById('tiffFile').addEventListener('change', async (e)=>{
    const file = e.target.files[0];
    if(!file) return;
    const arrayBuffer = await file.arrayBuffer();
    const georaster = await parseGeoraster(arrayBuffer);
    const layer = new GeoRasterLayer({ georaster, opacity:0.7, resolution: 256 });
    layer.addTo(map);
    try { map.fitBounds(layer.getBounds()); } catch(_){}
  });

  async function addGeoTiff(url){
    try{
      const response = await fetch(url);
      const arrayBuffer = await response.arrayBuffer();
      const georaster = await parseGeoraster(arrayBuffer);
      const layer = new GeoRasterLayer({ georaster, opacity:0.7, resolution: 256 });
      layer.addTo(map);
      try { map.fitBounds(layer.getBounds()); } catch(_){}
    }catch(err){
      alert('Failed to load GeoTIFF: '+err);
    }
  }

  // Import (GeoJSON or KML)
  document.getElementById('importFile').addEventListener('change', async (e)=>{
    const file = e.target.files[0];
    if(!file) return;
    const text = await file.text();
    let geojson;
    if(file.name.toLowerCase().endsWith('.kml')){
      const dom = new DOMParser().parseFromString(text, 'text/xml');
      geojson = toGeoJSON.kml(dom);
    } else {
      geojson = JSON.parse(text);
    }
    restoreFromGeoJSON(geojson);
  });

  function restoreFromGeoJSON(geojson){
    L.geoJSON(geojson, {
      pointToLayer: (feature, latlng)=>{
        const m = L.marker(latlng);
        if(feature.properties && feature.properties._am){
          const v = `${feature.properties._am.iconName},${feature.properties._am.color||'#d33'}`;
          setMarkerIcon(m, v);
        }
        return m;
      },
      onEachFeature: (feature, layer)=>{
        attachCommon(layer);
    ensureLayerId(layer);
        const p = feature.properties || {};
        // IDs & metadata
        ensureLayerId(layer);
        layer.options._id = p._id || layer.options._id;
        layer.options._meta = { createdBy:p._createdBy, createdAt:p._createdAt, updatedBy:p._updatedBy, updatedAt:p._updatedAt };
        // Style
        if(layer instanceof L.Polyline){
          const opts = { color: p.stroke||'#ff4757', opacity: p.opacity ?? 0.7, weight: 3, dashArray: p.dashArray||null };
          if(layer instanceof L.Polygon){
            opts.fillColor = p.fill||'#2ed573'; opts.fillOpacity = p.opacity ?? 0.7; opts.fill = true;
          }
          layer.setStyle(opts);
        }
        // Text
        if(p.label){ layer.bindTooltip(p.label, { permanent:true, direction:'center', className:'feature-label' }).openTooltip(); }
        if(p.popup){ layer.bindPopup(p.popup); }
      }
    }).addTo(map);
  }

  // Export GeoJSON
  document.getElementById('exportGeoJSON').onclick = ()=>{
    const fc = collectGeoJSON();
    downloadJSON(fc, 'quickmap.geojson');
  };

  // Export KML
  document.getElementById('exportKML').onclick = ()=>{
    const fc = collectGeoJSON();
    const kml = tokml(fc, { documentName: 'QuickMap Export', name: 'name' });
    downloadText(kml, 'quickmap.kml', 'application/vnd.google-earth.kml+xml');
  };

  // Export PNG (via screenshoter)
  document.getElementById('exportPNG').onclick = async ()=>{
    try{
      const blob = await screenshoter.takeScreen('blob');
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'quickmap.png';
      a.click();
    }catch(err){
      alert('PNG export failed (likely CORS on tiles/rasters). Try switching basemap or use your own CORS‑enabled tiles.\n'+err);
    }
  };

  function collectGeoJSON(){
    const features = [];
    drawn.eachLayer(layer=>{
      const gj = layer.toGeoJSON();
      const props = gj.properties || (gj.properties={});
      // Persist styles & texts
      if(layer instanceof L.Polyline){
        props.stroke = layer.options.color || '#ff4757';
        props.opacity = layer.options.opacity ?? 0.7;
        props.dashArray = layer.options.dashArray || null;
        if(layer instanceof L.Polygon){
          props.fill = layer.options.fillColor || '#2ed573';
        }
      }
      const tt = layer.getTooltip && layer.getTooltip();
      if(tt) props.label = tt.getContent();
      const pp = layer.getPopup && layer.getPopup();
      if(pp) props.popup = pp.getContent();
      if(layer instanceof L.Marker && layer.options._am){ props._am = layer.options._am; }
      features.push(gj);
    });
    return { type:'FeatureCollection', features };
  }

  // Download helpers
  function downloadJSON(obj, name){ downloadText(JSON.stringify(obj,null,2), name, 'application/geo+json'); }
  function downloadText(text, name, type){
    const blob = new Blob([text], { type });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
  }

  // Improve labels look
  const css = document.createElement('style');
  css.textContent = `.feature-label{background:rgba(13,19,58,.65);color:#fff;border:1px solid #2f3ea5;border-radius:10px;padding:2px 6px;box-shadow:0 2px 10px rgba(0,0,0,.3);font-weight:600}`;
  document.head.appendChild(css);

})();

