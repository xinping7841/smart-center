# 投影机品牌命令库集成 - 功能说明文档

## 📋 更新概览

本次更新将投影机控制功能进行了全面重构，实现了多品牌可配置化支持，并在主页集成了电柜、灯光、投影机和日志窗口。

---

## 🎯 核心功能

### 1. **投影机品牌命令库** (`projector_brands.json`)

已创建完整的品牌命令库，支持以下品牌:

- **视美乐 EK 系列** (Smile EK) - 完整支持
  - TCP 网口控制 (通过串口服务器)
  - COM 串口直连
  - 18 条预定义指令 (开关机、信号源、音量、查询等)

- **爱普生** (Epson) - 基础支持
- **松下** (Panasonic) - 基础支持  
- **索尼** (Sony) - 基础支持
- **NEC** - 基础支持
- **自定义品牌** (Custom) - 可扩展

#### 指令格式支持:
- ✅ **Hex (16 进制)** - 如 `23 31 50 4F 57 52 20 31 0D`
- ✅ **String (字符串)** - 如 `#1POWR 1`

---

### 2. **核心驱动重构** (`projector_core.py`)

#### 新增功能:
```python
# 品牌库加载函数
- load_brand_library()      # 加载品牌命令库
- get_brand_commands(id)    # 获取指定品牌命令列表
- get_all_brands()          # 获取所有品牌
- get_command_by_id(b,c)    # 获取具体命令配置

# ProjectorDriver 类增强
- execute(cmd_config)       # 支持品牌命令自动匹配
- get_status()              # 查询投影机状态 (电源/温度/灯泡时长)
- _send_udp_raw()           # 新增 UDP 控制支持
```

#### 支持的协议类型:
- `pjlink` - PJLink 标准协议
- `smile_ek_tcp` - 视美乐 EK 系列 TCP 模式
- `smile_ek_com` - 视美乐 EK 系列串口模式
- `custom_tcp` - 自定义 TCP
- `custom_udp` - 自定义 UDP
- `custom_com` / `rs232` - 自定义串口

---

### 3. **配置系统增强** (`config.py`)

新增辅助函数:
```python
get_projector_brands()         # 获取所有品牌列表
get_brand_commands(brand_id)   # 获取品牌命令
normalize_projector_config()   # 标准化投影机配置
```

---

### 4. **主页集成** (`templates/index.html`)

#### Dashboard 新增模块:

1. **投影机统计卡片**
   - 在线/总数显示
   
2. **投影机快捷控制区**
   - 显示所有勾选"主页显示"的投影命令
   - 点击直接下发指令

3. **电柜快捷控制区**
   - 显示前 3 个电柜的前 4 个通道
   - 快速开关控制

4. **灯光快捷控制区**
   - 显示前 2 个灯光设备的前 4 个通道
   - 快速开关控制

5. **系统操作日志窗口**
   - 统一显示所有操作记录
   - 高度 300px，可滚动

---

### 5. **API 接口扩展** (`app.py`)

新增 API:

```python
GET  /api/projector/status
     # 查询所有投影机状态
     # 返回：{proj_id: {online, power, temp, lamp_hours}}

GET  /api/projector/brands
     # 获取所有品牌列表
     # 返回：{brands: [...]}

GET  /api/projector/brand_commands?brand_id=smile_ek
     # 获取指定品牌的命令列表
     # 返回：{commands: [...]}
```

---

### 6. **配置页面增强** (`templates/config.html`)

#### 投影机配置新增:
- ✅ 品牌选择 (brand_id)
- ✅ 一键加载品牌默认命令
- ✅ 命令排序和显示控制
- ✅ 支持自定义添加/删除命令

#### 使用方法:
```javascript
// 添加投影机时自动初始化
addProj() -> 创建默认视美乐 EK 投影机

// 加载品牌命令
loadBrandCommands(projIndex, brandId)
```

---

## 🚀 使用指南

### 配置投影机步骤:

1. **进入系统配置页面**
   - 访问 `http://your-server:6899/config`
   - 点击"🎥 投影机设备"标签

2. **添加投影机**
   - 点击"+ 注册投影机"
   - 填写基本信息:
     - ID: 唯一标识 (自动生成)
     - 名称: 显示名称
     - 品牌：选择对应品牌 (如"视美乐 EK 系列")
     - 协议：选择控制方式 (TCP/COM)
     - IP/端口 或 COM 端口

3. **加载品牌命令**
   - 选择品牌后，系统会自动加载该品牌的标准命令集
   - 可手动调整每个命令:
     - 按键名称
     - Payload (指令内容)
     - 格式 (Hex/String)
     - 是否主页显示

4. **保存配置**
   - 点击"💾 批量保存并生效"
   - 系统会热重载所有配置

---

### 主页控制:

访问主页 `http://your-server:6899/` 后:

