"""Haplugin集成的常量文件。"""

DOMAIN = "haplugin"

# 配置键
CONF_MQTT_URL = "mqtt_url"
CONF_ENTITY_TYPES = "entity_types"
CONF_ENTITIES = "entities"

# MQTT配置
MQTT_RECONNECT_INTERVAL = 5  # 断线后重连间隔，单位：秒
MQTT_COMMAND_TOPIC = "ha2xiaodu/command"  # 订阅的命令主题
MQTT_REPORT_TOPIC = "ha2xiaodu/report"  # 上报状态的主题

# 传感器
ATTR_ENTITIES_COUNT = "entities_count"  # 实体数量属性
ATTR_LAST_PUBLISH = "last_publish"  # 最后发布时间属性

# VIP 相关属性
ATTR_VIP_TYPE = "vip_type"  # VIP 类型
ATTR_VIP_EXPIRE_TIME = "vip_expire_time"  # VIP 到期时间
ATTR_VIP_EXPIRE_TIME_HUMAN = "vip_expire_time_human"  # VIP 到期时间（人类可读格式）

# 全局信号
SIGNAL_MQTT_CONNECTED = f"{DOMAIN}_mqtt_connected"
SIGNAL_MQTT_DISCONNECTED = f"{DOMAIN}_mqtt_disconnected"

# 固定路由
CONST_POST_CHANGE_STATE_URL = "/api/device/change_state"
CONST_POST_SYNC_DEVICE_URL = "/api/device/sync_entity_v1"

# 最大队列长度
MAX_QUEUE_SIZE = 3000

# 受支持的实体类型
SUPPORTED_ENTITY_TYPES = [
    {
        "value": "automation",
        "name": "自动化(automation)"
    },
    {
        "value": "button",
        "name": "按钮(button)"
    },
    {
        "value": "climate",
        "name": "空调/恒温器(climate)"
    },
    {
        "value": "fan",
        "name": "风扇(fan)"
    },
    {
        "value": "cover",
        "name": "窗帘/门(cover)"
    },
    {
        "value": "input_button",
        "name": "输入按钮(input_button)"
    },
    {
        "value": "light",
        "name": "灯光(light)"
    },
    {
        "value": "scene",
        "name": "场景(scene)"
    },
    {
        "value": "script",
        "name": "脚本(script)"
    },
    {
        "value": "switch",
        "name": "开关(switch)"
    },
    {
        "value": "water_heater",
        "name": "热水器(water_heater)"
    }
]