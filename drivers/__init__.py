from .light_coxe import CoxeLightDriver
from .light_niren_poe_kp import NirenPoeKpRelayDriver
from .light_rf_tcp import RfTcpLightDriver
from .power_adapter import PowerCabinetDriver


def create_device(device_config):
    device_type = device_config.get("type", "power")
    brand = str(device_config.get("brand", "UNKNOWN") or "UNKNOWN").upper()

    if device_type == "light":
        if brand == "COXE":
            return CoxeLightDriver(device_config)
        if brand in {"NIREN_POE_KP", "POE_KP_I101"}:
            return NirenPoeKpRelayDriver(device_config)
        if brand == "RF_TCP":
            return RfTcpLightDriver(device_config)

    if device_type == "power":
        return PowerCabinetDriver(device_config)

    raise ValueError(f"未知的设备类型或品牌: type={device_type}, brand={brand}")
