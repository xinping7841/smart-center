smart_power_monitor/app.py
#!/usr/bin/env python3
"""
主应用入口
"""
import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from config_manager import ConfigManager

# 初始化日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # 实际部署时请使用随机密钥

# Flask-Login 初始化
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# 用户模型（示例）
class User(UserMixin):
    def __init__(self, id):
        self.id = id

users = {
    'admin': {'password': 'admin123'}  # 示例用户
}

@login_manager.user_loader
def load_user(user_id):
    if user_id in users:
        return User(user_id)
    return None

# 初始化配置
config = Config()
config_manager = ConfigManager(config)

# 主页
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username in users and users[username]['password'] == password:
            user = User(username)
            login_user(user)
            return redirect(url_for('config_page'))
        flash('用户名或密码错误')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# 配置管理页面路由
@app.route('/config')
@login_required
def config_page():
    current_config = config.config_data()
    available_configs = config_manager.get_available_configs()
    return render_template('config.html', 
                          current_config=current_config,
                          available_configs=available_configs)

# 配置 API
@app.route('/api/config', methods=['GET', 'POST'])
@login_required
def config_handler():
    if request.method == 'POST':
        try:
            action = request.form.get('action', 'update')
            
            if action == 'update':
                # 获取 JSON 数据
                config_data = request.get_json()
                
                # 更新配置（仅更新允许的字段）
                modbus_fields = ['modbus_port', 'modbus_baudrate', 'modbus_timeout', 'modbus_retry_count']
                threshold_fields = ['power_threshold', 'voltage_min', 'voltage_max', 'current_threshold', 'door_timeout']
                logging_fields = ['log_level', 'log_file']
                
                if 'modbus' in config_data:
                    for k, v in config_data['modbus'].items():
                        if k in modbus_fields:
                            config.set(k, v)
                
                if 'thresholds' in config_data:
                    for k, v in config_data['thresholds'].items():
                        if k in threshold_fields:
                            config.set(k, v)
                
                if 'logging' in config_data:
                    for k, v in config_data['logging'].items():
                        if k in logging_fields:
                            config.set(k, v)
                
                # 保存
                config.save_config()
                config_manager.save_current_config()
                
                return jsonify({'status': 'success', 'message': '配置已更新并保存'})
            
            elif action == 'export':
                export_file = request.form.get('export_file')
                if not export_file:
                    return jsonify({'status': 'error', 'message': '未指定导出文件路径'})
                
                success = config_manager.export_config(export_file)
                if success:
                    return jsonify({'status': 'success', 'message': '配置已导出', 'file': export_file})
                else:
                    return jsonify({'status': 'error', 'message': '导出失败'})
            
            elif action == 'import':
                import_file = request.form.get('import_file')
                if not import_file:
                    return jsonify({'status': 'error', 'message': '未指定导入文件路径'})
                
                success = config_manager.import_config(import_file)
                if success:
                    config.save_config()
                    return jsonify({'status': 'success', 'message': '配置已导入'})
                else:
                    return jsonify({'status': 'error', 'message': '导入失败'})
            
            elif action == 'reset':
                success = config_manager.reset_to_default()
                if success:
                    config.save_config()
                    return jsonify({'status': 'success', 'message': '已重置为默认配置'})
                else:
                    return jsonify({'status': 'error', 'message': '重置失败'})
            
            elif action == 'list':
                configs = config_manager.get_available_configs()
                return jsonify({'status': 'success', 'configs': configs})
            
            else:
                return jsonify({'status': 'error', 'message': '未知操作'})
                
        except Exception as e:
            logger.error(f"配置处理失败: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': str(e)})
    
    else:  # GET
        current_config = config.config_data()
        available_configs = config_manager.get_available_configs()
        return jsonify({
            'status': 'success',
            'current_config': current_config,
            'available_configs': available_configs
        })

if __name__ == '__main__':
    # 启动前确保数据目录存在
    config.data_dir.mkdir(exist_ok=True)
    config.log_dir.mkdir(exist_ok=True)
    
    # 启动应用
    app.run(host='0.0.0.0', port=5000, debug=True)smart_power_monitor/templates/config.html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>配置管理</title>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css">
</head>
<body>
<div class="container mt-4">
    <h1>配置管理</h1>

    <!-- Tab Nav -->
    <ul class="nav nav-tabs mb-3">
        <li class="nav-item"><a class="nav-link active" data-bs-toggle="tab" href="#current">当前配置</a></li>
        <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#import">导入配置</a></li>
        <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#backup">备份管理</a></li>
    </ul>

    <!-- Tab Content -->
    <div class="tab-content">
        <!-- 当前配置 -->
        <div class="tab-pane fade show active" id="current">
            <div class="card">
                <div class="card-header">
                    <h5>当前配置</h5>
                </div>
                <div class="card-body">
                    <form id="configForm">
                        <div class="row">
                            <div class="col-md-6">
                                <h6>Modbus配置</h6>
                                <div class="mb-3">
                                    <label class="form-label">端口</label>
                                    <input type="text" class="form-control" id="modbus_port" value="{{ current_config.modbus.port }}">
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">波特率</label>
                                    <input type="number" class="form-control" id="modbus_baudrate" value="{{ current_config.modbus.baudrate }}">
                                </div>
smart_power_monitor/config_mansmart_power_monitor/config.py
#!/usr/bin/env python3
"""
配置管理模块
"""
import os
import json
import logging
from pathlib import Path
from datetime import datetime

# 创建日志记录器（如果尚未初始化）
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Config:
    """配置类"""
    
    def __init__(self):
        """初始化配置"""
        # Modbus配置
        self.modbus_port = "/dev/ttyUSB0"
        self.modbus_baudrate = 9600
        self.modbus_timeout = 10
        self.modbus_retry_count = 3
        
        # 阈值配置
        self.power_threshold = 2000
        self.voltage_min = 210
        self.voltage_max = 250
        self.current_threshold = 15
        self.door_timeout = 300
        
        # 日志配置
        self.log_level = "INFO"
        self.log_file = "smart_power_monitor.log"
        
        # 路径配置
        self.data_dir = Path(__file__).parent / "data"
        self.log_dir = Path(__file__).parent / "logs"
        
        # 日志文件名
        self.energy_log_file = "energy_log.json"
        self.operation_log_file = "operation_logs.json"
        
        # 确保目录存在
        self.data_dir.mkdir(exist_ok=True)
        self.log_dir.mkdir(exist_ok=True)
        
        # 尝试加载保存的配置
        self._load_saved_config()
    
    def _load_saved_config(self):
        """加载保存的配置"""
        saved_config_file = Path(__file__).parent / "config.json"
        if saved_config_file.exists():
            try:
                with open(saved_config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                # 更新配置
                if "modbus" in config_data:
                    self.modbus_port = config_data["modbus"].get("port", self.modbus_port)
                    self.modbus_baudrate = config_data["modbus"].get("baudrate", self.modbus_baudrate)
                    self.modbus_timeout = config_data["modbus"].get("timeout", self.modbus_timeout)
                    self.modbus_retry_count = config_data["modbus"].get("retry_count", self.modbus_retry_count)
                
                if "thresholds" in config_data:
                    self.power_threshold = config_data["thresholds"].get("power_threshold", self.power_threshold)
                    self.voltage_min = config_data["thresholds"].get("voltage_min", self.voltage_min)
                    self.voltage_max = config_data["thresholds"].get("voltage_max", self.voltage_max)
                    self.current_threshold = config_data["thresholds"].get("current_threshold", self.current_threshold)
                    self.door_timeout = config_data["thresholds"].get("door_timeout", self.door_timeout)
                
                if "logging" in config_data:
                    self.log_level = config_data["logging"].get("log_level", self.log_level)
                    self.log_file = config_data["logging"].get("log_file", self.log_file)
                
                if "paths" in config_data:
                    if "data_dir" in config_data["paths"]:
                        self.data_dir = Path(config_data["paths"]["data_dir"])
                        self.data_dir.mkdir(exist_ok=True)
                    if "log_dir" in config_data["paths"]:
                        self.log_dir = Path(config_data["paths"]["log_dir"])
                        self.log_dir.mkdir(exist_ok=True)
                
                logger.info("已加载保存的配置")
            except Exception as e:
                logger.error(f"加载配置失败: {e}")
    
    def set(self, key, value):
        """设置配置项"""
        if hasattr(self, key):
            setattr(self, key, value)
            return True
        return False
    
    def get(self, key):
        """获取配置项"""
        if hasattr(self, key):
            return getattr(self, key)
        return None
    
    def config_data(self):
        """返回配置数据字典"""
        return {
            "timestamp": datetime.now().isoformat(),
            "modbus": {
                "port": self.modbus_port,
                "baudrate": self.modbus_baudrate,
                "timeout": self.modbus_timeout,
                "retry_count": self.modbus_retry_count
            },
            "thresholds": {
                "power_threshold": self.power_threshold,
                "voltage_min": self.voltage_min,
                "voltage_max": self.voltage_max,
                "current_threshold": self.current_threshold,
                "door_timeout": self.door_timeout
            },
            "logging": {
                "log_level": self.log_level,
                "log_file": self.log_file
            },
            "paths": {
                "data_dir": str(self.data_dir),
                "log_dir": str(self.log_dir)
            }
        }
    
    def save_config(self):
        """保存配置到 config.json"""
        config_data = self.config_data()
        saved_config_file = Path(__file__).parent / "config.json"
        try:
            with open(saved_config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
            logger.info("配置已保存到 config.json")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")

    def export_config(self, export_file):
        """导出配置到指定文件"""
        try:
            config_data = self.config_data()
            with open(export_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
            logger.info(f"配置已导出到 {export_file}")
            return True
        except Exception as e:
            logger.error(f"导出配置失败: {e}")
            return False

    def import_config(self, import_file):
        """从指定文件导入配置"""
        try:
            with open(import_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # 更新配置
            if "modbus" in config_data:
                self.modbus_port = config_data["modbus"].get("port", self.modbus_port)
                self.modbus_baudrate = config_data["modbus"].get("baudrate", self.modbus_baudrate)
                self.modbus_timeout = config_data["modbus"].get("timeout", self.modbus_timeout)
                self.modbus_retry_count = config_data["modbus"].get("retry_count", self.modbus_retry_count)
            
            if "thresholds" in config_data:
                self.power_threshold = config_data["thresholds"].get("power_threshold", self.power_threshold)
                self.voltage_min = config_data["thresholds"].get("voltage_min", self.voltage_min)
                self.voltage_max = config_data["thresholds"].get("voltage_max", self.voltage_max)
                self.current_threshold = config_data["thresholds"].get("current_threshold", self.current_threshold)
                self.door_timeout = config_data["thresholds"].get("door_timeout", self.door_timeout)
            
            if "logging" in config_data:
                self.log_level = config_data["logging"].get("log_level", self.log_level)
                self.log_file = config_data["logging"].get("log_file", self.log_file)
            
            if "paths" in config_data:
                if "data_dir" in config_data["paths"]:
                    self.data_dir = Path(config_data["paths"]["data_dir"])
                    self.data_dir.mkdir(exist_ok=True)
                if "log_dir" in config_data["paths"]:
                    self.log_dir = Path(config_data["paths"]["log_dir"])
                    self.log_dir.mkdir(exist_ok=True)
            
            logger.info(f"配置已从 {import_file} 导入")
            return True
        except Exception as e:
            logger.error(f"导入配置失败: {e}")
            return False

    def get_config_info(self):
        """获取配置信息"""
        return {
            "modbus_port": self.modbus_port,
            "modbus_baudrate": self.modbus_baudrate,
            "modbus_timeout": self.modbus_timeout,
            "modbus_retry_count": self.modbus_retry_count,
            "power_threshold": self.power_threshold,
            "voltage_min": self.voltage_min,
            "voltage_max": self.voltage_max,
            "current_threshold": self.current_threshold,
            "door_timeout": self.door_timeout,
            "log_level": self.log_level,
            "log_file": self.log_file,
            "data_dir": str(self.data_dir),
            "log_dir": str(self.log_dir)
        }smart_power_monitor/config_manager.py
#!/usr/bin/env python3
"""
配置管理器
"""
import os
import json
import logging
from pathlib import Path
from datetime import datetime

# 创建日志记录器
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config):
        self.config = config
        self.backup_dir = Path(__file__).parent / "backups"
        self.backup_dir.mkdir(exist_ok=True)
    
    def save_current_config(self):
        """保存当前配置到备份目录"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = self.backup_dir / f"config_backup_{timestamp}.json"
            config_data = self.config.config_data()
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
            logger.info(f"配置已备份到 {backup_file}")
            return True
        except Exception as e:
            logger.error(f"备份配置失败: {e}")
            return False
    
    def get_available_configs(self):
        """获取可用的配置文件列表"""
        try:
            configs = []
            for file in self.backup_dir.glob("config_backup_*.json"):
                configs.append({
                    "name": file.name,
                    "path": str(file),
                    "timestamp": file.stat().st_mtime
                })
            configs.sort(key=lambda x: x["timestamp"], reverse=True)
            return configs
        except Exception as e:
            logger.error(f"获取配置列表失败: {e}")
            return []
    
    def export_config(self, export_file):
        """导出当前配置"""
        return self.config.export_config(export_file)
    
    def import_config(self, import_file):
        """导入配置"""
        return self.config.import_config(import_file)
    
    def reset_to_default(self):
        """重置为默认配置"""
        try:
            # 重新初始化默认配置
            self.config = Config()  # 这里需要导入Config类
            self.config.save_config()
            logger.info("已重置为默认配置")
            return True
        except Exception as e:
            logger.error(f"重置配置失败: {e}")
            return Falsesmart_power_monitor/app.py
#!/usr/bin/env python3
"""
主应用入口
"""
import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

# 导入配置模块
from config import Config

# 初始化日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # 实际部署时请使用随机密钥

# Flask-Login 初始化
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# 用户模型（示例）
class User(UserMixin):
    def __init__(self, id):
        self.id = id

users = {
    'admin': {'password': 'admin123'}  # 示例用户
}

@login_manager.user_loader
def load_user(user_id):
    if user_id in users:
        return User(user_id)
    return None

# 初始化配置
config = Config()

# 主页
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username in users and users[username]['password'] == password:
            user = User(username)
            login_user(user)
            return redirect(url_for('config_page'))
        flash('用户名或密码错误')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# 配置管理页面路由
@app.route('/config')
@login_required
def config_page():
    current_config = config.config_data()
    return render_template('config.html', current_config=current_config)

# 配置 API
@app.route('/api/config', methods=['GET', 'POST'])
@login_required
def config_handler():
    if request.method == 'POST':
        try:
            action = request.form.get('action', 'update')
            
            if action == 'update':
                # 获取 JSON 数据
                config_data = request.get_json()
                
                # 更新配置（仅更新允许的字段）
                modbus_fields = ['modbus_port', 'modbus_baudrate', 'modbus_timeout', 'modbus_retry_count']
                threshold_fields = ['power_threshold', 'voltage_min', 'voltage_max', 'current_threshold', 'door_timeout']
                logging_fields = ['log_level', 'log_file']
                
                if 'modbus' in config_data:
                    for k, v in config_data['modbus'].items():
                        if k in modbus_fields:
                            config.set(k, v)
                
                if 'thresholds' in config_data:
                    for k, v in config_data['thresholds'].items():
                        if k in threshold_fields:
                            config.set(k, v)
                
                if 'logging' in config_data:
                    for k, v in config_data['logging'].items():
                        if k in logging_fields:
                            config.set(k, v)
                
                # 保存
                config.save_config()
                
                return jsonify({'status': 'success', 'message': '配置已更新并保存'})
            
            elif action == 'export':
                export_file = request.form.get('export_file')
                if not export_file:
                    return jsonify({'status': 'error', 'message': '未指定导出文件路径'})
                
                success = config.export_config(export_file)
                if success:
                    return jsonify({'status': 'success', 'message': '配置已导出', 'file': export_file})
                else:
                    return jsonify({'status': 'error', 'message': '导出失败'})
            
            elif action == 'import':
                import_file = request.form.get('import_file')
                if not import_file:
                    return jsonify({'status': 'error', 'message': '未指定导入文件路径'})
                
                success = config.import_config(import_file)
                if success:
                    config.save_config()
                    return jsonify({'status': 'success', 'message': '配置已导入'})
                else:
                    return jsonify({'status': 'error', 'message': '导入失败'})
            
            elif action == 'reset':
                # 重置为默认配置
                config = Config()  # 重新初始化默认配置
                config.save_config()
                return jsonify({'status': 'success', 'message': '已重置为默认配置'})
            
            else:
                return jsonify({'status': 'error', 'message': '未知操作'})
                
        except Exception as e:
            logger.error(f"配置处理失败: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': str(e)})
    
    else:  # GET
        current_config = config.config_data()
        return jsonify({
            'status': 'success',
            'current_config': current_config
        })

if __name__ == '__main__':
    # 启动前确保数据目录存在
    config.data_dir.mkdir(exist_ok=True)
    config.log_dir.mkdir(exist_ok=True)
    
    # 启动应用
    app.run(host='0.0.0.0', port=5000, debug=True)smart_power_monitor/templates/config.html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>配置管理</title>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css">
</head>
<body>
<div class="container mt-4">
    <h1>配置管理</h1>

    <!-- 当前配置 -->
    <div class="card mb-4">
        <div class="card-header">
            <h5>当前配置</h5>
        </div>
        <div class="card-body">
            <form id="configForm">
                <div class="row">
                    <div class="col-md-6">
                        <h6>Modbus配置</h6>
                        <div class="mb-3">
                            <label class="form-label">端口</label>
                            <input type="text" class="form-control" id="modbus_port" value="{{ current_config.modbus.port }}">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">波特率</label>
                            <input type="number" class="form-control" id="modbus_baudrate" value="{{ current_config.modbus.baudrate }}">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">超时时间</label>
                            <input type="number" class="form-control" id="modbus_timeout" value="{{ current_config.modbus.timeout }}">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">重试次数</label>
                            <input type="number" class="form-control" id="modbus_retry_count" value="{{ current_config.modbus.retry_count }}">
                        </div>
                    </div>
                    <div class="col-md-6">
                        <h6>阈值配置</h6>
                        <div class="mb-3">
                            <label class="form-label">功率阈值</label>
                            <input type="number" class="form-control"y
#!/usr/bin/env python3
"""
配置管理器
"""
import os
import json
import logging
from pathlib import Path
from datetime import datetime

# 创建日志记录器
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config):
        self.config = config
        self.backup_dir = Path(__file__).parent / "backups"
        self.backup_dir.mkdir(exist_ok=True)
    
    def save_current_config(self):
        """保存当前配置到备份目录"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = self.backup_dir / f"config_backup_{timestamp}.json"
            config_data = self.config.config_data()
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
            logger.info(f"配置已备份到 {backup_file}")
            return True
        except Exception as e:
            logger.error(f"备份配置失败: {e}")
            return False
    
    def get_available_configs(self):
        """获取可用的配置文件列表"""
        try:
            configs = []
            for file in self.backup_dir.glob("config_backup_*.json"):
                configs.append({
                    "name": file.name,
                    "path": str(file),
                    "timestamp": file.stat().st_mtime
                })
            configs.sort(key=lambda x: x["timestamp"], reverse=True)
            return configs
        except Exception as e:
            logger.error(f"获取配置列表失败: {e}")
            return []
    
    def export_config(self, export_file):
        """导出当前配置"""
        return self.config.export_config(export_file)
    
    def import_config(self, import_file):
        """导入配置"""
        return self.config.import_config(import_file)
    
    def reset_to_default(self):
        """重置为默认配置"""
        try:
            # 重置为默认值
            self.config = Config()  # 重新初始化默认配置
            self.config.save_config()
            logger.info("已重置为默认配置")
            return True
        except Exception as e:
            logger.error(f"重置配置失败: {e}")
            return False#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
视美乐指令格式转换工具
将所有指令转换为带感叹号的格式
"""

def str_to_hex(cmd_str):
    """将字符串转换为 16 进制格式"""
    return ' '.join(f'{b:02X}' for b in cmd_str.encode('utf-8'))

# 视美乐指令列表 (带感叹号格式)
commands = [
    # 电源控制
    {"id": "power_on", "name": "开机", "cmd": "#PWR0,1!", "sort": 1, "icon": "🔌", "show_on_home": True},
    {"id": "power_off", "name": "关机", "cmd": "#PWR0,0!", "sort": 2, "icon": "🔌", "show_on_home": True},
    
    # 信号源
    {"id": "source_pc", "name": "切换至 PC", "cmd": "#SOUR0,01!", "sort": 3, "icon": "💻", "show_on_home": True},
    {"id": "source_hdmi1", "name": "切换至 HDMI1", "cmd": "#SOUR0,17!", "sort": 4, "icon": "📺", "show_on_home": True},
    {"id": "source_hdmi2", "name": "切换至 HDMI2", "cmd": "#SOUR0,18!", "sort": 5, "icon": "📺", "show_on_home": True},
    {"id": "source_dp", "name": "切换至 DP", "cmd": "#SOUR0,19!", "sort": 6, "icon": "🖥️", "show_on_home": True},
    {"id": "source_vga", "name": "切换至 VGA", "cmd": "#SOUR0,02!", "sort": 7, "icon": "🖥️", "show_on_home": False},
    {"id": "source_dvi", "name": "切换至 DVI", "cmd": "#SOUR0,03!", "sort": 8, "icon": "🖥️", "show_on_home": False},
    
    # 静音控制
    {"id": "mute_on", "name": "静音开启", "cmd": "#AVMT0,01!", "sort": 9, "icon": "🔇", "show_on_home": False},
    {"id": "mute_off", "name": "静音关闭", "cmd": "#AVMT0,00!", "sort": 10, "icon": "🔊", "show_on_home": False},
    
    # 冻结
    {"id": "freeze_on", "name": "冻结开启", "cmd": "#FRZ0,01!", "sort": 11, "icon": "❄️", "show_on_home": False},
    {"id": "freeze_off", "name": "冻结关闭", "cmd": "#FRZ0,00!", "sort": 12, "icon": "❄️", "show_on_home": False},
    
    # 音量控制
    {"id": "volume_up", "name": "音量增加", "cmd": "#VOL0,1!", "sort": 13, "icon": "🔊", "show_on_home": False},
    {"id": "volume_down", "name": "音量减少", "cmd": "#VOL0,0!", "sort": 14, "icon": "🔉", "show_on_home": False},
    
    # 菜单控制
    {"id": "menu_on", "name": "菜单开启", "cmd": "#MENU0,01!", "sort": 15, "icon": "📋", "show_on_home": False},
    {"id": "menu_off", "name": "菜单关闭", "cmd": "#MENU0,00!", "sort": 16, "icon": "📋", "show_on_home": False},
    
    # 方向键
    {"id": "key_up", "name": "上键", "cmd": "#KEY0,01!", "sort": 17, "icon": "⬆️", "show_on_home": False},
    {"id": "key_down", "name": "下键", "cmd": "#KEY0,02!", "sort": 18, "icon": "⬇️", "show_on_home": False},
    {"id": "key_left", "name": "左键", "cmd": "#KEY0,03!", "sort": 19, "icon": "⬅️", "show_on_home": False},
    {"id": "key_right", "name": "右键", "cmd": "#KEY0,04!", "sort": 20, "icon": "➡️", "show_on_home": False},
    {"id": "key_enter", "name": "确认键", "cmd": "#KEY0,05!", "sort": 21, "icon": "✅", "show_on_home": False},
    
    # 退出
    {"id": "key_exit", "name": "退出", "cmd": "#KEY0,06!", "sort": 22, "icon": "❌", "show_on_home": False},
    
    # 自动调整
    {"id": "auto_adjust", "name": "自动调整", "cmd": "#AUTO0,01!", "sort": 23, "icon": "⚙️", "show_on_home": False},
    
    # 灯泡模式
    {"id": "lamp_eco_on", "name": "节能模式开", "cmd": "#LAMP0,01!", "sort": 24, "icon": "🌱", "show_on_home": False},
    {"id": "lamp_normal", "name": "正常模式", "cmd": "#LAMP0,00!", "sort": 25, "icon": "💡", "show_on_home": False},
    
    # 查询指令 (不带感叹号，因为是查询)
    {"id": "get_power_status", "name": "查询电源", "cmd": "#PWR0,?", "sort": 26, "icon": "🔌", "show_on_home": False},
    {"id": "get_source", "name": "查询信号源", "cmd": "#SOUR0,?", "sort": 27, "icon": "📺", "show_on_home": False},
    {"id": "get_volume", "name": "查询音量", "cmd": "#VOL0,?", "sort": 28, "icon": "🔊", "show_on_home": False},
    {"id": "get_mute", "name": "查询静音", "cmd": "#AVMT0,?", "sort": 29, "icon": "🔇", "show_on_home": False},
    {"id": "get_temp", "name": "查询温度", "cmd": "#TEMP0,?", "sort": 30, "icon": "🌡️", "show_on_home": False},
    {"id": "get_lamp_hours", "name": "查询灯泡时长", "cmd": "#LAMP0,?", "sort": 31, "icon": "⏱️", "show_on_home": False},
]

def main():
    print("\n" + "="*80)
    print("📋 视美乐 EK 系列指令列表 (带感叹号格式)")
    print("="*80)
    
    for cmd in commands:
        hex_val = str_to_hex(cmd["cmd"])
        print(f"\n{cmd['icon']} {cmd['name']} ({cmd['id']})")
        print(f"   字符串：{cmd['cmd']}")
        print(f"   16 进制：{hex_val}")
        print(f"   排序：{cmd['sort']}")
        print(f"   主页显示：{'是' if cmd['show_on_home'] else '否'}")
    
    print(f"\n{'='*80}")
    print(f"💡 说明:")
    print(f"   1. 所有控制指令都以 ! 结尾 (0x21)")
    print(f"   2. 查询指令以 ? 结尾 (0x3F)")
    print(f"   3. 设备 ID 可配置，默认 30")
    print(f"   4. 指令格式：#CMD{ID},{param}!")
    print()

if __name__ == "__main__":
    main()


