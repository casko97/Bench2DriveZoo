#!/usr/bin/env python3
"""List Vulkan adapter indices and PCI addresses without vulkaninfo."""
import ctypes as c
import ctypes.util
import sys


class ApplicationInfo(c.Structure):
    _fields_ = [('sType', c.c_uint32), ('pNext', c.c_void_p),
                ('pApplicationName', c.c_char_p), ('applicationVersion', c.c_uint32),
                ('pEngineName', c.c_char_p), ('engineVersion', c.c_uint32),
                ('apiVersion', c.c_uint32)]


class InstanceInfo(c.Structure):
    _fields_ = [('sType', c.c_uint32), ('pNext', c.c_void_p), ('flags', c.c_uint32),
                ('pApplicationInfo', c.POINTER(ApplicationInfo)),
                ('enabledLayerCount', c.c_uint32), ('ppEnabledLayerNames', c.c_void_p),
                ('enabledExtensionCount', c.c_uint32), ('ppEnabledExtensionNames', c.c_void_p)]


class Extension(c.Structure):
    _fields_ = [('extensionName', c.c_char * 256), ('specVersion', c.c_uint32)]


class PciInfo(c.Structure):
    _fields_ = [('sType', c.c_uint32), ('pNext', c.c_void_p), ('pciDomain', c.c_uint32),
                ('pciBus', c.c_uint32), ('pciDevice', c.c_uint32), ('pciFunction', c.c_uint32)]


class Properties2(c.Structure):
    # VkPhysicalDeviceProperties is smaller than this aligned opaque buffer.
    _fields_ = [('sType', c.c_uint32), ('pNext', c.c_void_p), ('properties', c.c_uint64 * 512)]


def check(result, operation):
    if result != 0:
        raise RuntimeError('%s failed with Vulkan result %s' % (operation, result))


def main():
    lib = ctypes.util.find_library('vulkan')
    if not lib:
        raise RuntimeError('Vulkan loader library not found (libvulkan.so.1)')
    vk = c.CDLL(lib)
    vk.vkCreateInstance.argtypes = [c.POINTER(InstanceInfo), c.c_void_p, c.POINTER(c.c_void_p)]
    vk.vkCreateInstance.restype = c.c_int32
    vk.vkEnumeratePhysicalDevices.argtypes = [c.c_void_p, c.POINTER(c.c_uint32), c.POINTER(c.c_void_p)]
    vk.vkEnumeratePhysicalDevices.restype = c.c_int32
    vk.vkEnumerateDeviceExtensionProperties.argtypes = [c.c_void_p, c.c_char_p, c.POINTER(c.c_uint32), c.POINTER(Extension)]
    vk.vkEnumerateDeviceExtensionProperties.restype = c.c_int32
    vk.vkGetPhysicalDeviceProperties2.argtypes = [c.c_void_p, c.POINTER(Properties2)]
    vk.vkDestroyInstance.argtypes = [c.c_void_p, c.c_void_p]
    app = ApplicationInfo(0, None, b'vulkan-device-probe', 0, None, 0, (1 << 22) | (1 << 12))
    info = InstanceInfo(1, None, 0, c.pointer(app), 0, None, 0, None)
    instance = c.c_void_p()
    check(vk.vkCreateInstance(c.byref(info), None, c.byref(instance)), 'vkCreateInstance')
    try:
        count = c.c_uint32()
        check(vk.vkEnumeratePhysicalDevices(instance, c.byref(count), None), 'enumerate adapters')
        devices = (c.c_void_p * count.value)()
        check(vk.vkEnumeratePhysicalDevices(instance, c.byref(count), devices), 'enumerate adapters')
        if not count.value:
            raise RuntimeError('Vulkan found no adapters')
        for index, device in enumerate(devices[:count.value]):
            n = c.c_uint32()
            check(vk.vkEnumerateDeviceExtensionProperties(device, None, c.byref(n), None), 'enumerate device extensions')
            extensions = (Extension * n.value)()
            check(vk.vkEnumerateDeviceExtensionProperties(device, None, c.byref(n), extensions), 'enumerate device extensions')
            has_pci = any(e.extensionName == b'VK_EXT_pci_bus_info' for e in extensions[:n.value])
            pci = PciInfo(1000212000, None, 0, 0, 0, 0)
            props = Properties2(1000059001, c.addressof(pci) if has_pci else None)
            vk.vkGetPhysicalDeviceProperties2(device, c.byref(props))
            raw = c.string_at(c.addressof(props.properties), 20 + 256)
            name = raw[20:].split(b'\0', 1)[0].decode('utf-8', 'replace')
            address = '%08X:%02X:%02X.%X' % (pci.pciDomain, pci.pciBus, pci.pciDevice, pci.pciFunction) if has_pci else 'unavailable (VK_EXT_pci_bus_info not supported)'
            print('Vulkan adapter %s: %s | PCI %s' % (index, name, address))
    finally:
        vk.vkDestroyInstance(instance, None)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, AttributeError) as exc:
        print('Vulkan probe: %s' % exc, file=sys.stderr)
        sys.exit(1)
