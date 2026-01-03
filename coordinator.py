"""Haplugin协调器模块。"""
import asyncio
import json
import logging
import datetime
import aiohttp
from typing import List, Optional
import paho.mqtt.client as mqtt

from homeassistant.core import HomeAssistant, callback, State
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.const import (
    EVENT_STATE_CHANGED,
    EVENT_HOMEASSISTANT_STOP,
)

from .const import *

_LOGGER = logging.getLogger(__name__)

class MqttSyncCoordinator(DataUpdateCoordinator):
    """Haplugin协调器，管理MQTT连接和实体状态。"""

    def __init__(
        self, 
        hass: HomeAssistant,
        mqtt_url: str,
        mqtt_port: int,
        username: str,
        password: str,
        web_url: str,
        entities: List[str]
    ):
        """初始化Haplugin协调器。"""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # 我们不需要周期性更新
        )
        self.hass = hass
        self.mqtt_url = mqtt_url
        # 确保端口是整数
        self.mqtt_port = int(mqtt_port) if mqtt_port else 1883
        self.username = username  # 用于MQTT连接和API调用的用户名
        self.password = password  # 用于MQTT连接和API调用的密码
        self.web_url = web_url    # Web服务器URL，用于API调用
        self.entities = entities  # 用于监听和同步的实体列表
        self.client_id = f"ha-xiaodu-{self.username}"
        self._connected = False
        self._last_publish = None
        self._unsub_state_listener = None
        self._unsub_stop_listener = None
        self._reconnect_task = None
        self._reconnect_attempt = 0
        self._mqtt_client = None  # 直接使用Paho MQTT客户端
        self._manual_disconnect = False  # 是否是手动断开连接
        
        # VIP相关信息
        self._vip_type = None
        self._vip_expire_time = None
        
        # 创建消息队列和处理任务
        self._message_queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self._queue_processor_task = None
        self._processing = False
        self._messages_processed = 0
        self._messages_failed = 0
    
    async def _async_update_data(self):
        """获取最新数据。"""
        # 格式化VIP到期时间为人类可读格式
        vip_expire_time_human = None
        if self._vip_expire_time:
            try:
                from datetime import datetime
                timestamp = int(self._vip_expire_time)
                dt = datetime.fromtimestamp(timestamp)
                vip_expire_time_human = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                _LOGGER.error("格式化VIP到期时间失败: %s", str(e))
        
        return {
            "connected": self._connected,
            "last_publish": self._last_publish,
            "entities_count": len(self.entities),
            "entities": self.entities,
            "messages_processed": self._messages_processed,
            "messages_failed": self._messages_failed,
            "queue_size": self._message_queue.qsize() if self._message_queue else 0,
            "vip_type": self._vip_type,
            "vip_expire_time": self._vip_expire_time,
            "vip_expire_time_human": vip_expire_time_human,
        }
    
    async def async_config_entry_first_refresh(self) -> None:
        """首次加载配置时执行初始刷新。"""
        # 设置状态变化监听器
        self._unsub_state_listener = self.hass.bus.async_listen(
            EVENT_STATE_CHANGED, self._state_changed_listener
        )
        
        # 设置停止监听器
        self._unsub_stop_listener = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, self.async_shutdown
        )
        
        # 连接MQTT - 使用非阻塞方式
        self.hass.async_create_task(self.async_connect())
        
        
        # 调用父类方法更新数据
        await super().async_config_entry_first_refresh()
    
    def _start_queue_processor(self):
        """启动队列处理任务，但不阻塞。"""
        if self._queue_processor_task is None or self._queue_processor_task.done():
            self._processing = True

            self._queue_processor_task = self.hass.async_create_background_task(
                self._process_queue(), f"queue_processor_{self.username}"
            )
    
    async def _process_queue(self):
        """处理消息队列，发送HTTP请求。"""
        try:
            while self._processing:
                try:
                    # 获取队列中的消息（等待直到有消息）
                    message = await self._message_queue.get()
                    
                    # 如果队列停止处理，则退出
                    if not self._processing:
                        break
                    
                    # 构建API URL
                    api_url = f"{self.web_url.rstrip('/')}{CONST_POST_CHANGE_STATE_URL}"
                    
                    # 发送HTTP POST请求
                    await self._post_data(api_url, message)
                    
                    # 标记任务完成
                    self._message_queue.task_done()
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    _LOGGER.error("处理消息队列时出错: %s", str(e))
                    # 短暂延迟避免CPU使用率过高
                await asyncio.sleep(0.01)
        finally:
            self._processing = False
            _LOGGER.info("队列处理任务已停止")
    
    async def async_connect(self):
        """连接到MQTT服务器。"""
        _LOGGER.info("正在连接到MQTT服务器 %s:%s (尝试 %s)", 
                    self.mqtt_url, self.mqtt_port, self._reconnect_attempt + 1)
        
        # 重置手动断开标志
        self._manual_disconnect = False
        
        # 创建全新的MQTT客户端实例，避免复用旧实例
        if self._mqtt_client:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except Exception:
                pass
            self._mqtt_client = None
            
        # 创建一个新的客户端ID，避免会话冲突
        self.client_id = f"ha-mqtt-sync-{id(self)}-{datetime.datetime.now().timestamp()}"
        self._mqtt_client = mqtt.Client(
            client_id=self.client_id,
            clean_session=True,  # 使用干净会话，避免旧会话问题
            protocol=mqtt.MQTTv311  # 使用MQTT v3.1.1协议
        )
            
        # 设置用户名和密码（如果提供有效值）
        if self.username and self.username.strip() != "" and self.password:
            self._mqtt_client.username_pw_set(self.username, self.password)
            
        # 设置回调
        self._mqtt_client.on_connect = self._on_connect
        self._mqtt_client.on_disconnect = self._on_disconnect
        self._mqtt_client.on_message = self._on_message
        
        # 设置保活间隔，减少断开连接的检测时间
        self._mqtt_client.keepalive = 30
        
        # 优化重连行为
        self._mqtt_client.reconnect_delay_set(min_delay=1, max_delay=120)
        
        # 添加遗嘱消息，当客户端意外断开时通知其他客户端
        self._mqtt_client.will_set(
            topic=f"{MQTT_COMMAND_TOPIC}/{self.username}/status",
            payload=json.dumps({"status": "disconnected"}),
            qos=1,
            retain=True
        )
        
        try:
            # 在事件循环中执行连接
            await self.hass.async_add_executor_job(
                self._connect_mqtt
            )
            return True
        except Exception as e:
            _LOGGER.error("MQTT连接错误: %s", str(e))
            # 在后台处理连接失败，不阻塞启动流程
            self.hass.async_create_task(self._handle_connection_failure())
            return False
    
    def _connect_mqtt(self):
        """在执行器中连接MQTT客户端。"""
        try:
            # 确保端口是整数类型
            port = int(self.mqtt_port)
            # 设置较短的连接超时，避免启动卡顿
            self._mqtt_client.connect(
                self.mqtt_url, 
                port, 
                keepalive=30
            )
            self._mqtt_client.loop_start()  # 启动后台线程
        except Exception as e:
            _LOGGER.error("MQTT连接失败: %s", str(e))
            raise
    
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT连接成功回调。"""
        if rc == 0:
            _LOGGER.info("已连接到MQTT服务器 %s:%s (返回码: %s, 已清除会话: %s)", 
                        self.mqtt_url, self.mqtt_port, rc, 
                        flags.get("session present", False))
            
            # 订阅命令主题
            self._mqtt_client.subscribe(f'{MQTT_COMMAND_TOPIC}/{self.username}')
            
            # 发布测试消息
            self._mqtt_client.publish(
                "testtopic/info", 
                f"Connected: client_id={self.client_id}", 
                qos=1,  # 使用QoS 1确保消息至少送达一次
                retain=False
            )
            
            # 发布连接状态消息，清除遗嘱消息
            self._mqtt_client.publish(
                topic=f"{MQTT_COMMAND_TOPIC}/{self.username}/status",
                payload=json.dumps({"status": "connected", "client_id": self.client_id}),
                qos=1,
                retain=True
            )
            
            # 重置重连尝试计数
            self._reconnect_attempt = 0
            
            # 在主线程中执行连接成功处理
            asyncio.run_coroutine_threadsafe(
                self._handle_connection_success(), 
                self.hass.loop
            )
        else:
            _LOGGER.error("无法连接到MQTT服务器，返回码: %s", rc)
            # 在主线程中执行连接失败处理
            asyncio.run_coroutine_threadsafe(
                self._handle_connection_failure(), 
                self.hass.loop
            )
    
    def _on_disconnect(self, client, userdata, rc):
        """MQTT断开连接回调。"""
        if self._manual_disconnect and rc == 0:
            # 正常手动断开连接
            _LOGGER.info("已手动断开与MQTT服务器的连接")
            return
            
        # 其他所有情况都视为非预期断开
        _LOGGER.warning("从MQTT服务器断开连接，返回码: %s (是否手动断开: %s)", 
                        rc, self._manual_disconnect)
        
        # 确保断开后停止loop，防止资源泄漏
        try:
            client.loop_stop()
        except Exception:
            pass
        
        # 在主线程中执行连接失败处理
        asyncio.run_coroutine_threadsafe(
            self._handle_connection_failure(), 
            self.hass.loop
        )
    
    def _on_message(self, client, userdata, msg):
        """处理收到的MQTT消息。"""
        try:
            topic = msg.topic
            payload_str = msg.payload.decode('utf-8')
            
            _LOGGER.debug("收到MQTT消息: 主题=%s, 内容=%s", topic, payload_str)
            
            # 验证消息是否为有效的JSON
            try:
                payload_json = json.loads(payload_str)
                
                # 验证payload是对象而不是数组或原始类型
                if not isinstance(payload_json, dict):
                    _LOGGER.warning("收到的消息不是JSON对象，已丢弃: %s", payload_str)
                    return
                
                # 处理消息内容
                cmd_type = payload_json.get('type')
                if cmd_type:
                    # 根据消息类型处理
                    if cmd_type == 'syncentity':
                        # 同步实体列表
                        asyncio.run_coroutine_threadsafe(
                            self._sync_device_entities_async(self.entities),
                            self.hass.loop
                        )
                    elif cmd_type == 'callservice':
                        # 调用服务
                        asyncio.run_coroutine_threadsafe(
                            self._call_service_async(payload_json),
                            self.hass.loop
                        )
                    elif cmd_type == 'initinfo':
                        # 处理初始化信息，包括VIP信息
                        _LOGGER.info("收到初始化信息")
                        self._process_initinfo_message(payload_json)
                        # 更新数据并通知监听器
                        asyncio.run_coroutine_threadsafe(
                            self._update_data_after_initinfo(),
                            self.hass.loop
                        )
            except json.JSONDecodeError:
                _LOGGER.warning("收到的消息不是有效的JSON，已丢弃: %s", payload_str)
                return
                
        except Exception as e:
            _LOGGER.error("处理MQTT消息时出错: %s", str(e))
    
    async def _add_to_queue(self, state: State):
        """添加消息到队列中。"""
        try:
            # 如果队列已满，则移除最旧的消息
            if self._message_queue.full():
                try:
                    # 非阻塞获取，避免死锁
                    self._message_queue.get_nowait()
                    _LOGGER.warning("队列已满，丢弃最旧的消息")
                except asyncio.QueueEmpty:
                    pass

            if isinstance(state, State):
                post_device_data = {
                    'type': 'state_changed',
                    'data': state.as_dict(),
                    'openid': self.username,
                    'secret': self.password
                }
                await self._message_queue.put(post_device_data)     
                _LOGGER.debug("消息已加入队列，当前队列长度: %s", self._message_queue.qsize())
            
            # 确保队列处理器在运行
            if not self._processing:
                self._start_queue_processor()
            
        except Exception as e:
            _LOGGER.error("添加消息到队列时出错: %s", str(e))
    
    async def _handle_connection_success(self):
        """处理连接成功。"""
        _LOGGER.info("MQTT连接成功处理")
        
        # 更新连接状态
        self._connected = True
        
        # 取消重连任务
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None

        
        self.async_set_updated_data(await self._async_update_data())
        
        # 发送连接信号
        async_dispatcher_send(self.hass, SIGNAL_MQTT_CONNECTED)
    
    async def _handle_connection_failure(self):
        """处理连接失败。"""
        _LOGGER.error("无法连接到MQTT服务器 %s:%s (尝试次数: %s)", 
                     self.mqtt_url, self.mqtt_port, self._reconnect_attempt)
        
        # 更新连接状态
        self._connected = False
        
        self.async_set_updated_data(await self._async_update_data())
        
        # 发送断连信号
        async_dispatcher_send(self.hass, SIGNAL_MQTT_DISCONNECTED)
        
        # 增加重连尝试计数
        self._reconnect_attempt += 1
        
        # 启动重连，但避免重复创建重连任务
        # 检查任务是否存在、是否已完成或是否处于异常状态
        if not self._reconnect_task or self._reconnect_task.done():
            _LOGGER.info("创建新的重连任务")
            # 取消可能存在的旧任务
            if self._reconnect_task:
                self._reconnect_task.cancel()
            self._reconnect_task = self.hass.async_create_task(
                self._reconnect_with_delay()
            )
        else:
            _LOGGER.info("重连任务已存在，不再创建新任务")
    
    async def _reconnect_with_delay(self):
        """延迟后重新连接。"""
        # 指数退避重连策略，但限制最大延迟
        delay = min(MQTT_RECONNECT_INTERVAL * (1 + self._reconnect_attempt * 0.5), 60)
        _LOGGER.info("将在 %.1f 秒后尝试第 %s 次重新连接MQTT服务器", 
                    delay, self._reconnect_attempt + 1)
        
        try:
            await asyncio.sleep(delay)
            if not self._manual_disconnect:  # 只有在非手动断开的情况下才尝试重连
                success = await self.async_connect()
                if not success and not self._manual_disconnect:
                    # 如果连接失败且不是手动断开，则立即安排下一次重连尝试
                    _LOGGER.warning("连接尝试失败，准备下一次重连")
                    # 直接递归调用，避免创建过多任务
                    self._reconnect_task = self.hass.async_create_task(
                        self._reconnect_with_delay()
                    )
        except asyncio.CancelledError:
            _LOGGER.info("重连任务已取消")
        except Exception as e:
            _LOGGER.error("重连过程中发生错误: %s，将在下次尝试", str(e))
            # 即使发生异常，也要确保安排下一次重连
            if not self._manual_disconnect:
                self._reconnect_task = self.hass.async_create_task(
                    self._reconnect_with_delay()
                )
    
    async def async_disconnect(self):
        """断开与MQTT服务器的连接。"""
        # 设置手动断开标志
        self._manual_disconnect = True
        
        # 停止消息处理
        self._processing = False
        if self._queue_processor_task:
            self._queue_processor_task.cancel()
            try:
                await self._queue_processor_task
            except asyncio.CancelledError:
                pass
            self._queue_processor_task = None
        
        # 停止MQTT客户端
        if self._mqtt_client:
            try:
                # 先发布断开消息
                try:
                    self._mqtt_client.publish(
                        "testtopic/info", 
                        f"Disconnected: client_id={self.client_id}", 
                        qos=0, 
                        retain=False
                    )
                    # 发布断开状态消息
                    self._mqtt_client.publish(
                        topic=f"{MQTT_COMMAND_TOPIC}/{self.username}/status",
                        payload=json.dumps({"status": "disconnected"}),
                        qos=1,
                        retain=True
                    )
                except Exception:
                    pass
                
                # 关闭客户端
                self._mqtt_client.loop_stop()
                await self.hass.async_add_executor_job(self._mqtt_client.disconnect)
            except Exception as e:
                _LOGGER.error("断开MQTT连接时出错: %s", str(e))
            self._mqtt_client = None
        
        # 更新连接状态
        self._connected = False
        
        # 取消重连任务
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        
        self.async_set_updated_data(await self._async_update_data())
        
        _LOGGER.info("已断开与MQTT服务器的连接")
    
    def _process_initinfo_message(self, payload_json):
        """处理初始化信息消息，提取VIP相关数据。"""
        try:
            data = payload_json.get('data', {})
            vip_info = data.get('vip', {})
            
            if vip_info:
                self._vip_type = vip_info.get('vip_type')
                self._vip_expire_time = vip_info.get('vip_time')
                _LOGGER.info("更新VIP信息: 类型=%s, 到期时间=%s", 
                            self._vip_type, self._vip_expire_time)
        except Exception as e:
            _LOGGER.error("处理初始化信息时出错: %s", str(e))
    
    async def _update_data_after_initinfo(self):
        """在接收到初始化信息后更新数据。"""
        self.async_set_updated_data(await self._async_update_data())
    
    async def async_shutdown(self, event=None):
        """当Home Assistant停止时关闭。"""
        # 移除事件监听器
        if self._unsub_state_listener:
            self._unsub_state_listener()
            self._unsub_state_listener = None
        
        if self._unsub_stop_listener:
            self._unsub_stop_listener()
            self._unsub_stop_listener = None
        
        # 停止消息处理
        self._processing = False
        if self._queue_processor_task:
            self._queue_processor_task.cancel()
        
        # 断开MQTT连接
        await self.async_disconnect()
    
    @callback
    def _state_changed_listener(self, event):
        """监听实体状态变化事件。"""
        entity_id = event.data.get("entity_id")
        
        # 检查是否为我们要监听的实体
        if entity_id in self.entities:
            new_state = event.data.get("new_state")
            
            # 如果状态变化不为None
            if new_state is not None:
                # 使用run_coroutine_threadsafe在同步上下文中调用异步方法
                asyncio.run_coroutine_threadsafe(
                    self._add_to_queue(new_state),
                    self.hass.loop
                )
    
    async def _sync_device_entities_async(self, entities: list[str]):
        """同步设备实体列表到Web服务器。"""
        if isinstance(entities, list):
            _LOGGER.debug('开始同步实体列表')
            entity_list = []
            for entity in entities:
                state: State = self.hass.states.get(entity)
                if isinstance(state, State):
                    entity_dic = dict(state.as_dict())
                    entity_list.append(entity_dic)
            _LOGGER.debug(f'同步设备实体列表:{entity_list}')
            post_device_data = {
                'type': 'syncentity',
                'data': entity_list,
                'openid': self.username,
                'secret': self.password
            }
            await self._post_data(
                f'{self.web_url.rstrip("/")}{CONST_POST_SYNC_DEVICE_URL}',
                post_device_data
            )
            _LOGGER.debug('同步实体列表完成')
    
    async def _call_service_async(self, data: dict) -> None:
        """调用Home Assistant服务。"""
        _LOGGER.debug(f'调用Home Assistant服务: {data}')
        service = data.get('service')
        s_data = data.get('service_data')
        entity_id = data.get('entity_id')
        
        if not entity_id:
            _LOGGER.error("调用服务缺少entity_id参数")
            return

        domain = entity_id.split('.')[0]
        if not s_data:
            s_data = {
                'entity_id': entity_id
            }
        if isinstance(s_data, dict):
            s_data['entity_id'] = entity_id

        _LOGGER.debug(f'调用服务数据:{s_data},{service}')
        await self.hass.services.async_call(
            domain=domain, service=service, service_data=s_data, blocking=False
        )
    
    async def _post_data(self, api_url: str, message: dict) -> bool:
        """向Web服务器发送POST请求。"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url, 
                    json=message,
                    headers={"Content-Type": "application/json"},
                    timeout=10
                ) as response:
                    if response.status >= 200 and response.status < 300:
                        self._messages_processed += 1
                        _LOGGER.debug(
                            "消息发送成功: 状态码=%s, URL=%s", 
                            response.status, api_url
                        )
                        return True
                    else:
                        self._messages_failed += 1
                        resp_text = await response.text()
                        _LOGGER.error(
                            "消息发送失败: 状态码=%s, URL=%s, 响应=%s", 
                            response.status, api_url, resp_text
                        )
                        return False
        except Exception as e:
            self._messages_failed += 1
            _LOGGER.error("发送HTTP请求时出错: %s, URL=%s", str(e), api_url)
            return False