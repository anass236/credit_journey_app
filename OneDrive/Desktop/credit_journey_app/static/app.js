/* CreditFlow: permissions are enforced by the API as well as the interface. */
const $ = (id) => document.getElementById(id);
const isAdmin = document.body.dataset.role === 'admin';
const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
const PHASES = {Discovery:'#22b5be',Application:'#a78bfa',Assessment:'#f59e0b',Contracting:'#3b82f6',Fulfillment:'#34d399',Lifecycle:'#fb7185',Other:'#94a3b8'};
let data = {stages:[], teams:[], edges:[]};
let currentStage = null;
let currentEdge = null;
let connectionDrag = null;
let connectionSaving = false;
let connectionStyleSaving = false;
let toastTimer;
const displayName = item => item.display_name ?? item.name;
const roleLabel = role => ({admin:'Administrateur', viewer:'Lecteur'}[role] || 'Rôle inconnu');
function localizeFormValidation() {
  document.addEventListener('input', event => {event.target.setCustomValidity?.('');}, true);
  document.addEventListener('reset', event => {
    event.target.querySelectorAll('input, select, textarea').forEach(field => field.setCustomValidity?.(''));
  }, true);
  document.addEventListener('invalid', event => {
    const field = event.target;
    if (typeof field.setCustomValidity !== 'function') return;
    field.setCustomValidity('');
    const state = field.validity;
    let message = 'Veuillez saisir une valeur valide.';
    if (state.valueMissing) message = 'Veuillez renseigner ce champ.';
    else if (state.tooShort) message = `Veuillez saisir au moins ${field.minLength} caractères.`;
    else if (state.tooLong) message = `Veuillez saisir au maximum ${field.maxLength} caractères.`;
    else if (state.patternMismatch) message = 'Utilisez de 3 à 50 lettres non accentuées, chiffres, points, tirets ou traits de soulignement.';
    else if (state.rangeUnderflow) message = `La valeur minimale est ${field.min}.`;
    else if (state.rangeOverflow) message = `La valeur maximale est ${field.max}.`;
    field.setCustomValidity(message);
  }, true);
}
localizeFormValidation();
function toast(message) {
  $('toast').textContent = message;
  $('toast').classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('toast').classList.remove('show'), 3500);
}
async function api(url, method = 'GET', body) {
  const opts = {method, headers: {}};
  if (method !== 'GET') opts.headers['X-CSRF-Token'] = csrfToken;
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  let response;
  try {response = await fetch(url, opts);} catch {throw new Error('Connexion au serveur impossible. Vérifiez votre connexion, puis réessayez.');}
  const value = await response.json().catch(() => ({}));
  if (response.status === 401) window.location.assign('/login');
  if (!response.ok) throw new Error(value.error || `La requête a échoué (code ${response.status}).`);
  return value;
}
async function refresh(keepView = true) {
  const previousMacroCount = (data.macros || []).length;
  data = await api('/api/journey');
  $('stageCount').textContent = data.stages.length;
  $('teamCount').textContent = data.teams.length;
  $('edgeCount').textContent = data.edges.length;
  if (currentMacroId !== null && currentMacroId !== 'all' && currentMacroId !== 'unclassified' && !(data.macros || []).some(macro => macro.id === currentMacroId)) {currentMacroId = null;keepView = false;}
  if (isMacroOverview() && previousMacroCount !== data.macros.length) keepView = false;
  $('macroCount').textContent = (data.macros || []).length;
  $('subteamCount').textContent = plural((data.subteams || []).length, 'sous-équipe');
  renderGraph(keepView);
  renderTeamDirectory();
  renderConnectionHandles();
  if (currentEdge !== null) selectConnection(currentEdge);
  updateHierarchyNavigation();
  renderMacroDirectory();
}
function teamList(stage) {
  return stage.team_ids.map(id => data.teams.find(t => t.id === id)).filter(Boolean);
}
function openDrawer(id) {
  closeDrawers();
  $('overlay').hidden = false;
  $(id).classList.add('open');
  $(id).setAttribute('aria-hidden', 'false');
}
function closeDrawers() {
  $('overlay').hidden = true;
  for (const id of ['stageDrawer', 'teamDrawer', 'accountDrawer', 'passwordDrawer', 'macroDrawer']) {
    $(id).classList.remove('open');
    $(id).setAttribute('aria-hidden', 'true');
  }
}
function openStage(id = null) {
  if (!isAdmin && id === null) return;
  cancelConnectionDrag();
  currentStage = id;
  const stage = data.stages.find(s => s.id === id);
  $('drawerTitle').textContent = !isAdmin ? 'Détails de l’étape' : stage ? 'Modifier l’étape' : 'Ajouter une étape';
  $('stageName').value = stage ? displayName(stage) : '';
  $('stageDesc').value = stage?.display_description ?? stage?.description ?? '';
  $('stagePhase').value = stage?.phase || 'Discovery';
  renderMacroOptions(stage?.macro_id ?? (Number.isInteger(currentMacroId) ? currentMacroId : null));
  $('deleteStage').hidden = !stage || !isAdmin;
  $('teamChecks').replaceChildren();
  for (const team of data.teams) {
    const label = document.createElement('label'); label.className = 'team-chip';
    const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.value = team.id;
    checkbox.checked = !!stage?.team_ids.includes(team.id); checkbox.disabled = !isAdmin;
    const name = document.createElement('span'); name.textContent = displayName(team);
    const count = document.createElement('small'); count.textContent = teamStaffLabel(team);
    label.append(checkbox, teamColorDot(team.color), name, count); $('teamChecks').append(label);
    checkbox.addEventListener('change', renderStageTeamDetails);
  }
  for (const field of ['stageName','stageDesc','stagePhase','stageMacro']) {
    $(field).disabled = !isAdmin;
    $(field).setCustomValidity?.('');
  }
  renderStageTeamDetails();
  openDrawer('stageDrawer');
  if (isAdmin) $('stageName').focus();
}
async function saveStage(event) {
  event.preventDefault();
  if (!isAdmin) return;
  const existing = data.stages.find(s => s.id === currentStage);
  const payload = {name:$('stageName').value, description:$('stageDesc').value, phase:$('stagePhase').value,
    macro_id:$('stageMacro').value ? Number($('stageMacro').value) : null,
    team_ids:[...$('teamChecks').querySelectorAll('input:checked')].map(i => Number(i.value)),
    x:existing?.x ?? (200+Math.random()*240), y:existing?.y ?? (200+Math.random()*100)};
  try {
    await api(currentStage ? `/api/stages/${currentStage}` : '/api/stages', currentStage ? 'PUT' : 'POST', payload);
    closeDrawers();
    await refresh();
    toast(currentStage ? 'Étape mise à jour' : 'Étape créée');
  } catch (err) {toast(err.message);}
}
function teamColorDot(color) {
  const dot = document.createElement('i'); dot.className = 'team-color';
  dot.style.backgroundColor = /^#[0-9a-fA-F]{6}$/.test(color) ? color : '#94a3b8';
  return dot;
}
function renderTeamDirectory() {renderTeamHierarchy();}
async function renderAccounts() {
  const result = await api('/api/users');
  $('accountDirectory').replaceChildren();
  for (const user of result.users) {
    const row = document.createElement('div'); row.className = 'team-directory-row account-directory-row';
    const name = document.createElement('span'); name.textContent = user.username;
    const role = document.createElement('span'); role.className = 'role-pill'; role.textContent = user.disabled ? 'Désactivé' : roleLabel(user.role);
    row.append(name, role);
    for (const action of ['access', 'sessions']) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'account-action';
      button.textContent = action === 'access' ? (user.disabled ? 'Activer' : 'Désactiver') : 'Déconnecter';
      button.onclick = async () => {
        if (!confirm(`${button.textContent} le compte « ${user.username} »${action === 'sessions' ? ' sur tous les appareils' : ''} ?`)) return;
        button.disabled = true;
        try {
          if (action === 'access') await api(`/api/users/${user.id}`, 'PATCH', {disabled:!user.disabled});
          else await api(`/api/users/${user.id}/revoke-sessions`, 'POST', {});
          await renderAccounts(); toast(action === 'access' ? 'Accès au compte mis à jour' : 'Toutes les sessions du compte ont été fermées');
        } catch (err) {toast(err.message);} finally {button.disabled = false;}
      };
      row.append(button);
    }
    $('accountDirectory').append(row);
  }
}
function wire() {
  $('passwordBtn').onclick = () => { $('passwordForm').reset(); openDrawer('passwordDrawer'); };
  $('passwordForm').onsubmit = async event => {
    event.preventDefault();
    if ($('passwordNew').value !== $('passwordConfirm').value) {toast('Les nouveaux mots de passe ne correspondent pas.'); return;}
    const button = $('passwordSubmit'); button.disabled = true;
    try {
      await api('/api/auth/password', 'POST', {current_password:$('passwordCurrent').value, new_password:$('passwordNew').value});
      window.location.assign('/login');
    } catch (err) {toast(err.message);} finally {button.disabled = false;}
  };
  $('addStageBtn').onclick = () => openStage();
  $('newStageSide').onclick = () => openStage();
  $('manageTeams').onclick = () => {renderTeamDirectory(); resetSubteamEditor(); openDrawer('teamDrawer');};
  wireHierarchy();
  $('manageAccounts').onclick = async () => {
    if (!isAdmin) return;
    try {await renderAccounts(); openDrawer('accountDrawer');} catch (err) {toast(err.message);}
  };
  $('manageAccountsMobile').onclick = () => $('manageAccounts').click();
  $('overlay').onclick = closeDrawers;
  document.querySelectorAll('[data-close]').forEach(b => b.onclick = closeDrawers);
  $('stageForm').onsubmit = saveStage;
  $('deleteStage').onclick = async () => {
    if (!isAdmin || !confirm('Supprimer cette étape et toutes ses liaisons ?')) return;
    try {await api(`/api/stages/${currentStage}`, 'DELETE'); closeDrawers(); await refresh(); toast('Étape supprimée');} catch (err) {toast(err.message);}
  };
  $('teamForm').onsubmit = async event => {
    event.preventDefault();
    if (!isAdmin) return;
    try {await api('/api/teams', 'POST', {name:$('newTeamName').value,color:$('newTeamColor').value}); $('newTeamName').value=''; await refresh(); toast('Équipe créée');} catch (err) {toast(err.message);}
  };
  $('teamDirectory').onclick = async event => {
    const button = event.target.closest('[data-delete-team]');
    if (!isAdmin || !button || !confirm('Supprimer cette équipe de l’annuaire et de toutes les étapes ?')) return;
    try {await api(`/api/teams/${button.dataset.deleteTeam}`, 'DELETE'); await refresh(); resetSubteamEditor(); toast('Équipe supprimée');} catch (err) {toast(err.message);}
  };
  wireGraph();
  wireConnections();
  $('accountForm').onsubmit = async event => {
    event.preventDefault();
    if (!isAdmin) return;
    const submit = event.currentTarget.querySelector('button[type="submit"]');
    submit.disabled = true;
    try {
      await api('/api/users', 'POST', {username:$('accountUsername').value, password:$('accountPassword').value, role:$('accountRole').value});
      $('accountForm').reset();
      await renderAccounts();
      toast('Compte créé');
    } catch (err) {toast(err.message);} finally {submit.disabled = false;}
  };
  $('showTeams').onchange = setTeamLabels;
  $('fitBtn').onclick = fitGraph;
  $('zoomIn').onclick = () => zoomGraph(graphZoom * 1.2);
  $('zoomOut').onclick = () => zoomGraph(graphZoom / 1.2);
  $('exportBtn').onclick = async () => {
    try {
      const result = await api('/api/export');
      const url = URL.createObjectURL(new Blob([JSON.stringify(result,null,2)], {type:'application/json'}));
      const link = document.createElement('a'); link.href = url; link.download = 'parcours-credit.json'; link.click(); URL.revokeObjectURL(url);
    } catch (err) {toast(err.message);}
  };
  document.addEventListener('keydown', event => {if (event.key === 'Escape') {closeDrawers(); finishGraphGesture(true); cancelConnectionDrag(); closeConnectionTools();}});
}
function wireSignOut() {
  const button = $('logoutBtn');
  // Current pages use a native POST form. Keep older open tabs able to sign out too.
  if (!button || button.form) return;
  button.onclick = async () => {
    button.disabled = true;
    try {
      const stateResponse = await fetch('/api/auth/session', {cache:'no-store'});
      if (!stateResponse.ok) throw new Error('Impossible de vérifier votre session. Veuillez réessayer.');
      const state = await stateResponse.json();
      const response = await fetch('/api/auth/logout', {method:'POST', headers:{'X-CSRF-Token':state.csrf_token}});
      if (!response.ok && response.status !== 401) throw new Error('Impossible de vous déconnecter. Veuillez réessayer.');
      window.location.assign('/login');
    } catch {toast('Impossible de vous déconnecter. Vérifiez votre connexion, puis réessayez.');} finally {button.disabled = false;}
  };
}
window.addEventListener('DOMContentLoaded', async () => {
  wireSignOut();
  try {
    if (!$('journeyCanvas') || !$('connectionHandles') || !$('connectionTools') || !$('passwordBtn') || !$('passwordForm') || !$('viewToolbar') || !$('subteamForm') || !$('macroForm')) {
      window.location.replace('/?refresh=workspace');
      return;
    }
    wire();
    await refresh(false);
  } catch {toast('Impossible d’afficher le parcours. Actualisez la page ou contactez votre administrateur.');}
});

