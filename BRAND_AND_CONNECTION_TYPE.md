# 光峰 DH 系列品牌和连接类型配置说明

## ✅ 完成情况

已完善光峰 DH 系列的品牌和连接类型配置，现在可以清晰区分:
1. **品牌和型号** (光峰 DH 系列)
2. **连接方式** (网络接入 vs 串口接入)

## 📊 配置结构

### 品牌信息

```json
{
  "id": "appotronics_dh",
  "name": "光峰 DH 系列",
  "brand": "appotronics",      // 品牌标识
  "series": "dh",              // 系列标识
  "display_name": "光峰 DH 系列" // 显示名称
}
```

### 连接类型

系统支持三种连接方式，每种都有独立的配置:

#### 1. 网络接入 (TCP)
```json
{
  "id": "appotronics_dh_tcp",
  "name": "网络接入 (TCP)",
  "default_port": 9761,
  "icon": "🌐"
}
```

#### 2. 网络接入 (UDP)
```json
{
  "id": "appotronics_dh_udp",
  "name": "网络接入 (UDP)",
  "default_port": 9761,
  "icon": "🌐"
}
```

#### 3. 串口接入 (RS232)
```json
{
  "id": "appotronics_dh_com",
  "name": "串口接入 (RS232)",
  "default_port": 9600,
  "icon": "🔌"
}
```

## 🎯 使用方式

### 配置投影机设备

#### 方式 1: 网络接入 (TCP) - 推荐

```json
{
  "projectors": [
    {
      "id": "dh_001",
      "name": "主投影机",
      "brand_id": "appotronics_dh",
      "control_type": "appotronics_dh_tcp",
      "ip": "192.168.50.110",
      "port": 9761
    }
  ]
}
```

**显示效果:**
- 品牌系列：光峰 DH 系列
- 连接方式：网络接入 (TCP) 🌐
- IP 地址：192.168.50.110:9761

#### 方式 2: 网络接入 (UDP)

```json
{
  "projectors": [
    {
      "id": "dh_002",
      "name": "备用投影机",
      "brand_id": "appotronics_dh",
      "control_type": "appotronics_dh_udp",
      "ip": "192.168.50.110",
      "port": 9761
    }
  ]
}
```

**显示效果:**
- 品牌系列：光峰 DH 系列
- 连接方式：网络接入 (UDP) 🌐
- IP 地址：192.168.50.110:9761

#### 方式 3: 串口接入 (RS232)

```json
{
  "projectors": [
    {
      "id": "dh_003",
      "name": "串口投影机",
      "brand_id": "appotronics_dh",
      "control_type": "appotronics_dh_com",
      "port_name": "COM3",
      "baudrate": 9600
    }
  ]
}
```

**显示效果:**
- 品牌系列：光峰 DH 系列
- 连接方式：串口接入 (RS232) 🔌
- 串口：COM3 @ 9600

## 📋 配置层次

```
品牌 (Brand)
├── 光峰 (appotronics)
│   └── DH 系列 (dh)
│       ├── 网络接入 (TCP) - appotronics_dh_tcp
│       ├── 网络接入 (UDP) - appotronics_dh_udp
│       └── 串口接入 (RS232) - appotronics_dh_com
```

## 🔧 API 接口

### 获取品牌列表 (包含连接类型)

```bash
GET /api/projector/brands
```

**响应示例:**
```json
{
  "brands": [
    {
      "id": "appotronics_dh",
      "name": "光峰 DH 系列",
      "brand": "appotronics",
      "series": "dh",
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
      }
    }
  ]
}
```

### 获取品牌命令

```bash
GET /api/projector/brands?brand_id=appotronics_dh
```

**响应示例:**
```json
{
  "commands": [...],
  "brand_info": {
    "id": "appotronics_dh",
    "name": "光峰 DH 系列",
    "brand": "appotronics",
    "series": "dh"
  },
  "connection_types": {
    "tcp": {...},
    "udp": {...},
    "com": {...}
  }
}
```

## 🧪 测试验证

### 运行测试脚本

```bash
python test_dh_brand_connection.py
```

