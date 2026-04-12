import json
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote, unquote
from urllib.request import Request, urlopen

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Plain, Video
from astrbot.api.star import Context, Star, register


AGGREGATE_API = (
    "https://api.zhcnli.cn/API/jhjx.php"
    "?apikey={apikey}&url="
)
DOUYIN_PROFILE_API = (
    "http://douyin.zhcnli.cn/api.php"
    "?apikey={apikey}&url="
)
DOUYIN_COLLECTION_API = (
    "http://你的域名/api"
    "?apikey={apikey}"
)
URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")


@register("astrbot_plugin_media_parser", "Anlan", "聚合解析与抖音主页解析插件", "2.0.0")
class MediaParserPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.play_indexes: Dict[str, int] = {}
        self.config.save_config()

    async def initialize(self):
        logger.info("media_parser 插件已初始化")

    @filter.command("jx")
    async def aggregate_parse(self, event: AstrMessageEvent):
        """聚合解析：输入分享链接，仅返回视频和图片资源。"""
        target_url = self._extract_url(event.message_str)
        if not target_url:
            yield event.plain_result("用法：/jx 分享链接")
            return

        aggregate_api_key = self.config.get("aggregate_api_key", "")
        if not aggregate_api_key:
            yield event.plain_result("未配置聚合解析 API 密钥")
            return

        try:
            api_url = AGGREGATE_API.format(apikey=quote(aggregate_api_key, safe="")) + quote(target_url, safe="")
            payload = self._request_json(api_url)
        except Exception as exc:
            logger.exception("聚合解析失败: %s", exc)
            yield event.plain_result(f"聚合解析失败：{exc}")
            return

        message = self._format_aggregate_result(payload)
        yield event.plain_result(message)

    @filter.command("dyhome")
    async def douyin_profile_parse(self, event: AstrMessageEvent):
        """抖音主页解析：输入抖音主页分享文本或链接，返回作品链接与 TXT 下载地址。"""
        raw_text = self._extract_profile_text(event.message_str)
        if not raw_text:
            yield event.plain_result("用法：/dyhome 抖音主页分享文本或链接")
            return

        douyin_profile_api_key = self.config.get("douyin_profile_api_key", "")
        if not douyin_profile_api_key:
            yield event.plain_result("未配置抖音主页解析 API 密钥")
            return

        try:
            api_url = DOUYIN_PROFILE_API.format(apikey=quote(douyin_profile_api_key, safe="")) + quote(raw_text, safe="")
            payload = self._request_json(api_url)
        except Exception as exc:
            logger.exception("抖音主页解析失败: %s", exc)
            yield event.plain_result(f"抖音主页解析失败：{exc}")
            return

        download_info = self._save_profile_txt(payload)
        message = self._format_douyin_profile_result(payload, download_info)
        yield event.plain_result(message)

    @filter.command("dyplay")
    async def douyin_profile_play(self, event: AstrMessageEvent):
        """每次调用播放 TXT 中的一个视频链接。"""
        file_key = self._extract_dyplay_text(event.message_str)
        if not file_key:
            yield event.plain_result("用法：/dyplay 文件名")
            return

        file_path = self._find_download_txt(file_key)
        if not file_path:
            yield event.plain_result(f"未找到文件：{file_key}")
            return

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
                urls = [line.strip() for line in file if line.strip()]
        except Exception as exc:
            yield event.plain_result(f"读取文件失败：{exc}")
            return

        if not urls:
            yield event.plain_result("TXT 文件为空")
            return

        current_index = self.play_indexes.get(file_path, 0)
        if current_index >= len(urls):
            current_index = 0

        current_url = urls[current_index]
        self.play_indexes[file_path] = current_index + 1

        playable_url = self._resolve_direct_media_url(current_url)
        message_chain = [
            Plain(
                f"🎬 正在播放：{os.path.basename(file_path)}\n"
                f"📍 当前进度：{current_index + 1}/{len(urls)}\n"
                f"🔗 视频直链：{playable_url}"
            ),
            Video.fromURL(playable_url),
        ]
        yield event.chain_result(message_chain)

    # @filter.command("dycollection")
    async def douyin_collection_parse(self, event: AstrMessageEvent):
        """抖音收藏解析：无法直接对接 douyin.zhcnli.cn，需独立部署。"""
        yield event.plain_result(
            "抖音收藏解析功能无法直接对接 douyin.zhcnli.cn；该能力必须独立部署后使用。\n"
            "部署说明请查看：https://blog.zhcnli.com/876.html"
        )

    # @filter.command("dycollection_query")
    async def douyin_collection_query(self, event: AstrMessageEvent):
        """抖音收藏查询：无法直接对接 douyin.zhcnli.cn，需独立部署。"""
        yield event.plain_result(
            "抖音收藏查询功能无法直接对接 douyin.zhcnli.cn；该能力必须独立部署后使用。\n"
            "部署说明请查看：https://blog.zhcnli.com/876.html"
        )

    def _request_json(self, url: str) -> Dict[str, Any]:
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            },
        )

        with urlopen(request, timeout=20) as response:
            content = response.read().decode("utf-8", errors="ignore")

        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise ValueError("接口返回格式异常")
        return payload

    def _extract_url(self, text: str) -> Optional[str]:
        if not text:
            return None

        cleaned_text = text.strip()
        if cleaned_text.startswith("/jx"):
            cleaned_text = cleaned_text[3:].strip()

        match = URL_PATTERN.search(cleaned_text)
        return match.group(0) if match else None

    def _extract_profile_text(self, text: str) -> Optional[str]:
        if not text:
            return None

        cleaned_text = text.strip()
        if cleaned_text.startswith("/dyhome"):
            cleaned_text = cleaned_text[7:].strip()

        return cleaned_text or None

    def _extract_collection_text(self, text: str) -> Optional[str]:
        if not text:
            return None

        cleaned_text = text.strip()
        if cleaned_text.startswith("/dycollection"):
            cleaned_text = cleaned_text[len("/dycollection"):].strip()
        elif cleaned_text.startswith("dycollection"):
            cleaned_text = cleaned_text[len("dycollection"):].strip()

        return cleaned_text or None

    def _build_collection_submit_api(self, raw_text: str) -> str:
        douyin_profile_api_key = self.config.get("douyin_profile_api_key", "")
        collection_email = self.config.get("collection_email", "")
        collection_filename = self.config.get("collection_filename", "")
        return (
            f"{DOUYIN_COLLECTION_API.format(apikey=quote(douyin_profile_api_key, safe=''))}"
            f"&url={quote(raw_text, safe='')}"
            "&type=1"
            "&mode=collection"
            f"&email={quote(collection_email, safe='')}"
            f"&filename={quote(collection_filename, safe='')}"
            "&xz=1"
        )

    def _extract_collection_query_text(self, text: str) -> Optional[str]:
        if not text:
            return None

        cleaned_text = text.strip()
        if cleaned_text.startswith("/dycollection_query"):
            cleaned_text = cleaned_text[len("/dycollection_query"):].strip()
        elif cleaned_text.startswith("dycollection_query"):
            cleaned_text = cleaned_text[len("dycollection_query"):].strip()

        return cleaned_text or None

    def _format_aggregate_result(self, payload: Dict[str, Any]) -> str:
        code = payload.get("code")
        if code != 200:
            return f"聚合解析失败：{payload.get('msg', '接口未返回成功状态')}"

        data = payload.get("data") or {}
        if not isinstance(data, dict):
            return "聚合解析失败：接口 data 字段格式异常"

        platform = self._detect_platform(data)
        lines: List[str] = [f"✅ 解析成功：{payload.get('msg', '成功')}"]
        lines.append(f"🌐 平台：{platform}")

        author = data.get("author")
        title = data.get("title")
        if author:
            lines.append(f"👤 作者：{author}")
        if title:
            lines.append(f"📝 标题：{title}")

        video_url = self._pick_video_url(data)
        image_urls = self._pick_image_urls(data)
        image_count = len(image_urls)

        if video_url or image_urls:
            lines.append("📦 资源概览：")
            lines.append(f"- 视频：{'1 个' if video_url else '0 个'}")
            lines.append(f"- 图片：{image_count} 张")

        if video_url:
            lines.append("🎬 视频链接：")
            lines.append(video_url)
        if image_urls:
            lines.append("🖼️ 图片链接：")
            lines.extend([f"{index}. {item}" for index, item in enumerate(image_urls, start=1)])

        if not video_url and not image_urls:
            return "⚠️ 聚合解析完成，但未找到视频或图片链接"

        return "\n".join(lines)

    def _format_douyin_profile_result(self, payload: Dict[str, Any], download_info: Optional[Dict[str, str]] = None) -> str:
        code = payload.get("code")
        if code != 200:
            return f"抖音主页解析失败：{payload.get('msg', '接口未返回成功状态')}"

        author = str(payload.get("author") or "").strip()
        count = payload.get("count") or 0
        raw_download = self._extract_download_url(payload)
        download = self._uppercase_domain(raw_download) if raw_download else ""
        file_name = self._extract_file_name(download)

        if download_info:
            file_name = download_info.get("file_name") or file_name

        if not file_name and author:
            file_name = f"{author}.txt"

        if not download and file_name:
            download = self._uppercase_domain(
                f"http://douyin.zhcnli.cn/download.php?file={quote(file_name, safe='')}"
            )

        lines: List[str] = [f"✅ 成功获取 {count} 个视频链接，文件已保存到 downloads 文件夹"]
        if author:
            lines.append(f"👤 作者：{author}")
        if file_name:
            lines.append(f"📁 文件名: {file_name}")
            lines.append(f"📂 本地保存：{file_name}")
        if download:
            lines.append(f"📥 下载链接：{download}")
        else:
            fallback_file_name = self._extract_file_name(raw_download) or (f"{author}.txt" if author else "")
            if fallback_file_name:
                fallback_download = self._uppercase_domain(
                    f"http://douyin.zhcnli.cn/download.php?file={quote(fallback_file_name, safe='')}"
                )
                lines.append(f"📁 文件名: {fallback_file_name}")
                lines.append(f"📥 下载链接：{fallback_download}")
            else:
                lines.append("📥 下载链接：接口未返回下载地址")

        return "\n".join(lines)

    def _save_profile_txt(self, payload: Dict[str, Any]) -> Optional[Dict[str, str]]:
        data = payload.get("data")
        if not isinstance(data, list):
            return None

        author = str(payload.get("author") or "").strip() or "douyin_profile"
        file_name = f"{self._sanitize_file_name(author)}.txt"
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        file_path = os.path.join(DOWNLOAD_DIR, file_name)

        urls = [item.strip() for item in data if isinstance(item, str) and item.strip()]
        if not urls:
            return None

        with open(file_path, "w", encoding="utf-8") as file:
            file.write("\n".join(urls))

        return {"file_name": file_name, "file_path": file_path}

    def _sanitize_file_name(self, value: str) -> str:
        sanitized = re.sub(r'[\\/:*?"<>|]+', "_", value).strip()
        return sanitized or "douyin_profile"

    def _extract_dyplay_text(self, text: str) -> Optional[str]:
        if not text:
            return None
        cleaned_text = text.strip()
        if cleaned_text.startswith("/dyplay"):
            cleaned_text = cleaned_text[len("/dyplay"):].strip()
        elif cleaned_text.startswith("dyplay"):
            cleaned_text = cleaned_text[len("dyplay"):].strip()
        return cleaned_text or None

    def _find_download_txt(self, file_key: str) -> Optional[str]:
        normalized = self._sanitize_file_name(file_key)
        candidates = [
            os.path.join(DOWNLOAD_DIR, f"{normalized}.txt"),
            os.path.join(DOWNLOAD_DIR, normalized),
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
        return None

    def _resolve_direct_media_url(self, url: str) -> str:
        if not isinstance(url, str) or not url:
            return ""

        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            },
        )

        try:
            with urlopen(request, timeout=20) as response:
                final_url = response.geturl()
                return final_url or url
        except Exception as exc:
            logger.warning("直链访问失败，回退原链接: %s", exc)
            return url

    def _format_collection_submit_result(self, payload: Dict[str, Any]) -> str:
        msg = str(payload.get("msg") or "获取成功").strip()
        job_id = self._extract_job_id(payload)
        lines = [f"🕒 {msg}", "📌 任务状态：正在解析", "⏳ 正在等待后台解析完成..."]
        if job_id:
            lines.append(f"🆔 任务ID：{job_id}")
        return "\n".join(lines)

    def _build_collection_query_api(self, job_id: str) -> str:
        douyin_profile_api_key = self.config.get("douyin_profile_api_key", "")
        return (
            f"{DOUYIN_COLLECTION_API.format(apikey=quote(douyin_profile_api_key, safe=''))}"
            f"&job_id={quote(job_id, safe='')}"
        )

    def _format_collection_query_result(self, payload: Dict[str, Any], job_id: str) -> str:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        status = str(data.get("status") or payload.get("status") or "").strip().lower()
        if status != "done":
            return f"🕒 获取成功\n📌 任务状态：正在解析\n⏳ 正在等待后台解析完成...\n🆔 任务ID：{job_id}"

        return self._format_collection_done_result(payload)

    def _extract_job_id(self, payload: Dict[str, Any]) -> str:
        direct_job_id = str(payload.get("job_id") or "").strip()
        if direct_job_id:
            return direct_job_id

        data = payload.get("data")
        if isinstance(data, dict):
            nested_job_id = str(data.get("job_id") or "").strip()
            if nested_job_id:
                return nested_job_id

        query = str(payload.get("query") or "").strip()
        if query:
            match = re.search(r"[?&]job_id=([^&]+)", query, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        payload_text = json.dumps(payload, ensure_ascii=False)
        regex_patterns = [
            r'"job_id"\s*:\s*"([^"]+)"',
            r'[?&]job_id=([^&"\s]+)',
        ]
        for pattern in regex_patterns:
            match = re.search(pattern, payload_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return ""

    def _format_collection_done_result(self, payload: Dict[str, Any]) -> str:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        count = data.get("count") or 0
        file_name = str(data.get("filename") or "").strip()
        download_url = str(data.get("download_url") or "").strip()
        job_id = str(data.get("job_id") or "").strip()
        message = str(data.get("message") or payload.get("msg") or "解析完成").strip()

        if download_url:
            download_url = self._uppercase_domain(download_url)
        elif file_name:
            download_url = self._uppercase_domain(
                f"http://douyin.zhcnli.cn/download.php?file={quote(file_name, safe='')}"
            )

        lines = [f"✅ {message}"]
        if job_id:
            lines.append(f"🆔 任务ID：{job_id}")
        if file_name:
            lines.append(f"📁 文件名: {file_name}")
        if download_url:
            lines.append(f"📥 下载链接：{download_url}")
        return "\n".join(lines)

    def _extract_download_url(self, payload: Dict[str, Any]) -> str:
        direct_download = payload.get("download")
        if isinstance(direct_download, str) and direct_download.strip():
            return direct_download.strip()

        payload_text = json.dumps(payload, ensure_ascii=False)
        match = re.search(r'"download"\s*:\s*"(https?://[^"\\]+)"', payload_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        return ""

    def _extract_file_name(self, url: str) -> str:
        if not isinstance(url, str) or not url:
            return ""

        match = re.search(r"[?&]file=([^&]+)", url, re.IGNORECASE)
        if match:
            return unquote(match.group(1))

        tail = url.rsplit("/", 1)[-1]
        return tail or ""

    def _detect_platform(self, data: Dict[str, Any]) -> str:
        url_text = " ".join(self._collect_candidate_urls(data)).lower()
        if "douyin" in url_text or "aweme" in url_text:
            return "抖音"
        if "kuaishou" in url_text or "yximgs" in url_text or "djvod" in url_text:
            return "快手"
        if "xhscdn" in url_text or "xiaohongshu" in url_text:
            return "小红书"
        if "ppxvod" in url_text or "pipixia" in url_text:
            return "皮皮虾"
        if "izuiyou" in url_text:
            return "最右"
        if "bilivideo" in url_text or "bilibili" in url_text:
            return "哔哩哔哩"
        return "未知"

    def _pick_video_url(self, data: Dict[str, Any]) -> Optional[str]:
        candidates = [
            data.get("url"),
            data.get("video"),
            data.get("video_url"),
            data.get("play"),
            data.get("play_url"),
        ]

        videos = data.get("videos")
        if isinstance(videos, list):
            for item in videos:
                if isinstance(item, dict) and item.get("url"):
                    candidates.append(item.get("url"))

        for item in candidates:
            if isinstance(item, str) and item.startswith(("http://", "https://")):
                return item
        return None

    def _pick_image_urls(self, data: Dict[str, Any]) -> List[str]:
        candidates: List[str] = []
        for key in ["images", "image", "imgurl", "image_urls", "pics"]:
            value = data.get(key)
            if isinstance(value, list):
                candidates.extend(
                    item for item in value if isinstance(item, str) and item.startswith(("http://", "https://"))
                )
            elif isinstance(value, str) and value.startswith(("http://", "https://")):
                candidates.append(value)

        return candidates

    def _collect_candidate_urls(self, data: Dict[str, Any]) -> List[str]:
        urls: List[str] = []
        for value in data.values():
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                urls.append(value)
            elif isinstance(value, list):
                urls.extend(item for item in value if isinstance(item, str))
            elif isinstance(value, dict):
                urls.extend(self._collect_candidate_urls(value))
        return urls

    def _uppercase_domain(self, url: str) -> str:
        if not isinstance(url, str) or not url:
            return ""

        match = re.match(r"^(https?://)([^/]+)(.*)$", url, re.IGNORECASE)
        if not match:
            return url

        prefix, domain, rest = match.groups()
        return f"{prefix}{domain.upper()}{rest}"

    async def terminate(self):
        logger.info("media_parser 插件已卸载")