;
/* Native DOM/SVG journey canvas. All coordinates are stored in diagram space. */
const STAGE_WIDTH = 270;
const STAGE_HEIGHT = 180;
let graphZoom = 1;
let graphPan = {x:0, y:0};
let graphGesture = null;
let graphClickSuppressed = false;
const stageElements = new Map();

function svgElement(name, attributes = {}) {
  const element = document.createElementNS('http://www.w3.org/2000/svg', name);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
  return element;
}

function diagramToScreen(point) {
  return {x:point.x * graphZoom + graphPan.x, y:point.y * graphZoom + graphPan.y};
}

function screenToDiagram(point) {
  return {x:(point.x - graphPan.x) / graphZoom, y:(point.y - graphPan.y) / graphZoom};
}

function stageScreenBox(stage) {
  const center = diagramToScreen(stage);
  return {x1:center.x - STAGE_WIDTH * graphZoom / 2, x2:center.x + STAGE_WIDTH * graphZoom / 2,
    y1:center.y - STAGE_HEIGHT * graphZoom / 2, y2:center.y + STAGE_HEIGHT * graphZoom / 2};
}

function boundaryPoint(stage, toward, width = STAGE_WIDTH, height = STAGE_HEIGHT) {
  const dx = toward.x - stage.x, dy = toward.y - stage.y;
  const scale = 1 / (Math.max(Math.abs(dx) / (width / 2 + 2), Math.abs(dy) / (height / 2 + 2)) || 1);
  return {x:stage.x + dx * scale, y:stage.y + dy * scale};
}