**输出示例:**
```
================================================================================
🔍 光峰 DH 系列品牌结构验证
================================================================================

✅ 品牌信息:
   品牌 ID: appotronics_dh
   品牌名称：光峰 DH 系列
   品牌标识：appotronics
   系列标识：dh
   显示名称：光峰 DH 系列

✅ 连接类型:

   🌐 网络接入 (TCP)
      类型 ID: appotronics_dh_tcp
      默认端口：9761

   🌐 网络接入 (UDP)
      类型 ID: appotronics_dh_udp
      默认端口：9761

   🔌 串口接入 (RS232)
      类型 ID: appotronics_dh_com
      默认端口：9600

--------------------------------------------------------------------------------
✅ 所有验证通过 - 品牌和连接类型已正确区分
================================================================================
```

## 📝 代码使用

### Python 代码

```python
from projector_core import (
    get_brand_info,
    get_connection_types,
    get_connection_type_name
)

# 获取品牌信息
brand = get_brand_info("appotronics_dh")
print(brand["name"])  # 光峰 DH 系列
print(brand["brand"]) # appotronics
print(brand["series"]) # dh

# 获取所有连接类型
conn_types = get_connection_types("appotronics_dh")
# 返回：{"tcp": {...}, "udp": {...}, "com": {...}}

# 获取连接类型名称
name = get_connection_type_name("appotronics_dh", "appotronics_dh_tcp")
print(name)  # 网络接入 (TCP)
```

### 前端 JavaScript

```javascript
// 获取品牌列表 (包含连接类型)
fetch('/api/projector/brands')
  .then(res => res.json())
  .then(data => {
    data.brands.forEach(brand => {
      console.log(`品牌：${brand.display_name}`);
      console.log(`品牌标识：${brand.brand}`);
      console.log(`系列：${brand.series}`);
      
      // 遍历连接类型
      Object.values(brand.connection_types).forEach(conn => {
        console.log(`${conn.icon} ${conn.name} - 端口：${conn.default_port}`);
      });
    });
  });
```

## 🎨 UI 显示建议

### 投影机配置界面

```
┌─────────────────────────────────────────────┐
│ 投影机配置                                  │
├─────────────────────────────────────────────┤
│ 品牌系列：[光峰 DH 系列 ▼]                  │
│                                             │
│ 连接方式：○ 网络接入 (TCP) 🌐              │
│           ○ 网络接入 (UDP) 🌐              │
│           ○ 串口接入 (RS232) 🔌            │
│                                             │
│ [网络接入选项]                              │
│ IP 地址：[192.168.50.110]                   │
│ 端口：  [9761]                              │
│                                             │
│ [串口接入选项] (如果选择串口)               │
│ 串口：  [COM3 ▼]                            │
│ 波特率：[9600 ▼]                            │
└─────────────────────────────────────────────┘
```

## ⚠️ 注意事项

1. **品牌区分**: 
   - `brand_id` 使用 `appotronics_dh` 格式 (品牌_系列)
   - 便于后续扩展其他系列 (如 appotronics_hd500)

2. **连接类型区分**:
   - `control_type` 使用 `appotronics_dh_tcp` 格式
   - 明确标识连接方式

3. **端口配置**:
   - 网络接入默认端口：9761
   - 串口接入默认波特率：9600
   - 支持自定义端口覆盖

4. **图标使用**:
   - 🌐 表示网络接入
   - 🔌 表示串口接入

## 📄 相关文件

- [`projector_brands.json`](./projector_brands.json) - 品牌配置
- [`projector_core.py`](./projector_core.py) - 驱动核心 (新增辅助函数)
- [`app.py`](./app.py) - API 接口 (已更新)
- [`test_dh_brand_connection.py`](./test_dh_brand_connection.py) - 测试工具

## 📚 相关文档

- [DH_PORT_CONFIG.md](./DH_PORT_CONFIG.md) - 端口配置说明
- [APPOTRONICS_DH_PROTOCOL.md](./APPOTRONICS_DH_PROTOCOL.md) - DH 系列协议
- [QUICK_CONFIG_GUIDE.md](./QUICK_CONFIG_GUIDE.md) - 快速配置指南

---

**更新时间**: 2026-03-23  
**版本**: v1.2 (品牌与连接类型区分)  
**状态**: ✅ 已完成并验证  
**特性**: 
- ✅ 品牌和型号区分
- ✅ 网络接入和串口接入区分
- ✅ 三种连接类型支持 (TCP/UDP/COM)
- ✅ 自动端口配置
- ✅ 自定义端口覆盖
