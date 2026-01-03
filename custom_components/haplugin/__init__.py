"""Haplugin组件。"""

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    CONF_ENTITIES,
)
from .coordinator import MqttSyncCoordinator

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

# 此集成支持的平台
PLATFORMS = ["binary_sensor", "sensor"]

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """设置Haplugin组件。"""
    hass.data[DOMAIN] = {}
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """设置Haplugin组件。"""
    # 从配置中获取数据
    mqtt_url = entry.data.get("mqtt_url")
    mqtt_port = entry.data.get("mqtt_port")
    username = entry.data.get("username")
    password = entry.data.get("password")
    web_url = entry.data.get("web_url")
    entities = entry.data.get(CONF_ENTITIES, [])
    
    # 创建coordinator
    coordinator = MqttSyncCoordinator(
        hass,
        mqtt_url,
        mqtt_port,
        username,
        password,
        web_url,
        entities
    )
    
    # 初始化coordinator
    await coordinator.async_config_entry_first_refresh()
    
    # 存储coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    # 设置平台，使用新的API
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # 注册更新监听器
    entry.async_on_unload(entry.add_update_listener(update_listener))
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载Haplugin配置项。"""
    # 卸载平台，使用新的API
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # 获取coordinator并关闭
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    
    return unload_ok

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """处理配置项更新。"""
    await hass.config_entries.async_reload(entry.entry_id)