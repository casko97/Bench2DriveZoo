import os
import unittest
from unittest.mock import patch

from scripts import select_carla_gpu as selector


class SelectCarlaGpuTests(unittest.TestCase):
    def test_select_adapter_by_pci_not_vulkan_ordinal(self):
        output = ('Vulkan adapter 0: software | PCI unavailable (VK_EXT_pci_bus_info not supported)\n'
                  'Vulkan adapter 1: GPU | PCI 00000000:B5:00.0\n'
                  'Vulkan adapter 2: GPU | PCI 00000000:40:00.0\n')
        self.assertEqual(selector.matching_adapter(output, '0000:40:00.0'), 2)

    def test_reject_missing_or_ambiguous_adapter(self):
        with self.assertRaisesRegex(RuntimeError, 'found 0'):
            selector.matching_adapter('Vulkan adapter 0: software | PCI unavailable\n', '0000:40:00.0')
        with self.assertRaisesRegex(RuntimeError, 'found 2'):
            selector.matching_adapter('Vulkan adapter 0: GPU | PCI 0000:40:00.0\n'
                                      'Vulkan adapter 1: GPU | PCI 00000000:40:00.0\n', '0000:40:00.0')

    def test_probe_uses_model_device_visibility(self):
        class Result:
            stdout = 'Vulkan adapter 2: GPU | PCI 00000000:40:00.0\n'
        with patch.dict(os.environ, {'CUDA_VISIBLE_DEVICES': '3,7'}, clear=True), \
             patch.object(selector, 'cuda_pci_addresses', return_value=['0000:40:00.0', '0000:b5:00.0']), \
             patch.object(selector.subprocess, 'run', return_value=Result()) as run, \
             patch('sys.stdout') as stdout, patch('sys.stderr'):
            selector.main()
        self.assertEqual(run.call_args.kwargs['env']['CUDA_VISIBLE_DEVICES'], '7')
        stdout.write.assert_any_call('2')

    def test_rejects_stale_manual_override(self):
        class Result:
            stdout = 'Vulkan adapter 2: GPU | PCI 00000000:40:00.0\n'
        with patch.dict(os.environ, {'CUDA_VISIBLE_DEVICES': '0,1', 'CARLA_VULKAN_ADAPTER': '0'}, clear=True), \
             patch.object(selector, 'cuda_pci_addresses', return_value=['0000:40:00.0', '0000:b5:00.0']), \
             patch.object(selector.subprocess, 'run', return_value=Result()), \
             patch('sys.stderr'), self.assertRaisesRegex(RuntimeError, 'does not match'):
            selector.main()


if __name__ == '__main__':
    unittest.main()
