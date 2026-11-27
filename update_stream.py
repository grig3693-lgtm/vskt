import json
import os
import re
import subprocess
import sys
import time
from urllib.parse import urljoin, urlparse
import urllib.request

# Փոխեք այս արժեքները ձեր ռեպոզիտորիայի տվյալներով (կամ փոխանցեք Environment Variable-ով)
REPO_OWNER = os.getenv("REPO_OWNER", "grig3693-lgtm")
REPO_NAME = os.getenv("REPO_NAME", "vskt")
BRANCH = os.getenv("GIT_BRANCH", "main")
PLAYLIST_FILE = "playlist.m3u"

VIJU_REFRESH_URL = "https://api.viju.ru/v2/sessions/refresh"
VIJU_PLAYLIST_URL_TEMPLATE = "https://api.viju.ru/api/v1/tv/channels/viju-tv1000-novella/playlist"

# Դադար հարցումների միջև (վայրկյաններով)
REQUEST_DELAY_SECONDS = 1.5

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

STREAMS = [
    {
        "name": "OK Live 1",
        "group": "OK Live",
        "tvg_id": "ok.live.664807546380",
        "tvg_logo": "",
        "url": "https://ok.ru/live/664807546380",
        "output": "stream1.m3u8",
        "referer": "https://ok.ru/live/664807546380",
        "origin": "https://ok.ru",
        "user_agent": DEFAULT_USER_AGENT,
    },
    {
        "name": "OK Live 2",
        "group": "OK Live",
        "tvg_id": "ok.live.664807546380",
        "tvg_logo": "",
        "url": "https://ok.ru/live/8602647142043",
        "output": "stream2.m3u8",
        "referer": "https://ok.ru/live/8602647142043",
        "origin": "https://ok.ru",
        "user_agent": DEFAULT_USER_AGENT,
    },
    {
        "name": "VK Stream",
        "group": "VK",
        "tvg_id": "vk.-44869284_456248275",
        "tvg_logo": "https://raw.githubusercontent.com/grig3693-lgtm/vskt/refs/heads/main/logos/other.png",
        "url": "https://vkvideo.ru/video-44869284_456248275",
        "output": "stream3.m3u8",
        "referer": "https://vkvideo.ru/video-44869284_456248275",
        "origin": "https://vkvideo.ru",
        "user_agent": DEFAULT_USER_AGENT,
    },
    {
        "name": "OK Stream",
        "group": "OK",
        "tvg_id": "vk.-44869284_456248275",
        "tvg_logo": "https://raw.githubusercontent.com/grig3693-lgtm/vskt/refs/heads/main/logos/other.png",
        "url": "https://ok.ru/video/2961812233904",
        "output": "stream4.m3u8",
        "referer": "https://ok.ru/video/2961812233904",
        "origin": "https://ok.ru",
        "user_agent": DEFAULT_USER_AGENT,
    },
    {
        "name": "OK Live 3",
        "group": "OK",
        "tvg_id": "vk.-44869284_456248275",
        "tvg_logo": "https://raw.githubusercontent.com/grig3693-lgtm/vskt/refs/heads/main/logos/other.png",
        "url": "https://vkvideo.ru/video-224958559_456239406",
        "output": "stream5.m3u8",
        "referer": "https://vkvideo.ru/video-224958559_456239406",
        "origin": "https://vkvideo.ru/",
        "user_agent": DEFAULT_USER_AGENT,
    },
    {
        "name": "OK Live 4",
        "group": "OK",
        "tvg_id": "vk.-44869284_456248275",
        "tvg_logo": "https://raw.githubusercontent.com/grig3693-lgtm/vskt/refs/heads/main/logos/other.png",
        "url": "https://vkvideo.ru/video-49246642_456257599",
        "output": "stream6.m3u8",
        "referer": "https://vkvideo.ru/video-49246642_456257599",
        "origin": "https://vkvideo.ru/",
        "user_agent": DEFAULT_USER_AGENT,
    },
    # Viju ալիքների օրինակ՝
    {
        "name": "viju TV1000 Novella",
        "group": "Viju",
        "tvg_id": "viju.tv1000.novella",
        "tvg_logo": "",
        "source": "viju",
        "slug": "viju-tv1000-novella",
        "output": "stream7.m3u8",
        "referer": "https://viju.ru/",
        "origin": "https://viju.ru",
        "user_agent": DEFAULT_USER_AGENT,
    },
]