function connectionGeometry(edge, source, target) {
  const dx = target.x - source.x, dy = target.y - source.y;
  const length = Math.hypot(dx, dy) || 1;
  const control = {x:(source.x + target.x) / 2 - dy / length * edge.bend,
    y:(source.y + target.y) / 2 + dx / length * edge.bend};
  const start = boundaryPoint(source, edge.shape === 'curved' ? control : target);
  const end = boundaryPoint(target, edge.shape === 'curved' ? control : source);
  let path, label = {x:(start.x + end.x) / 2, y:(start.y + end.y) / 2};
  if (edge.shape === 'curved') {
    path = `M${start.x} ${start.y} Q${control.x} ${control.y} ${end.x} ${end.y}`;
    label = {x:(start.x + 2 * control.x + end.x) / 4, y:(start.y + 2 * control.y + end.y) / 4};
  } else if (edge.shape === 'elbow') {
    if (Math.abs(dx) >= Math.abs(dy)) {
      const direction = dx >= 0 ? 1 : -1;
      start.x = source.x + direction * (STAGE_WIDTH / 2 + 2); start.y = source.y;
      end.x = target.x - direction * (STAGE_WIDTH / 2 + 2); end.y = target.y;
      const middle = (start.x + end.x) / 2;
      path = `M${start.x} ${start.y} H${middle} V${end.y} H${end.x}`;
    } else {
      const direction = dy >= 0 ? 1 : -1;
      start.x = source.x; start.y = source.y + direction * (STAGE_HEIGHT / 2 + 2);
      end.x = target.x; end.y = target.y - direction * (STAGE_HEIGHT / 2 + 2);
      const middle = (start.y + end.y) / 2;
      path = `M${start.x} ${start.y} V${middle} H${end.x} V${end.y}`;
    }
    label = {x:(start.x + end.x) / 2, y:(start.y + end.y) / 2};
  } else path = `M${start.x} ${start.y} L${end.x} ${end.y}`;
  return {path, label, control};
}

function renderEdges(preview = null) {
  if (isMacroOverview()) return;
  const svg = $('graphEdges');
  if (!svg) return;
  svg.replaceChildren();
  const defs = svgElement('defs');
  svg.append(defs);
  const visibleIds = new Set(visibleStages().map(stage => stage.id));
  for (const saved of data.edges.filter(edge => visibleIds.has(edge.source) && visibleIds.has(edge.target))) {
    const edge = preview?.id === saved.id ? preview : saved;
    const source = data.stages.find(stage => stage.id === edge.source);
    const target = data.stages.find(stage => stage.id === edge.target);
    if (!source || !target) continue;
    const geometry = connectionGeometry(edge, source, target);
    const marker = svgElement('marker', {id:`edgeArrow${edge.id}`, viewBox:'0 0 10 10', refX:9, refY:5, markerWidth:7, markerHeight:7, orient:'auto'});
    marker.append(svgElement('path', {d:'M0 0 L10 5 L0 10 z', fill:edge.color}));
    defs.append(marker);
    const group = svgElement('g', {'data-edge-id':edge.id, class:currentEdge === edge.id ? 'graph-edge selected' : 'graph-edge', tabindex:isAdmin ? 0 : -1, role:'button', 'aria-label':`${displayName(source)} vers ${displayName(target)}${edge.label ? ' : ' + edge.label : ''}`});
    const hit = svgElement('path', {d:geometry.path, class:'edge-hit', fill:'none', stroke:'transparent', 'stroke-width':Math.max(16, edge.width + 8)});
    const line = svgElement('path', {d:geometry.path, class:'edge-line', fill:'none', stroke:edge.color, 'stroke-width':edge.width,
      'stroke-dasharray':edge.line_style === 'dashed' ? '9 6' : edge.line_style === 'dotted' ? '2 5' : 'none', 'marker-end':`url(#edgeArrow${edge.id})`});
    group.append(hit, line);
    if (edge.label) {
      const label = svgElement('text', {x:geometry.label.x, y:geometry.label.y - 8, class:'edge-label', 'text-anchor':'middle'});
      label.textContent = edge.label;
      group.append(label);
    }
    group.addEventListener('click', event => {event.stopPropagation(); if (!graphClickSuppressed) selectConnection(edge.id);});
    group.addEventListener('keydown', event => {if (event.key === 'Enter' || event.key === ' ') {event.preventDefault(); selectConnection(edge.id);}});
    svg.append(group);
  }
}

function renderGraph(keepView = true) {
  if (isMacroOverview()) {renderMacroOverview(keepView); return;}
  const container = $('journeyCanvas');
  container.replaceChildren();
  const viewport = document.createElement('div');
  viewport.id = 'graphViewport'; viewport.className = 'graph-viewport';
  const edges = svgElement('svg', {id:'graphEdges', class:'graph-edges', width:1, height:1, 'aria-label':'Liaisons du parcours'});
  viewport.append(edges);
  stageElements.clear();
  for (const [index, stage] of visibleStages().entries()) {
    const card = document.createElement('button');
    card.type = 'button'; card.className = 'graph-stage'; card.dataset.stageId = stage.id;
    card.style.left = `${stage.x}px`; card.style.top = `${stage.y}px`;
    const heading = uiElement('span','stage-eyebrow');
    const phaseDot = uiElement('i','stage-phase-dot');
    phaseDot.style.backgroundColor = PHASES[stage.phase] || PHASES.Other;
    phaseDot.setAttribute('aria-hidden','true');
    heading.append(uiElement('span','',`SOUS-ÉTAPE ${String(index+1).padStart(2,'0')}`),phaseDot);
    const title = uiElement('strong','stage-title',displayName(stage));
    const description = uiElement('span','stage-description',stage.display_description ?? stage.description ?? '');
    if (!description.textContent.trim()) description.textContent = 'Consultez les informations et les équipes impliquées.';
    const assignedTeams = teamList(stage);
    const teamDetails = assignedTeams.map(team => `${displayName(team)} (${teamStaffLabel(team)})`).join(' · ');
    const footer = uiElement('span','stage-footer');
    const teams = uiElement('span','graph-team-label',plural(assignedTeams.length,'équipe'));
    teams.title = teamDetails || 'Aucune équipe associée';
    card.title = teamDetails;
    teams.hidden = !$('showTeams').checked;
    footer.append(teams,uiElement('span','stage-enter','Détails ↗'));
    card.append(heading,title,description,footer);
    card.addEventListener('click', event => {
      event.stopPropagation();
      if (graphClickSuppressed) return;
      closeConnectionTools(); openStage(stage.id);
    });
    stageElements.set(stage.id, card);
    viewport.append(card);
  }
  container.append(viewport);
  renderEdges();
  if (keepView) updateGraphView(); else fitGraph();
  renderEmptyView();
}

function setTeamLabels() {
  document.querySelectorAll('.graph-team-label').forEach(label => label.hidden = !$('showTeams').checked);
}

