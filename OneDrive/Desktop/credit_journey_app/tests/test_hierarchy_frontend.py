"""Native hierarchy navigation and role checks through Python's JS engine."""
import json
import unittest

import test_frontend


FIXTURE = """
testModel.macros = [1,2,3,4,5].map(id => ({id,name:`Macro ${id}`,description:'Un grand temps du parcours',color:'#123456',sort_order:id}));
testModel.stages.forEach(stage => stage.macro_id = stage.id === 3 ? 2 : 1);
testModel.teams = [{id:1,name:'Marketing',color:'#123456',headcount:13,has_example_headcounts:true,
  subteams:[{id:1,team_id:1,name:'Acquisition digitale',headcount:6,is_example:1},{id:2,team_id:1,name:'Communication',headcount:7,is_example:1}]}];
testModel.subteams = testModel.teams[0].subteams;
testModel.stages[0].team_ids = [1];
testModel.edges.push({...testModel.edges[0],id:2,source:2,target:3});
function allText(element) {return element.textContent+' '+element.children.map(allText).join(' ');}
"""


@unittest.skipIf(test_frontend.MiniRacer is None, 'Install requirements-dev.txt for JavaScript logic checks.')
class HierarchyFrontendTests(unittest.TestCase):
    workspace = test_frontend.FrontendTests.workspace

    def context(self, role='admin', extra=''):
        return self.workspace(role, FIXTURE + extra)

    def test_five_clickable_macros_no_stage_handles_and_aggregate_links(self):
        ctx = self.context()
        self.assertEqual(ctx.eval("$('journeyCanvas').querySelectorAll('.macro-card').length"), 5)
        self.assertEqual(ctx.eval('stageElements.size'), 0)
        self.assertEqual(ctx.eval("$('connectionHandles').children.length"), 0)
        self.assertEqual(ctx.eval("$('graphEdges').querySelectorAll('path').length"), 2)
        self.assertEqual(ctx.eval("$('canvasCounter').textContent"), '5 macro-étapes')
        self.assertNotIn('NaN', ctx.eval("JSON.stringify($('graphEdges').children.map(e=>e.attributes))"))

    def test_zoom_filters_children_and_return_restores_camera_without_writes(self):
        ctx = self.context('viewer')
        ctx.eval('graphZoom=.8;graphPan={x:40,y:55};enterMacro(1,false)').get()
        self.assertEqual(json.loads(ctx.eval('JSON.stringify([...stageElements.keys()])')), [1,2])
        self.assertEqual(ctx.eval("$('graphEdges').querySelectorAll('.graph-edge').length"), 1)
        self.assertEqual(ctx.eval("$('viewTitle').textContent"), 'Macro 1')
        self.assertTrue(ctx.eval("!$('backToOverview').hidden && !navigationInProgress"))
        ctx.eval('returnToOverview(false)').get()
        self.assertEqual(ctx.eval('graphZoom'), .8)
        self.assertEqual(json.loads(ctx.eval('JSON.stringify(graphPan)')), {'x':40,'y':55})
        self.assertEqual(ctx.eval("$('journeyCanvas').querySelectorAll('.macro-card').length"), 5)
        self.assertEqual(ctx.eval("requests.filter(r=>r.method!=='GET').length"), 0)

    def test_scope_handles_empty_group_unclassified_and_all_stages(self):
        ctx = self.context(extra='testModel.stages[2].macro_id=null;')
        self.assertEqual(ctx.eval("$('journeyCanvas').querySelectorAll('.macro-card').length"), 6)
        ctx.eval('enterMacro(1,false)').get()
        self.assertEqual(ctx.eval("$('connectionHandles').children.length"), 2)
        ctx.eval('enterMacro(3,false)').get()
        self.assertEqual(ctx.eval('stageElements.size'), 0)
        self.assertIn('encore vide', ctx.eval("allText($('journeyCanvas'))"))
        ctx.eval('enterMacro("unclassified",false)').get()
        self.assertEqual(json.loads(ctx.eval('JSON.stringify([...stageElements.keys()])')), [3])
        ctx.eval('enterMacro("all",false)').get()
        self.assertEqual(ctx.eval('stageElements.size'), 3)
        self.assertEqual(ctx.eval("$('connectionHandles').children.length"), 3)
        self.assertEqual(ctx.eval("$('graphEdges').querySelectorAll('.graph-edge').length"), 2)

    def test_reduced_motion_click_and_deleted_current_macro(self):
        ctx = self.context(extra='window.matchMedia=()=>({matches:true});')
        ctx.eval("(async()=>{$('journeyCanvas').querySelectorAll('.macro-card')[1].dispatchEvent({type:'click',stopPropagation(){}});for(let i=0;i<12;i++)await Promise.resolve();})()").get()
        self.assertEqual(ctx.eval('currentMacroId'), 2)
        self.assertFalse(ctx.eval('navigationInProgress'))
        ctx.eval('testModel.macros=testModel.macros.filter(m=>m.id!==2);testModel.stages[2].macro_id=null;refresh()').get()
        self.assertIsNone(ctx.eval('currentMacroId'))
        self.assertEqual(ctx.eval('data.stages.length'), 3)

    def test_team_tree_and_stage_show_subteams_and_viewer_has_no_edit_buttons(self):
        ctx = self.context('viewer')
        self.assertIn('13 personnes', ctx.eval("allText($('teamDirectory'))"))
        self.assertIn('Acquisition digitale', ctx.eval("allText($('teamDirectory'))"))
        self.assertEqual(ctx.eval("$('teamDirectory').querySelectorAll('button').length"), 0)
        self.assertTrue(ctx.eval("$('teamDirectory').children[0].open"))
        ctx.eval('openStage(1)')
        self.assertTrue(ctx.eval("$('stageMacro').disabled"))
        self.assertIn('Acquisition digitale : 6 personnes (exemple)', ctx.eval("allText($('stageTeamDetails'))"))
        ctx.eval("(async()=>{await $('subteamForm').onsubmit({preventDefault(){}});await $('macroForm').onsubmit({preventDefault(){}});})()").get()
        self.assertEqual(ctx.eval("requests.filter(r=>r.method!=='GET').length"), 0)

    def test_admin_edits_headcounts_and_sets_new_stage_group(self):
        ctx = self.context()
        ctx.eval("editSubteam(1);$('subteamHeadcount').value='9';$('subteamForm').onsubmit({preventDefault(){}})").get()
        request = json.loads(ctx.eval("JSON.stringify(requests.find(r=>r.url==='/api/subteams/1'))"))
        self.assertEqual(request['method'], 'PUT')
        self.assertEqual(request['payload'], {'team_id':1,'name':'Acquisition digitale','headcount':9})
        ctx.eval('enterMacro(2,false)').get()
        ctx.eval("openStage();$('stageName').value='Nouvelle demande';saveStage({preventDefault(){}})").get()
        self.assertEqual(ctx.eval("requests.find(r=>r.url==='/api/stages').payload.macro_id"), 2)
        ctx.eval("openMacroEditor(1);$('macroName').value='Découverte';$('macroForm').onsubmit({preventDefault(){}})").get()
        self.assertEqual(ctx.eval("requests.find(r=>r.url==='/api/macros/1').payload.name"), 'Découverte')

    def test_resize_reflows_overview_and_prevents_overlapping_navigation(self):
        ctx = self.context()
        ctx.eval("$('journeyCanvas').getBoundingClientRect=()=>({left:0,top:0,width:390,height:600});window.listeners.resize.forEach(callback=>callback());")
        self.assertEqual(ctx.eval("new Set($('journeyCanvas').querySelectorAll('.macro-card').map(card=>card.style.left)).size"), 1)
        ctx.eval('(async()=>{const first=enterMacro(1,false);await enterMacro(2,false);await first;})()').get()
        self.assertEqual(ctx.eval('currentMacroId'), 1)
        ctx.eval('window.listeners.resize.forEach(callback=>callback());returnToOverview(false)').get()
        self.assertFalse(ctx.eval('navigationInProgress'))
        self.assertTrue(ctx.eval('isMacroOverview()'))


if __name__ == '__main__':
    unittest.main()
