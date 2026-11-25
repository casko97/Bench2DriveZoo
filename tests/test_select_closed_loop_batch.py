import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/select_closed_loop_batch.py'


class BatchSelectionTests(unittest.TestCase):
    def test_batches_cover_each_route_once_in_order(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            source = folder / 'routes.xml'
            source.write_text('<routes version="1"><metadata value="kept"/>' +
                              ''.join('<route id="%s"><waypoints/></route>' % i for i in range(12)) + '</routes>')
            count = subprocess.check_output([sys.executable, str(SCRIPT), str(source), '--count'], text=True)
            self.assertEqual(count.strip(), '3')
            ids = []
            for index, expected in enumerate((5, 5, 2)):
                output = folder / ('batch%d.xml' % index)
                subprocess.run([sys.executable, str(SCRIPT), str(source), '--index', str(index), '--output', str(output)], check=True, capture_output=True)
                root = ET.parse(output).getroot()
                self.assertEqual(root.attrib['version'], '1')
                self.assertIsNotNone(root.find('metadata'))
                routes = root.findall('route')
                self.assertEqual(len(routes), expected)
                ids.extend(route.get('id') for route in routes)
            self.assertEqual(ids, [str(i) for i in range(12)])
            invalid = subprocess.run([sys.executable, str(SCRIPT), str(source), '--index', '3', '--output', str(folder / 'invalid.xml')], capture_output=True)
            self.assertNotEqual(invalid.returncode, 0)

    def test_grouped_batches_cover_all_routes_without_mixing_towns(self):
        from scripts.select_closed_loop_batch import make_batches
        routes = [ET.Element('route', id=str(i), town=town) for i, town in
                  enumerate(['A', 'B', 'A', 'C', 'B', 'A', 'A', 'A', 'A'])]
        batches = make_batches(routes, 5, True)
        self.assertTrue(all(len(batch) <= 5 and len({r.get('town') for r in batch}) == 1 for batch in batches))
        self.assertEqual(sorted(r.get('id') for batch in batches for r in batch), sorted(r.get('id') for r in routes))
        self.assertEqual([[r.get('id') for r in batch] for batch in batches],
                         [['0', '2', '5', '6', '7'], ['8'], ['1', '4'], ['3']])

    def test_rejects_duplicate_ids_and_bad_batch_size(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'routes.xml'
            source.write_text('<routes><route id="1"/><route id="1"/></routes>')
            for args in (['--count'], ['--count', '--batch-size', '0']):
                result = subprocess.run([sys.executable, str(SCRIPT), str(source)] + args, capture_output=True)
                self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
