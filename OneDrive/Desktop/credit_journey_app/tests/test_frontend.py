"""Run vanilla JavaScript logic checks through a Python-embedded JS engine.

Install requirements-dev.txt to run these tests. No browser or JS server is used.
The small DOM double checks logic, not visual layout or native browser behavior.
"""
import json
from pathlib import Path
import re
import unittest

try:
    from py_mini_racer import MiniRacer
except ImportError:
    MiniRacer = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(MiniRacer is None, 'Install requirements-dev.txt for JavaScript logic checks.')
class FrontendTests(unittest.TestCase):
    def workspace(self, role='admin', before_start=''):
        context = MiniRacer()
        self.addCleanup(context.close)
        html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        context.eval('const TEST_IDS = ' + json.dumps(re.findall(r'\bid="([^"]+)"', html)) + '; const TEST_ROLE = ' + json.dumps(role) + ';')
        context.eval((ROOT / 'tests/frontend_dom_stub.js').read_text(encoding='utf-8'))
        for name in ['app.js']:
            context.eval((ROOT / 'static' / name).read_text(encoding='utf-8'))
        if before_start:
            context.eval(before_start)
        context.eval('window.listeners.DOMContentLoaded[0]()').get()
        return context

    def test_sign_out_still_works_when_diagram_initialization_fails(self):
        context = self.workspace(before_start="wireGraph = () => {throw new Error('Graph initialization failed');}")
        self.assertIn('Impossible d’afficher le parcours', context.eval("$('toast').textContent"))
        context.eval("$('logoutBtn').onclick()").get()
        self.assertEqual(context.eval('window.location.lastUrl'), '/login')
        self.assertEqual(context.eval("requests.find(r => r.url === '/api/auth/logout').headers['X-CSRF-Token']"), 'fresh-token')

    def test_older_open_page_redirects_to_current_template(self):
        context = self.workspace(before_start="elements.delete('journeyCanvas');")
        self.assertEqual(context.eval('window.location.lastUrl'), '/?refresh=workspace')
        context.eval("$('logoutBtn').onclick()").get()
        self.assertEqual(context.eval('window.location.lastUrl'), '/login')

    def test_all_browser_scripts_parse(self):
        context = self.workspace()
        for name in ['login.js']:
            context.eval('(function() {\n' + (ROOT / 'static' / name).read_text(encoding='utf-8') + '\n})')

    def test_untrusted_stage_and_team_names_are_text_not_html(self):
        malicious = '<img src=x onerror=alert(1)>'
        context = self.workspace(before_start='testModel.stages[0].name = ' + json.dumps(malicious) + '; testModel.teams = [{id:1,name:' + json.dumps(malicious) + ',color:"#123456"}]; testModel.stages[0].team_ids = [1];')
        self.assertEqual(context.eval("stageElements.get(1).querySelector('.stage-title').textContent"), malicious)
        context.eval('openStage(1)')
        self.assertEqual(context.eval("$('teamChecks').children[0].children[2].textContent"), malicious)
        self.assertNotIn('innerHTML', (ROOT / 'static/app.js').read_text(encoding='utf-8'))

    def test_french_display_labels_and_input_validation(self):
        context = self.workspace(before_start="testModel.stages[0].display_name='Découverte et acquisition'; testModel.stages[0].display_description='Description française';")
        self.assertEqual(context.eval("stageElements.get(1).querySelector('.stage-title').textContent"), 'Découverte et acquisition')
        self.assertEqual(context.eval("stageElements.get(1).querySelector('.stage-description').textContent"), 'Description française')
        context.eval('openStage(1)')
        self.assertEqual(context.eval("$('stageName').value"), 'Découverte et acquisition')
        self.assertEqual(context.eval("$('stageDesc').value"), 'Description française')
        self.assertEqual(context.eval('data.stages[0].name'), 'Stage 1')
        self.assertEqual(context.eval("roleLabel('viewer')"), 'Lecteur')
        context.eval("const invalidField = $('stageName'); invalidField.setCustomValidity = message => invalidField.message=message; invalidField.validity={valueMissing:true}; document.body.dispatchEvent({type:'invalid',target:invalidField});")
        self.assertEqual(context.eval('invalidField.message'), 'Veuillez renseigner ce champ.')
        context.eval('openStage(1)')
        self.assertEqual(context.eval('invalidField.message'), '')
        context.eval("document.body.dispatchEvent({type:'invalid',target:invalidField});")
        context.eval("document.body.dispatchEvent({type:'input',target:invalidField});")
        self.assertEqual(context.eval('invalidField.message'), '')

    def test_admin_drop_saves_without_form_or_stage_movement(self):
        context = self.workspace()
        context.eval('dropConnection(1,3)').get()
        self.assertEqual(context.eval('data.edges.length'), 2)
        self.assertEqual(context.eval("requests.filter(r => r.method === 'POST').length"), 1)
        self.assertEqual(context.eval('data.stages[0].x'), 200)
        self.assertTrue(context.eval("$('connectionTools').hidden && $('connectionPreview').hidden"))

    def test_duplicate_and_self_connections_are_rejected(self):
        context = self.workspace()
        context.eval('(async() => {await dropConnection(1,1); await dropConnection(1,2);})()').get()
        self.assertEqual(context.eval("requests.filter(r => r.method !== 'GET').length"), 0)

    def test_pan_zoom_hit_testing_and_cancellation(self):
        context = self.workspace()
        context.eval('graphZoom = .7; graphPan = {x:90,y:30}; updateGraphView();')
        self.assertEqual(context.eval('stageAtPointer({clientX:870,clientY:290})'), 3)
        context.eval("pointer(testHandle(1),data.stages[0]); pointer(testHandle(1),data.stages[2],'pointercancel');")
        self.assertTrue(context.eval("connectionDrag === null && $('connectionPreview').hidden"))
        context.eval('dropConnection(1,3)').get()
        self.assertEqual(context.eval('data.edges.length'), 2)
        self.assertAlmostEqual(context.eval('graphZoom'), .7)

    def test_failed_save_does_not_leave_a_connection(self):
        context = self.workspace()
        context.eval('failWrites = true; dropConnection(1,3)').get()
        self.assertEqual(context.eval('data.edges.length'), 1)
        self.assertTrue(context.eval("$('connectionPreview').hidden && !connectionSaving"))

    def test_viewer_cannot_connect_or_drag_stages(self):
        context = self.workspace('viewer')
        self.assertEqual(context.eval("$('connectionHandles').children.length"), 0)
        context.eval('createDraggedConnection(1,3)').get()
        self.assertEqual(context.eval("requests.filter(r => r.method !== 'GET').length"), 0)
        context.eval("const card = stageElements.get(1); $('journeyCanvas').dispatchEvent({type:'pointerdown',target:card,button:0,pointerId:1,clientX:200,clientY:200});")
        self.assertTrue(context.eval('graphGesture === null'))

    def test_native_svg_routes_and_inline_save(self):
        context = self.workspace()
        for shape, command in [('curved','Q'), ('elbow','H'), ('straight','L')]:
            path = context.eval(f"connectionGeometry({{...data.edges[0],shape:'{shape}'}},data.stages[0],data.stages[2]).path")
            self.assertIn(command, path)
            self.assertNotIn('NaN', path)
        context.eval("selectConnection(1); $('edgeShape').value = 'elbow'; saveConnectionStyle()").get()
        self.assertEqual(context.eval('data.edges[0].shape'), 'elbow')

    def test_admin_stage_drag_saves_diagram_coordinates(self):
        context = self.workspace()
        context.eval("""
          graphZoom = .5; graphPan = {x:40,y:20};
          const canvas = $('journeyCanvas');
          const card = stageElements.get(1);
          const event = (type,x,y) => ({type,pointerId:1,button:0,target:card,clientX:x,clientY:y,preventDefault(){}});
          canvas.dispatchEvent(event('pointerdown',200,200));
          canvas.dispatchEvent(event('pointermove',250,225));
        """)
        context.eval('finishGraphGesture()').get()
        position = json.loads(context.eval("JSON.stringify(requests.find(r => r.method === 'PATCH').payload)"))
        self.assertEqual(position, {'x':300, 'y':250})

    def test_stage_drag_cancel_and_failed_save_restore_position(self):
        context = self.workspace()
        context.eval("""
          function startTestMove() {
            const canvas = $('journeyCanvas'), card = stageElements.get(1);
            canvas.dispatchEvent({type:'pointerdown',pointerId:1,button:0,target:card,clientX:200,clientY:200});
            canvas.dispatchEvent({type:'pointermove',pointerId:1,target:card,clientX:250,clientY:225,preventDefault(){}});
          }
          startTestMove();
        """)
        context.eval('finishGraphGesture(true)').get()
        self.assertEqual(context.eval('data.stages[0].x'), 200)
        context.eval('failWrites = true; startTestMove(); finishGraphGesture()').get()
        self.assertEqual(context.eval('data.stages[0].x'), 200)


if __name__ == '__main__':
    unittest.main()
