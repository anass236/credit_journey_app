/* Minimal browser API doubles for Python-driven JavaScript logic tests. */
class TestElement {
  constructor(tag = 'div') {
    this.tagName = tag; this.children = []; this.dataset = {}; this.style = {}; this.attributes = {};
    this.listeners = {}; this.hidden = false; this.disabled = false; this.value = ''; this.textContent = '';
    this.classes = new Set();
    this.classList = {add:(...items) => items.forEach(item => this.classes.add(item)),
      remove:(...items) => items.forEach(item => this.classes.delete(item)), contains:item => this.classes.has(item),
      toggle:(item,active) => active ? this.classes.add(item) : this.classes.delete(item)};
  }
  set id(value) {this._id = value; elements.set(value,this);}
  get id() {return this._id;}
  set className(value) {this.classes = new Set(value.split(' '));}
  get className() {return [...this.classes].join(' ');}
  append(...children) {children.forEach(child => {child.parentElement = this; this.children.push(child);});}
  replaceChildren(...children) {this.children = []; this.append(...children);}
  setAttribute(key,value) {this.attributes[key] = String(value); if (key === 'class') this.className = value; if (key === 'id') this.id = value;}
  getAttribute(key) {return this.attributes[key];}
  matches(selector) {
    if (selector === 'input:checked') return this.tagName === 'input' && this.checked;
    return selector.startsWith('.') ? this.classes.has(selector.slice(1)) : this.tagName === selector;
  }
  closest(selectors) {return selectors.split(',').some(selector => this.matches(selector.trim())) ? this : this.parentElement?.closest(selectors);}
  querySelectorAll(selectors) {
    const result = [];
    for (const child of this.children) {
      if (selectors.split(',').some(selector => child.matches(selector.trim()))) result.push(child);
      result.push(...child.querySelectorAll(selectors));
    }
    return result;
  }
  querySelector(selector) {return this.querySelectorAll(selector)[0] || null;}
  addEventListener(type,callback) {(this.listeners[type] ||= []).push(callback);}
  dispatchEvent(event) {event.currentTarget = this; event.target ||= this; for (const callback of this.listeners[event.type] || []) callback(event);}
  getBoundingClientRect() {return {left:80,top:120,width:1400,height:700};}
  setPointerCapture(id) {this.pointer = id;}
  hasPointerCapture(id) {return this.pointer === id;}
  releasePointerCapture() {this.pointer = null;}
  checkValidity() {return true;}
  reportValidity() {return true;}
  focus() {}
}
const elements = new Map();
const body = new TestElement('body'); body.dataset.role = TEST_ROLE;
const document = {
  body, hidden:false,
  getElementById:id => elements.get(id),
  createElement:tag => new TestElement(tag),
  createElementNS:(ns,tag) => new TestElement(tag),
  querySelector:selector => selector.startsWith('meta') ? {content:'test-token'} : null,
  querySelectorAll:selector => body.querySelectorAll(selector),
  addEventListener:(...args) => body.addEventListener(...args),
};
const window = {listeners:{}, addEventListener(type,callback) {(this.listeners[type] ||= []).push(callback);},
  location:{lastUrl:null, assign(url) {this.lastUrl = url;}, replace(url) {this.lastUrl = url;}}};
function setTimeout() {return 1;}
function clearTimeout() {}
function confirm() {return true;}
for (const id of TEST_IDS) {const element = new TestElement(); element.id = id; body.append(element);}
const canvasParent = new TestElement(); canvasParent.append(elements.get('journeyCanvas'));
elements.get('connectionTools').hidden = true;
elements.get('connectionPreview').hidden = true;
elements.get('showTeams').checked = true;
const testModel = {
  stages:[1,2,3].map((id,i) => ({id,name:`Stage ${id}`,description:'',phase:'Discovery',team_ids:[],x:200+i*400,y:200})),
  teams:[], edges:[{id:1,source:1,target:2,label:'Existing',shape:'curved',line_style:'solid',color:'#a9c1c7',width:2.3,bend:80}],
};
const requests = []; let failWrites = false;
async function fetch(url,options = {}) {
  const method = options.method || 'GET', payload = options.body ? JSON.parse(options.body) : null;
  requests.push({url,method,payload,headers:options.headers});
  if (failWrites && method !== 'GET') return {ok:false,status:403,json:async() => ({error:'Admin access required'})};
  if (url === '/api/edges' && method === 'POST') testModel.edges.push({id:2,label:'',shape:'curved',line_style:'solid',color:'#a9c1c7',width:2.3,bend:80,...payload});
  if (url.startsWith('/api/edges/') && method === 'PUT') Object.assign(testModel.edges.find(edge => edge.id === Number(url.split('/').pop())),payload);
  if (url.startsWith('/api/edges/') && method === 'DELETE') testModel.edges = testModel.edges.filter(edge => edge.id !== Number(url.split('/').pop()));
  return {ok:true,status:200,json:async() => JSON.parse(JSON.stringify(url === '/api/journey' ? testModel : url === '/api/auth/session' ? {user:{role:TEST_ROLE},csrf_token:'fresh-token'} : {ok:true,id:2}))};
}
function pointer(handle,stage,type = 'pointerdown',pointerId = 1) {
  const position = diagramToScreen(stage);
  const event = {type,pointerId,button:0,pointerType:'touch',clientX:position.x+80,clientY:position.y+120,
    target:handle,currentTarget:handle,preventDefault() {},stopPropagation() {}};
  handle.dispatchEvent(event);
}
function testHandle(id) {return elements.get('connectionHandles').children.find(handle => Number(handle.dataset.stageId) === id);}
async function dropConnection(source,target) {
  const handle = testHandle(source);
  pointer(handle,data.stages.find(stage => stage.id === source));
  pointer(handle,data.stages.find(stage => stage.id === target),'pointermove');
  pointer(handle,data.stages.find(stage => stage.id === target),'pointerup');
  for (let i = 0; i < 10; i++) await Promise.resolve();
}
