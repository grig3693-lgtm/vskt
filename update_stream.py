import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
from urllib.parse import urljoin, urlparse
import urllib.request
import uuid

try:
    from nacl import encoding, public

    HAS_NACL = True
except ImportError:
    HAS_NACL = False

# Ռեպոզիտորիայի տվյալները (կարող են փոխանցվել Environment Variable-ով)
REPO_OWNER = os.getenv("REPO_OWNER", "grig3693-lgtm")
REPO_NAME = os.getenv("REPO_NAME", "vskt")
BRANCH = os.getenv("GIT_BRANCH", "main")
PLAYLIST_FILE = "playlist.m3u"

VIJU_REFRESH_URL = "https://api.viju.ru/v2/sessions/refresh"
VIJU_PLAYLIST_URL_TEMPLATE = "https://api.viju.ru/api/v1/tv/channels/{slug}/playlist"
VIJU_API_AUTH = os.getenv(
    "VIJU_API_AUTH",
    "APIAuth web:Fk0sdNBgnnz6V7tSxc0aKXfOiNY=",
).strip()

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
    # Viju ալիքներ՝ ավելացրեք նոր
