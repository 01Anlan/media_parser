# astrbot_plugin_media_parser

AstrBot 聚合解析插件。

## 功能概览

- 聚合解析
- 抖音主页解析
- 抖音收藏解析（默认停用，需独立部署）

核心实现位于 [`main.py`](README.md)，插件元数据位于 [`metadata.yaml`](metadata.yaml)。

## 支持的指令

| 指令 | 说明 | 状态 |
| --- | --- | --- |
| `/jx 分享链接` | 聚合解析，返回视频或图片资源链接 | 可用 |
| `/dyhome 抖音主页分享文本或链接` | 解析抖音主页并生成本地 TXT 文件 | 可用 |
| `/dyplay 文件名` | 顺序播放指定 TXT 中的视频链接 | 可用 |
| `/dycollection 抖音分享文本` | 抖音收藏解析 | 默认停用 |
| `/dycollection_query 任务ID` | 抖音收藏任务查询 | 默认停用 |

## 功能说明

### 聚合解析

- 指令：`/jx 分享链接`
- 处理函数：[`MediaParserPlugin.aggregate_parse()`](main.py:44)
- 特性：
  - 调用聚合解析接口
  - 自动识别常见平台
  - 仅返回视频和图片链接
  - 尽量过滤无关字段

### 抖音主页解析

- 指令：`/dyhome 抖音主页分享文本或链接`
- 处理函数：[`MediaParserPlugin.douyin_profile_parse()`](main.py:63)
- 特性：
  - 调用抖音主页解析接口
  - 将作品链接保存为本地 TXT 文件
  - 回复中仅保留下载信息与文件信息

示例返回：

```text
✅ 成功获取 93 个视频链接，文件已保存到 downloads 文件夹
📁 文件名: 某某_videos.txt
📥 下载链接：http://DOUYIN.ZHCNLI.CN/download.php?file=某某_videos.txt
```

相关实现：

- 输出格式化：[`MediaParserPlugin._format_douyin_profile_result()`](main.py:276)
- 文件名提取：[`MediaParserPlugin._extract_file_name()`](main.py:471)
- 域名转大写：[`MediaParserPlugin._uppercase_domain()`](main.py:542)

### 抖音收藏解析

> [!WARNING]
> 收藏解析功能已在插件内默认停用。该能力不能直接对接 `douyin.zhcnli.cn`，必须通过独立部署环境提供。

- 停用处理函数：[`MediaParserPlugin.douyin_collection_parse()`](main.py:125)
- 停用处理函数：[`MediaParserPlugin.douyin_collection_query()`](main.py:134)
- 独立部署说明：<https://blog.zhcnli.com/876.html>

当前插件中如果调用相关指令，仅会提示用户该功能不能直接对接 [`douyin.zhcnli.cn`](README.md:61)，并引导前往独立部署说明页面。

#### 如何取消注释并启用

如需重新启用收藏解析命令，需要修改 [`main.py`](main.py) 中这两个函数上方被注释掉的装饰器：

```python
# @filter.command("dycollection")
async def douyin_collection_parse(self, event: AstrMessageEvent):

# @filter.command("dycollection_query")
async def douyin_collection_query(self, event: AstrMessageEvent):
```

将其改回：

```python
@filter.command("dycollection")
async def douyin_collection_parse(self, event: AstrMessageEvent):

@filter.command("dycollection_query")
async def douyin_collection_query(self, event: AstrMessageEvent):
```

对应位置：

- [`MediaParserPlugin.douyin_collection_parse()`](main.py:125)
- [`MediaParserPlugin.douyin_collection_query()`](main.py:134)

启用后说明：

1. 取消注释后，AstrBot 才会重新注册 `/dycollection` 与 `/dycollection_query` 指令。
2. 当前函数内部已改为“仅提示独立部署”的返回逻辑；如果你要恢复真实收藏解析能力，还需要把这两个函数的提示逻辑改回原本的接口请求逻辑。
3. 抖音收藏功能不能直接对接 `douyin.zhcnli.cn` 现有接口，必须使用独立部署方案，建议优先参考 [独立部署说明](https://blog.zhcnli.com/876.html)。

## 配置说明

配置界面 schema 位于 [`_conf_schema.json`](_conf_schema.json)。AstrBot 会基于该文件生成图形化配置界面。

> [!IMPORTANT]
> 当前 schema 已移除默认 API Key 与默认收藏参数，使用前必须由部署者自行填写。

### 基础配置

```json
{
  "aggregate_api_key": "你的聚合解析密钥",
  "douyin_profile_api_key": "你的抖音主页解析密钥"
}
```

字段说明：

- [`aggregate_api_key`](_conf_schema.json)：聚合解析接口密钥
- [`douyin_profile_api_key`](_conf_schema.json)：抖音主页解析接口密钥

API Key 获取地址：

- 聚合解析 API Key：前往 <https://api.zhcnli.cn/> 获取
- 抖音主页解析 / 抖音收藏解析 API Key：前往 <https://douyin.zhcnli.cn/apikey_apply.php> 获取

### 扩展配置

```json
{
  "collection_email": "your@example.com",
  "collection_filename": "自定义收藏文件名",
  "debug_mode": false
}
```

字段说明：

- [`collection_email`](_conf_schema.json)：抖音收藏任务提交时使用的邮箱
- [`collection_filename`](_conf_schema.json)：抖音收藏任务提交时使用的导出文件名
- [`debug_mode`](_conf_schema.json)：是否开启调试模式

说明：

- 当前版本不会直接启用抖音收藏解析流程，上述收藏相关配置仅供独立部署方案对接时参考。
- 如果未填写 [`aggregate_api_key`](_conf_schema.json) 或 [`douyin_profile_api_key`](_conf_schema.json)，对应指令会直接提示“未配置 API 密钥”。

## 文件结构

- [`main.py`](main.py)：插件主逻辑
- [`metadata.yaml`](metadata.yaml)：插件元数据
- [`README.md`](README.md)：项目说明文档
- [`_conf_schema.json`](_conf_schema.json)：AstrBot 配置界面 schema

## 相关链接

- [独立部署说明](https://blog.zhcnli.com/876.html)
- [聚合解析 API Key 获取](https://api.zhcnli.cn/)
- [抖音主页 / 收藏解析 API Key 获取](https://douyin.zhcnli.cn/apikey_apply.php)
- [AstrBot Repo](https://github.com/AstrBotDevs/AstrBot)
- [AstrBot Plugin Development Docs (Chinese)](https://docs.astrbot.app/dev/star/plugin-new.html)
- [AstrBot Plugin Development Docs (English)](https://docs.astrbot.app/en/dev/star/plugin-new.html)
