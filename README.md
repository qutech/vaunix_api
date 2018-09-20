# Vaunix API

This is a small package to download and wrap the C library of LabBrick signal generators.
It can be extended for other LabBrick devices.

```
pip install vaunix_api
```

The required binaries can be downloaded via `vaunix_api.lsg.download_lsg_binaries()`.

Example:
```python
import vaunix_api.lsg as lsg

api = lsg.VNX_LSG_API.default()

# necessary to refresh device list
api.get_num_devices()

for device_id in api.get_dev_info():
    print(api.get_serial_number(device_id),
          api.get_model_name(device_id),
          lsg.LSGStatus(api.get_device_status(device_id)))
```
