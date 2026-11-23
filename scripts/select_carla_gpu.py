#!/usr/bin/env python3
"""Resolve the first Slurm-visible CUDA device to a Vulkan adapter by PCI ID."""
import ctypes
import os
import re
import subprocess
import sys
from pathlib import Path


def pci_address(value):
    match = re.fullmatch(r'([0-9a-fA-F]{1,8}):([0-9a-fA-F]{2}):([0-9a-fA-F]{2})\.([0-7])', value.strip())
    if not match:
        raise ValueError('Invalid PCI address: ' + value)
    return tuple(int(part, 16) for part in match.groups())


def cuda_pci_addresses():
    cuda = ctypes.CDLL('libcuda.so.1')
    cuda.cuInit.argtypes = [ctypes.c_uint]
    cuda.cuInit.restype = ctypes.c_int
    cuda.cuDeviceGetCount.argtypes = [ctypes.POINTER(ctypes.c_int)]
    cuda.cuDeviceGetCount.restype = ctypes.c_int
    cuda.cuDeviceGet.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_int]
    cuda.cuDeviceGet.restype = ctypes.c_int
    cuda.cuDeviceGetPCIBusId.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
    cuda.cuDeviceGetPCIBusId.restype = ctypes.c_int

    def check(code, name):
        if code:
            raise RuntimeError('%s failed with CUDA driver error %d' % (name, code))

    check(cuda.cuInit(0), 'cuInit')
    count = ctypes.c_int()
    check(cuda.cuDeviceGetCount(ctypes.byref(count)), 'cuDeviceGetCount')
    if count.value != 2:
        raise RuntimeError('Expected exactly two CUDA-visible devices, found %d' % count.value)
    addresses = []
    for ordinal in range(count.value):
        device = ctypes.c_int()
        check(cuda.cuDeviceGet(ctypes.byref(device), ordinal), 'cuDeviceGet')
        buffer = ctypes.create_string_buffer(32)
        check(cuda.cuDeviceGetPCIBusId(buffer, len(buffer), device), 'cuDeviceGetPCIBusId')
        addresses.append(buffer.value.decode('ascii'))
    if pci_address(addresses[0]) == pci_address(addresses[1]):
        raise RuntimeError('Allocated CUDA devices share a PCI address; cannot safely separate CARLA and VAD')
    return addresses


def matching_adapter(output, carla_pci):
    matches = []
    for line in output.splitlines():
        match = re.fullmatch(r'Vulkan adapter (\d+): .* \| PCI ([0-9a-fA-F:.]+)', line)
        if match and pci_address(match.group(2)) == pci_address(carla_pci):
            matches.append(int(match.group(1)))
    if len(matches) != 1:
        raise RuntimeError('Expected one Vulkan adapter matching CARLA PCI %s; found %d' % (carla_pci, len(matches)))
    return matches[0]


def main():
    tokens = os.environ.get('CUDA_VISIBLE_DEVICES', '').split(',')
    if len(tokens) != 2 or any(not token.strip() for token in tokens) or tokens[0].strip() == tokens[1].strip():
        raise RuntimeError('CUDA_VISIBLE_DEVICES must identify exactly two distinct allocated devices')
    addresses = cuda_pci_addresses()
    # The evaluator gives its children this reduced CUDA visibility. Probe Vulkan
    # in the same environment in case a driver changes enumeration accordingly.
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=tokens[1].strip())
    probe = Path(__file__).with_name('list_vulkan_adapters.py')
    result = subprocess.run([sys.executable, str(probe)], env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, universal_newlines=True, check=True)
    print('CUDA ordinal 0 (CARLA): PCI %s; ordinal 1 (VAD): PCI %s' % tuple(addresses), file=sys.stderr)
    print(result.stdout, end='', file=sys.stderr)
    adapter = matching_adapter(result.stdout, addresses[0])
    requested = os.environ.get('CARLA_VULKAN_ADAPTER')
    if requested and (not requested.isdigit() or int(requested) != adapter):
        raise RuntimeError('CARLA_VULKAN_ADAPTER=%s does not match detected adapter %s' % (requested, adapter))
    print(adapter)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            print(exc.stderr, file=sys.stderr, end='')
        print('GPU allocation check: %s' % exc, file=sys.stderr)
        sys.exit(1)
