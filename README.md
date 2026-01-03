# Haplugin - 小度语音控制 Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![version](https://img.shields.io/badge/version-0.1.1-blue.svg)](https://github.com/yuanxin32323/haplugin/releases)

通过小度智能音箱语音控制 Home Assistant 设备的集成插件。

## ✨ 功能特点

- 🎤 **语音控制**：通过小度音箱语音控制 HA 设备
- 🔄 **实时同步**：设备状态实时同步到小度
- 📱 **多设备支持**：支持灯光、开关、空调、风扇、窗帘、场景等
- 🏨 **双版本支持**：支持家庭版和酒店版小度音箱

## 📦 支持的设备类型

| 类型         | 说明        |
| ------------ | ----------- |
| light        | 灯光        |
| switch       | 开关        |
| climate      | 空调/恒温器 |
| fan          | 风扇        |
| cover        | 窗帘/门     |
| scene        | 场景        |
| button       | 按钮        |
| input_button | 输入按钮    |
| water_heater | 热水器      |

## 🚀 安装方式

### 方式一：通过 HACS 安装（推荐）

1. 确保已安装 [HACS](https://hacs.xyz/)
2. 在 HACS 中点击右上角 **⋮** → **自定义存储库**
3. 添加存储库地址：`https://github.com/yuanxin32323/haplugin`
4. 类别选择：**Integration**
5. 点击 **添加** → 搜索 **Haplugin** → 点击 **下载**
6. 重启 Home Assistant

### 方式二：手动安装

1. 下载本仓库的 `custom_components/haplugin` 文件夹
2. 将 `haplugin` 文件夹复制到 Home Assistant 的 `custom_components` 目录
3. 重启 Home Assistant

## ⚙️ 配置步骤

### 1. 获取 Token

访问 [https://smarthome.haplugin.com](https://smarthome.haplugin.com) 注册账号并获取 Token。

### 2. 添加集成

1. 进入 Home Assistant → **设置** → **设备与服务**
2. 点击右下角 **添加集成**
3. 搜索 **Haplugin**
4. 输入从网站获取的 Token
5. 选择要同步的设备类型
6. 选择要同步的具体设备
7. 完成配置

### 3. 绑定小度

按照网站说明，在小度 App 中绑定账号即可使用语音控制。

## 🔧 修改配置

配置完成后，可以随时修改设置：

1. 进入 **设置** → **设备与服务** → **Haplugin**
2. 点击 **配置**
3. 选择要修改的内容：
   - 🔑 **修改 Token**：更换账号或刷新连接
   - 📱 **修改同步设备**：增减需要同步的设备

## 📊 状态传感器

集成会创建以下传感器实体：

| 传感器                | 说明                       |
| --------------------- | -------------------------- |
| Haplugin 连接状态     | MQTT 连接状态（在线/离线） |
| Haplugin VIP 类型     | 当前 VIP 等级              |
| Haplugin VIP 到期时间 | VIP 到期时间               |

## ❓ 常见问题

**Q: 连接状态一直显示离线？**  
A: 请检查 Token 是否正确，或尝试重新输入 Token。

**Q: 设备无法被小度发现？**  
A: 确保设备已添加到同步列表，并在小度 App 中重新搜索设备。

**Q: 如何更新集成？**  
A: 如果通过 HACS 安装，在 HACS 中更新即可。手动安装需重新下载替换文件。

## 📝 更新日志

### v0.1.1

- 优化设备选择流程，支持分步选择和全选功能
- 新增修改 Token 功能
- 界面优化和 Bug 修复

### v0.1.0

- 初始版本发布

## 📄 许可证

MIT License

## 🔗 相关链接

- [官方网站](https://smarthome.haplugin.com)
- [问题反馈](https://github.com/yuanxin32323/haplugin/issues)
