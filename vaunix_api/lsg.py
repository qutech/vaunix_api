import ctypes
import urllib.request
import tempfile
import os
import zipfile
import platform
import shutil
import logging
import inspect
from typing import List, Dict

from vaunix_api import VNXError

__all__ = ['download_lsg_binaries', 'VNX_LSG_API', 'LSGStatus']


def default_library_location():
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), 'vnx_fsynth')


def download_lsg_binaries(target_path=None):
    if target_path is None:
        target_path = os.path.dirname(default_library_location())

    if os.name != 'nt' or platform.architecture()[0] != '64bit':
        raise RuntimeError('Only implemented for Windows x64 :(\n'
                           'For linux you have to compile LSGhid.c to get the binary')

    zip_url = 'https://vaunix.com/resources/vnx_LSG_API.zip'

    with tempfile.TemporaryDirectory() as temp_dir:
        main_zip_file = os.path.join(temp_dir, 'vnx_LSG_API.zip')

        logging.getLogger('vaunix_api').info('Downloading LSG API')
        urllib.request.urlretrieve(zip_url, main_zip_file)

        logging.getLogger('vaunix_api').info('Unzipping LSG API')
        with zipfile.ZipFile(main_zip_file, 'r') as main_zip:
            for file_name in main_zip.namelist():
                if '64Bit SDK' in file_name:
                    sdk_file = file_name
                    break
            else:
                raise RuntimeError('64bit SDK not found', main_zip.namelist())

            main_zip.extract(sdk_file, temp_dir)

        logging.getLogger('vaunix_api').info('Unzipping LSG SDK')
        with zipfile.ZipFile(os.path.join(temp_dir, sdk_file)) as sdk_zip:
            for file_name in sdk_zip.namelist():
                if file_name.endswith('vnx_fsynth.dll'):
                    dll_file = file_name
                    break
            else:
                raise RuntimeError('DLL not found', sdk_zip.namelist())

            sdk_zip.extract(dll_file, temp_dir)

            extracted_dll_location = os.path.join(temp_dir, dll_file)

        logging.getLogger('vaunix_api').info('Moving to target location')
        shutil.move(extracted_dll_location, target_path)


class LSGStatus:
    """Helper class for inspecting answer of get_device_status"""
    def __init__(self, raw_status: int):
        self._raw_status = raw_status

    def is_invalid(self) -> bool:
        return bool(self._raw_status & VNX_LSG_API.INVALID_DEVID)

    def is_connected(self) -> bool:
        return bool(self._raw_status & VNX_LSG_API.DEV_CONNECTED)

    def is_open(self) -> bool:
        return bool(self._raw_status & VNX_LSG_API.DEV_OPENED)

    def is_sweeping(self) -> bool:
        return bool(self._raw_status & VNX_LSG_API.SWP_ACTIVE)

    def is_sweeping_up(self) -> bool:
        return bool(self._raw_status & VNX_LSG_API.SWP_UP)

    def is_repeating_sweep(self) -> bool:
        return bool(self._raw_status & VNX_LSG_API.SWP_REPEAT)

    def is_sweeping_bidirectional(self) -> bool:
        return bool(self._raw_status & VNX_LSG_API.SWP_BIDIRECTIONAL)

    def is_pll_locked(self) -> bool:
        return bool(self._raw_status & VNX_LSG_API.PLL_LOCKED)

    def as_dict(self) -> Dict[str, bool]:
        state_methods = [method for method in dir(self) if method.startswith('is_')]

        return {method: getattr(self, method)()
                for method in state_methods}

    def __repr__(self):
        # only show True flags
        return 'LSGState(%r)' % {key: value
                                 for key, value in self.as_dict().items()
                                 if value}


