# 投影机品牌和系列三层结构说明

## ✅ 重构完成

已成功重构投影机配置为**三层结构**:

```
品牌 (Brand)
└── 系列 (Series)
    ├── 连接类型 (Connection Type)
    └── 命令列表 (Commands)
```

## 📊 层级说明

### 第一层：品牌 (Brand)

**作用**: 表示投影机制造商

**示例品牌:**
- 光峰 (appotronics)
- 视美乐 (smile)
- 爱普生 (epson)
- 松下 (panasonic)
- 索尼 (sony)
- NEC (nec)
- 自定义 (custom)

**特点:**
- 品牌下可以有多个系列
- 品牌本身不包含命令
- 品牌用于组织和分类

### 第二层：系列 (Series)

**作用**: 表示品牌下的具体产品系列

**示例系列:**
- 光峰 → DH 系列
- 视美乐 → EK 系列

**包含内容:**
- 系列基本信息 (ID、名称、显示名称)
- 连接类型配置
- 命令列表

**特点:**
- 每个系列有独立的命令集
- 每个系列有独立的连接类型配置
- 系列名称在品牌内唯一

### 第三层：连接类型 (Connection Type)

**作用**: 表示系列的物理连接方式

**连接类型:**
- 🌐 网络接入 (TCP) - 默认端口 9761
- 🌐 网络接入 (UDP) - 默认端口 9761
- 🔌 串口接入 (RS232) - 默认波特率 9600

**特点:**
- 每个系列可以有多种连接方式
- 每种连接类型有独立的端口配置
- 连接类型决定通讯协议

## 🎯 使用流程

### 步骤 1: 选择品牌

```javascript
// 获取所有品牌
GET /api/projector/brands

响应:
{
  "brands": [
    {"id": "appotronics", "name": "光峰", "series_count": 1},
    {"id": "smile", "name": "视美乐", "series_count": 1},
    ...
  ]
}
```

### 步骤 2: 选择系列

```javascript
// 获取品牌下的系列
GET /api/projector/series?brand_id=appotronics

响应:
{
  "series": [
    {
      "id": "dh",
      "name": "DH 系列",
      "display_name": "光峰 DH 系列"
    }
  ]
}
```

### 步骤 3: 获取系列详情

```javascript
// 获取系列详细信息 (包括连接类型)
GET /api/projector/series_info?brand_id=appotronics&series_id=dh

响应:
{
  "series_info": {
    "id": "dh",
    "name": "DH 系列",
    "display_name": "光峰 DH 系列",
    "connection_types": {...},
    "commands": [...]
  },
  "connection_types": {
    "tcp": {
      "id": "appotronics_dh_tcp",
      "name": "网络接入 (TCP)",
      "default_port": 9761,
      "icon": "🌐"
    },
    ...
  }
}
```

### 步骤 4: 加载命令

```javascript
// 获取系列的命令列表
GET /api/projector/series_commands?brand_id=appotronics&series_id=dh

响应:
{
  "commands": [
    {
      "id": "power_on",
      "name": "开机",
      "icon": "🔌",
      "payload_hex": "AA 01 01 01 00 00 00 03",
      ...
    },
    ...
  ]
}
```

## 📝 配置示例

### JSON 配置结构

```json
{
  "brands": [
    {
      "id": "appotronics",
      "name": "光峰",
      "series": [
        {
          "id": "dh",
          "name": "DH 系列",
          "display_name": "光峰 DH 系列",
          "connection_types": {
            "tcp": {
              "id": "appotronics_dh_tcp",
              "name": "网络接入 (TCP)",
              "default_port": 9761,
              "icon": "🌐"
            },
            "udp": {
              "id": "appotronics_dh_udp",
              "name": "网络接入 (UDP)",
              "default_port": 9761,
              "icon": "🌐"
            },
            "com": {
              "id": "appotronics_dh_com",
              "name": "串口接入 (RS232)",
              "default_port": 9600,
              "icon": "🔌"
            }
          },
          "commands": [...]
        }
      ]
    },
    {
      "id": "smile",
      "name": "视美乐",
      "series": [
        {
          "id": "ek",
          "name": "EK 系列",
          "display_name": "视美乐 EK 系列",
          "control_types": ["smile_ek_tcp", "smile_ek_com", "pjlink"],
          "default_port_tcp": 502,
          "default_port_com": 9600,
          "default_id": 30,
          "commands": [...]
        }
      ]
    }
  ]
}
```

### 设备配置

```json
{
  "projectors": [
    {
      "id": "dh_001",
      "name": "1 号投影机",
      "brand_id": "appotronics",      // 品牌：光峰
      "series_id": "dh",              // 系列：DH 系列
      "control_type": "appotronics_dh_tcp",  // 连接类型：TCP
      "ip": "192.168.50.110",
      "port": 9761
    },
    {
      "id": "ek_001",
      "name": "视美乐投影机",
      "brand_id": "smile",            // 品牌：视美乐
      "series_id": "ek",              // 系列：EK 系列
      "control_type": "smile_ek_tcp", // 连接类型：TCP
      "ip": "192.168.50.72",
      "port": 502
    }
  ]
}
```

## 🔧 API 接口

### 1. 获取品牌列表

```bash
GET /api/projector/brands
```

**响应:**
```json
{
  "brands": [
    {"id": "appotronics", "name": "光峰", "series_count": 1},
    {"id": "smile", "name": "视美乐", "series_count": 1}
  ]
}
```

### 2. 获取品牌下的系列

```bash
GET /api/projector/series?brand_id=appotronics
```

**响应:**
```json
{
  "series": [
    {
      "id": "dh",
      "name": "DH 系列",
      "display_name": "光峰 DH 系列"
    }
  ]
}
```