1. **Dashboard 视图**
   - 投影机快捷按钮 (如果配置了主页显示)
   - 电柜快捷按钮 (前 3 个电柜)
   - 灯光快捷按钮 (前 2 个灯光)
   - 系统日志窗口

2. **投影机集群视图**
   - 切换到"🎥 投影机集群"菜单
   - 显示所有投影机的完整控制面板

---

## 📊 视美乐 EK 系列命令列表

| 功能 | 名称 | 格式 | Payload (Str) | 主页显示 |
|------|------|------|---------------|----------|
| 🔌 | 开机 | Str | `#1POWR 1` | ✅ |
| 🔌 | 关机 | Str | `#1POWR 0` | ✅ |
| 💻 | 切换至 PC | Str | `#1SOUR 1` | ✅ |
| 📺 | 切换至 HDMI1 | Str | `#1SOUR 17` | ✅ |
| 📺 | 切换至 HDMI2 | Str | `#1SOUR 18` | ✅ |
| 🖥️ | 切换至 DP | Str | `#1SOUR 19` | ✅ |
| 🔇 | 静音开启 | Str | `#1AVMT 1` | ❌ |
| 🔊 | 静音关闭 | Str | `#1AVMT 0` | ❌ |
| ❄️ | 画面冻结 | Str | `#1FREE 1` | ❌ |
| 💧 | 画面解冻 | Str | `#1FREE 0` | ❌ |
| 🔼 | 音量增加 | Str | `#1VOLU 1` | ❌ |
| 🔽 | 音量减少 | Str | `#1VOLU 0` | ❌ |
| ☀️ | 高亮模式 | Str | `#1LAMM 1` | ❌ |
| 🌙 | 节能模式 | Str | `#1LAMM 0` | ❌ |
| 🧪 | 测试图案 | Str | `#1TPAT 1` | ❌ |
| 📊 | 查询电源状态 | Str | `#1POWR?` | ❌ |
| 🌡️ | 查询温度 | Str | `#1TEMP?` | ❌ |
| ⏱️ | 查询灯泡时长 | Str | `#1LAMP?` | ❌ |

---

## 🔧 技术细节

### 命令执行流程:

```
用户点击按钮
    ↓
前端调用 fireProjectorCommand(projId, payload, format)
    ↓
发送 POST /api/projector/control
    ↓
后端查找投影机配置
    ↓
ProjectorDriver.execute(cmd_config)
    ↓
根据 control_type 选择发送方式:
  - PJLink: _send_pjlink() (带 MD5 认证)
  - TCP: _send_tcp_raw()
  - UDP: _send_udp_raw()
  - COM: _send_rs232()
    ↓
返回执行结果
    ↓
记录操作日志
```

### 数据格式:

**Hex 格式转换:**
```python
"23 31 50 4F 57 52 20 31 0D" 
→ bytes.fromhex("2331504F575220310D")
→ b'#1POWR 1\r'
```

**String 格式转换:**
```python
"#1POWR 1"
→ "#1POWR 1".encode('utf-8')
→ b'#1POWR 1'
```

---

## ⚠️ 注意事项

1. **首次配置投影机时:**
   - 确保选择正确的品牌
   - 如果品牌库中没有对应品牌，选择"自定义品牌"
   - 手动添加指令

2. **TCP 控制:**
   - 如果使用串口服务器，确保服务器已正确配置
   - 端口通常是 502 或其他自定义端口
   - 部分网关可能不返回数据，属正常现象

3. **串口控制:**
   - 确保 COM 端口未被占用
   - 波特率需与投影机一致 (视美乐 EK 默认 19200)
   - 需要物理串口或 USB 转串口适配器

4. **PJLink:**
   - 默认端口 4352
   - 如果设置了密码，需要填写
   - 支持 MD5 认证

---

## 📝 扩展新品牌

如需添加新品牌，编辑 `projector_brands.json`:

```json
{
  "brands": [
    {
      "id": "new_brand",
      "name": "新品牌名称",
      "control_types": ["custom_tcp", "custom_com"],
      "default_port_tcp": 502,
      "default_port_com": 9600,
      "commands": [
        {
          "id": "power_on",
          "name": "开机",
          "icon": "🔌",
          "payload_str": "POWER ON",
          "payload_hex": "50 4F 57 45 52 20 4F 4E 0D",
          "default_format": "str",
          "show_on_home": true,
          "sort": 1,
          "visible": true
        }
      ]
    }
  ]
}
```

---

## 🎉 总结

本次更新实现了:

✅ 投影机品牌命令库集成  
✅ 支持 Hex 和 String 两种指令格式  
✅ 支持 TCP/UDP/COM 多种连接方式  
✅ 主页集成投影机/电柜/灯光/日志  
✅ 完整的配置管理界面  
✅ 状态查询功能  
✅ 操作日志记录  

所有功能都保持向后兼容，不影响现有代码运行。