class VNX_LSG_API:
    """Wrapper for LabBroick Signal Generator API.
    All methods are explicit members for static type checking"""

    _default = None

    MAX_NUM_DEVICES = 64
    MAX_MODELNAME = 32

    MODE_RFON = 0x00000010  # bit is 1 for RF on, 0 if RF is off
    MODE_INTREF = 0x00000020  # bit is 1 for internal osc., 0 for external reference
    MODE_SWEEP = 0x0000000F  # bottom 4 bits are used to keep the sweep control bits

    STATUS_OK = 0
    BAD_PARAMETER = 0x80010000  # out of range input -- frequency outside min/max etc.
    BAD_HID_IO = 0x80020000
    DEVICE_NOT_READY = 0x80030000  # device isn't open, no handle, etc.
    F_INVALID_DEVID = -1.0  # for functions that return a float
    F_DEVICE_NOT_READY = -3.0

    INVALID_DEVID = 0x80000000  # MSB is set if the device ID is invalid
    DEV_CONNECTED = 0x00000001  # LSB is set if a device is connected
    DEV_OPENED = 0x00000002  # set if the device is opened
    SWP_ACTIVE = 0x00000004  # set if the device is sweeping
    SWP_UP = 0x00000008  # set if the device is sweeping up in frequency
    SWP_REPEAT = 0x00000010  # set if the device is in continuous sweep mode
    SWP_BIDIRECTIONAL = 0x00000020  # set if the device is in bi-directional sweep mode
    PLL_LOCKED = 0x00000040  # set if the PLL lock status is TRUE (both PLL's are locked)

    ERROR_BIT = 0x80000000

    DEVID = ctypes.c_uint
    DeviceIDArray: type = MAX_NUM_DEVICES * DEVID

    @classmethod
    def default(cls):
        if cls._default is None:
            cls._default = VNX_LSG_API()
        return cls._default

    def __init__(self, library: ctypes.CDLL=None):
        if library is None:
            library = ctypes.cdll.LoadLibrary(default_library_location())

        self._library = library

        self._library.fnLSG_SetTestMode.restype = None
        self._library.fnLSG_SetTestMode.argtypes = (ctypes.c_bool,)

        self._library.fnLSG_GetNumDevices.restype = int
        self._library.fnLSG_GetNumDevices.argtypes = ()

        self._library.fnLSG_GetDevInfo.restype = int
        self._library.fnLSG_GetDevInfo.argtypes = (self.DeviceIDArray,)

        if os.name == 'nt':
            self._get_model_name_char = self._library.fnLSG_GetModelNameA
        else:
            self._get_model_name_char = self._library.fnLSG_GetModelName
        self._get_model_name_char.restype = int
        self._get_model_name_char.argtypes = (self.DEVID, ctypes.c_char_p)
        self._get_model_name_char.errcheck = self.parse_int_answer

        self._library.fnLSG_InitDevice.restype = int
        self._library.fnLSG_InitDevice.argtypes = (self.DEVID,)
        self._library.fnLSG_InitDevice.errcheck = self.parse_int_answer

        self._library.fnLSG_CloseDevice.restype = int
        self._library.fnLSG_CloseDevice.argtypes = (self.DEVID,)
        self._library.fnLSG_CloseDevice.errcheck = self.parse_int_answer

        self._library.fnLSG_GetDLLVersion.restype = int
        self._library.fnLSG_GetDLLVersion.argtypes = ()
        self._library.fnLSG_GetDLLVersion.errcheck = self.parse_int_answer

        self._library.fnLSG_SetFrequency.restype = int
        self._library.fnLSG_SetFrequency.argtypes = (self.DEVID, ctypes.c_int)
        self._library.fnLSG_SetFrequency.errcheck = self.parse_int_answer

        self._library.fnLSG_SetStartFrequency.restype = int
        self._library.fnLSG_SetStartFrequency.argtypes = (self.DEVID, ctypes.c_int)
        self._library.fnLSG_SetStartFrequency.errcheck = self.parse_int_answer

        self._library.fnLSG_SetEndFrequency.restype = int
        self._library.fnLSG_SetEndFrequency.argtypes = (self.DEVID, ctypes.c_int)
        self._library.fnLSG_SetEndFrequency.errcheck = self.parse_int_answer

        self._library.fnLSG_SetFrequencyStep.restype = int
        self._library.fnLSG_SetFrequencyStep.argtypes = (self.DEVID, ctypes.c_int)
        self._library.fnLSG_SetFrequencyStep.errcheck = self.parse_int_answer

        self._library.fnLSG_SetDwellTime.restype = int
        self._library.fnLSG_SetDwellTime.argtypes = (self.DEVID, ctypes.c_int)
        self._library.fnLSG_SetDwellTime.errcheck = self.parse_int_answer

        self._library.fnLSG_SetPowerLevel.restype = int
        self._library.fnLSG_SetPowerLevel.argtypes = (self.DEVID, ctypes.c_int)
        self._library.fnLSG_SetPowerLevel.errcheck = self.parse_int_answer

        self._library.fnLSG_SetRFOn.restype = int
        self._library.fnLSG_SetRFOn.argtypes = (self.DEVID, ctypes.c_bool)
        self._library.fnLSG_SetRFOn.errcheck = self.parse_int_answer

        self._library.fnLSG_SetUseInternalRef.restype = int
        self._library.fnLSG_SetUseInternalRef.argtypes = (self.DEVID, ctypes.c_bool)
        self._library.fnLSG_SetUseInternalRef.errcheck = self.parse_int_answer

        self._library.fnLSG_SetSweepDirection.restype = int
        self._library.fnLSG_SetSweepDirection.argtypes = (self.DEVID, ctypes.c_bool)
        self._library.fnLSG_SetSweepDirection.errcheck = self.parse_int_answer

        self._library.fnLSG_SetSweepMode.restype = int
        self._library.fnLSG_SetSweepMode.argtypes = (self.DEVID, ctypes.c_bool)
        self._library.fnLSG_SetSweepMode.errcheck = self.parse_int_answer

        self._library.fnLSG_StartSweep.restype = int
        self._library.fnLSG_StartSweep.argtypes = (self.DEVID, ctypes.c_bool)
        self._library.fnLSG_StartSweep.errcheck = self.parse_int_answer

        self._library.fnLSG_SaveSettings.restype = int
        self._library.fnLSG_SaveSettings.argtypes = (self.DEVID,)
        self._library.fnLSG_SaveSettings.errcheck = self.parse_int_answer

        get_functions = ['fnLSG_GetSerialNumber',
                         'fnLSG_GetFrequency',
                         'fnLSG_GetPowerLevel',
                         'fnLSG_GetStartFrequency',
                         'fnLSG_GetEndFrequency',
                         'fnLSG_GetDwellTime',
                         'fnLSG_GetFrequencyStep',
                         'fnLSG_GetRF_On',
                         'fnLSG_GetUseInternalRef',
                         'fnLSG_GetPowerLevelAbs',
                         'fnLSG_GetMaxPwr',
                         'fnLSG_GetMinPwr',
                         'fnLSG_GetMaxFreq',
                         'fnLSG_GetMinFreq']

        # no return check
        self._library.fnLSG_GetDeviceStatus.restype = int
        self._library.fnLSG_GetDeviceStatus.argtypes = (self.DEVID,)

        for func_name in get_functions:
            func_ptr = getattr(self._library, func_name)
            func_ptr.restype = int
            func_ptr.argtypes = (self.DEVID,)
            func_ptr.errcheck = self.parse_int_answer

    def set_test_mode(self, test_mode: bool) -> None:
        self._library.fnLSG_SetTestMode(test_mode)

    def get_dll_version(self) -> int:
        return self._library.fnLSG_GetDLLVersion()

    def get_num_devices(self) -> int:
        return self._library.fnLSG_GetNumDevices()

    def get_dev_info(self) -> List[int]:
        device_ids = self.DeviceIDArray()
        active_devices = self._library.fnLSG_GetDevInfo(device_ids)
        return list(device_ids[:active_devices])

    def get_model_name(self, device_id: int) -> str:
        buffer = ctypes.create_string_buffer(self.MAX_MODELNAME)
        name_len = self._get_model_name_char(device_id, buffer)
        return buffer.value[:name_len].decode()

    def get_serial_number(self, device_id: int) -> int:
        return self._library.fnLSG_GetSerialNumber(device_id)

    def init_device(self, device_id: int) -> int:
        return self._library.fnLSG_InitDevice(device_id)

    def close_device(self, device_id: int) -> int:
        return self._library.fnLSG_CloseDevice(device_id)

    def start_sweep(self, device_id: int, go: bool) -> int:
        return self._library.fnLSG_StartSweep(device_id, go)

    def save_settings(self, device_id: int) -> int:
        return self._library.fnLSG_SaveSettings(device_id)

    # get / set methods
    def set_frequency(self, device_id: int, frequency: int) -> int:
        return self._library.fnLSG_SetFrequency(device_id, frequency)

    def get_frequency(self, device_id: int) -> int:
        return self._library.fnLSG_GetFrequency(device_id)

    def set_power_level(self, device_id: int, power_level: int) -> int:
        return self._library.fnLSG_SetPowerLevel(device_id, power_level)

    def get_power_level(self, device_id: int) -> int:
        # fnLSG_GetPowerLevel returns something strange
        return self._library.fnLSG_GetPowerLevelAbs(device_id)

    def set_rf_on(self, device_id: int, rf_on: bool) -> int:
        return self._library.fnLSG_SetRFOn(device_id, rf_on)

    def get_rf_on(self, device_id: int) -> int:
        return self._library.fnLSG_GetRF_On(device_id)

    def set_start_frequency(self, device_id: int, start_frequency: int) -> int:
        return self._library.fnLSG_SetStartFrequency(device_id, start_frequency)

    def get_start_frequency(self, device_id: int) -> int:
        return self._library.fnLSG_GetStartFrequency(device_id)

    def set_end_frequency(self, device_id: int, end_frequency: int) -> int:
        return self._library.fnLSG_SetEndFrequency(device_id, end_frequency)

    def get_end_frequency(self, device_id: int) -> int:
        return self._library.fnLSG_GetEndFrequency(device_id)

    def set_frequency_step(self, device_id: int, frequency_step: int) -> int:
        return self._library.fnLSG_SetFrequencyStep(device_id, frequency_step)

    def get_frequency_step(self, device_id: int) -> int:
        return self._library.fnLSG_GetFrequencyStep(device_id)

    def set_dwell_time(self, device_id: int, dwell_time: int) -> int:
        return self._library.fnLSG_SetDwellTime(device_id, dwell_time)

    def get_dwell_time(self, device_id: int) -> int:
        return self._library.fnLSG_GetDwellTime(device_id)

    def set_use_internal_ref(self, device_id: int, use_internal: bool) -> int:
        return self._library.fnLSG_SetUseInternalRef(device_id, use_internal)

    def get_use_internal_ref(self, device_id: int) -> int:
        return self._library.fnLSG_GetUseInternalRef(device_id)

    # set only
    def set_sweep_direction(self, device_id: int, sweep_direction: bool) -> int:
        return self._library.fnLSG_SetSweepDirection(device_id, sweep_direction)

    def set_sweep_mode(self, device_id: int, sweep_mode: bool) -> int:
        return self._library.fnLSG_SetSweepMode(device_id, sweep_mode)

    # get constants
    def get_min_pwr(self, device_id: int) -> int:
        return self._library.fnLSG_GetMinPwr(device_id)

    def get_max_pwr(self, device_id: int) -> int:
        return self._library.fnLSG_GetMaxPwr(device_id)

    def get_min_freq(self, device_id: int) -> int:
        return self._library.fnLSG_GetMinFreq(device_id)

    def get_max_freq(self, device_id: int) -> int:
        return self._library.fnLSG_GetMaxFreq(device_id)

    def get_device_status(self, device_id: int) -> int:
        return self._library.fnLSG_GetDeviceStatus(device_id)

    @classmethod
    def parse_int_answer(cls, answer: int, func, arguments) -> int:
        if answer <= ctypes.c_int(cls.DEVICE_NOT_READY).value:
            raise VNXError("Error executing %s" % func.__name__, answer, arguments)
        return answer


