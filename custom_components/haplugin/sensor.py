"""Haplugin的传感器平台。"""

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import ATTR_FRIENDLY_NAME

from .const import (
    DOMAIN,
    CONF_DEVICE_UID,
    ATTR_VIP_TYPE,
    ATTR_VIP_EXPIRE_TIME,
    ATTR_VIP_EXPIRE_TIME_HUMAN,
)


from datetime import datetime
import pytz
from homeassistant.util import dt as dt_util

def _get_device_uid(config_entry: ConfigEntry) -> str:
    """Return the stable device identifier for this config entry."""
    return config_entry.data.get(CONF_DEVICE_UID) or config_entry.entry_id


class VipExpireTimeSensor(SensorEntity):
    """表示VIP到期时间的传感器。"""

    def __init__(self, coordinator, config_entry: ConfigEntry):
        """初始化VIP到期时间传感器。"""
        self.coordinator = coordinator
        self._attr_name = "Haplugin VIP到期时间"

        device_uid = _get_device_uid(config_entry)
        self._attr_unique_id = f"{DOMAIN}_vip_expire_{device_uid}"
        # 设置设备类为时间
        self._attr_device_class = "timestamp"
        # 对于timestamp类型的传感器，不应设置state_class

        # 设置设备信息，使多个实体关联到同一个设备
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_uid)},
            "name": "Haplugin 集成",
            "manufacturer": "Haplugin",
            "model": "MQTT 同步网关",
            "sw_version": "1.0",
        }

    @property
    def native_value(self):
        """返回传感器的原始值。"""
        # 获取整数时间戳并转换为带时区的datetime对象
        timestamp = self.coordinator.data.get(ATTR_VIP_EXPIRE_TIME)
        if timestamp is not None:
            # 转换为带时区的datetime对象，使用Home Assistant的时区
            dt = datetime.fromtimestamp(timestamp)
            # 添加时区信息，使用系统默认时区
            return dt_util.as_local(dt)
        return None

    @property
    def available(self):
        """指示传感器是否可用。"""
        # 只有当有VIP到期时间数据且coordinator更新成功时才可用
        return (self.coordinator.last_update_success and
                self.coordinator.data.get(ATTR_VIP_EXPIRE_TIME) is not None)

    @property
    def extra_state_attributes(self):
        """返回额外的状态属性。"""
        data = self.coordinator.data
        return {
            ATTR_FRIENDLY_NAME: self._attr_name,
            ATTR_VIP_TYPE: data.get(ATTR_VIP_TYPE),
            ATTR_VIP_EXPIRE_TIME_HUMAN: data.get(ATTR_VIP_EXPIRE_TIME_HUMAN),
        }

    async def async_added_to_hass(self):
        """当实体被添加到Home Assistant时调用。"""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self):
        """更新传感器状态。"""
        await self.coordinator.async_request_refresh()


class VipTypeSensor(SensorEntity):
    """表示VIP类型的传感器。"""

    def __init__(self, coordinator, config_entry: ConfigEntry):
        """初始化VIP类型传感器。"""
        self.coordinator = coordinator
        self._attr_name = "Haplugin VIP类型"

        device_uid = _get_device_uid(config_entry)
        self._attr_unique_id = f"{DOMAIN}_vip_type_{device_uid}"
        # 对于字符串类型的传感器，不应设置state_class

        # 设置设备信息，使多个实体关联到同一个设备
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_uid)},
            "name": "Haplugin 集成",
            "manufacturer": "Haplugin",
            "model": "MQTT 同步网关",
            "sw_version": "1.0",
        }

    @property
    def native_value(self):
        """返回传感器的原始值。"""
        # 返回VIP类型
        vip_type = self.coordinator.data.get(ATTR_VIP_TYPE)
        # 转换英文类型为中文显示
        if vip_type == "pro":
            return "专业版"
        elif vip_type == "premium":
            return "高级版"
        elif vip_type == "basic":
            return "基础版"
        return vip_type

    @property
    def available(self):
        """指示传感器是否可用。"""
        # 只有当有VIP类型数据且coordinator更新成功时才可用
        return (self.coordinator.last_update_success and
                self.coordinator.data.get(ATTR_VIP_TYPE) is not None)

    @property
    def extra_state_attributes(self):
        """返回额外的状态属性。"""
        data = self.coordinator.data
        return {
            ATTR_FRIENDLY_NAME: self._attr_name,
            ATTR_VIP_EXPIRE_TIME: data.get(ATTR_VIP_EXPIRE_TIME),
            ATTR_VIP_EXPIRE_TIME_HUMAN: data.get(ATTR_VIP_EXPIRE_TIME_HUMAN),
        }

    async def async_added_to_hass(self):
        """当实体被添加到Home Assistant时调用。"""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self):
        """更新传感器状态。"""
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """设置从配置项添加的传感器。"""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    # 添加VIP相关传感器
    async_add_entities([
        VipExpireTimeSensor(coordinator, config_entry),
        VipTypeSensor(coordinator, config_entry)
    ])