function updateGraphView() {
  const viewport = $('graphViewport');
  if (viewport) viewport.style.transform = `translate(${graphPan.x}px, ${graphPan.y}px) scale(${graphZoom})`;
  positionConnectionHandles();
}

function zoomGraph(level, point = null) {
  if (connectionDrag || graphGesture || navigationInProgress) return;
  const rect = $('journeyCanvas').getBoundingClientRect();
  point = point || {x:rect.width / 2, y:rect.height / 2};
  const before = screenToDiagram(point);
  graphZoom = Math.max(.25, Math.min(2.5, level));
  graphPan = {x:point.x - before.x * graphZoom, y:point.y - before.y * graphZoom};
  updateGraphView();
}

function fitGraph() {
  if (isMacroOverview()) {fitMacroOverview(); return;}
  if (connectionDrag || graphGesture) return;
  const rect = $('journeyCanvas').getBoundingClientRect();
  const scopedStages = visibleStages();
  if (!scopedStages.length || !rect.width || !rect.height) {graphZoom = 1; graphPan = {x:0,y:0}; updateGraphView(); return;}
  const xs = scopedStages.flatMap(stage => [stage.x - STAGE_WIDTH/2 - 24, stage.x + STAGE_WIDTH/2 + 24]);
  const ys = scopedStages.flatMap(stage => [stage.y - STAGE_HEIGHT/2 - 24, stage.y + STAGE_HEIGHT/2 + 24]);
  for (const edge of data.edges.filter(edge => edge.shape === 'curved' && scopedStages.some(s => s.id === edge.source) && scopedStages.some(s => s.id === edge.target))) {
    const source = data.stages.find(stage => stage.id === edge.source), target = data.stages.find(stage => stage.id === edge.target);
    if (source && target) {const point = connectionGeometry(edge, source, target).control; xs.push(point.x); ys.push(point.y);}
  }
  const x1 = Math.min(...xs), x2 = Math.max(...xs), y1 = Math.min(...ys), y2 = Math.max(...ys);
  graphZoom = Math.max(.25, Math.min(1.2, (rect.width - 80) / (x2 - x1), (rect.height - 100) / (y2 - y1)));
  graphPan = {x:rect.width / 2 - (x1 + x2) / 2 * graphZoom, y:rect.height / 2 - (y1 + y2) / 2 * graphZoom};
  updateGraphView();
}

function moveStageOnCanvas(stage) {
  const card = stageElements.get(stage.id);
  if (card) {card.style.left = `${stage.x}px`; card.style.top = `${stage.y}px`;}
  renderEdges(); positionConnectionHandles();
}

async function finishGraphGesture(cancelled = false) {
  const gesture = graphGesture;
  if (!gesture) return;
  graphGesture = null;
  if ($('journeyCanvas').hasPointerCapture(gesture.pointerId)) $('journeyCanvas').releasePointerCapture(gesture.pointerId);
  if (gesture.moved) {graphClickSuppressed = true; setTimeout(() => graphClickSuppressed = false, 0);}
  if (!gesture.stage || !gesture.moved) return;
  const stage = gesture.stage;
  if (cancelled) {Object.assign(stage, gesture.original); moveStageOnCanvas(stage); return;}
  try {
    const position = {x:Math.round(stage.x),y:Math.round(stage.y)};
    await api(`/api/stages/${stage.id}/position`, 'PATCH', position);
    Object.assign(stage, position); moveStageOnCanvas(stage); toast('Position de l’étape enregistrée');
  } catch (err) {Object.assign(stage, gesture.original); moveStageOnCanvas(stage); toast(err.message);}
}

function wireGraph() {
  const container = $('journeyCanvas');
  container.addEventListener('pointerdown', event => {
    if (connectionDrag || connectionSaving || graphGesture || navigationInProgress || event.target.closest('.macro-card') || event.button !== 0 || event.target.closest('.graph-edge')) return;
    const card = event.target.closest('.graph-stage');
    if (card && !isAdmin) return;
    const stage = card ? data.stages.find(stage => stage.id === Number(card.dataset.stageId)) : null;
    graphGesture = {pointerId:event.pointerId, x:event.clientX, y:event.clientY, pan:{...graphPan}, stage,
      original:stage ? {x:stage.x,y:stage.y} : null, moved:false};
    // Keep ordinary card clicks targeted at the card; capture only once dragging starts.
    if (!card) container.setPointerCapture(event.pointerId);
  });
  container.addEventListener('pointermove', event => {
    const gesture = graphGesture;
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    const dx = event.clientX - gesture.x, dy = event.clientY - gesture.y;
    if (!gesture.moved && Math.hypot(dx,dy) < 4) return;
    gesture.moved = true; container.setPointerCapture(event.pointerId); event.preventDefault();
    if (gesture.stage) {
      gesture.stage.x = Math.max(-10000,Math.min(10000,gesture.original.x + dx / graphZoom));
      gesture.stage.y = Math.max(-10000,Math.min(10000,gesture.original.y + dy / graphZoom));
      moveStageOnCanvas(gesture.stage);
    } else {graphPan = {x:gesture.pan.x + dx,y:gesture.pan.y + dy}; updateGraphView();}
  });
  container.addEventListener('pointerup', event => {if (graphGesture?.pointerId === event.pointerId) finishGraphGesture();});
  container.addEventListener('pointercancel', () => finishGraphGesture(true));
  container.addEventListener('lostpointercapture', event => {if (graphGesture?.pointerId === event.pointerId) finishGraphGesture(true);});
  container.addEventListener('wheel', event => {
    event.preventDefault();
    const rect = container.getBoundingClientRect();
    zoomGraph(graphZoom * Math.exp(-event.deltaY * .0015), {x:event.clientX - rect.left,y:event.clientY - rect.top});
  }, {passive:false});
  container.addEventListener('click', event => {if (!event.target.closest('.graph-stage, .graph-edge')) closeConnectionTools();});
  window.addEventListener('blur', () => finishGraphGesture(true));
  window.addEventListener('resize', positionConnectionHandles);
}

;
/* Direct manipulation for connections. No creation form or graph extension is needed. */
let keyboardConnectionSource = null;
const connectionHint = 'Glissez le bouton + d’une étape vers une autre pour les relier';

function renderConnectionHandles() {
  const layer = $('connectionHandles');
  layer.replaceChildren();
  if (!isAdmin || isMacroOverview()) return;
  for (const stage of visibleStages()) {
    const handle = document.createElement('button');
    handle.type = 'button';
    handle.className = 'connection-handle';
    handle.dataset.stageId = stage.id;
    handle.textContent = '+';
    handle.title = `Glissez pour créer une liaison depuis « ${displayName(stage)} »`;
    handle.setAttribute('aria-label', `Créer une liaison depuis « ${displayName(stage)} ». Glissez vers une étape, ou appuyez sur Entrée puis activez le bouton + de l’étape d’arrivée.`);
    handle.addEventListener('pointerdown', startConnectionDrag);
    handle.addEventListener('pointermove', moveConnectionDrag);
    handle.addEventListener('pointerup', finishConnectionDrag);
    handle.addEventListener('pointercancel', cancelConnectionDrag);
    handle.addEventListener('lostpointercapture', event => {
      if (connectionDrag?.pointerId === event.pointerId) cancelConnectionDrag();
    });
    handle.addEventListener('click', event => {
      event.stopPropagation();
      // Pointer gestures save on drop. Keyboard activation can choose two handles.
      if (event.detail !== 0 || !isAdmin || connectionSaving) return;
      const source = keyboardConnectionSource;
      cancelConnectionDrag();
      if (source !== null) {createDraggedConnection(source, stage.id); return;}
      keyboardConnectionSource = stage.id;
      stageElements.get(stage.id)?.classList.add('connection-source');
      $('connectionHint').textContent = 'Activez le bouton + de l’étape d’arrivée · Échap pour annuler';
    });
    layer.append(handle);
  }
  positionConnectionHandles();
}

