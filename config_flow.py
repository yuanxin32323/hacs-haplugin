"""MQTT同步配置流程。"""
import logging
import json
import base64
import voluptuous as vol
from typing import List, Dict, Any

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_MQTT_URL,
    CONF_ENTITY_TYPES,
    CONF_ENTITIES,
    CONF_DEVICE_UID,
    CONF_MOBILE_MASKED,
    SUPPORTED_ENTITY_TYPES,
)

_LOGGER = logging.getLogger(__name__)

class MqttSyncFlowMixin:
    """MQTT同步配置流程的共享逻辑混合类。"""

    def __init__(self):
        """初始化混合类。"""
        self._entity_types = []
        self._current_type_index = 0  # 当前正在选择的实体类型索引
        self._selected_entities = {}  # 每个类型已选择的实体 {type: [entities]}
        self._mqtt_url = None
        self._mqtt_port = None
        self._web_url = None
        self._username = None
        self._password = None
        self._mobile_masked = None

    async def _async_handle_entity_types_step(self, user_input, current_types=None):
        """处理实体类型选择步骤的共享逻辑。"""
        errors = {}

        if user_input is not None:
            entity_types = user_input.get(CONF_ENTITY_TYPES, [])

            if not entity_types or len(entity_types) == 0:
                errors["entity_types"] = "no_entity_types_selected"
            else:
                self._entity_types = entity_types
                self._current_type_index = 0
                # 保留那些仍在新选择的实体类型中的已选实体（用于编辑模式）
                self._selected_entities = {
                    k: v for k, v in self._selected_entities.items()
                    if k in entity_types
                }
                # 进入第一个类型的实体选择
                return await self._async_step_select_type_entities()

        return self.async_show_form(
            step_id=CONF_ENTITY_TYPES,
            data_schema=self._create_entity_types_schema(current_types),
            errors=errors,
        )

    async def _async_step_select_type_entities(self, user_input=None):
        """处理单个实体类型的设备选择步骤。"""
        errors = {}

        # 获取当前要处理的实体类型
        current_type = self._entity_types[self._current_type_index]
        type_name = self._get_type_display_name(current_type)

        if user_input is not None:
            selected = user_input.get(CONF_ENTITIES, []) or []
            if isinstance(selected, str):
                selected = [selected]

            selected = [
                entity_id
                for entity_id in selected
                if entity_id.split(".")[0] == current_type
            ]

            selected = self._merge_hidden_existing_entities(current_type, selected)

            if not selected:
                errors[CONF_ENTITIES] = "no_entities_selected"
            else:
                # 保存当前类型的选择
                self._selected_entities[current_type] = self._dedupe_entities(selected)

                # 移动到下一个类型
                self._current_type_index += 1

                if self._current_type_index >= len(self._entity_types):
                    # 所有类型都选择完毕，完成配置
                    return await self._process_final_entities()
                else:
                    # 继续选择下一个类型
                    return await self._async_step_select_type_entities()

        # 获取当前类型的实体列表
        entity_ids = self._get_entity_ids_for_type(current_type)
        entity_count = len(entity_ids)

        # 获取当前类型已选择的实体（用于编辑模式）
        current_selected = self._selected_entities.get(current_type, [])
        current_selected_for_type = [
            entity_id
            for entity_id in current_selected
            if entity_id.split(".")[0] == current_type and entity_id in entity_ids
        ]

        # 计算进度信息
        progress = f"({self._current_type_index + 1}/{len(self._entity_types)})"

        return self.async_show_form(
            step_id="select_entities",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_ENTITIES,
                    default=current_selected_for_type,
                ):
                    selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            multiple=True,
                            domain=current_type,
                        )
                    ),
            }),
            errors=errors,
            description_placeholders={
                "type_name": type_name,
                "progress": progress,
                "count": str(entity_count),
            },
        )

    def _dedupe_entities(self, entities: List[str]) -> List[str]:
        """按原顺序去重实体ID。"""
        seen = set()
        deduped = []
        for entity_id in entities:
            if entity_id in seen:
                continue
            seen.add(entity_id)
            deduped.append(entity_id)
        return deduped

    def _merge_hidden_existing_entities(self, entity_type: str, selected: List[str]) -> List[str]:
        """保留编辑页没有展示出来的旧实体，避免保存时意外丢失。"""
        current_entity_ids = set(self._get_entity_ids_for_type(entity_type))
        hidden_existing = [
            entity_id
            for entity_id in self._selected_entities.get(entity_type, [])
            if entity_id.split(".")[0] == entity_type
            and entity_id not in current_entity_ids
        ]
        return self._dedupe_entities([*selected, *hidden_existing])

    async def _process_final_entities(self):
        """处理最终选择的实体列表，由子类实现具体逻辑。"""
        raise NotImplementedError("子类必须实现此方法")

    async def _get_entities_for_single_type(self, entity_type: str) -> List[Dict[str, str]]:
        """获取单个类型的实体列表。"""
        entities = []

        all_states = self.hass.states.async_all()

        domain_states = [
            state for state in all_states
            if state.entity_id.split('.')[0] == entity_type
        ]

        for state in domain_states:
            entity_id = state.entity_id
            friendly_name = state.attributes.get("friendly_name", entity_id)
            entity_item = {"value": entity_id, "label": f"{friendly_name} ({entity_id})"}
            entities.append(entity_item)

        return entities

    def _get_entity_ids_for_type(self, entity_type: str) -> List[str]:
        """获取单个类型的实体ID列表。"""
        return [
            state.entity_id
            for state in self.hass.states.async_all()
            if state.entity_id.split(".")[0] == entity_type
        ]

    def _get_type_display_name(self, entity_type: str) -> str:
        """获取实体类型的显示名称。"""
        for type_info in SUPPORTED_ENTITY_TYPES:
            if type_info["value"] == entity_type:
                return type_info["name"]
        return entity_type

    def _get_all_selected_entities(self) -> List[str]:
        """获取所有选中的实体ID列表。"""
        all_entities = []
        for entities in self._selected_entities.values():
            all_entities.extend(entities)
        return all_entities

    def _create_entity_types_schema(self, default_types=None):
        """创建实体类型选择的Schema。"""

        entity_type_options = [
            {"value": entity_type["value"], "label": entity_type["name"]}
            for entity_type in SUPPORTED_ENTITY_TYPES
        ]

        schema_key = vol.Optional(
            CONF_ENTITY_TYPES,
            default=default_types if default_types else None
        )

        return vol.Schema({
            schema_key: selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=entity_type_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
        })

    async def _get_entities_for_types(self, entity_types: List[str]):
        """根据实体类型获取实体列表（保留兼容性）。"""
        entities = []

        all_states = self.hass.states.async_all()

        for entity_type in entity_types:
            domain_states = [
                state for state in all_states
                if state.entity_id.split('.')[0] == entity_type
            ]

            for state in domain_states:
                entity_id = state.entity_id
                friendly_name = state.attributes.get("friendly_name", entity_id)
                entity_item = {"value": entity_id, "label": f"{friendly_name} ({entity_id})"}
                entities.append(entity_item)

        if not entities:
            entities = [{"value": "", "label": "未找到匹配的实体"}]

        return entities

    def _get_connection_data(self):
        """获取连接数据字典。"""
        return {
            "mqtt_url": self._mqtt_url,
            "mqtt_port": self._mqtt_port,
            "web_url": self._web_url,
            "username": self._username,
            "password": self._password,
            CONF_MOBILE_MASKED: self._mobile_masked,
            CONF_ENTITY_TYPES: self._entity_types,
        }

    def _generate_title(self):
        """根据配置生成一个有意义的集成条目标题。"""
        if self._mobile_masked:
            return f"Haplugin-{self._mobile_masked}"
        if self._username:
            return f"Haplugin-{self._username}"
        if self._mqtt_url:
            return f"Haplugin-{self._mqtt_url}"
        return "Haplugin"

    def _decode_token_config(self, token: str) -> Dict[str, Any]:
        """解析并校验网站生成的Token内容。"""
        token = (token or "").strip()
        if not token:
            raise ValueError("empty token")

        padding = "=" * (-len(token) % 4)
        decoded_bytes = base64.b64decode(token + padding)
        json_str = decoded_bytes.decode("utf-8")
        config_data = json.loads(json_str)

        if not isinstance(config_data, dict):
            raise ValueError("token payload is not object")

        required_keys = ("mqtt_url", "port", "web_url", "username", "password")
        if any(not config_data.get(key) for key in required_keys):
            raise ValueError("missing required token fields")

        return config_data

    def _set_connection_data_from_token(self, config_data: Dict[str, Any]) -> None:
        """将Token中的连接信息写入当前流程状态。"""
        self._mqtt_url = config_data.get("mqtt_url")
        self._mqtt_port = config_data.get("port")
        self._web_url = config_data.get("web_url")
        self._username = config_data.get("username")
        self._password = config_data.get("password")
        self._mobile_masked = config_data.get(CONF_MOBILE_MASKED)

    def _get_token_unique_key(self, username=None, web_url=None) -> str:
        """返回用于区分Token配置项的唯一键。"""
        username = username if username is not None else self._username
        web_url = web_url if web_url is not None else self._web_url
        return f"{str(web_url or '').rstrip('/')}|{username or ''}"

    def _is_token_configured(
        self,
        username: str,
        web_url: str,
        ignore_entry_id: str | None = None,
    ) -> bool:
        """判断同一个Token身份是否已经存在配置项。"""
        token_key = self._get_token_unique_key(username, web_url)
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if ignore_entry_id and entry.entry_id == ignore_entry_id:
                continue
            if self._get_token_unique_key(
                entry.data.get("username"),
                entry.data.get("web_url"),
            ) == token_key:
                return True
        return False