def detect_referer(video_url: str, stream_url: str = "", custom_referer: str = "") -> str:
    if custom_referer:
        return custom_referer
    match = re.search(r"/mid/(\d+)", stream_url)
    if match:
        return f"https://ok.ru/live/{match.group(1)}"
    if "ok.ru" in video_url:
        return video_url
    parsed = urlparse(video_url)
    return f"{parsed.scheme}://{parsed.netloc}/" if parsed.netloc else ""


def detect_origin(referer: str, video_url: str, custom_origin: str = "") -> str:
    if custom_origin:
        return custom_origin
    for candidate in (referer, video_url):
        if not candidate:
            continue
        parsed = urlparse(candidate)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return ""


def http_json_request(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    payload: dict | None = None,
    timeout: int = 20,
) -> dict:
    req_headers = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        req_headers.update(headers)

    data_bytes = None
    if payload is not None:
        req_headers.setdefault("Content-Type", "application/json")
        data_bytes = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return json.loads(body)


def fetch_viju_access_token(user_agent: str) -> str:
    refresh_token = os.getenv("VIJU_REFRESH_TOKEN", "").strip()
    if not refresh_token:
        raise RuntimeError("VIJU_REFRESH_TOKEN environment variable is not set.")

    visitor_id = os.getenv("VIJU_VISITOR_ID", "").strip()
    headers = {
        "User-Agent": user_agent,
        "Origin": "https://viju.ru",
        "Referer": "https://viju.ru/",
    }
    if visitor_id:
        headers["visitorid"] = visitor_id

    data = http_json_request(
        VIJU_REFRESH_URL,
        method="POST",
        headers=headers,
        payload={"refresh_token": refresh_token},
    )
    access_token = (data.get("access_token") or "").strip()
    if not access_token:
        raise RuntimeError("No access_token returned from /v2/sessions/refresh.")
    return access_token


def fetch_viju_stream_url(slug: str, access_token: str, user_agent: str) -> str:
    visitor_id = os.getenv("VIJU_VISITOR_ID", "").strip()
    headers = {
        "User-Agent": user_agent,
        "Origin": "https://viju.ru",
        "Referer": "https://viju.ru/",
        "Authorization": f"Bearer {access_token}",
    }
    if visitor_id:
        headers["visitorid"] = visitor_id

    url = VIJU_PLAYLIST_URL_TEMPLATE.format(slug=slug)
    data = http_json_request(url, method="GET", headers=headers)
    stream_url = (data.get("url") or "").strip()
    if not stream_url:
        raise RuntimeError(f"No stream url returned for Viju slug '{slug}'.")
    return stream_url


def get_ytdlp_info(video_url: str, referer: str, user_agent: str) -> dict:
    cmd = ["yt-dlp", "--no-warnings", "--user-agent", user_agent]
    if referer:
        cmd.extend(["--referer", referer])
    cmd.extend(["-J", video_url])
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def fetch_text(url: str, referer: str, origin: str, user_agent: str) -> str:
    headers = {"User-Agent": user_agent}
    if referer:
        headers["Referer"] = referer
    if origin:
        headers["Origin"] = origin

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def is_media_playlist(manifest_text: str) -> bool:
    return "#EXTINF:" in manifest_text or ".ts" in manifest_text


def build_master_from_manifest(manifest_text: str, base_url: str) -> str | None:
    if is_media_playlist(manifest_text):
        return None

    raw_lines = [line.rstrip("\r\n") for line in manifest_text.splitlines()]
    output_lines: list[str] = ["#EXTM3U", "#EXT-X-VERSION:5"]

    for line in raw_lines:
        stripped = line.strip()
        if not stripped or stripped in ("#EXTM3U", "#EXT-X-INDEPENDENT-SEGMENTS"):
            continue
        if stripped.startswith("#EXT-X-VERSION:"):
            continue
        if stripped.startswith("#") and 'URI="' in line:
            line = re.sub(
                r'URI="([^"]+)"',
                lambda m: f'URI="{urljoin(base_url, m.group(1))}"',
                line,
            )
            output_lines.append(line)
            continue
        if stripped.startswith("#"):
            output_lines.append(line)
            continue
        output_lines.append(urljoin(base_url, stripped))

    output_lines.append("#EXT-X-INDEPENDENT-SEGMENTS")
    return "\n".join(output_lines) + "\n"


