import os
import re
import shutil
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Dict, Tuple
from urllib.parse import urljoin

import pytz
from app.core.config import settings
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import NotificationType
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from webdav3.client import Client

lock = threading.Lock()


class WebDAVBackup(_PluginBase):
    # 插件名称
    plugin_name = "WebDAV备份"
    # 插件描述
    plugin_desc = "定时通过WebDAV备份。"
    # 插件图标
    plugin_icon = "https://github.com/InfinityPacer/MoviePilot-Plugins/raw/main/icons/webdavbackup.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "webdavbackup_"
    # 加载顺序
    plugin_order = 60
    # 可使用的用户级别
    auth_level = 1

    # region 私有属性

    # client
    _client = None
    # 是否开启
    _enabled = False
    # 任务执行间隔
    _cron = None
    # 最大备份数量
    _max_count = None
    # 服务器地址
    _hostname = None
    # 用户名
    _login = None
    # 密码
    _password = None
    # 是否使用Digest认证
    _digest_auth = False
    # 立即执行一次
    _onlyonce = False
    # 开启通知
    _notify = False
    # 定时器
    _scheduler = None
    # 退出事件
    _event = threading.Event()

    # endregion

    def init_plugin(self, config: dict = None):
        if not config:
            logger.info("WebDAV备份失败，无法获取插件配置")
            return False

        # 停止现有任务
        self.stop_service()

        self._enabled = config.get("enabled", False)
        self._cron = config.get("cron")
        self._notify = config.get("notify", False)
        self._onlyonce = config.get("onlyonce", False)
        try:
            self._max_count = int(config.get("max_count", 0))
        except ValueError:
            logger.error("配置错误: 'max_count' 必须是一个整数。使用默认值 0。")
            self._max_count = 0

        self._hostname = config.get('hostname')
        self._login = config.get('login')
        self._password = config.get('password')
        self._digest_auth = config.get('digest_auth', False)

        if not self._enabled:
            logger.info("WebDAV备份未启用")

        # 初始化 WebDAV 客户端
        webdav_config = {
            'webdav_hostname': self._hostname,
            'webdav_login': self._login,
            'webdav_password': self._password,
            'webdav_digest_auth': self._digest_auth
        }

        self._client = Client(webdav_config)
        if not self._client:
            logger.info("WebDAV客户端实例化失败，无法启动备份服务")
            return

        if not self.__connect_to_webdav():
            return

        self._scheduler = BackgroundScheduler(timezone=settings.TZ)
        if self._onlyonce:
            logger.info("WebDAV备份服务，立即运行一次")
            self._scheduler.add_job(
                func=self.backup,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name="WebDAV备份",
            )
            self._onlyonce = False

        # 启动任务
        if self._scheduler.get_jobs():
            self._scheduler.print_jobs()
            self._scheduler.start()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程控制命令
        :return: 命令关键字、事件、描述、附带数据
        """
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'onlyonce',
                                            'label': '立即运行一次',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'notify',
                                            'label': '开启通知',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'digest_auth',
                                            'label': '启用Digest认证'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 12
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'hostname',
                                            'label': '服务器地址'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'login',
                                            'label': '登录名'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'password',
                                            'label': '登录密码'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '备份周期'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'max_count',
                                            'label': '最大保留备份数'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '如备份失败，请检查日志，并确认WebDAV目录存在，如果存在中文字符，可以尝试进行Url编码后备份'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "notify": True
        }

    def get_page(self) -> List[dict]:
        pass

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        [{
            "id": "服务ID",
            "name": "服务名称",
            "trigger": "触发器：cron/interval/date/CronTrigger.from_crontab()",
            "func": self.xxx,
            "kwargs": {} # 定时器参数
        }]
        """
        services = []

        if self._enabled and self._cron:
            logger.info(f"WebDAV备份定时服务已开启，时间间隔 {self._cron} ")
            services.append({
                "id": "WebDAVBackup",
                "name": "WebDAV备份",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.backup,
                "kwargs": {}
            })

        if not services:
            logger.info("WebDAV备份定时服务未开启")

        return services

    def stop_service(self):
        """
        退出插件
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._event.set()
                    self._scheduler.shutdown()
                    self._event.clear()
                self._scheduler = None
        except Exception as e:
            print(str(e))

    def backup(self):
        logger.info("开始执行WebDAV备份")
        try:
            file, success = self.__backup_files_to_webdav()

            if self._max_count:
                self.__clean_old_backups(max_count=self._max_count)
            if success:
                logger.info(f"WebDAV备份成功, 文件路径: {file}")
                msg = f"备份成功"
            else:
                msg = "备份失败，请排查日志"
                logger.info(msg)
            if self._notify:
                self.__notify_user(msg)
        except Exception as e:
            msg = f"备份失败，请排查日志，错误：{e}"
            logger.error(msg)
            if self._notify:
                self.__notify_user(msg)

    def __backup_files_to_webdav(self) -> [str, bool]:
        """
        执行备份并上传到WebDAV服务器
        """
        file = self.__backup_and_zip_file()
        if not file:
            logger.error("无法创建备份文件")
            return None, False

        try:
            # 使用urljoin确保路径正确
            remote_file_path = urljoin(f'{self._hostname}/', os.path.basename(file))
            logger.info(f"远程备份路径为：{remote_file_path}")

            self._client.upload_sync(remote_path=os.path.basename(file), local_path=file)
            return os.path.basename(file), True
        except Exception as e:
            logger.error(f"上传到WebDAV服务器失败: {e}")
            if hasattr(e, 'response'):
                logger.error(f"服务器响应: {e.response.text}")
        finally:
            # 不论上传成功与否都清理本地文件
            if os.path.exists(file):
                logger.info(f"清理本地文件：{file}")
                os.remove(file)
        return None, False

    @staticmethod
    def __backup_and_zip_file() -> str:
        """备份文件并压缩成ZIP文件，按指定格式命名"""
        try:
            config_path = Path(settings.CONFIG_PATH)
            current_time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            backup_file_name = f"MoviePliot-Backup-{current_time}"
            backup_path = config_path / backup_file_name
            zip_file_path = str(backup_path) + '.zip'

            # 确保备份路径存在
            backup_path.mkdir(parents=True, exist_ok=True)

            # 需要备份的文件列表
            backup_files = [
                config_path / "user.db",
                config_path / "app.env",
                config_path / "category.yaml"
            ]

            # 将文件复制到备份文件夹
            for file_path in backup_files:
                logger.info(f"正在备份文件: {file_path}")
                if file_path.exists():
                    shutil.copy(file_path, backup_path)

            # 打包备份文件夹为ZIP
            shutil.make_archive(base_name=str(backup_path), format='zip', root_dir=str(backup_path))
            shutil.rmtree(backup_path)  # 删除临时备份文件夹

            logger.info(f"正在压缩备份文件: {zip_file_path}")
            return zip_file_path
        except Exception as e:
            logger.error(f"创建备份ZIP文件失败: {e}")
            return ""

    def __clean_old_backups(self, max_count):
        """
        清理旧的WebDAV备份文件
        """
        # 定义备份文件的正则表达式模式
        pattern = re.compile(r"MoviePliot-Backup-\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.zip")

        # 清理WebDAV服务器上的旧备份
        try:
            remote_files = self._client.list('/')
            logger.info(f"remote_files {remote_files}")
            filtered_files = [f for f in remote_files if pattern.match(f)]
            logger.info(f"filtered_files {filtered_files}")
            sorted_files = sorted(filtered_files,
                                  key=lambda x: datetime.strptime(x,
                                                                  "MoviePliot-Backup-%Y-%m-%d_%H-%M-%S.zip"))
            logger.info(f"sorted_files {sorted_files}")
            logger.info(f"sorted_files len {len(sorted_files)}")
            if len(sorted_files) > max_count:
                for file_info in sorted_files[:-max_count]:
                    remote_file_path = f"/{file_info}"
                    try:
                        self._client.clean(remote_file_path)
                        logger.info(f"WebDAV上的备份文件 {remote_file_path} 已删除")
                    except Exception as e:
                        logger.error(f"删除WebDAV文件 {remote_file_path} 失败: {e}")
        except Exception as e:
            logger.error(f"获取WebDAV文件列表失败: {e}")

    def __connect_to_webdav(self) -> bool:
        """尝试连接到WebDAV服务器，并验证连接是否成功。"""
        try:
            # 尝试列出根目录来检查连接
            files = self._client.list('/')  # 如果不成功，会抛出异常
            logger.info("成功连接到WebDAV服务器")
            return True
        except Exception as e:
            self._client = None
            logger.error(f"连接到WebDAV服务器失败: {e}")
            return False

    def __notify_user(self, message):
        """发送通知到用户，包括当前时间和消息内容"""
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        formatted_message = f"{message}，备份时间：{current_time}"
        self.post_message(
            mtype=NotificationType.SiteMessage,
            title="【WebDAV备份完成】",
            text=formatted_message
        )