def _test_get_set(really=False):
    """Feel free to turn this into a real test"""

    if not really:
        raise RuntimeError('PLease make shure that your device is not connected to something important')

    api = VNX_LSG_API.default()

    api.set_test_mode(True)

    assert api.get_num_devices() == 2

    for device_id in api.get_dev_info():
        print(api.get_serial_number(device_id),
              api.get_model_name(device_id),
              LSGStatus(api.get_device_status(device_id)))

    for device_id in api.get_dev_info():
        for name, attr in inspect.getmembers(api):
            if inspect.ismethod(attr) and name.startswith('get_'):
                if inspect.getfullargspec(attr).annotations == {'return': int, 'device_id': int}:
                    old_value = attr(device_id)
                    assert isinstance(old_value, int), "%s no int" % name
                    print('tested', name, old_value)

                    set_name = name.replace('get_', 'set_')
                    if set_name in dir(api):
                        setter = getattr(api, set_name)
                        annotations = inspect.getfullargspec(setter).annotations.copy()
                        del annotations['return']
                        del annotations['device_id']

                        set_type = next(iter(annotations.values()))

                        if set_type is int:
                            if old_value < 10:
                                new_value = old_value + 2
                            else:
                                new_value = old_value - 2
                        else:
                            new_value = not old_value

                        try:
                            setter(device_id, new_value)
                        except VNXError as err:
                            if err.args[1] == ctypes.c_int(api.BAD_PARAMETER).value:
                                print('tested', set_name, 'with range error')
                            else:
                                raise
                        else:
                            assert new_value == attr(device_id), "%r != %r" % (new_value, attr(device_id))
                            print('tested', set_name)
