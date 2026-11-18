import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'select_openloop_closed_loop_routes.py'
SPEC = importlib.util.spec_from_file_location('openloop_selector', SCRIPT)
SELECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SELECTOR)

TRAJECTORY_SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'build_openloop_trajectory_routes.py'
sys.path.insert(0, str(TRAJECTORY_SCRIPT.parent))
TRAJECTORY_SPEC = importlib.util.spec_from_file_location('trajectory_routes', TRAJECTORY_SCRIPT)
TRAJECTORY = importlib.util.module_from_spec(TRAJECTORY_SPEC)
TRAJECTORY_SPEC.loader.exec_module(TRAJECTORY)

LOG_INFORMED_SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'build_openloop_log_informed_routes.py'
LOG_INFORMED_SPEC = importlib.util.spec_from_file_location('log_informed_routes', LOG_INFORMED_SCRIPT)
LOG_INFORMED = importlib.util.module_from_spec(LOG_INFORMED_SPEC)
LOG_INFORMED_SPEC.loader.exec_module(LOG_INFORMED)


class SelectOpenloopClosedLoopRoutesTest(unittest.TestCase):
    def write_xml(self, path, ids):
        root = ET.Element('routes')
        for route_id in ids:
            ET.SubElement(root, 'route', id=str(route_id), town='Town01')
        ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)

    def test_selects_manifest_route_ids_and_preserves_xml_order(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / 'routes.xml'
            manifest = directory / 'split.json'
            output = directory / 'val.xml'
            self.write_xml(source, (20, 10, 30))
            manifest.write_text(json.dumps({
                'train': ['v0.0.4/Task_Town01_Route10_Weather1'],
                'val': ['Task_Town01_Route20_Weather1', 'Task_Town01_Route30_Weather1'],
            }), encoding='utf-8')

            SELECTOR.select_routes(source, manifest, 'val', output)

            selected = ET.parse(output).getroot().findall('route')
            self.assertEqual([route.get('id') for route in selected], ['20', '30'])

    def test_rejects_incomplete_xml_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / 'routes.xml'
            manifest = directory / 'split.json'
            self.write_xml(source, (10,))
            manifest.write_text(json.dumps({
                'train': [],
                'val': ['Task_Town01_Route10_Weather1', 'Task_Town01_Route20_Weather1'],
            }), encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'open-loop archives do not contain'):
                SELECTOR.select_routes(source, manifest, 'val', directory / 'val.xml')

    def test_builds_route_only_xml_from_extracted_annotations(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            route_name = 'Task_Town01_Route10_Weather1'
            annotations = directory / 'data' / route_name / 'anno'
            annotations.mkdir(parents=True)
            for frame, location in enumerate(((1.0, 2.0, 3.0), (4.0, 5.0, 6.0))):
                payload = {
                    'bounding_boxes': [{'class': 'ego_vehicle', 'location': location}],
                    'weather': {'cloudiness': 25.0, 'sun_altitude_angle': 50.0},
                }
                import gzip
                with gzip.open(annotations / f'{frame:05d}.json.gz', 'wt', encoding='utf-8') as handle:
                    json.dump(payload, handle)
            manifest = directory / 'split.json'
            manifest.write_text(json.dumps({'train': [], 'val': [route_name]}), encoding='utf-8')
            output = directory / 'routes.xml'

            TRAJECTORY.build_routes(manifest, 'val', directory / 'data',
                                    directory / 'archives', output)

            route = ET.parse(output).getroot().find('route')
            self.assertEqual(route.get('id'), '10')
            self.assertEqual(route.get('town'), 'Town01')
            self.assertEqual(len(route.findall('./waypoints/position')), 2)
            self.assertIsNotNone(route.find('scenarios'))

    def test_builds_log_informed_scenario_and_provenance_report(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            route_name = 'Accident_Town01_Route10_Weather1'
            annotations = directory / 'data' / route_name / 'anno'
            annotations.mkdir(parents=True)
            for frame, location in enumerate(((1.0, 2.0, 3.0), (11.0, 2.0, 3.0))):
                payload = {
                    'bounding_boxes': [{'class': 'ego_vehicle', 'location': location, 'road_id': 7}],
                    'weather': {'cloudiness': 25.0, 'sun_altitude_angle': 50.0},
                }
                import gzip
                with gzip.open(annotations / f'{frame:05d}.json.gz', 'wt', encoding='utf-8') as handle:
                    json.dump(payload, handle)
            manifest = directory / 'split.json'
            manifest.write_text(json.dumps({'train': [], 'val': [route_name]}), encoding='utf-8')
            template = directory / 'template.xml'
            root = ET.Element('routes')
            template_route = ET.SubElement(root, 'route', id='99', town='Town01')
            template_waypoints = ET.SubElement(template_route, 'waypoints')
            ET.SubElement(template_waypoints, 'position', x='0', y='0', z='0')
            ET.SubElement(template_waypoints, 'position', x='100', y='0', z='0')
            template_scenarios = ET.SubElement(template_route, 'scenarios')
            scenario = ET.SubElement(template_scenarios, 'scenario', name='Accident_1', type='Accident')
            ET.SubElement(scenario, 'trigger_point', x='25', y='0', z='0', yaw='0')
            ET.SubElement(scenario, 'distance', value='20')
            ET.SubElement(scenario, 'direction', value='left')
            ET.SubElement(scenario, 'speed', value='5')
            ET.ElementTree(root).write(template, encoding='utf-8', xml_declaration=True)
            output = directory / 'routes.xml'
            report = directory / 'report.json'

            LOG_INFORMED.build_routes(manifest, 'val', template, directory / 'data',
                                      directory / 'archives', output, report)

            generated = ET.parse(output).getroot().find('route')
            trigger = generated.find('./scenarios/scenario/trigger_point')
            self.assertEqual(generated.get('road_id'), '7')
            self.assertEqual(generated.find('./scenarios/scenario').get('type'), 'Accident')
            self.assertAlmostEqual(float(trigger.get('x')), 3.5)
            self.assertEqual(json.loads(report.read_text())['routes'][0]['parameters'],
                             'template priors; not observed')


if __name__ == '__main__':
    unittest.main()
