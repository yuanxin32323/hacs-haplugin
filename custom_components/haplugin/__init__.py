"""Haplugin组件。"""

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    CONF_ENTITIES,
    CONF_DEVICE_UID,
)
from .coordinator import MqttSyncCoordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

# 此集成支持的平台
PLATFORMS = ["binary_sensor", "sensor"]

ENTITY_REGISTRY_MIGRATIONS = (
    ("binary_sensor", f"{DOMAIN}_connection_", f"{DOMAIN}_connection"),
    ("sensor", f"{DOMAIN}_vip_expire_", f"{DOMAIN}_vip_expire"),
    ("sensor", f"{DOMAIN}_vip_type_", f"{DOMAIN}_vip_type"),
)

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
    device_uid = entry.data.get(CONF_DEVICE_UID) or entry.entry_id

    if entry.data.get(CONF_DEVICE_UID) != device_uid:
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_DEVICE_UID: device_uid,
            },
        )

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
    _migrate_legacy_registry_entries(hass, entry, username, device_uid)

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


def _migrate_legacy_registry_entries(
    hass: HomeAssistant,
    entry: ConfigEntry,
    username: str | None,
    device_uid: str,
) -> None:
    """Collapse legacy username-based registry rows into one stable device."""
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    stable_identifier = (DOMAIN, device_uid)
    kept_device_id = None

    for platform, legacy_prefix, stable_prefix in ENTITY_REGISTRY_MIGRATIONS:
        stable_unique_id = f"{stable_prefix}_{device_uid}"
        legacy_current_unique_id = (
            f"{legacy_prefix}{username}" if username else None
        )
        candidates = [
            item
            for item in entity_registry.entities.values()
            if item.platform == DOMAIN
            and item.domain == platform
            and _registry_entry_belongs_to_config_entry(item, entry)
            and (
                item.unique_id == stable_unique_id
                or (
                    legacy_current_unique_id
                    and item.unique_id == legacy_current_unique_id
                )
            )
        ]

        if not candidates:
            continue

        _LOGGER.info(
            "Migrating %s registry entries for %s to stable id %s",
            len(candidates),
            stable_prefix,
            stable_unique_id,
        )

        keeper = next(
            (item for item in candidates if item.unique_id == stable_unique_id),
            None,
        )
        if keeper is None and legacy_current_unique_id:
            keeper = next(
                (item for item in candidates if item.unique_id == legacy_current_unique_id),
                None,
            )
        if keeper is None:
            keeper = candidates[0]

        if keeper.unique_id != stable_unique_id:
            try:
                keeper = entity_registry.async_update_entity(
                    keeper.entity_id,
                    new_unique_id=stable_unique_id,
                )
            except ValueError:
                keeper = next(
                    (
                        item
                        for item in entity_registry.entities.values()
                        if item.platform == DOMAIN
                        and item.domain == platform
                        and _registry_entry_belongs_to_config_entry(item, entry)
                        and item.unique_id == stable_unique_id
                    ),
                    keeper,
                )

        if keeper.device_id:
            kept_device_id = keeper.device_id

        for item in candidates:
            if item.entity_id != keeper.entity_id:
                entity_registry.async_remove(item.entity_id)

    candidate_devices = [
        device
        for device in device_registry.devices.values()
        if entry.entry_id in device.config_entries
        and any(identifier[0] == DOMAIN for identifier in device.identifiers)
    ]
    if not candidate_devices:
        return

    keep_device = next(
        (
            device
            for device in candidate_devices
            if stable_identifier in device.identifiers
        ),
        None,
    )
    if keep_device is None and kept_device_id:
        keep_device = next(
            (device for device in candidate_devices if device.id == kept_device_id),
            None,
        )
    if keep_device is None and username:
        keep_device = next(
            (
                device
                for device in candidate_devices
                if (DOMAIN, username) in device.identifiers
            ),
            None,
        )
    if keep_device is None:
        keep_device = candidate_devices[0]

    if keep_device.identifiers != {stable_identifier}:
        device_registry.async_update_device(
            keep_device.id,
            new_identifiers={stable_identifier},
        )

    referenced_device_ids = {
        item.device_id
        for item in entity_registry.entities.values()
        if item.platform == DOMAIN
        and item.device_id
    }

    for device in candidate_devices:
        if device.id == keep_device.id or device.id in referenced_device_ids:
            continue
        device_registry.async_remove_device(device.id)


def _registry_entry_belongs_to_config_entry(item, entry: ConfigEntry) -> bool:
    """Return whether a registry entity belongs to the config entry being migrated."""
    config_entry_id = getattr(item, "config_entry_id", None)
    return config_entry_id in (None, entry.entry_id)
