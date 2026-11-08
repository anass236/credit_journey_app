"""Hierarchy persistence, migration, validation, and authorization regressions."""
import unittest

import test_app


class HierarchyTests(unittest.TestCase):
    setUpClass = classmethod(test_app.JourneyTests.setUpClass.__func__)
    tearDownClass = classmethod(test_app.JourneyTests.tearDownClass.__func__)
    setUp = test_app.JourneyTests.setUp
    tearDown = test_app.JourneyTests.tearDown
    token = test_app.JourneyTests.token
    send = test_app.JourneyTests.send
    setup_admin = test_app.JourneyTests.setup_admin
    viewer = test_app.JourneyTests.viewer

    def test_five_macro_examples_and_derived_team_totals(self):
        data = self.module.get_data()
        self.assertEqual(len(data['macros']), 5)
        self.assertEqual([m['sort_order'] for m in data['macros']], [1, 2, 3, 4, 5])
        self.assertTrue(all(s['macro_id'] in {m['id'] for m in data['macros']} for s in data['stages']))
        marketing = next(t for t in data['teams'] if t['name'] == 'Marketing')
        self.assertEqual(marketing['headcount'], 13)
        self.assertEqual(len(marketing['subteams']), 3)
        self.assertTrue(marketing['has_example_headcounts'])
        self.assertTrue(all(s['is_example'] for s in data['subteams']))

    def test_subteam_crud_and_counts_survive_restart_without_reseeding(self):
        self.setup_admin()
        original = self.module.get_data()
        team = next(t for t in original['teams'] if t['name'] == 'Marketing')
        child = team['subteams'][0]
        payload = {'team_id':team['id'], 'name':'Acquisition régionale', 'headcount':12}
        self.assertEqual(self.send(f"/api/subteams/{child['id']}", 'PUT', payload).status_code, 200)
        result = self.send('/api/subteams', payload={**payload, 'name':'Événements', 'headcount':2})
        self.assertEqual(result.status_code, 201)
        self.assertEqual(self.send(f"/api/subteams/{result.json['id']}", 'DELETE').status_code, 200)
        self.assertEqual(self.send(f"/api/subteams/{team['subteams'][1]['id']}", 'DELETE').status_code, 200)
        before = self.module.get_data()
        self.module.init_db()
        self.assertEqual(before, self.module.get_data())
        updated = next(t for t in before['teams'] if t['id'] == team['id'])
        self.assertEqual(updated['headcount'], 12 + team['subteams'][2]['headcount'])
        self.assertEqual(next(s for s in updated['subteams'] if s['id'] == child['id'])['is_example'], 0)
        self.assertEqual(original['stages'], before['stages'])
        self.assertEqual(original['edges'], before['edges'])

    def test_macro_crud_reassignment_and_delete_preserve_stages_and_edges(self):
        self.setup_admin()
        result = self.send('/api/macros', payload={'name':'Recouvrement', 'color':'#123456', 'sort_order':6})
        self.assertEqual(result.status_code, 201)
        mid = result.json['id']
        self.assertEqual(self.send(f'/api/macros/{mid}', 'PUT', {'name':'Accompagnement', 'description':'Après financement', 'sort_order':0}).status_code, 200)
        stage = self.module.get_data()['stages'][0]
        payload = {k:stage[k] for k in ('name','description','phase','x','y','team_ids')}
        self.assertEqual(self.send(f"/api/stages/{stage['id']}", 'PUT', {**payload,'macro_id':mid}).status_code, 200)
        self.assertEqual(self.send(f"/api/stages/{stage['id']}", 'PUT', payload).status_code, 200)
        before = self.module.get_data()
        self.assertEqual(next(s for s in before['stages'] if s['id'] == stage['id'])['macro_id'], mid)
        self.assertEqual(self.send(f'/api/macros/{mid}', 'DELETE').status_code, 200)
        after = self.module.get_data()
        self.assertEqual(before['edges'], after['edges'])
        self.assertEqual(len(before['stages']), len(after['stages']))
        self.assertIsNone(next(s for s in after['stages'] if s['id'] == stage['id'])['macro_id'])
        self.module.init_db()
        self.assertEqual(after, self.module.get_data())

    def test_parent_removal_cascades_children_and_not_stages(self):
        self.setup_admin()
        before = self.module.get_data()
        team = before['subteams'][0]['team_id']
        self.assertEqual(self.send(f'/api/teams/{team}', 'DELETE').status_code, 200)
        after = self.module.get_data()
        self.assertFalse(any(s['team_id'] == team for s in after['subteams']))
        self.assertEqual(len(before['stages']), len(after['stages']))
        self.assertEqual(before['edges'], after['edges'])

    def test_invalid_hierarchy_inputs_do_not_change_data(self):
        self.setup_admin()
        before = self.module.get_data()
        team = before['teams'][0]['id']
        for value in [-1, 1.5, True, '4', None, 10001, []]:
            with self.subTest(headcount=value):
                self.assertEqual(self.send('/api/subteams', payload={'team_id':team,'name':'Test','headcount':value}).status_code, 400)
        for payload in [{'name':'Test','color':'red'}, {'name':'Test','sort_order':True}, {'name':'x'*101}]:
            self.assertEqual(self.send('/api/macros', payload=payload).status_code, 400)
        self.assertEqual(self.send('/api/subteams', payload={'team_id':999,'name':'Test','headcount':4}).status_code, 404)
        child = before['subteams'][0]
        self.assertEqual(self.send('/api/subteams', payload={**child, 'name':child['name'].upper()}).status_code, 409)
        stage = before['stages'][0]
        for mid in [999999, True, '1', -1]:
            self.assertEqual(self.send(f"/api/stages/{stage['id']}", 'PUT', {**stage,'macro_id':mid}).status_code, 400)
        self.assertEqual(before, self.module.get_data())

    def test_hierarchy_writes_require_admin_and_csrf(self):
        viewer = self.viewer()
        before = viewer.get('/api/journey').json
        self.assertEqual(len(before['macros']), 5)
        for method, url in [('POST','/api/macros'),('PUT','/api/macros/1'),('DELETE','/api/macros/1'),
                            ('POST','/api/subteams'),('PUT','/api/subteams/1'),('DELETE','/api/subteams/1')]:
            with self.subTest(method=method,url=url):
                self.assertEqual(self.send(url,method,{},viewer).status_code, 403)
                self.assertEqual(self.client.open(url,method=method,json={}).status_code, 403)
                self.assertEqual(self.app.test_client().open(url,method=method,json={}).status_code, 401)
        self.assertEqual(before, viewer.get('/api/journey').json)

    def test_hierarchy_resource_caps_and_moving_between_parents(self):
        self.setup_admin()
        data = self.module.get_data()
        team, other = data['teams'][:2]
        with self.module.connection() as db:
            count = db.execute('SELECT COUNT(*) FROM subteams WHERE team_id=?', (team['id'],)).fetchone()[0]
            db.executemany('INSERT INTO subteams(team_id,name,headcount) VALUES (?,?,0)',
                           [(team['id'], f'Groupe {i}') for i in range(100-count)])
            db.executemany('INSERT INTO macro_stages(name) VALUES (?)', [(f'Macro {i}',) for i in range(45)])
        self.assertEqual(self.send('/api/macros', payload={'name':'Dépassement'}).status_code, 400)
        self.assertEqual(self.send('/api/subteams', payload={'team_id':team['id'],'name':'Dépassement','headcount':1}).status_code, 400)
        child = other['subteams'][0]
        self.assertEqual(self.send(f"/api/subteams/{child['id']}", 'PUT', {'team_id':team['id'],'name':'Transfert','headcount':2}).status_code, 400)
        result = self.send('/api/subteams', payload={'team_id':other['id'],'name':'Transfert','headcount':0})
        self.assertEqual(result.status_code, 201)
        self.assertEqual(self.send(f"/api/subteams/{result.json['id']}", 'PUT', {'team_id':other['id'],'name':'Transfert','headcount':10000}).status_code, 200)


if __name__ == '__main__':
    unittest.main()