function positionConnectionHandles() {
  if (!isAdmin || isMacroOverview()) return;
  $('connectionHandles').querySelectorAll('.connection-handle').forEach(handle => {
    const stage = data.stages.find(stage => stage.id === Number(handle.dataset.stageId));
    if (!stage) {handle.hidden = true; return;}
    const box = stageScreenBox(stage);
    handle.style.left = `${box.x2}px`;
    handle.style.top = `${(box.y1 + box.y2) / 2}px`;
    handle.disabled = connectionSaving;
  });
}

function startConnectionDrag(event) {
  if (!isAdmin || isMacroOverview() || navigationInProgress || connectionSaving || graphGesture || (event.button !== 0 && event.pointerType !== 'touch')) return;
  event.preventDefault();
  event.stopPropagation();
  closeConnectionTools();
  cancelConnectionDrag();
  const handle = event.currentTarget;
  connectionDrag = {source:Number(handle.dataset.stageId), target:null, handle, pointerId:event.pointerId};
  stageElements.get(connectionDrag.source)?.classList.add('connection-source');
  handle.setPointerCapture(event.pointerId);
  $('connectionPreview').hidden = false;
  $('connectionHint').textContent = 'Relâchez sur une étape pour créer la liaison · Échap pour annuler';
  $('journeyCanvas').parentElement.classList.add('is-connecting');
  moveConnectionDrag(event);
}

function stageAtPointer(event) {
  const rect = $('journeyCanvas').getBoundingClientRect();
  const point = {x:event.clientX - rect.left, y:event.clientY - rect.top};
  // Coordinates are rendered pixels, so hit testing also works after pan or zoom.
  if (point.x < 0 || point.y < 0 || point.x > rect.width || point.y > rect.height) return null;
  const scopedStages = visibleStages();
  for (let i = scopedStages.length - 1; i >= 0; i--) {
    const stage = scopedStages[i];
    const box = stageScreenBox(stage);
    if (point.x >= box.x1 && point.x <= box.x2 && point.y >= box.y1 && point.y <= box.y2) return stage.id;
  }
  return null;
}

function moveConnectionDrag(event) {
  if (!connectionDrag || event.pointerId !== connectionDrag.pointerId) return;
  event.preventDefault();
  event.stopPropagation();
  const drag = connectionDrag;
  drag.target = stageAtPointer(event);
  const valid = drag.target !== null && drag.target !== drag.source && !data.edges.some(e => e.source === drag.source && e.target === drag.target);
  stageElements.forEach(card => card.classList.remove('connection-target'));
  if (valid) stageElements.get(drag.target)?.classList.add('connection-target');
  const source = stageScreenBox(data.stages.find(stage => stage.id === drag.source));
  const rect = $('journeyCanvas').getBoundingClientRect();
  const start = {x:source.x2, y:(source.y1 + source.y2) / 2};
  const end = {x:event.clientX - rect.left, y:event.clientY - rect.top};
  const distance = Math.hypot(end.x - start.x, end.y - start.y) || 1;
  const bend = Math.min(80 * graphZoom, distance / 3);
  const control = {x:(start.x + end.x) / 2 - (end.y - start.y) / distance * bend,
    y:(start.y + end.y) / 2 + (end.x - start.x) / distance * bend};
  $('connectionPreviewPath').setAttribute('d', `M${start.x} ${start.y} Q${control.x} ${control.y} ${end.x} ${end.y}`);
  $('connectionPreviewPath').classList.toggle('valid-target', valid);
}

function finishConnectionDrag(event) {
  if (!connectionDrag || event.pointerId !== connectionDrag.pointerId) return;
  moveConnectionDrag(event);
  const {source, target} = connectionDrag;
  cancelConnectionDrag();
  if (target !== null) createDraggedConnection(source, target);
}

function cancelConnectionDrag() {
  const drag = connectionDrag;
  connectionDrag = null;
  keyboardConnectionSource = null;
  if (drag) {
    if (drag.handle.hasPointerCapture(drag.pointerId)) drag.handle.releasePointerCapture(drag.pointerId);
  }
  stageElements.forEach(card => card.classList.remove('connection-source', 'connection-target'));
  $('connectionPreview').hidden = true;
  $('journeyCanvas').parentElement.classList.remove('is-connecting');
  $('connectionHint').textContent = connectionHint;
}

async function createDraggedConnection(source, target) {
  if (!isAdmin || isMacroOverview() || connectionSaving) return;
  if (source === target) {toast('Choisissez une autre étape à relier.'); return;}
  if (data.edges.some(e => e.source === source && e.target === target)) {toast('Ces étapes sont déjà reliées dans ce sens.'); return;}
  connectionSaving = true;
  positionConnectionHandles();
  $('connectionHint').textContent = 'Enregistrement de la liaison…';
  try {
    await api('/api/edges', 'POST', {source, target});
    await refresh();
    toast('Étapes reliées');
  } catch (err) {toast(err.message);} finally {
    connectionSaving = false;
    positionConnectionHandles();
    $('connectionHint').textContent = connectionHint;
  }
}

function selectConnection(id) {
  if (!isAdmin) return;
  const edge = data.edges.find(e => e.id === id);
  if (!edge) {closeConnectionTools(); return;}
  currentEdge = id;
  const names = Object.fromEntries(data.stages.map(s => [s.id, displayName(s)]));
  $('connectionName').textContent = `${names[edge.source]} → ${names[edge.target]}`;
  for (const [field, key] of [['edgeLabel','label'],['edgeShape','shape'],['edgePattern','line_style'],['edgeColor','color'],['edgeWidth','width'],['edgeBend','bend']]) $(field).value = edge[key];
  $('edgeBendControl').hidden = edge.shape !== 'curved';
  $('connectionTools').hidden = false;
  renderEdges();
  positionConnectionHandles();
}

function closeConnectionTools() {
  currentEdge = null;
  if (!connectionStyleSaving) renderEdges();
  if ($('connectionTools').hidden) return;
  $('connectionTools').hidden = true;
  positionConnectionHandles();
}

function selectedConnectionValues() {
  const edge = data.edges.find(e => e.id === currentEdge);
  if (!edge) return null;
  return {...edge, label:$('edgeLabel').value, shape:$('edgeShape').value, line_style:$('edgePattern').value,
    color:$('edgeColor').value, width:Number($('edgeWidth').value), bend:Number($('edgeBend').value)};
}

function previewConnectionStyle() {
  if (!isAdmin || connectionStyleSaving) return;
  if (!$('edgeWidth').checkValidity()) return;
  const edge = selectedConnectionValues();
  if (!edge) return;
  $('edgeBendControl').hidden = edge.shape !== 'curved';
  renderEdges(edge);
}

