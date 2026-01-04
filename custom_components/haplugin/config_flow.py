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
    SUPPORTED_ENTITY_TYPES,
)

_LOGGER = logging.getLogger(__name__)

# 全选选项的前缀
SELECT_ALL_PREFIX = "__select_all__"


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
            selected = user_input.get(CONF_ENTITIES, [])
            
            # 处理全选逻辑
            select_all_key = f"{SELECT_ALL_PREFIX}{current_type}"
            if select_all_key in selected:
                # 获取该类型的所有实体
                all_entities = await self._get_entities_for_single_type(current_type)
                selected = [e["value"] for e in all_entities if e["value"]]
            else:
                # 移除可能误选的全选项
                selected = [e for e in selected if not e.startswith(SELECT_ALL_PREFIX)]
            
            # 保存当前类型的选择
            self._selected_entities[current_type] = selected
            
            # 移动到下一个类型
            self._current_type_index += 1
            
            if self._current_type_index >= len(self._entity_types):
                # 所有类型都选择完毕，完成配置
                return await self._process_final_entities()
            else:
                # 继续选择下一个类型
                return await self._async_step_select_type_entities()
        
        # 获取当前类型的实体列表
        entities = await self._get_entities_for_single_type(current_type)
        
        # 在列表开头添加"全选"选项
        select_all_option = {
            "value": f"{SELECT_ALL_PREFIX}{current_type}",
            "label": f"✅ 全选所有{type_name} ({len(entities)}个)"
        }
        
        options = [select_all_option] + entities
        
        # 获取当前类型已选择的实体（用于编辑模式）
        current_selected = self._selected_entities.get(current_type, [])
        
        # 计算进度信息
        progress = f"({self._current_type_index + 1}/{len(self._entity_types)})"
        
        return self.async_show_form(
            step_id="select_entities",
            data_schema=vol.Schema({
                vol.Optional(CONF_ENTITIES, default=current_selected if current_selected else None): 
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
            }),
            errors=errors,
            description_placeholders={
                "type_name": type_name,
                "progress": progress,
                "count": str(len(entities)),
            },
        )
    
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
            CONF_ENTITY_TYPES: self._entity_types,
        }
        
    def _generate_title(self):
        """根据配置生成一个有意义的集成条目标题。"""
        if self._mqtt_url:
            return f"Haplugin-{self._mqtt_url}"
        else:
            return "Haplugin"


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
        # 检查是否已经存在配置项
        existing_entries = self.hass.config_entries.async_entries(DOMAIN)
        if existing_entries:
            # 如果已经存在配置项，显示单配置提示
            return self.async_abort(reason="single_config_only")
        
        return await self.async_step_mqtt_url(user_input)

    async def async_step_mqtt_url(self, user_input=None):
        """处理MQTT URL配置步骤。"""
        errors = {}

        if user_input is not None:
            base64_str = user_input[CONF_MQTT_URL]
            
            try:
                decoded_bytes = base64.b64decode(base64_str)
                json_str = decoded_bytes.decode('utf-8')
                config_data = json.loads(json_str)
                
                self._mqtt_url = config_data.get("mqtt_url")
                self._mqtt_port = config_data.get("port")
                self._web_url = config_data.get("web_url")
                self._username = config_data.get("username")
                self._password = config_data.get("password")
                
                if not self._mqtt_url or not self._mqtt_port or not self._web_url or not self._username or not self._password:
                    errors["mqtt_url"] = "invalid_mqtt_url"
                    _LOGGER.error("缺少必要的MQTT连接参数: mqtt_url=%s, port=%s", 
                                  self._mqtt_url, self._mqtt_port)
                else:
                    if _LOGGER.isEnabledFor(logging.INFO):
                        _LOGGER.info("成功解析MQTT连接信息: %s:%s", self._mqtt_url, self._mqtt_port)
                    
                    return await self.async_step_entity_types()
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
                decoded_bytes = base64.b64decode(base64_str)
                json_str = decoded_bytes.decode('utf-8')
                config_data = json.loads(json_str)
                
                new_mqtt_url = config_data.get("mqtt_url")
                new_mqtt_port = config_data.get("port")
                new_web_url = config_data.get("web_url")
                new_username = config_data.get("username")
                new_password = config_data.get("password")
                
                if not new_mqtt_url or not new_mqtt_port or not new_web_url or not new_username or not new_password:
                    errors["mqtt_url"] = "invalid_mqtt_url"
                    _LOGGER.error("缺少必要的MQTT连接参数: mqtt_url=%s, port=%s", 
                                  new_mqtt_url, new_mqtt_port)
                else:
                    # 更新连接信息
                    self._mqtt_url = new_mqtt_url
                    self._mqtt_port = new_mqtt_port
                    self._web_url = new_web_url
                    self._username = new_username
                    self._password = new_password
                    
                    # 保存更新后的配置（保留原有的实体选择）
                    new_data = self._get_connection_data()
                    new_data[CONF_ENTITIES] = self._original_entities
                    
                    self.hass.config_entries.async_update_entry(
                        self._config_entry, data=new_data
                    )
                    
                    _LOGGER.info("Token已更新: %s:%s", self._mqtt_url, self._mqtt_port)
                    return self.async_create_entry(title="", data={})
                    
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
        
        self.hass.config_entries.async_update_entry(
            self._config_entry, data=new_data
        )
        return self.async_create_entry(title="", data={})