class MqttSyncFlowHandler(config_entries.ConfigFlow, MqttSyncFlowMixin, domain=DOMAIN):
    """处理MQTT同步配置流程。"""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_PUSH

    def __init__(self):
        """初始化配置流程。"""
        super().__init__()
        MqttSyncFlowMixin.__init__(self)
        self._entities = []

    async def async_step_user(self, user_input=None):
        """处理用户步骤，这是配置流程的入口点。

        直接跳转到MQTT URL配置步骤。
        """
        return await self.async_step_mqtt_url(user_input)

    async def async_step_mqtt_url(self, user_input=None):
        """处理MQTT URL配置步骤。"""
        errors = {}

        if user_input is not None:
            base64_str = user_input[CONF_MQTT_URL]

            try:
                config_data = self._decode_token_config(base64_str)
                self._set_connection_data_from_token(config_data)

                if self._is_token_configured(self._username, self._web_url):
                    errors["mqtt_url"] = "token_already_configured"
                else:
                    await self.async_set_unique_id(self._get_token_unique_key())

                    if _LOGGER.isEnabledFor(logging.INFO):
                        _LOGGER.info("成功解析MQTT连接信息: %s:%s", self._mqtt_url, self._mqtt_port)

                    return await self.async_step_entity_types()
            except ValueError as e:
                _LOGGER.error("Token校验失败: %s", str(e))
                errors["mqtt_url"] = "invalid_mqtt_url"
            except Exception as e:
                _LOGGER.error("解析Token失败: %s", str(e))
                errors["mqtt_url"] = "invalid_user_token"

        return self.async_show_form(
            step_id=CONF_MQTT_URL,
            data_schema=vol.Schema({
                vol.Required(CONF_MQTT_URL): str,
            }),
            errors=errors,
        )

    async def async_step_entity_types(self, user_input=None):
        """处理实体类型选择步骤。"""
        return await self._async_handle_entity_types_step(user_input)

    async def async_step_select_entities(self, user_input=None):
        """处理分步实体选择步骤。"""
        return await self._async_step_select_type_entities(user_input)

    async def _process_final_entities(self):
        """处理最终选择的实体列表，创建配置条目。"""
        all_entities = self._get_all_selected_entities()

        if not all_entities:
            # 如果没有选择任何实体，返回错误
            self._current_type_index = 0
            return await self._async_step_select_type_entities()

        data = self._get_connection_data()
        data[CONF_ENTITIES] = all_entities

        title = self._generate_title()

        return self.async_create_entry(title=title, data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """获取选项流程。"""
        return MqttSyncOptionsFlowHandler(config_entry)


class MqttSyncOptionsFlowHandler(config_entries.OptionsFlow, MqttSyncFlowMixin):
    """处理MQTT同步选项流程。"""

    def __init__(self, config_entry):
        """初始化选项处理程序。"""
        super().__init__()
        MqttSyncFlowMixin.__init__(self)

        # 保存config_entry引用
        self._config_entry = config_entry

        data = config_entry.data
        self._entity_types = data.get(CONF_ENTITY_TYPES, [])
        self._mqtt_url = data.get("mqtt_url")
        self._mqtt_port = data.get("mqtt_port")
        self._web_url = data.get("web_url")
        self._username = data.get("username")
        self._password = data.get("password")
        self._mobile_masked = data.get(CONF_MOBILE_MASKED)

        # 生成当前token的base64编码，用于显示
        self._current_token = self._generate_token_base64()

        # 从现有配置中恢复已选择的实体
        existing_entities = data.get(CONF_ENTITIES, [])
        self._init_selected_entities_from_list(existing_entities)

        # 保存原始实体列表，用于仅修改Token时保留设备选择
        self._original_entities = existing_entities

    def _generate_token_base64(self) -> str:
        """根据当前配置生成token的base64编码。"""
        try:
            token_data = {
                "mqtt_url": self._mqtt_url,
                "port": self._mqtt_port,
                "web_url": self._web_url,
                "username": self._username,
                "password": self._password,
                CONF_MOBILE_MASKED: self._mobile_masked,
            }
            json_str = json.dumps(token_data)
            return base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
        except Exception:
            return ""

    def _init_selected_entities_from_list(self, entities: List[str]):
        """从实体列表初始化已选择的实体字典。"""
        self._selected_entities = {}
        for entity_id in entities:
            entity_type = entity_id.split('.')[0]
            if entity_type not in self._selected_entities:
                self._selected_entities[entity_type] = []
            self._selected_entities[entity_type].append(entity_id)

    async def async_step_init(self, user_input=None):
        """处理初始步骤，显示选项菜单。"""
        if user_input is not None:
            action = user_input.get("action")
            if action == "modify_token":
                return await self.async_step_modify_token()
            elif action == "modify_entities":
                return await self.async_step_entity_types()

        # 显示选项菜单
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("action", default="modify_entities"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "modify_token", "label": "🔑 修改Token"},
                            {"value": "modify_entities", "label": "📱 修改同步设备"},
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }),
        )

    async def async_step_modify_token(self, user_input=None):
        """处理修改Token步骤。"""
        errors = {}

        if user_input is not None:
            base64_str = user_input.get(CONF_MQTT_URL)

            try:
                config_data = self._decode_token_config(base64_str)
                new_username = config_data.get("username")
                new_web_url = config_data.get("web_url")

                if self._is_token_configured(
                    new_username,
                    new_web_url,
                    ignore_entry_id=self._config_entry.entry_id,
                ):
                    errors["mqtt_url"] = "token_already_configured"
                else:
                    # 更新连接信息
                    self._set_connection_data_from_token(config_data)

                    # 保存更新后的配置（保留原有的实体选择）
                    new_data = self._get_connection_data()
                    new_data[CONF_ENTITIES] = self._original_entities
                    new_data[CONF_DEVICE_UID] = (
                        self._config_entry.data.get(CONF_DEVICE_UID)
                        or self._config_entry.entry_id
                    )

                    self.hass.config_entries.async_update_entry(
                        self._config_entry,
                        title=self._generate_title(),
                        data=new_data
                    )

                    _LOGGER.info("Token已更新: %s:%s", self._mqtt_url, self._mqtt_port)
                    return self.async_create_entry(title="", data={})

            except ValueError as e:
                _LOGGER.error("Token校验失败: %s", str(e))
                errors["mqtt_url"] = "invalid_mqtt_url"
            except Exception as e:
                _LOGGER.error("解析Token失败: %s", str(e))
                errors["mqtt_url"] = "invalid_user_token"

        return self.async_show_form(
            step_id="modify_token",
            data_schema=vol.Schema({
                vol.Required(CONF_MQTT_URL, default=self._current_token): str,
            }),
            errors=errors,
        )

    async def async_step_entity_types(self, user_input=None):
        """处理实体类型选择步骤。"""
        return await self._async_handle_entity_types_step(user_input, self._entity_types)

    async def async_step_select_entities(self, user_input=None):
        """处理分步实体选择步骤。"""
        return await self._async_step_select_type_entities(user_input)

    async def _process_final_entities(self):
        """处理最终选择的实体列表，更新配置条目。"""
        all_entities = self._get_all_selected_entities()

        if not all_entities:
            # 如果没有选择任何实体，返回错误
            self._current_type_index = 0
            return await self._async_step_select_type_entities()

        new_data = self._get_connection_data()
        new_data[CONF_ENTITIES] = all_entities
        new_data[CONF_DEVICE_UID] = (
            self._config_entry.data.get(CONF_DEVICE_UID)
            or self._config_entry.entry_id
        )

        self.hass.config_entries.async_update_entry(
            self._config_entry, data=new_data
        )
        return self.async_create_entry(title="", data={})
