import ctypes
import re
import urllib.request
import tempfile
import os
import zipfile
import platform
import shutil
import logging
from typing import List

from vaunix_api import VNXError

__all__ = ['download_lsg_binaries', 'VNX_LSG_API']


def download_lsg_binaries(target_path=None):
    if target_path is None:
        target_path = os.path.dirname(os.path.realpath(__file__))

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


class VNX_LSG_API:
    """Wrapper for LabBroick Signal Generator API.
    All methods are explicit members for static type checking"""

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

    def __init__(self, library: ctypes.CDLL):
        self._library = library

        self._library.fnLSG_SetTestMode.restype = None
        self._library.fnLSG_SetTestMode.argtypes = (bool,)
        self._library.fnLSG_SetTestMode.errcheck = None

        self._library.fnLSG_GetNumDevices.restype = None
        self._library.fnLSG_GetNumDevices.argtypes = ()
        self._library.fnLSG_GetNumDevices.errcheck = None

        self._library.fnLSG_GetDevInfo.restype = int
        self._library.fnLSG_GetDevInfo.argtypes = (self.DeviceIDArray,)
        self._library.fnLSG_GetDevInfo.errcheck = None

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

        self._library.fnLSG_GetSerialNumber.restype = int
        self._library.fnLSG_GetSerialNumber.argtypes = (self.DEVID,)
        self._library.fnLSG_GetSerialNumber.errcheck = self.parse_int_answer

        self._library.fnLSG_GetDLLVersion.restype = int
        self._library.fnLSG_GetDLLVersion.argtypes = ()
        self._library.fnLSG_GetDLLVersion.errcheck = self.parse_int_answer

        self._library.fnLSG_SetFrequency.restype = int
        self._library.fnLSG_SetFrequency.argtypes = (self.DEVID, int)
        self._library.fnLSG_SetFrequency.errcheck = self.parse_int_answer

        self._library.fnLSG_SetStartFrequency.restype = int
        self._library.fnLSG_SetStartFrequency.argtypes = (self.DEVID, int)
        self._library.fnLSG_SetStartFrequency.errcheck = self.parse_int_answer
        self.set_start_frequency = self._library.fnLSG_SetStartFrequency

        self._library.fnLSG_SetEndFrequency.restype = int
        self._library.fnLSG_SetEndFrequency.argtypes = (self.DEVID, int)
        self._library.fnLSG_SetEndFrequency.errcheck = self.parse_int_answer
        self.set_end_frequency = self._library.fnLSG_SetEndFrequency

        self._library.fnLSG_SetFrequencyStep.restype = int
        self._library.fnLSG_SetFrequencyStep.argtypes = (self.DEVID, int)
        self._library.fnLSG_SetFrequencyStep.errcheck = self.parse_int_answer
        self.set_frequency_step = self._library.fnLSG_SetFrequencyStep

        self._library.fnLSG_SetDwellTime.restype = int
        self._library.fnLSG_SetDwellTime.argtypes = (self.DEVID, int)
        self._library.fnLSG_SetDwellTime.errcheck = self.parse_int_answer
        self.set_dwell_time = self._library.fnLSG_SetDwellTime

        self._library.fnLSG_SetPowerLevel.restype = int
        self._library.fnLSG_SetPowerLevel.argtypes = (self.DEVID, int)
        self._library.fnLSG_SetPowerLevel.errcheck = self.parse_int_answer
        self.set_power_level = self._library.fnLSG_SetPowerLevel

        self._library.fnLSG_SetRFOn.restype = int
        self._library.fnLSG_SetRFOn.argtypes = (self.DEVID, bool)
        self._library.fnLSG_SetRFOn.errcheck = self.parse_int_answer
        self.set_rf_on = self._library.fnLSG_SetRFOn

        self._library.fnLSG_SetUseInternalRef.restype = int
        self._library.fnLSG_SetUseInternalRef.argtypes = (self.DEVID, bool)
        self._library.fnLSG_SetUseInternalRef.errcheck = self.parse_int_answer
        self.set_use_internal_ref = self._library.fnLSG_SetUseInternalRef

        self._library.fnLSG_SetSweepDirection.restype = int
        self._library.fnLSG_SetSweepDirection.argtypes = (self.DEVID, bool)
        self._library.fnLSG_SetSweepDirection.errcheck = self.parse_int_answer
        self.set_sweep_direction = self._library.fnLSG_SetSweepDirection

        self._library.fnLSG_SetSweepMode.restype = int
        self._library.fnLSG_SetSweepMode.argtypes = (self.DEVID, bool)
        self._library.fnLSG_SetSweepMode.errcheck = self.parse_int_answer
        self.set_sweep_mode = self._library.fnLSG_SetSweepMode

        self._library.fnLSG_StartSweep.restype = int
        self._library.fnLSG_StartSweep.argtypes = (self.DEVID, bool)
        self._library.fnLSG_StartSweep.errcheck = self.parse_int_answer
        self.start_sweep = self._library.fnLSG_StartSweep

        self._library.fnLSG_SaveSettings.restype = int
        self._library.fnLSG_SaveSettings.argtypes = (self.DEVID,)
        self._library.fnLSG_SaveSettings.errcheck = self.parse_int_answer
        self.save_settings = self._library.fnLSG_SaveSettings

        # get functions
        self._library.fnLSG_GetFrequency.restype = int
        self._library.fnLSG_GetFrequency.argtypes = (self.DEVID,)
        self._library.fnLSG_GetFrequency.errcheck = self.parse_int_answer
        self.get_frequency = self._library.fnLSG_GetFrequency

        self._library.fnLSG_GetPowerLevel.restype = int
        self._library.fnLSG_GetPowerLevel.argtypes = (self.DEVID,)
        self._library.fnLSG_GetPowerLevel.errcheck = self.parse_int_answer
        self.get_power_level = self._library.fnLSG_GetPowerLevel

        get_functions = [
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
                         'fnLSG_GetMinFreq', ]
        py_name_reg = re.compile(r'(.+?)([A-Z])')

        def to_snake_case(name):
            return py_name_reg.sub(lambda match: match.group(1).lower() + "_" + match.group(2).lower(), name, 0)

        for func_name in get_functions:
            func_ptr = getattr(self._library, func_name)
            func_ptr.restype = int
            func_ptr.argtypes = (self.DEVID,)
            func_ptr.errcheck = self.parse_int_answer

            py_name = to_snake_case(func_name[6:]).replace('__', '_')

            setattr(self, py_name, func_ptr)

    def set_test_mode(self, test_mode: bool):
        self._library.fnLSG_SetTestMode(test_mode)

    def get_dll_version(self):
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

    def set_frequency(self, device_id: int, frequency: int) -> int:
        return self._library.fnLSG_SetFrequency(device_id, frequency)

    def get_frequency(self, device_id: int) -> int:
        return self._library.fnLSG_GetFrequency(device_id)

    def set_power_level(self, device_id, power_level: int):
        return self._library.fnLSG_SetPowerLevel(device_id, power_level)

    def get_power_level(self, device_id: int) -> int:
        return self._library.fnLSG_GetPowerLevel(device_id)

    @classmethod
    def parse_int_answer(cls, answer, func, arguments):
        if answer & cls.ERROR_BIT:
            raise VNXError("Error executing %s" % func.__name__, answer, arguments)
        return answer