def build_master_from_formats(info: dict, stream_name: str) -> str | None:
    formats = info.get("formats") or []
    hls_variants: list[tuple[int, str, str]] = []
    seen_urls: set[str] = set()

    for fmt in formats:
        url = fmt.get("url")
        if not url or url in seen_urls:
            continue
        if ".ts" in url.split("?")[0]:
            continue

        protocol = (fmt.get("protocol") or "").lower()
        ext = (fmt.get("ext") or "").lower()
        if "m3u8" not in protocol and "m3u8" not in url and ext != "m3u8":
            continue

        seen_urls.add(url)

        tbr = fmt.get("tbr") or fmt.get("vbr") or 0
        bandwidth = int(float(tbr) * 1000) if tbr else 1000000

        width = fmt.get("width")
        height = fmt.get("height")
        resolution_attr = f",RESOLUTION={width}x{height}" if width and height else ""

        fmt_note = fmt.get("format_note") or fmt.get("format_id") or stream_name
        safe_name = str(fmt_note).replace('"', "")

        attrs = f'BANDWIDTH={bandwidth}{resolution_attr},NAME="{safe_name}"'
        hls_variants.append((bandwidth, attrs, url))

    if not hls_variants:
        return None

    hls_variants.sort(key=lambda item: item[0])

    lines: list[str] = ["#EXTM3U", "#EXT-X-VERSION:5"]
    for _, attrs, url in hls_variants:
        lines.append(f"#EXT-X-STREAM-INF:{attrs}")
        lines.append(url)

    lines.append("#EXT-X-INDEPENDENT-SEGMENTS")
    return "\n".join(lines) + "\n"


def generate_stream_m3u8(
    stream_cfg: dict,
    stream_name: str,
    output_file: str,
    viju_token: str | None = None,
) -> tuple[bool, str, str]:
    source_type = (stream_cfg.get("source") or "").strip().lower()
    video_url = (stream_cfg.get("url") or "").strip()
    custom_referer = stream_cfg.get("referer") or ""
    custom_origin = stream_cfg.get("origin") or ""
    user_agent = stream_cfg.get("user_agent") or DEFAULT_USER_AGENT

    if source_type == "viju":
        slug = (stream_cfg.get("slug") or "").strip()
        if not slug:
            print(f"[{stream_name}] Missing Viju slug.", file=sys.stderr)
            return False, custom_referer or "https://viju.ru/", user_agent
        if not viju_token:
            print(f"[{stream_name}] Missing Viju access token.", file=sys.stderr)
            return False, custom_referer or "https://viju.ru/", user_agent
        try:
            video_url = fetch_viju_stream_url(slug, viju_token, user_agent)
        except Exception as exc:
            print(f"[{stream_name}] Viju playlist fetch failed: {exc}", file=sys.stderr)
            return False, custom_referer or "https://viju.ru/", user_agent

    initial_referer = detect_referer(video_url, custom_referer=custom_referer)
    info = None

    # Ուղղակի .m3u8 հղման դեպքում yt-dlp-ի վրա ժամանակ չենք վատնում
    if ".m3u8" not in video_url.lower():
        try:
            info = get_ytdlp_info(video_url, referer=initial_referer, user_agent=user_agent)
        except subprocess.CalledProcessError as exc:
            print(f"[{stream_name}] yt-dlp failed: {exc.stderr.strip()}", file=sys.stderr)
        except Exception as exc:
            print(f"[{stream_name}] Error parsing yt-dlp info: {exc}", file=sys.stderr)

    playlist = None
    effective_url = video_url

    if info:
        playlist = build_master_from_formats(info, stream_name)
        if not playlist:
            candidate_url = info.get("url") or ""
            if candidate_url:
                effective_url = candidate_url
                referer = detect_referer(video_url, effective_url, custom_referer)
                origin = detect_origin(referer, video_url, custom_origin)
                try:
                    manifest_text = fetch_text(effective_url, referer=referer, origin=origin, user_agent=user_agent)
                    playlist = build_master_from_manifest(manifest_text, base_url=effective_url)
                except Exception as exc:
                    print(f"[{stream_name}] Manifest check failed ({exc}).", file=sys.stderr)

    if not playlist:
        referer = detect_referer(video_url, effective_url, custom_referer)
        origin = detect_origin(referer, video_url, custom_origin)
        if ".m3u8" in video_url.lower():
            try:
                manifest_text = fetch_text(video_url, referer=referer, origin=origin, user_agent=user_agent)
                playlist = build_master_from_manifest(manifest_text, base_url=video_url)
            except Exception as exc:
                print(f"[{stream_name}] Direct m3u8 fetch failed ({exc}).", file=sys.stderr)

        if not playlist and info and info.get("url"):
            playlist = (
                "#EXTM3U\n"
                "#EXT-X-VERSION:5\n"
                f'#EXT-X-STREAM-INF:BANDWIDTH=2000000,NAME="{stream_name}"\n'
                f"{info['url']}\n"
                "#EXT-X-INDEPENDENT-SEGMENTS\n"
            )
        elif not playlist and ".m3u8" in video_url.lower():
            playlist = (
                "#EXTM3U\n"
                "#EXT-X-VERSION:5\n"
                f'#EXT-X-STREAM-INF:BANDWIDTH=2000000,NAME="{stream_name}"\n'
                f"{video_url}\n"
                "#EXT-X-INDEPENDENT-SEGMENTS\n"
            )

    if not playlist:
        return False, initial_referer, user_agent

    with open(output_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(playlist)

    final_referer = detect_referer(video_url, effective_url, custom_referer)
    print(f"[{stream_name}] Wrote {output_file} successfully.")
    return True, final_referer, user_agent


def build_combined_playlist(generated_entries: list[dict]) -> str:
    lines: list[str] = ["#EXTM3U"]
    for item in generated_entries:
        name = item["name"]
        group = item.get("group") or "Live"
        filename = item["output"]
        referer = item.get("referer") or ""
        user_agent = item.get("user_agent") or DEFAULT_USER_AGENT
        raw_url = (
            f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}"
            f"/refs/heads/{BRANCH}/{filename}"
        )

        attrs = [f'group-title="{group}"']
        if item.get("tvg_id"):
            attrs.append(f'tvg-id="{item["tvg_id"]}"')
        if item.get("tvg_logo"):
            attrs.append(f'tvg-logo="{item["tvg_logo"]}"')

        lines.append(f"#EXTINF:-1 {' '.join(attrs)},{name}")
        lines.append(f"#EXTVLCOPT:http-user-agent={user_agent}")
        if referer:
            lines.append(f"#EXTVLCOPT:http-referrer={referer}")
        lines.append(raw_url)
    return "\n".join(lines) + "\n"