async function saveConnectionStyle() {
  if (!isAdmin || connectionStyleSaving) return;
  if (!$('edgeWidth').reportValidity()) return;
  previewConnectionStyle();
  const edge = selectedConnectionValues();
  if (!edge) return;
  const previous = data.edges.find(e => e.id === edge.id);
  connectionStyleSaving = true;
  const controls = $('connectionTools').querySelectorAll('input, select, button');
  controls.forEach(control => control.disabled = true);
  try {
    await api(`/api/edges/${edge.id}`, 'PUT', edge);
    Object.assign(previous, edge);
    renderEdges(edge);
    toast('Style de la liaison enregistré');
  } catch (err) {
    renderEdges();
    if (currentEdge === edge.id) selectConnection(edge.id);
    toast(err.message);
  } finally {connectionStyleSaving = false; controls.forEach(control => control.disabled = false);}
}

function wireConnections() {
  $('connectionTools').addEventListener('input', previewConnectionStyle);
  $('connectionTools').addEventListener('change', saveConnectionStyle);
  $('closeConnectionTools').onclick = closeConnectionTools;
  $('deleteConnection').onclick = async () => {
    if (!isAdmin || currentEdge === null || connectionStyleSaving) return;
    const id = currentEdge;
    $('deleteConnection').disabled = true;
    try {
      await api(`/api/edges/${id}`, 'DELETE');
      closeConnectionTools();
      await refresh();
      toast('Liaison supprimée');
    } catch (err) {toast(err.message);} finally {$('deleteConnection').disabled = false;}
  };
  window.addEventListener('blur', cancelConnectionDrag);
  window.addEventListener('resize', cancelConnectionDrag);
  document.addEventListener('visibilitychange', () => {if (document.hidden) cancelConnectionDrag();});
}

/* Teams and journey hierarchy: native DOM/SVG, no additional runtime scripts. */
let currentMacroId = null;
let currentMacroEditor = null;
let currentSubteamEditor = null;
let navigationInProgress = false;
let overviewView = null;
const expandedTeams = new Set();
let teamTreeInitialized = false;
const MACRO_WIDTH = 280;
const MACRO_HEIGHT = 180;
const plural = (count, word) => `${count} ${word}${count > 1 ? 's' : ''}`;

function uiElement(tag, className = '', text = '') {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  return element;
}
function teamStaffLabel(team) {
  if (!(team.subteams || []).length) return 'effectif à renseigner';
  return `${plural(team.headcount || 0, 'personne')}${team.has_example_headcounts ? ' · exemple' : ''}`;
}
function isMacroOverview() {return Array.isArray(data.macros) && currentMacroId === null;}
function visibleStages() {
  if (!Array.isArray(data.macros) || currentMacroId === null || currentMacroId === 'all') return data.stages;
  return data.stages.filter(stage => currentMacroId === 'unclassified' ? stage.macro_id == null : stage.macro_id === currentMacroId);
}
function macroItems() {
  const items = [...(data.macros || [])];
  if (data.stages.some(stage => stage.macro_id == null)) items.push({id:'unclassified', name:'Étapes à classer', description:'Ces sous-étapes ne sont pas encore associées à une macro-étape.', color:'#94a3b8'});
  const width = $('journeyCanvas').getBoundingClientRect().width;
  const columns = width < 500 ? 1 : width < 760 ? 2 : 3;
  return items.map((macro,index) => {
    const row = Math.floor(index / columns), column = row % 2 ? columns - 1 - index % columns : index % columns;
    return {...macro, number:index+1, x:180+column*355, y:150+row*270};
  });
}
function macroChildren(id) {return data.stages.filter(stage => id === 'unclassified' ? stage.macro_id == null : stage.macro_id === id);}

