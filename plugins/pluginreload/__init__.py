from typing import Any, List, Dict, Tuple

from app.core.plugin import PluginManager
from app.log import logger
from app.plugins import _PluginBase
from app.scheduler import Scheduler


class PluginReload(_PluginBase):
    # 插件名称
    plugin_name = "插件热重载"
    # 插件描述
    plugin_desc = "支持插件热重载，用于Docker调试。"
    # 插件图标
    plugin_icon = "https://github.com/InfinityPacer/MoviePilot-Plugins/raw/main/icons/reload.png"
    # 插件版本
    plugin_version = "1.3"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "pluginreload_"
    # 加载顺序
    plugin_order = 99
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    _plugin_id = None
    _previous_state = False

    def init_plugin(self, config: dict = None):
        if config:
            self._previous_state = config.get("previous_state", None)
            self._plugin_id = config.get("plugin_id", None)
            if not self._plugin_id:
                self.__update_config()
                return

            self.__update_config()
            self.__reload(plugin_id=self._plugin_id)

    def get_state(self):
        pass

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        plugin_manager = PluginManager()
        # 获取本地所有插件的列表
        local_plugins = plugin_manager.get_local_plugins()
        # 遍历 local_plugins，生成插件类型选项
        plugin_options = []

        for index, local_plugin in enumerate(local_plugins, start=1):
            plugin_options.append({
                "title": f"{index}. {local_plugin.plugin_name} v{local_plugin.plugin_version}",
                "value": local_plugin.id
            })

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
                                    'md': 8
                                },
                                'content': [
                                    {
                                        'component': 'VAutocomplete',
                                        'props': {
                                            'multiple': False,
                                            'model': 'plugin_id',
                                            'label': '插件重载',
                                            'items': plugin_options,
                                            "clearable": True
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'previous_state',
                                            'label': '记住上一次',
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
                                            'text': '请选择已安装的本地插件，保存后对应插件将会在内存中重新加载'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "plugin_id": "",
            "previous_state": True,
        }

    def get_page(self) -> List[dict]:
        pass

    def stop_service(self):
        """
        退出插件
        """
        pass

    @staticmethod
    def __reload(plugin_id: str):
        logger.info(f"准备热加载插件: {plugin_id}")

        # 加载插件到内存
        try:
            PluginManager().reload_plugin(plugin_id)
            logger.info(f"成功热加载插件: {plugin_id} 到内存")
        except Exception as e:
            logger.error(f"失败热加载插件: {plugin_id} 到内存. 错误信息: {e}")
            return

        # 注册插件服务
        try:
            Scheduler().update_plugin_job(plugin_id)
            logger.info(f"成功热加载插件到插件服务: {plugin_id}")
        except Exception as e:
            logger.error(f"失败热加载插件到插件服务: {plugin_id}. 错误信息: {e}")
            return

        logger.info(f"已完成插件热加载: {plugin_id}")

    def __update_config(self):
        """
        更新配置
        """
        config_mapping = {}
        if self._plugin_id != "PluginReload":
            config_mapping['previous_state'] = self._previous_state
            if self._previous_state:
                config_mapping["plugin_id"] = self._plugin_id

        self.update_config(config_mapping)
