"""Haplugin的二进制传感器平台。"""

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.const import ATTR_FRIENDLY_NAME

# 确保所有导入都在文件开头，不在异步函数中导入
from .const import (
    DOMAIN,
    ATTR_ENTITIES_COUNT,
    ATTR_LAST_PUBLISH,
)

class MqttConnectionBinarySensor(BinarySensorEntity):
    """表示MQTT连接状态的二进制传感器。"""

    def __init__(self, coordinator):
        """初始化MQTT连接传感器。"""
        self.coordinator = coordinator
        self._attr_name = "Haplugin连接状态"
        
        # 使用用户名作为唯一标识，确保每个实例都有不同的实体ID
        username = coordinator.username or "unknown"
        self._attr_unique_id = f"{DOMAIN}_connection_{username}"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        
        # 设置设备信息，使多个实体关联到同一个设备
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.username)},
            "name": "Haplugin 集成",
            "manufacturer": "Haplugin",
            "model": "MQTT 同步网关",
            "sw_version": "1.0",
        }
    
    @property
    def is_on(self):
        """返回传感器的状态。"""
        return self.coordinator.data.get("connected", False)
    
    @property
    def available(self):
        """指示传感器是否可用。"""
        return self.coordinator.last_update_success
    
    @property
    def extra_state_attributes(self):
        """返回额外的状态属性。"""
        data = self.coordinator.data
        return {
            ATTR_FRIENDLY_NAME: self._attr_name,
            ATTR_ENTITIES_COUNT: data.get("entities_count", 0),
            ATTR_LAST_PUBLISH: data.get("last_publish", None),
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
    
    # 添加MQTT连接状态传感器
    async_add_entities([MqttConnectionBinarySensor(coordinator)])