def main() -> None:
    if not STREAMS:
        print("STREAMS list is empty.", file=sys.stderr)
        sys.exit(1)

    has_viju = any((s.get("source") or "").strip().lower() == "viju" for s in STREAMS)
    viju_token: str | None = None

    if has_viju:
        try:
            viju_token = fetch_viju_access_token(DEFAULT_USER_AGENT)
            print("[Viju] Refreshed access_token successfully.")
        except Exception as exc:
            print(f"[Viju] Token refresh failed: {exc}", file=sys.stderr)

    successful_entries: list[dict] = []

    for index, stream in enumerate(STREAMS):
        name = stream.get("name") or f"Stream {index + 1}"
        group = stream.get("group") or "Live"
        source_type = (stream.get("source") or "").strip().lower()
        url = (stream.get("url") or "").strip()
        slug = (stream.get("slug") or "").strip()
        output_file = stream.get("output") or f"stream{index + 1}.m3u8"

        if source_type != "viju" and not url:
            print(f"[{name}] Missing URL, skipping.", file=sys.stderr)
            continue
        if source_type == "viju" and not slug:
            print(f"[{name}] Missing Viju slug, skipping.", file=sys.stderr)
            continue

        ok, resolved_referer, resolved_ua = generate_stream_m3u8(
            stream,
            name,
            output_file,
            viju_token=viju_token,
        )
        if ok:
            successful_entries.append(
                {
                    "name": name,
                    "group": group,
                    "tvg_id": stream.get("tvg_id") or "",
                    "tvg_logo": stream.get("tvg_logo") or "",
                    "output": output_file,
                    "referer": resolved_referer,
                    "user_agent": resolved_ua,
                }
            )

        if index < len(STREAMS) - 1 and REQUEST_DELAY_SECONDS > 0:
            time.sleep(REQUEST_DELAY_SECONDS)

    if not successful_entries:
        print("No stream playlists were generated.", file=sys.stderr)
        sys.exit(1)

    combined_content = build_combined_playlist(successful_entries)
    with open(PLAYLIST_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(combined_content)

    print(f"Wrote {PLAYLIST_FILE} with {len(successful_entries)} stream(s).")


if __name__ == "__main__":
    main()