### 3. 获取系列详情

```bash
GET /api/projector/series_info?brand_id=appotronics&series_id=dh
```

**响应:**
```json
{
  "series_info": {...},
  "connection_types": {...}
}
```

### 4. 获取系列命令

```bash
GET /api/projector/series_commands?brand_id=appotronics&series_id=dh
```

**响应:**
```json
{
  "commands": [...]
}
```

## 💻 Python 代码使用

```python
from projector_core import (
    get_all_brands,
    get_brand_series,
    get_series_info,
    get_series_commands,
    get_connection_types,
    get_connection_type_name
)

# 1. 获取所有品牌
brands = get_all_brands()
for brand in brands:
    print(f"{brand['id']}: {brand['name']}")

# 2. 获取品牌下的系列
series_list = get_brand_series("appotronics")
for series in series_list:
    print(f"{series['id']}: {series['display_name']}")

# 3. 获取系列详情
dh_series = get_series_info("appotronics", "dh")
print(f"系列名称：{dh_series['display_name']}")

# 4. 获取连接类型
conn_types = get_connection_types("appotronics", "dh")
for key, info in conn_types.items():
    print(f"{info['icon']} {info['name']} - 端口：{info['default_port']}")

# 5. 获取命令列表
commands = get_series_commands("appotronics", "dh")
for cmd in commands:
    print(f"{cmd['icon']} {cmd['name']}")

# 6. 获取连接类型名称
tcp_name = get_connection_type_name("appotronics", "dh", "appotronics_dh_tcp")
print(f"连接类型名称：{tcp_name}")  # 网络接入 (TCP)
```

## 🎨 UI 界面建议

### 投影机配置界面

```
┌─────────────────────────────────────────────┐
│ 投影机配置                                  │
├─────────────────────────────────────────────┤
│ 品牌：  [光峰 ▼]                            │
│                                             │
│ 系列：  [DH 系列 ▼]                         │
│                                             │
│ 连接方式：○ 🌐 网络接入 (TCP)              │
│           ○ 🌐 网络接入 (UDP)              │
│           ○ 🔌 串口接入 (RS232)            │
│                                             │
│ [网络接入选项]                              │
│ IP 地址：[192.168.50.110]                   │
│ 端口：  [9761]                              │
│                                             │
│ [串口接入选项] (如果选择串口)               │
│ 串口：  [COM3 ▼]                            │
│ 波特率：[9600 ▼]                            │
│                                             │
│ ┌─────────────────────────────────────┐    │
│ │ 快捷操作                            │    │
│ │                                     │    │
│ │ 🔌 开机   🔌 关机                   │    │
│ │ 💻 PC     📺 HDMI1                  │    │
│ │ 📺 HDMI2  🖥️ DP                     │    │
│ │                                     │    │
│ │ [一键加载标准命令集]                │    │
│ └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

## 📋 验证测试

### 运行测试脚本

```bash
python test_three_tier_structure.py
```

**输出:**
```
================================================================================
🏗️  三层结构测试：品牌 → 系列 → 连接类型
================================================================================

1️⃣  第一层：品牌列表
--------------------------------------------------------------------------------
   appotronics: 光峰 (系列数：1)
   smile: 视美乐 (系列数：1)
   ...

2️⃣  第二层：品牌下的系列
--------------------------------------------------------------------------------

📍 光峰品牌:
   - dh: DH 系列 (光峰 DH 系列)

📍 视美乐品牌:
   - ek: EK 系列 (视美乐 EK 系列)

3️⃣  第三层：系列详情和连接类型
--------------------------------------------------------------------------------

📍 光峰 DH 系列:
   系列 ID: dh
   显示名称：光峰 DH 系列

   连接类型:
      🌐 网络接入 (TCP) - 端口：9761
      🌐 网络接入 (UDP) - 端口：9761
      🔌 串口接入 (RS232) - 端口：9600

✅ 三层结构验证完成!
================================================================================
```

## ⚠️ 重要说明

### 品牌区分

- ✅ **正确**: 光峰品牌下只有光峰的系列
- ✅ **正确**: 视美乐品牌下只有视美乐的系列
- ❌ **错误**: 光峰品牌下出现视美乐系列

### 系列命名

- 格式：`{品牌拼音}_{系列名}`
- 示例：`appotronics_dh`, `smile_ek`

### 连接类型命名

- 格式：`{品牌拼音}_{系列名}_{连接方式}`
- 示例：
  - `appotronics_dh_tcp`
  - `appotronics_dh_com`
  - `smile_ek_tcp`

## 📄 相关文件

- [`projector_brands.json`](./projector_brands.json) - 三层结构配置
- [`projector_core.py`](./projector_core.py) - 驱动核心 (支持三层结构)
- [`app.py`](./app.py) - API 接口 (已更新)
- [`test_three_tier_structure.py`](./test_three_tier_structure.py) - 测试工具

## 📚 相关文档

- [BRAND_AND_CONNECTION_TYPE.md](./BRAND_AND_CONNECTION_TYPE.md) - 品牌和连接类型说明
- [DH_PORT_CONFIG.md](./DH_PORT_CONFIG.md) - 端口配置说明
- [APPOTRONICS_DH_PROTOCOL.md](./APPOTRONICS_DH_PROTOCOL.md) - DH 系列协议
- [QUICK_CONFIG_GUIDE.md](./QUICK_CONFIG_GUIDE.md) - 快速配置指南

---

**更新时间**: 2026-03-23  
**版本**: v2.0 (三层结构)  
**状态**: ✅ 已完成并验证  
**层级**: 品牌 → 系列 → 连接类型/命令