function renderMacroOverview(keepView) {
  const container = $('journeyCanvas'); container.replaceChildren(); stageElements.clear();
  const viewport = uiElement('div','graph-viewport'); viewport.id = 'graphViewport';
  const svg = svgElement('svg',{id:'graphEdges',class:'graph-edges',width:1,height:1,'aria-label':'Transitions entre les macro-étapes'});
  viewport.append(svg);
  const items = macroItems();
  const connections = new Map();
  for (const edge of data.edges) {
    const source = data.stages.find(stage => stage.id === edge.source), target = data.stages.find(stage => stage.id === edge.target);
    if (!source || !target) continue;
    const from = source.macro_id ?? 'unclassified', to = target.macro_id ?? 'unclassified';
    if (from === to) continue;
    const key = `${from}:${to}`;
    const link = connections.get(key) || {from,to,count:0}; link.count++; connections.set(key,link);
  }
  const defs = svgElement('defs'), marker = svgElement('marker',{id:'macroArrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:7,markerHeight:7,orient:'auto'});
  marker.append(svgElement('path',{d:'M0 0 L10 5 L0 10 z',fill:'#a5c1c8'})); defs.append(marker); svg.append(defs);
  for (const link of connections.values()) {
    const source = items.find(macro => macro.id === link.from), target = items.find(macro => macro.id === link.to);
    if (!source || !target) continue;
    const start = boundaryPoint(source,target,MACRO_WIDTH,MACRO_HEIGHT), end = boundaryPoint(target,source,MACRO_WIDTH,MACRO_HEIGHT);
    const dx = end.x-start.x, dy = end.y-start.y, distance = Math.hypot(dx,dy) || 1;
    const cx = (start.x+end.x)/2-dy/distance*35, cy = (start.y+end.y)/2+dx/distance*35;
    svg.append(svgElement('path',{d:`M${start.x} ${start.y} Q${cx} ${cy} ${end.x} ${end.y}`,fill:'none',stroke:'#a5c1c8','stroke-width':2.5,'marker-end':'url(#macroArrow)'}));
    const label = svgElement('text',{x:(start.x+2*cx+end.x)/4,y:(start.y+2*cy+end.y)/4-9,class:'edge-label','text-anchor':'middle'});
    label.textContent = plural(link.count,'liaison'); svg.append(label);
  }
  for (const macro of items) {
    const children = macroChildren(macro.id), teams = new Set(children.flatMap(stage => stage.team_ids));
    const card = uiElement('button','macro-card'); card.type = 'button'; card.dataset.macroId = macro.id;
    card.style.left = `${macro.x}px`; card.style.top = `${macro.y}px`; card.style.borderTopColor = macro.color;
    card.setAttribute('aria-label',`${macro.name} : afficher ${plural(children.length,'sous-étape')}`);
    card.append(uiElement('span','macro-eyebrow',macro.id === 'unclassified' ? 'À ORGANISER' : `MACRO-ÉTAPE ${String(macro.number).padStart(2,'0')}`),
      uiElement('strong','macro-title',macro.name),uiElement('span','macro-description',macro.description));
    const footer = uiElement('span','macro-footer');
    footer.append(uiElement('span','',plural(children.length,'sous-étape')),uiElement('span','',plural(teams.size,'équipe')),uiElement('span','macro-enter','Explorer ↗'));
    card.append(footer); card.addEventListener('click',event => {event.stopPropagation(); enterMacro(macro.id);});
    viewport.append(card);
  }
  container.append(viewport);
  if (keepView) updateGraphView(); else fitMacroOverview();
  renderEmptyView();
}
function fitMacroOverview() {
  const items = macroItems(), rect = $('journeyCanvas').getBoundingClientRect();
  if (!items.length) {graphZoom=1;graphPan={x:0,y:0};updateGraphView();return;}
  const x1 = Math.min(...items.map(item => item.x-MACRO_WIDTH/2-25)), x2 = Math.max(...items.map(item => item.x+MACRO_WIDTH/2+25));
  const y1 = Math.min(...items.map(item => item.y-MACRO_HEIGHT/2-25)), y2 = Math.max(...items.map(item => item.y+MACRO_HEIGHT/2+25));
  graphZoom = Math.max(.7,Math.min(1.1,(rect.width-50)/(x2-x1),(rect.height-85)/(y2-y1)));
  graphPan = {x:rect.width/2-(x1+x2)/2*graphZoom,y:(y2-y1)*graphZoom>rect.height-75 ? 55-y1*graphZoom : rect.height/2-(y1+y2)/2*graphZoom};
  updateGraphView();
}
function renderEmptyView() {
  if (isMacroOverview() ? macroItems().length : visibleStages().length) return;
  const message = uiElement('div','empty-graph');
  message.append(uiElement('strong','',isMacroOverview() ? 'Votre parcours commence ici' : 'Cette macro-étape est encore vide'),
    uiElement('p','',isAdmin ? 'Ajoutez une sous-étape ou modifiez son association depuis sa fiche.' : 'Les sous-étapes apparaîtront ici lorsqu’un administrateur les aura ajoutées.'));
  $('journeyCanvas').append(message);
}
function updateHierarchyNavigation() {
  const overview = isMacroOverview();
  const macro = (data.macros || []).find(item => item.id === currentMacroId);
  const name = overview ? 'Vue d’ensemble' : macro?.name || (currentMacroId === 'unclassified' ? 'Étapes à classer' : 'Toutes les sous-étapes');
  $('viewTitle').textContent = name;
  $('viewContext').textContent = overview ? 'LES GRANDS TEMPS DU PARCOURS' : 'VUE DÉTAILLÉE';
  $('viewCount').textContent = overview ? plural((data.macros || []).length,'macro-étape') : plural(visibleStages().length,'sous-étape');
  $('backToOverview').hidden = overview || !Array.isArray(data.macros);
  $('showAllStages').hidden = currentMacroId === 'all';
  $('newMacroBtn').hidden = !overview;
  $('editCurrentMacro').hidden = !macro;
  $('phaseLegend').hidden = overview;
  $('connectionHint').hidden = overview;
  $('workspaceTitle').textContent = overview ? 'Les grands temps du parcours' : name;
  $('workspaceDescription').textContent = overview ? 'Cliquez sur une macro-étape pour zoomer et découvrir ses sous-étapes.' :
    macro?.description || 'Consultez les étapes et leurs équipes. Les administrateurs peuvent les déplacer et les relier.';
  $('canvasCounter').textContent = overview ? plural((data.macros || []).length,'macro-étape') : plural(visibleStages().length,'sous-étape');
}
function setNavigationBusy(value) {
  navigationInProgress = value;
  $('journeyCanvas').parentElement.classList.toggle('is-navigating',value);
  $('journeyCanvas').setAttribute('aria-busy',String(value));
  for (const id of ['backToOverview','showAllStages','fitBtn','zoomIn','zoomOut','newMacroBtn','editCurrentMacro','manageMacros','addStageBtn','newStageSide']) $(id).disabled = value;
}
async function animateHierarchyView(point, scale, animate) {
  if (!animate || (typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches)) return;
  const viewport = $('graphViewport'), rect = $('journeyCanvas').getBoundingClientRect();
  if (!viewport) return;
  viewport.style.transition = 'transform 360ms cubic-bezier(.22,.68,0,1), opacity 180ms ease';
  graphZoom = Math.max(.25,Math.min(2.5,scale));
  graphPan = {x:rect.width/2-point.x*graphZoom,y:rect.height/2-point.y*graphZoom};
  updateGraphView();
  await new Promise(resolve => setTimeout(resolve,360));
}
async function enterMacro(id, animate = true) {
  if (navigationInProgress || !Array.isArray(data.macros)) return;
  if (id !== 'all' && id !== 'unclassified' && !data.macros.some(macro => macro.id === id)) return;
  setNavigationBusy(true);
  try {
    cancelConnectionDrag(); await finishGraphGesture(true); closeConnectionTools();
    if (currentMacroId === null) overviewView = {zoom:graphZoom,pan:{...graphPan}};
    const rect = $('journeyCanvas').getBoundingClientRect();
    const target = currentMacroId === null ? macroItems().find(macro => macro.id === id) : null;
    const point = target || screenToDiagram({x:rect.width/2,y:rect.height/2});
    await animateHierarchyView(point,Math.max(1.3,graphZoom*1.8),animate);
    currentMacroId=id; renderGraph(false); renderConnectionHandles(); updateHierarchyNavigation();
    $('graphViewport').classList.add('view-reveal');
  } finally {setNavigationBusy(false);$('backToOverview').focus();}
}
async function returnToOverview(animate = true) {
  if (navigationInProgress || isMacroOverview()) return;
  const previousMacroId = currentMacroId;
  setNavigationBusy(true);
  try {
    cancelConnectionDrag(); await finishGraphGesture(true); closeConnectionTools();
    const rect = $('journeyCanvas').getBoundingClientRect();
    await animateHierarchyView(screenToDiagram({x:rect.width/2,y:rect.height/2}),graphZoom*.65,animate);
    currentMacroId=null;
    if (overviewView) {graphZoom=overviewView.zoom;graphPan={...overviewView.pan};renderGraph(true);}
    else renderGraph(false);
    renderConnectionHandles(); updateHierarchyNavigation(); $('graphViewport').classList.add('view-reveal');
  } finally {
    setNavigationBusy(false);
    const cards = [...$('journeyCanvas').querySelectorAll('.macro-card')];
    (cards.find(card => String(card.dataset.macroId) === String(previousMacroId)) || cards[0] || $('showAllStages')).focus();
  }
}

function renderMacroOptions(selected) {
  $('stageMacro').replaceChildren();
  const empty = uiElement('option','','Étapes à classer'); empty.value=''; $('stageMacro').append(empty);
  for (const macro of data.macros || []) {const option=uiElement('option','',macro.name);option.value=macro.id;$('stageMacro').append(option);}
  $('stageMacro').value = selected ?? '';
}
function renderStageTeamDetails() {
  $('stageTeamDetails').replaceChildren();
  const ids = [...$('teamChecks').querySelectorAll('input:checked')].map(input => Number(input.value));
  const teams = data.teams.filter(team => ids.includes(team.id));
  if (!teams.length) return;
  $('stageTeamDetails').append(uiElement('h3','subheading','Organisation des équipes sélectionnées'));
  for (const team of teams) {
    const block=uiElement('div','stage-team-block'); block.append(uiElement('strong','',`${displayName(team)} · ${teamStaffLabel(team)}`));
    for (const subteam of team.subteams || []) block.append(uiElement('span','',`${subteam.name} : ${plural(subteam.headcount,'personne')}${subteam.is_example ? ' (exemple)' : ''}`));
    if (!(team.subteams || []).length) block.append(uiElement('span','','Aucune sous-équipe renseignée.'));
    $('stageTeamDetails').append(block);
  }
}
function renderTeamHierarchy() {
  $('teamDirectory').replaceChildren();
  $('headcountNotice').textContent = data.teams.some(team => team.has_example_headcounts) ? 'Les effectifs marqués « exemple » sont fictifs. L’administrateur peut les remplacer par les effectifs réels.' : 'Les effectifs sont renseignés par l’administrateur et totalisés par équipe.';
  for (const team of data.teams) {
    const details=uiElement('details','team-tree'), summary=uiElement('summary','team-summary');
    details.open=expandedTeams.has(team.id)||(!teamTreeInitialized&&displayName(team)==='Marketing');
    if (details.open) expandedTeams.add(team.id);
    details.addEventListener('toggle',()=>details.open ? expandedTeams.add(team.id) : expandedTeams.delete(team.id));
    const text=uiElement('span','team-summary-text');text.append(uiElement('strong','',displayName(team)),uiElement('small','',plural((team.subteams || []).length,'sous-équipe')));
    summary.append(teamColorDot(team.color),text,uiElement('span','staff-badge',teamStaffLabel(team)));details.append(summary);
    const children=uiElement('div','subteam-rows');
    for (const subteam of team.subteams || []) {
      const row=uiElement('div','subteam-row');row.append(uiElement('span','subteam-name',subteam.name),uiElement('span','subteam-count',plural(subteam.headcount,'personne')));
      if (subteam.is_example) row.append(uiElement('small','example-pill','Exemple'));
      if (isAdmin) {
        const edit=uiElement('button','text-action','Modifier');edit.type='button';edit.onclick=()=>editSubteam(subteam.id);row.append(edit);
        const remove=uiElement('button','text-action danger-text','Supprimer');remove.type='button';remove.onclick=async()=>{
          if (!confirm(`Supprimer la sous-équipe « ${subteam.name} » et son effectif ?`)) return;
          try {await api(`/api/subteams/${subteam.id}`,'DELETE');await refresh();resetSubteamEditor(team.id);toast('Sous-équipe supprimée');}catch(err){toast(err.message);}
        };row.append(remove);
      }
      children.append(row);
    }
    if (!(team.subteams || []).length) children.append(uiElement('p','drawer-description','Aucune sous-équipe renseignée.'));
    if (isAdmin) {
      const actions=uiElement('div','team-tree-actions');
      const add=uiElement('button','text-action','＋ Sous-équipe');add.type='button';add.onclick=()=>resetSubteamEditor(team.id,true);
      const remove=uiElement('button','text-action danger-text','Supprimer l’équipe');remove.type='button';remove.dataset.deleteTeam=team.id;
      actions.append(add,remove);children.append(actions);
    }
    details.append(children);$('teamDirectory').append(details);
  }
  teamTreeInitialized=true;
  const selected=$('subteamParent').value;$('subteamParent').replaceChildren();
  for (const team of data.teams) {const option=uiElement('option','',displayName(team));option.value=team.id;$('subteamParent').append(option);}
  if (data.teams.some(team=>String(team.id)===selected)) $('subteamParent').value=selected;
}
function resetSubteamEditor(teamId = null, focus = false) {
  currentSubteamEditor=null;$('subteamEditorTitle').textContent='Ajouter une sous-équipe';
  $('subteamName').value='';$('subteamHeadcount').value=0;
  if (teamId !== null) $('subteamParent').value=teamId;
  for(const id of ['subteamName','subteamHeadcount']) $(id).setCustomValidity?.('');
  if (focus) {$('subteamName').scrollIntoView?.({block:'center',behavior:'smooth'});$('subteamName').focus();}
}
function editSubteam(id) {
  if (!isAdmin) return;
  const subteam=(data.subteams || data.teams.flatMap(team=>team.subteams || [])).find(item=>item.id===id);
  if (!subteam) return;
  resetSubteamEditor(subteam.team_id);
  currentSubteamEditor=id;$('subteamEditorTitle').textContent='Modifier la sous-équipe';
  $('subteamName').value=subteam.name;$('subteamHeadcount').value=subteam.headcount;
  $('subteamName').scrollIntoView?.({block:'center',behavior:'smooth'});$('subteamName').focus();
}
function renderMacroDirectory() {
  $('macroDirectory').replaceChildren();
  for (const macro of data.macros || []) {
    const button=uiElement('button','macro-directory-item');button.type='button';
    button.append(teamColorDot(macro.color),uiElement('span','',macro.name),uiElement('small','',plural(macroChildren(macro.id).length,'sous-étape')));
    button.onclick=()=>openMacroEditor(macro.id);$('macroDirectory').append(button);
  }
}
function openMacroEditor(id = null) {
  if (!isAdmin) return;
  currentMacroEditor=id;const macro=(data.macros || []).find(item=>item.id===id);
  $('macroEditorTitle').textContent=macro ? 'Modifier la macro-étape' : 'Nouvelle macro-étape';
  $('macroName').value=macro?.name || '';$('macroDescription').value=macro?.description || '';
  $('macroColor').value=macro?.color || '#22b5be';$('macroOrder').value=macro?.sort_order ?? (data.macros || []).length+1;
  $('deleteMacro').hidden=!macro;
  for(const field of $('macroForm').querySelectorAll('input,textarea')) field.setCustomValidity?.('');
  renderMacroDirectory();openDrawer('macroDrawer');$('macroName').focus();
}
function wireHierarchy() {
  window.addEventListener('resize', () => {
    if (navigationInProgress) return;
    overviewView = null;
    if (isMacroOverview()) renderGraph(false);
  });
  $('navJourney').onclick=()=>returnToOverview();
  $('backToOverview').onclick=()=>returnToOverview();
  $('showAllStages').onclick=()=>enterMacro('all');
  $('manageMacros').onclick=()=>openMacroEditor();$('newMacroBtn').onclick=()=>openMacroEditor();
  $('editCurrentMacro').onclick=()=>openMacroEditor(currentMacroId);
  $('resetMacro').onclick=()=>openMacroEditor();$('resetSubteam').onclick=()=>resetSubteamEditor();
  $('subteamForm').onsubmit=async event=>{
    event.preventDefault();if(!isAdmin)return;
    try {
      const payload={team_id:Number($('subteamParent').value),name:$('subteamName').value,headcount:Number($('subteamHeadcount').value)};
      await api(currentSubteamEditor ? `/api/subteams/${currentSubteamEditor}` : '/api/subteams',currentSubteamEditor ? 'PUT' : 'POST',payload);
      expandedTeams.add(payload.team_id);await refresh();resetSubteamEditor(payload.team_id);toast('Sous-équipe et effectif enregistrés');
    }catch(err){toast(err.message);}
  };
  $('macroForm').onsubmit=async event=>{
    event.preventDefault();if(!isAdmin)return;
    try {
      await api(currentMacroEditor ? `/api/macros/${currentMacroEditor}` : '/api/macros',currentMacroEditor ? 'PUT' : 'POST',
        {name:$('macroName').value,description:$('macroDescription').value,color:$('macroColor').value,sort_order:Number($('macroOrder').value)});
      closeDrawers();await refresh();toast('Macro-étape enregistrée');
    }catch(err){toast(err.message);}
  };
  $('deleteMacro').onclick=async()=>{
    if(!isAdmin || currentMacroEditor===null || !confirm('Supprimer cette macro-étape ? Ses sous-étapes et leurs liaisons seront conservées dans « Étapes à classer ».'))return;
    try {await api(`/api/macros/${currentMacroEditor}`,'DELETE');closeDrawers();await refresh();toast('Macro-étape supprimée, sous-étapes conservées');}catch(err){toast(err.message);}
  };
}
