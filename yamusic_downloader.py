#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Yandex Music Downloader - Material You Desktop Application
==========================================================

A modern desktop application for searching, queueing, and batch downloading
music tracks from Yandex Music in maximum quality (Lossless/HQ).

Features:
    - Modern Material You GUI with dynamic accent colors
    - Search tracks, albums, playlists, and artists
    - Queue management with pause/resume/cancel support
    - Parallel downloads (configurable 1-5 threads)
    - Automatic metadata tagging (ID3/FLAC) with cover art and lyrics
    - Lossless (FLAC) priority with HQ (MP3 320kbps) fallback
    - Encrypted token storage via keyring
    - Dark/Light theme support with auto-detection

Author: Senior Principal Python Engineer
Python Version: 3.10+
Dependencies: PyQt6, yandex-music, mutagen, darkdetect, keyring, requests
"""

import sys
import os
import json
import time
import logging
import hashlib
import threading
import requests
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

# PyQt6 imports
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QPushButton, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QProgressBar, QFrame, QScrollArea, QSizePolicy,
    QSpacerItem, QFileDialog, QMessageBox, QDialog, QFormLayout,
    QSpinBox, QComboBox, QCheckBox, QTextEdit, QTabWidget,
    QSlider, QMenu, QAction, QSystemTrayIcon, QStyle, QStyledItemDelegate,
    QOption, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QObject, QSize, QTimer, QPropertyAnimation,
    QEasingCurve, QPoint, QRect, QMetaObject, Q_ARG, QUrl
)
from PyQt6.QtGui import (
    QIcon, QPixmap, QColor, QPalette, QFont, QFontDatabase, QAction,
    QLinearGradient, QPainter, QBrush, QPen, QCursor, QImage, QDesktopServices
)

# Third-party imports
from yandex_music import Client as YandexClient, Track, Album, Playlist, Artist
from mutagen.id3 import ID3, APIC, USLT, TIT2, TPE1, TALB, TDRC, TCON, TRCK, ID3NoHeaderError
from mutagen.flac import FLAC, Picture as FlacPicture
from mutagen.mp3 import MP3
import darkdetect
import keyring

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

APP_NAME = "Yandex Music Downloader"
APP_VERSION = "1.0.0"
SERVICE_NAME = "yamusic-downloader"
CACHE_DIR = Path.home() / ".yamusic_cache"
CONFIG_FILE = Path.home() / ".yamusic_config.json"

# Material You Color Palette (will be dynamically generated)
MATERIAL_COLORS = {
    "primary": "#6750A4",
    "on_primary": "#FFFFFF",
    "primary_container": "#EADDFF",
    "on_primary_container": "#21005D",
    "secondary": "#625B71",
    "on_secondary": "#FFFFFF",
    "secondary_container": "#E8DEF8",
    "on_secondary_container": "#1D192B",
    "tertiary": "#7D5260",
    "on_tertiary": "#FFFFFF",
    "tertiary_container": "#FFD8E4",
    "on_tertiary_container": "#31111D",
    "error": "#B3261E",
    "on_error": "#FFFFFF",
    "error_container": "#F9DEDC",
    "on_error_container": "#410E0B",
    "background": "#FFFBFE",
    "on_background": "#1C1B1F",
    "surface": "#FFFBFE",
    "on_surface": "#1C1B1F",
    "surface_variant": "#E7E0EC",
    "on_surface_variant": "#49454F",
    "outline": "#79747E",
    "outline_variant": "#CAC4D0",
}

MATERIAL_DARK_COLORS = {
    "primary": "#D0BCFF",
    "on_primary": "#381E72",
    "primary_container": "#4F378B",
    "on_primary_container": "#EADDFF",
    "secondary": "#CCC2DC",
    "on_secondary": "#332D41",
    "secondary_container": "#4A4458",
    "on_secondary_container": "#E8DEF8",
    "tertiary": "#EFB8C8",
    "on_tertiary": "#492532",
    "tertiary_container": "#633B48",
    "on_tertiary_container": "#FFD8E4",
    "error": "#F2B8B5",
    "on_error": "#601410",
    "error_container": "#8C1D18",
    "on_error_container": "#F9DEDC",
    "background": "#1C1B1F",
    "on_background": "#E6E1E5",
    "surface": "#1C1B1F",
    "on_surface": "#E6E1E5",
    "surface_variant": "#49454F",
    "on_surface_variant": "#CAC4D0",
    "outline": "#938F99",
    "outline_variant": "#49454F",
}


# =============================================================================
# DATA CLASSES AND ENUMS
# =============================================================================

class DownloadStatus(Enum):
    """Enumeration of possible download statuses."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class DownloadItem:
    """Data class representing a single download item in the queue."""
    track_id: str
    title: str
    artist: str
    album: str = ""
    cover_url: str = ""
    duration_ms: int = 0
    year: int = 0
    genre: str = ""
    track_number: int = 0
    lyrics: str = ""
    status: DownloadStatus = DownloadStatus.PENDING
    progress: int = 0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed_kbps: float = 0.0
    error_message: str = ""
    file_path: str = ""
    retry_count: int = 0
    max_retries: int = 3
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "track_id": self.track_id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "cover_url": self.cover_url,
            "duration_ms": self.duration_ms,
            "year": self.year,
            "genre": self.genre,
            "track_number": self.track_number,
            "lyrics": self.lyrics,
            "status": self.status.value,
            "progress": self.progress,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "speed_kbps": self.speed_kbps,
            "error_message": self.error_message,
            "file_path": self.file_path,
            "retry_count": self.retry_count,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DownloadItem":
        """Create from dictionary."""
        data["status"] = DownloadStatus(data["status"])
        return cls(**data)


@dataclass
class AppConfig:
    """Application configuration data class."""
    download_path: str = str(Path.home() / "Music" / "YandexMusic")
    max_parallel_downloads: int = 3
    preferred_quality: str = "lossless"  # lossless or hq
    theme_mode: str = "system"  # system, light, dark
    accent_color: str = "#6750A4"
    save_lyrics: bool = True
    save_cover: bool = True
    create_artist_folder: bool = True
    create_album_folder: bool = True
    auto_retry: bool = True
    max_retries: int = 3
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "download_path": self.download_path,
            "max_parallel_downloads": self.max_parallel_downloads,
            "preferred_quality": self.preferred_quality,
            "theme_mode": self.theme_mode,
            "accent_color": self.accent_color,
            "save_lyrics": self.save_lyrics,
            "save_cover": self.save_cover,
            "create_artist_folder": self.create_artist_folder,
            "create_album_folder": self.create_album_folder,
            "auto_retry": self.auto_retry,
            "max_retries": self.max_retries,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        """Create from dictionary."""
        return cls(**data)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def generate_material_palette(base_color: str, is_dark: bool = False) -> Dict[str, str]:
    """
    Generate a Material You color palette from a base accent color.
    
    This is a simplified implementation. For production, consider using
    a proper color science library like material-color-utilities.
    
    Args:
        base_color: Hex color code (e.g., "#6750A4")
        is_dark: Whether to generate dark theme palette
        
    Returns:
        Dictionary of color roles to hex values
    """
    base = MATERIAL_DARK_COLORS if is_dark else MATERIAL_COLORS
    # In a full implementation, we would compute colors from base_color
    # For now, we use predefined palettes
    return base.copy()


def get_cover_cache_path(url: str) -> Path:
    """Get cached cover image path based on URL hash."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return CACHE_DIR / f"{url_hash}.jpg"


def download_cover_image(url: str, size: int = 500) -> Optional[bytes]:
    """
    Download cover image from URL with caching.
    
    Args:
        url: Cover image URL from Yandex Music
        size: Desired size in pixels (Yandex supports various sizes)
        
    Returns:
        Image bytes or None if download failed
    """
    if not url:
        return None
    
    # Replace %%size%% with actual size
    if "%%" in url:
        url = url.replace("%%", f"{size}x{size}")
    
    cache_path = get_cover_cache_path(url)
    
    # Check cache first
    if cache_path.exists():
        try:
            return cache_path.read_bytes()
        except Exception:
            pass
    
    # Download from network
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # Save to cache
        cache_path.write_bytes(response.content)
        return response.content
    except Exception as e:
        logger.warning(f"Failed to download cover: {e}")
        return None


def load_config() -> AppConfig:
    """Load application configuration from file."""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            return AppConfig.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load config: {e}")
    return AppConfig()


def save_config(config: AppConfig) -> None:
    """Save application configuration to file."""
    try:
        CONFIG_FILE.write_text(json.dumps(config.to_dict(), indent=2))
    except Exception as e:
        logger.error(f"Failed to save config: {e}")


def format_duration(ms: int) -> str:
    """Format duration in milliseconds to MM:SS string."""
    seconds = ms // 1000
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes}:{seconds:02d}"


def format_size(bytes_: int) -> str:
    """Format bytes to human-readable size string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(bytes_) < 1024.0:
            return f"{bytes_:.1f} {unit}"
        bytes_ /= 1024.0
    return f"{bytes_:.1f} TB"


# =============================================================================
# YANDEX MUSIC API WRAPPER
# =============================================================================

class YandexMusicAPI:
    """
    Wrapper class for Yandex Music API interactions.
    
    Handles authentication, search, and track metadata retrieval.
    Implements exponential backoff for rate limiting.
    """
    
    def __init__(self, token: Optional[str] = None):
        """
        Initialize Yandex Music API client.
        
        Args:
            token: Yandex Music API token (OAuth token)
        """
        self.client = YandexClient(token=token)
        self.token = token
        self._rate_limit_delay = 0.5  # Base delay between requests
    
    def set_token(self, token: str) -> None:
        """Set authentication token."""
        self.token = token
        self.client = YandexClient(token=token)
    
    def is_authenticated(self) -> bool:
        """Check if client is authenticated."""
        return self.token is not None
    
    def _handle_rate_limit(self, attempt: int = 0) -> None:
        """
        Handle rate limiting with exponential backoff.
        
        Args:
            attempt: Current retry attempt number
        """
        delay = self._rate_limit_delay * (2 ** attempt)
        time.sleep(delay)
    
    def search(self, query: str, type_: str = "all", page: int = 0) -> Any:
        """
        Search Yandex Music.
        
        Args:
            query: Search query string
            type_: Type of search ("track", "album", "artist", "playlist", "all")
            page: Page number for pagination
            
        Returns:
            Search results object
        """
        try:
            result = self.client.search(query, type_=type_, page=page)
            return result
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return None
    
    def get_track(self, track_id: str) -> Optional[Track]:
        """
        Get track by ID.
        
        Args:
            track_id: Yandex track ID
            
        Returns:
            Track object or None
        """
        try:
            tracks = self.client.tracks([track_id])
            if tracks and len(tracks) > 0:
                return tracks[0]
        except Exception as e:
            logger.error(f"Failed to get track {track_id}: {e}")
        return None
    
    def get_album(self, album_id: str) -> Optional[Album]:
        """
        Get album by ID with all tracks.
        
        Args:
            album_id: Yandex album ID
            
        Returns:
            Album object or None
        """
        try:
            return self.client.albums(album_id)
        except Exception as e:
            logger.error(f"Failed to get album {album_id}: {e}")
        return None
    
    def get_playlist(self, user_id: str, playlist_id: str) -> Optional[Playlist]:
        """
        Get playlist by user ID and playlist ID.
        
        Args:
            user_id: Yandex user ID
            playlist_id: Playlist ID
            
        Returns:
            Playlist object or None
        """
        try:
            return self.client.users_playlists_list(user_id)
        except Exception as e:
            logger.error(f"Failed to get playlist: {e}")
        return None
    
    def get_track_lyrics(self, track: Track) -> str:
        """
        Get lyrics for a track.
        
        Args:
            track: Track object
            
        Returns:
            Lyrics text or empty string
        """
        try:
            supplement = track.get_supplement()
            if supplement and hasattr(supplement, 'lyrics') and supplement.lyrics:
                # Get the full lyrics text
                for lyric in supplement.lyrics:
                    if hasattr(lyric, 'text') and lyric.text:
                        return lyric.text
        except Exception as e:
            logger.debug(f"Failed to get lyrics: {e}")
        return ""
    
    def get_best_download_info(self, track: Track, prefer_lossless: bool = True) -> Tuple[str, int]:
        """
        Get best available download codec and bitrate for a track.
        
        Args:
            track: Track object
            prefer_lossless: Whether to prefer lossless quality
            
        Returns:
            Tuple of (codec, bitrate_in_kbps)
        """
        try:
            download_infos = track.get_download_info(get_direct_links=False)
            
            if not download_infos:
                return "mp3", 192
            
            # Sort by bitrate
            sorted_infos = sorted(download_infos, key=lambda x: x.bitrate_in_kbps, reverse=True)
            
            # Try to find lossless (FLAC)
            if prefer_lossless:
                for info in sorted_infos:
                    if info.codec == "flac" or info.bitrate_in_kbps >= 1000:
                        return "flac", info.bitrate_in_kbps
            
            # Fallback to highest quality MP3
            for info in sorted_infos:
                if info.codec == "mp3":
                    return "mp3", info.bitrate_in_kbps
            
            # Return best available
            best = sorted_infos[0]
            return best.codec, best.bitrate_in_kbps
            
        except Exception as e:
            logger.error(f"Failed to get download info: {e}")
            return "mp3", 192
    
    def parse_yandex_url(self, url: str) -> Optional[Dict[str, str]]:
        """
        Parse Yandex Music URL to extract type and ID.
        
        Supported formats:
        - https://music.yandex.ru/track/123456
        - https://music.yandex.ru/album/789012
        - https://music.yandex.ru/artist/345678
        - https://music.yandex.ru/users/username/playlists/901234
        
        Args:
            url: Yandex Music URL
            
        Returns:
            Dictionary with 'type' and 'id' keys, or None
        """
        try:
            from urllib.parse import urlparse
            
            parsed = urlparse(url)
            path_parts = parsed.path.strip('/').split('/')
            
            if len(path_parts) >= 2:
                type_ = path_parts[0]
                id_ = path_parts[1]
                
                if type_ == "users" and len(path_parts) >= 4:
                    # Playlist URL
                    return {"type": "playlist", "user_id": path_parts[1], "id": path_parts[3]}
                elif type_ in ["track", "album", "artist"]:
                    return {"type": type_, "id": id_}
        except Exception as e:
            logger.debug(f"Failed to parse URL: {e}")
        return None


# =============================================================================
# METADATA TAGGING
# =============================================================================

class MetadataTagger:
    """
    Class for embedding metadata into audio files.
    
    Supports MP3 (ID3v2) and FLAC (Vorbis comments) formats.
    """
    
    @staticmethod
    def tag_mp3(file_path: str, title: str, artist: str, album: str,
                year: int, genre: str, track_number: int,
                cover_data: Optional[bytes], lyrics: str) -> bool:
        """
        Tag MP3 file with metadata.
        
        Args:
            file_path: Path to MP3 file
            title: Track title
            artist: Artist name
            album: Album name
            year: Release year
            genre: Genre
            track_number: Track number
            cover_data: Cover image bytes
            lyrics: Lyrics text
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Load or create ID3 tag
            try:
                audio = ID3(file_path)
            except ID3NoHeaderError:
                audio = ID3()
            
            # Set basic metadata
            audio['TIT2'] = TIT2(encoding=3, text=title)
            audio['TPE1'] = TPE1(encoding=3, text=artist)
            audio['TALB'] = TALB(encoding=3, text=album)
            audio['TDRC'] = TDRC(encoding=3, text=str(year))
            audio['TCON'] = TCON(encoding=3, text=genre)
            audio['TRCK'] = TRCK(encoding=3, text=str(track_number))
            
            # Add cover art
            if cover_data:
                audio['APIC'] = APIC(
                    encoding=3,
                    mime='image/jpeg',
                    type=3,  # Front cover
                    desc='Cover',
                    data=cover_data
                )
            
            # Add lyrics
            if lyrics:
                audio['USLT'] = USLT(
                    encoding=3,
                    lang='rus',
                    desc='Lyrics',
                    text=lyrics
                )
            
            audio.save(file_path)
            logger.info(f"Tagged MP3: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to tag MP3: {e}")
            return False
    
    @staticmethod
    def tag_flac(file_path: str, title: str, artist: str, album: str,
                 year: int, genre: str, track_number: int,
                 cover_data: Optional[bytes], lyrics: str) -> bool:
        """
        Tag FLAC file with metadata.
        
        Args:
            file_path: Path to FLAC file
            title: Track title
            artist: Artist name
            album: Album name
            year: Release year
            genre: Genre
            track_number: Track number
            cover_data: Cover image bytes
            lyrics: Lyrics text
            
        Returns:
            True if successful, False otherwise
        """
        try:
            audio = FLAC(file_path)
            
            # Set basic metadata
            audio['title'] = title
            audio['artist'] = artist
            audio['album'] = album
            audio['date'] = str(year)
            audio['genre'] = genre
            audio['tracknumber'] = str(track_number)
            
            # Add lyrics
            if lyrics:
                audio['lyrics'] = lyrics
            
            # Add cover art
            if cover_data:
                pic = FlacPicture()
                pic.type = 3  # Front cover
                pic.mime = 'image/jpeg'
                pic.desc = 'Cover'
                pic.data = cover_data
                audio.add_picture(pic)
            
            audio.save()
            logger.info(f"Tagged FLAC: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to tag FLAC: {e}")
            return False
    
    @staticmethod
    def tag_file(file_path: str, title: str, artist: str, album: str,
                 year: int, genre: str, track_number: int,
                 cover_data: Optional[bytes], lyrics: str) -> bool:
        """
        Tag audio file with metadata (auto-detect format).
        
        Args:
            file_path: Path to audio file
            title: Track title
            artist: Artist name
            album: Album name
            year: Release year
            genre: Genre
            track_number: Track number
            cover_data: Cover image bytes
            lyrics: Lyrics text
            
        Returns:
            True if successful, False otherwise
        """
        if file_path.lower().endswith('.flac'):
            return MetadataTagger.tag_flac(
                file_path, title, artist, album, year, genre,
                track_number, cover_data, lyrics
            )
        else:
            return MetadataTagger.tag_mp3(
                file_path, title, artist, album, year, genre,
                track_number, cover_data, lyrics
            )


# =============================================================================
# DOWNLOAD WORKER THREAD
# =============================================================================

class DownloadWorker(QThread):
    """
    Worker thread for downloading individual tracks.
    
    Emits signals for progress updates and completion.
    Runs in separate thread to prevent GUI freezing.
    """
    
    # Signals
    progress = pyqtSignal(int, int, float)  # downloaded_bytes, total_bytes, speed_kbps
    finished = pyqtSignal(str)  # file_path
    error = pyqtSignal(str)  # error_message
    status_changed = pyqtSignal(object)  # DownloadStatus
    
    def __init__(self, item: DownloadItem, api: YandexMusicAPI, 
                 config: AppConfig, parent=None):
        """
        Initialize download worker.
        
        Args:
            item: DownloadItem to download
            api: YandexMusicAPI instance
            config: AppConfig instance
            parent: Parent QObject
        """
        super().__init__(parent)
        self.item = item
        self.api = api
        self.config = config
        self._stop_flag = False
        self._pause_flag = False
    
    def stop(self) -> None:
        """Stop the download."""
        self._stop_flag = True
    
    def pause(self) -> None:
        """Pause the download."""
        self._pause_flag = True
    
    def resume(self) -> None:
        """Resume the download."""
        self._pause_flag = False
    
    def run(self) -> None:
        """Main download logic."""
        try:
            self.status_changed.emit(DownloadStatus.DOWNLOADING)
            
            # Get track from API
            track = self.api.get_track(self.item.track_id)
            if not track:
                raise Exception("Failed to fetch track info")
            
            # Get best download quality
            codec, bitrate = self.api.get_best_download_info(
                track, 
                self.config.preferred_quality == "lossless"
            )
            
            # Determine file extension
            ext = "flac" if codec == "flac" else "mp3"
            
            # Create directory structure
            if self.config.create_artist_folder and self.item.artist:
                artist_dir = Path(self.config.download_path) / self._sanitize_filename(self.item.artist)
                artist_dir.mkdir(parents=True, exist_ok=True)
                
                if self.config.create_album_folder and self.item.album:
                    target_dir = artist_dir / self._sanitize_filename(self.item.album)
                    target_dir.mkdir(parents=True, exist_ok=True)
                else:
                    target_dir = artist_dir
            else:
                target_dir = Path(self.config.download_path)
                target_dir.mkdir(parents=True, exist_ok=True)
            
            # Build filename
            filename = f"{self.item.track_number:02d}. {self._sanitize_filename(self.item.title)}.{ext}"
            file_path = str(target_dir / filename)
            
            # Download cover image
            cover_data = None
            if self.config.save_cover and self.item.cover_url:
                cover_data = download_cover_image(self.item.cover_url, 1000)
            
            # Get lyrics
            lyrics = ""
            if self.config.save_lyrics:
                lyrics = self.api.get_track_lyrics(track)
            
            # Perform download
            start_time = time.time()
            self.item.downloaded_bytes = 0
            
            # Use track.download method with callback simulation
            # Since yandex-music doesn't support progress callback directly,
            # we'll download manually using requests
            
            download_infos = track.get_download_info(get_direct_links=True)
            if not download_infos:
                raise Exception("No download links available")
            
            # Get direct link
            direct_link = None
            for info in download_infos:
                if info.codec == codec or (codec == "flac" and info.bitrate_in_kbps >= 1000):
                    direct_link = info.download_info_url
                    break
            
            if not direct_link:
                direct_link = download_infos[0].download_info_url
            
            # Download with progress tracking
            response = requests.get(direct_link, stream=True, timeout=30)
            response.raise_for_status()
            
            self.item.total_bytes = int(response.headers.get('content-length', 0))
            
            with open(file_path, 'wb') as f:
                chunk_size = 8192
                last_update = time.time()
                last_bytes = 0
                
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if self._stop_flag:
                        # Cleanup cancelled download
                        f.close()
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        self.status_changed.emit(DownloadStatus.CANCELLED)
                        return
                    
                    while self._pause_flag:
                        time.sleep(0.1)
                        if self._stop_flag:
                            return
                    
                    if chunk:
                        f.write(chunk)
                        self.item.downloaded_bytes += len(chunk)
                        
                        # Update progress every 100ms
                        current_time = time.time()
                        if current_time - last_update >= 0.1:
                            elapsed = current_time - start_time
                            downloaded = self.item.downloaded_bytes
                            
                            if elapsed > 0:
                                speed = (downloaded - last_bytes) / (current_time - last_update) / 1024
                                self.item.speed_kbps = speed
                            
                            progress = int((downloaded / self.item.total_bytes * 100) if self.item.total_bytes > 0 else 0)
                            self.item.progress = progress
                            
                            self.progress.emit(downloaded, self.item.total_bytes, self.item.speed_kbps)
                            
                            last_update = current_time
                            last_bytes = downloaded
            
            # Tag the file
            if os.path.exists(file_path):
                success = MetadataTagger.tag_file(
                    file_path,
                    self.item.title,
                    self.item.artist,
                    self.item.album,
                    self.item.year,
                    self.item.genre,
                    self.item.track_number,
                    cover_data,
                    lyrics
                )
                
                if success:
                    self.item.file_path = file_path
                    self.item.progress = 100
                    self.item.status = DownloadStatus.COMPLETED
                    self.status_changed.emit(DownloadStatus.COMPLETED)
                    self.finished.emit(file_path)
                else:
                    raise Exception("Failed to tag file")
            else:
                raise Exception("Download failed - file not created")
                
        except Exception as e:
            error_msg = str(e)
            self.item.error_message = error_msg
            self.item.status = DownloadStatus.ERROR
            self.status_changed.emit(DownloadStatus.ERROR)
            self.error.emit(error_msg)
            logger.error(f"Download error for {self.item.title}: {error_msg}")
    
    def _sanitize_filename(self, filename: str) -> str:
        """Remove invalid characters from filename."""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename.strip()


# =============================================================================
# QUEUE MANAGER
# =============================================================================

class QueueManager(QObject):
    """
    Manages the download queue with parallel download support.
    
    Controls worker threads, handles pause/resume/cancel operations.
    """
    
    # Signals
    item_added = pyqtSignal(object)  # DownloadItem
    item_updated = pyqtSignal(object)  # DownloadItem
    item_removed = pyqtSignal(str)  # track_id
    queue_completed = pyqtSignal()
    
    def __init__(self, api: YandexMusicAPI, config: AppConfig, parent=None):
        """
        Initialize queue manager.
        
        Args:
            api: YandexMusicAPI instance
            config: AppConfig instance
            parent: Parent QObject
        """
        super().__init__(parent)
        self.api = api
        self.config = config
        self.queue: Dict[str, DownloadItem] = {}
        self.workers: Dict[str, DownloadWorker] = {}
        self.active_count = 0
        self._lock = threading.Lock()
    
    def add_item(self, item: DownloadItem) -> None:
        """Add item to download queue."""
        with self._lock:
            if item.track_id not in self.queue:
                self.queue[item.track_id] = item
                self.item_added.emit(item)
                self._process_queue()
    
    def remove_item(self, track_id: str) -> None:
        """Remove item from queue."""
        with self._lock:
            if track_id in self.queue:
                item = self.queue[track_id]
                
                # Stop worker if running
                if track_id in self.workers:
                    worker = self.workers[track_id]
                    worker.stop()
                    worker.wait(1000)
                    del self.workers[track_id]
                
                if item.status == DownloadStatus.DOWNLOADING:
                    self.active_count -= 1
                
                del self.queue[track_id]
                self.item_removed.emit(track_id)
    
    def pause_item(self, track_id: str) -> None:
        """Pause specific download."""
        if track_id in self.workers:
            self.workers[track_id].pause()
            self.queue[track_id].status = DownloadStatus.PAUSED
            self.item_updated.emit(self.queue[track_id])
    
    def resume_item(self, track_id: str) -> None:
        """Resume paused download."""
        if track_id in self.workers:
            self.workers[track_id].resume()
            self.queue[track_id].status = DownloadStatus.DOWNLOADING
            self.item_updated.emit(self.queue[track_id])
    
    def cancel_item(self, track_id: str) -> None:
        """Cancel specific download."""
        self.remove_item(track_id)
    
    def pause_all(self) -> None:
        """Pause all active downloads."""
        for track_id, worker in self.workers.items():
            if track_id in self.queue:
                worker.pause()
                self.queue[track_id].status = DownloadStatus.PAUSED
                self.item_updated.emit(self.queue[track_id])
    
    def resume_all(self) -> None:
        """Resume all paused downloads."""
        for track_id, worker in self.workers.items():
            if track_id in self.queue and self.queue[track_id].status == DownloadStatus.PAUSED:
                worker.resume()
                self.queue[track_id].status = DownloadStatus.DOWNLOADING
                self.item_updated.emit(self.queue[track_id])
    
    def clear_completed(self) -> None:
        """Remove all completed items from queue."""
        with self._lock:
            completed = [tid for tid, item in self.queue.items() 
                        if item.status in [DownloadStatus.COMPLETED, DownloadStatus.ERROR, DownloadStatus.CANCELLED]]
            for track_id in completed:
                self.remove_item(track_id)
    
    def _process_queue(self) -> None:
        """Process queue and start new workers if slots available."""
        with self._lock:
            # Count active downloads
            active = sum(1 for item in self.queue.values() 
                        if item.status == DownloadStatus.DOWNLOADING)
            
            # Start new downloads if slots available
            while active < self.config.max_parallel_downloads:
                # Find pending item
                pending = None
                for track_id, item in self.queue.items():
                    if item.status == DownloadStatus.PENDING:
                        pending = item
                        break
                
                if not pending:
                    break
                
                # Start worker
                self._start_worker(pending)
                active += 1
    
    def _start_worker(self, item: DownloadItem) -> None:
        """Start download worker for item."""
        worker = DownloadWorker(item, self.api, self.config)
        worker.progress.connect(lambda d, t, s, iid=item.track_id: self._on_progress(iid, d, t, s))
        worker.finished.connect(lambda fp, iid=item.track_id: self._on_finished(iid, fp))
        worker.error.connect(lambda err, iid=item.track_id: self._on_error(iid, err))
        worker.status_changed.connect(lambda st, iid=item.track_id: self._on_status_changed(iid, st))
        worker.finished.connect(self._on_worker_finished)
        worker.error.connect(self._on_worker_finished)
        
        self.workers[item.track_id] = worker
        item.status = DownloadStatus.DOWNLOADING
        worker.start()
    
    def _on_progress(self, track_id: str, downloaded: int, total: int, speed: float) -> None:
        """Handle progress update from worker."""
        if track_id in self.queue:
            item = self.queue[track_id]
            item.downloaded_bytes = downloaded
            item.total_bytes = total
            item.speed_kbps = speed
            item.progress = int((downloaded / total * 100) if total > 0 else 0)
            self.item_updated.emit(item)
    
    def _on_finished(self, track_id: str, file_path: str) -> None:
        """Handle download completion."""
        if track_id in self.queue:
            item = self.queue[track_id]
            item.file_path = file_path
            item.progress = 100
            self.item_updated.emit(item)
            self._process_queue()
    
    def _on_error(self, track_id: str, error_msg: str) -> None:
        """Handle download error."""
        if track_id in self.queue:
            item = self.queue[track_id]
            
            # Auto-retry if enabled
            if self.config.auto_retry and item.retry_count < item.max_retries:
                item.retry_count += 1
                item.status = DownloadStatus.PENDING
                item.error_message = f"Retry {item.retry_count}/{item.max_retries}: {error_msg}"
                self.item_updated.emit(item)
                self._process_queue()
            else:
                item.status = DownloadStatus.ERROR
                self.item_updated.emit(item)
                self._process_queue()
    
    def _on_status_changed(self, track_id: str, status: DownloadStatus) -> None:
        """Handle status change."""
        if track_id in self.queue:
            self.queue[track_id].status = status
            self.item_updated.emit(self.queue[track_id])
    
    def _on_worker_finished(self) -> None:
        """Called when any worker finishes."""
        # Check if queue is complete
        if all(item.status in [DownloadStatus.COMPLETED, DownloadStatus.ERROR, DownloadStatus.CANCELLED]
               for item in self.queue.values()):
            if self.queue:
                self.queue_completed.emit()


# =============================================================================
# MATERIAL YOU STYLESHEET GENERATOR
# =============================================================================

class MaterialStyleSheet:
    """Generates Material You QSS stylesheets."""
    
    @staticmethod
    def generate(accent_color: str, is_dark: bool = False) -> str:
        """
        Generate complete Material You stylesheet.
        
        Args:
            accent_color: Primary accent color (hex)
            is_dark: Whether to use dark theme
            
        Returns:
            Complete QSS stylesheet string
        """
        colors = MATERIAL_DARK_COLORS if is_dark else MATERIAL_COLORS
        
        # Override primary color with accent
        colors["primary"] = accent_color
        
        qss = f"""
/* ===== Material You Theme ===== */
/* Primary: {colors['primary']} */
/* Dark Mode: {is_dark} */

/* Global Styles */
QWidget {{
    font-family: "Segoe UI", "Roboto", "Arial", sans-serif;
    font-size: 14px;
    color: {colors['on_background']};
    background-color: {colors['background']};
}}

/* Main Window */
QMainWindow {{
    background-color: {colors['background']};
}}

/* ===== Buttons ===== */
QPushButton {{
    background-color: {colors['primary']};
    color: {colors['on_primary']};
    border: none;
    border-radius: 20px;
    padding: 10px 24px;
    font-weight: 500;
    font-size: 14px;
    min-height: 40px;
}}

QPushButton:hover {{
    background-color: {colors['primary_container']};
    color: {colors['on_primary_container']};
}}

QPushButton:pressed {{
    background-color: {colors['primary']};
    opacity: 0.8;
}}

QPushButton:disabled {{
    background-color: {colors['outline']};
    color: {colors['on_surface']};
    opacity: 0.5;
}}

/* Outlined Button */
QPushButton#outlinedButton {{
    background-color: transparent;
    border: 2px solid {colors['outline']};
    color: {colors['primary']};
}}

QPushButton#outlinedButton:hover {{
    background-color: {colors['surface_variant']};
}}

/* Text Button */
QPushButton#textButton {{
    background-color: transparent;
    color: {colors['primary']};
    border-radius: 10px;
    padding: 8px 16px;
    min-height: 36px;
}}

QPushButton#textButton:hover {{
    background-color: {colors['surface_variant']};
}}

/* Icon Button */
QPushButton#iconButton {{
    background-color: transparent;
    border-radius: 20px;
    padding: 10px;
    min-width: 40px;
    min-height: 40px;
}}

QPushButton#iconButton:hover {{
    background-color: {colors['surface_variant']};
}}

/* Floating Action Button */
QPushButton#fab {{
    background-color: {colors['primary_container']};
    color: {colors['on_primary_container']};
    border-radius: 28px;
    padding: 16px;
    min-width: 56px;
    min-height: 56px;
    font-size: 24px;
}}

QPushButton#fab:hover {{
    background-color: {colors['primary']};
    color: {colors['on_primary']};
}}

/* ===== Input Fields ===== */
QLineEdit {{
    background-color: {colors['surface_variant']};
    color: {colors['on_surface']};
    border: 1px solid {colors['outline']};
    border-radius: 12px;
    padding: 12px 16px;
    font-size: 14px;
}}

QLineEdit:focus {{
    border: 2px solid {colors['primary']};
}}

QLineEdit:disabled {{
    background-color: {colors['surface']};
    color: {colors['on_surface']};
    opacity: 0.5;
}}

QTextEdit {{
    background-color: {colors['surface_variant']};
    color: {colors['on_surface']};
    border: 1px solid {colors['outline']};
    border-radius: 12px;
    padding: 12px;
    font-size: 14px;
}}

QTextEdit:focus {{
    border: 2px solid {colors['primary']};
}}

/* ===== Labels ===== */
QLabel {{
    color: {colors['on_surface']};
    background-color: transparent;
    padding: 4px;
}}

QLabel#titleLabel {{
    font-size: 22px;
    font-weight: 600;
    color: {colors['on_surface']};
}}

QLabel#subtitleLabel {{
    font-size: 16px;
    color: {colors['on_surface_variant']};
}}

QLabel#captionLabel {{
    font-size: 12px;
    color: {colors['outline']};
}}

/* ===== Progress Bar ===== */
QProgressBar {{
    background-color: {colors['surface_variant']};
    border: none;
    border-radius: 8px;
    height: 16px;
    text-align: center;
    color: transparent;
}}

QProgressBar::chunk {{
    background-color: {colors['primary']};
    border-radius: 8px;
}}

/* ===== Scroll Area ===== */
QScrollArea {{
    background-color: transparent;
    border: none;
}}

QScrollBar:vertical {{
    background-color: {colors['surface']};
    width: 12px;
    border-radius: 6px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background-color: {colors['outline']};
    border-radius: 6px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {colors['on_surface_variant']};
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background-color: {colors['surface']};
    height: 12px;
    border-radius: 6px;
}}

QScrollBar::handle:horizontal {{
    background-color: {colors['outline']};
    border-radius: 6px;
    min-width: 20px;
}}

/* ===== List Widget ===== */
QListWidget {{
    background-color: transparent;
    border: none;
    outline: none;
    padding: 8px;
}}

QListWidget::item {{
    background-color: transparent;
    border-radius: 12px;
    padding: 8px;
    margin: 4px 0;
}}

QListWidget::item:hover {{
    background-color: {colors['surface_variant']};
}}

QListWidget::item:selected {{
    background-color: {colors['primary_container']};
    color: {colors['on_primary_container']};
}}

/* ===== Combo Box ===== */
QComboBox {{
    background-color: {colors['surface_variant']};
    color: {colors['on_surface']};
    border: 1px solid {colors['outline']};
    border-radius: 12px;
    padding: 10px 16px;
    min-height: 44px;
}}

QComboBox:hover {{
    border: 2px solid {colors['primary']};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
    padding-right: 8px;
}}

QComboBox QAbstractItemView {{
    background-color: {colors['surface']};
    border: 1px solid {colors['outline_variant']};
    border-radius: 12px;
    padding: 8px;
    selection-background-color: {colors['primary_container']};
    selection-color: {colors['on_primary_container']};
}}

/* ===== Slider ===== */
QSlider::groove:horizontal {{
    background-color: {colors['surface_variant']};
    height: 8px;
    border-radius: 4px;
}}

QSlider::handle:horizontal {{
    background-color: {colors['primary']};
    width: 20px;
    height: 20px;
    margin: -6px 0;
    border-radius: 10px;
}}

QSlider::handle:horizontal:hover {{
    background-color: {colors['primary_container']};
}}

/* ===== Tab Widget ===== */
QTabWidget::pane {{
    background-color: transparent;
    border: none;
}}

QTabBar::tab {{
    background-color: transparent;
    color: {colors['on_surface_variant']};
    padding: 12px 24px;
    border-bottom: 3px solid transparent;
}}

QTabBar::tab:selected {{
    color: {colors['primary']};
    border-bottom: 3px solid {colors['primary']};
}}

QTabBar::tab:hover {{
    color: {colors['primary']};
}}

/* ===== Frame/Card ===== */
QFrame#card {{
    background-color: {colors['surface']};
    border: 1px solid {colors['outline_variant']};
    border-radius: 16px;
    padding: 16px;
}}

QFrame#elevatedCard {{
    background-color: {colors['surface']};
    border-radius: 16px;
    padding: 16px;
}}

QFrame#filledCard {{
    background-color: {colors['surface_variant']};
    border-radius: 16px;
    padding: 16px;
}}

/* ===== Menu ===== */
QMenu {{
    background-color: {colors['surface']};
    border: 1px solid {colors['outline_variant']};
    border-radius: 12px;
    padding: 8px;
}}

QMenu::item {{
    padding: 10px 20px;
    border-radius: 8px;
    margin: 2px 0;
}}

QMenu::item:selected {{
    background-color: {colors['surface_variant']};
}}

/* ===== Checkbox ===== */
QCheckBox {{
    color: {colors['on_surface']};
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 20px;
    height: 20px;
    border-radius: 4px;
    border: 2px solid {colors['outline']};
    background-color: transparent;
}}

QCheckBox::indicator:checked {{
    background-color: {colors['primary']};
    border-color: {colors['primary']};
}}

/* ===== SpinBox ===== */
QSpinBox {{
    background-color: {colors['surface_variant']};
    color: {colors['on_surface']};
    border: 1px solid {colors['outline']};
    border-radius: 12px;
    padding: 10px 16px;
    min-height: 44px;
}}

QSpinBox:focus {{
    border: 2px solid {colors['primary']};
}}

/* ===== GroupBox ===== */
QGroupBox {{
    background-color: transparent;
    color: {colors['on_surface']};
    border: 2px solid {colors['outline_variant']};
    border-radius: 16px;
    margin-top: 16px;
    padding-top: 16px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: {colors['primary']};
}}

/* ===== ToolTip ===== */
QToolTip {{
    background-color: {colors['inverse_surface'] if 'inverse_surface' in colors else colors['on_surface']};
    color: {colors['inverse_on_surface'] if 'inverse_on_surface' in colors else colors['surface']};
    border: none;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 12px;
}}

/* ===== Separator ===== */
QFrame#separator {{
    background-color: {colors['outline_variant']};
    max-height: 1px;
}}

/* ===== Custom Widgets ===== */
QWidget#sidebar {{
    background-color: {colors['surface']};
    border-right: 1px solid {colors['outline_variant']};
}}

QWidget#header {{
    background-color: {colors['surface']};
    border-bottom: 1px solid {colors['outline_variant']};
}}

QWidget#searchResultCard {{
    background-color: {colors['surface']};
    border: 1px solid {colors['outline_variant']};
    border-radius: 16px;
    padding: 12px;
}}

QWidget#queueItem {{
    background-color: {colors['surface']};
    border: 1px solid {colors['outline_variant']};
    border-radius: 12px;
    padding: 12px;
    margin: 4px;
}}

QWidget#queueItem:hover {{
    background-color: {colors['surface_variant']};
}}

/* Snackbar/Toast */
QWidget#snackbar {{
    background-color: {colors['inverse_surface'] if 'inverse_surface' in colors else '#322F35'};
    color: {colors['inverse_on_surface'] if 'inverse_on_surface' in colors else '#F4EFF4'};
    border-radius: 8px;
    padding: 14px 16px;
}}
"""
        return qss


# =============================================================================
# CUSTOM WIDGETS
# =============================================================================

class SearchResultCard(QWidget):
    """Custom widget for displaying search result cards."""
    
    add_to_queue_signal = pyqtSignal(object)  # DownloadItem
    
    def __init__(self, track: Track, parent=None):
        """
        Initialize search result card.
        
        Args:
            track: Yandex Music Track object
            parent: Parent widget
        """
        super().__init__(parent)
        self.track = track
        self.setup_ui()
        self.load_cover()
    
    def setup_ui(self) -> None:
        """Setup card UI."""
        self.setObjectName("searchResultCard")
        self.setFixedHeight(100)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # Cover image
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(76, 76)
        self.cover_label.setStyleSheet("border-radius: 8px; background-color: #333;")
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.cover_label)
        
        # Info container
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(4)
        
        # Title
        self.title_label = QLabel(self._get_title())
        self.title_label.setObjectName("titleLabel")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.title_label.setWordWrap(True)
        info_layout.addWidget(self.title_label)
        
        # Artist
        self.artist_label = QLabel(self._get_artist())
        self.artist_label.setObjectName("subtitleLabel")
        info_layout.addWidget(self.artist_label)
        
        # Album and duration
        meta_label = QLabel(self._get_metadata())
        meta_label.setObjectName("captionLabel")
        info_layout.addWidget(meta_label)
        
        info_layout.addStretch()
        layout.addWidget(info_widget, 1)
        
        # Add button
        self.add_button = QPushButton("+")
        self.add_button.setObjectName("fab")
        self.add_button.setFixedSize(48, 48)
        self.add_button.clicked.connect(self._on_add_clicked)
        layout.addWidget(self.add_button)
    
    def _get_title(self) -> str:
        """Get track title."""
        return self.track.title or "Unknown"
    
    def _get_artist(self) -> str:
        """Get artist name."""
        if self.track.artists:
            return ", ".join([a.name for a in self.track.artists if a.name])
        return "Unknown Artist"
    
    def _get_metadata(self) -> str:
        """Get track metadata string."""
        parts = []
        if self.track.albums and len(self.track.albums) > 0:
            parts.append(self.track.albums[0].title or "Unknown Album")
        if self.track.duration_ms:
            parts.append(format_duration(self.track.duration_ms))
        return " • ".join(parts) if parts else ""
    
    def load_cover(self) -> None:
        """Load cover image asynchronously."""
        cover_url = self.track.cover_uri if hasattr(self.track, 'cover_uri') else None
        
        if cover_url:
            # Run in thread to avoid blocking
            threading.Thread(target=self._load_cover_thread, args=(cover_url,), daemon=True).start()
        else:
            self._set_default_cover()
    
    def _load_cover_thread(self, url: str) -> None:
        """Thread function to load cover image."""
        data = download_cover_image(url, 200)
        if data:
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            self.cover_label.setPixmap(pixmap.scaled(
                76, 76, 
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))
        else:
            # Use main thread for UI update
            QTimer.singleShot(0, self._set_default_cover)
    
    def _set_default_cover(self) -> None:
        """Set default cover placeholder."""
        self.cover_label.setText("♪")
        self.cover_label.setStyleSheet(
            "border-radius: 8px; background-color: #666; color: white; font-size: 32px;"
        )
    
    def _on_add_clicked(self) -> None:
        """Handle add to queue button click."""
        item = DownloadItem(
            track_id=str(self.track.id),
            title=self._get_title(),
            artist=self._get_artist(),
            album=self.track.albums[0].title if self.track.albums else "",
            cover_url=self.track.cover_uri or "",
            duration_ms=self.track.duration_ms or 0,
            year=self.track.albums[0].year if self.track.albums and self.track.albums[0].year else 0,
            genre=self.track.albums[0].genre if self.track.albums else "",
            track_number=1,
        )
        self.add_to_queue_signal.emit(item)


class QueueItemWidget(QWidget):
    """Custom widget for displaying queue items with progress."""
    
    remove_signal = pyqtSignal(str)  # track_id
    pause_signal = pyqtSignal(str)  # track_id
    resume_signal = pyqtSignal(str)  # track_id
    
    def __init__(self, item: DownloadItem, parent=None):
        """
        Initialize queue item widget.
        
        Args:
            item: DownloadItem to display
            parent: Parent widget
        """
        super().__init__(parent)
        self.item = item
        self.setup_ui()
        self.update_display()
    
    def setup_ui(self) -> None:
        """Setup widget UI."""
        self.setObjectName("queueItem")
        self.setFixedHeight(120)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # Cover image
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(76, 76)
        self.cover_label.setStyleSheet("border-radius: 8px; background-color: #333;")
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.cover_label)
        
        # Info and progress container
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(4)
        
        # Title
        self.title_label = QLabel(self.item.title)
        self.title_label.setObjectName("titleLabel")
        self.title_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        info_layout.addWidget(self.title_label)
        
        # Artist
        self.artist_label = QLabel(self.item.artist)
        self.artist_label.setObjectName("subtitleLabel")
        info_layout.addWidget(self.artist_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        info_layout.addWidget(self.progress_bar)
        
        # Status info
        self.status_label = QLabel("Pending")
        self.status_label.setObjectName("captionLabel")
        info_layout.addWidget(self.status_label)
        
        layout.addWidget(info_widget, 1)
        
        # Control buttons
        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(4)
        
        # Pause/Resume button
        self.control_button = QPushButton("⏸")
        self.control_button.setObjectName("iconButton")
        self.control_button.setFixedSize(40, 40)
        self.control_button.clicked.connect(self._on_control_clicked)
        controls_layout.addWidget(self.control_button)
        
        # Remove button
        self.remove_button = QPushButton("✕")
        self.remove_button.setObjectName("iconButton")
        self.remove_button.setFixedSize(40, 40)
        self.remove_button.setStyleSheet("color: #B3261E;")
        self.remove_button.clicked.connect(self._on_remove_clicked)
        controls_layout.addWidget(self.remove_button)
        
        controls_layout.addStretch()
        layout.addLayout(controls_layout)
        
        # Load cover
        self.load_cover()
    
    def load_cover(self) -> None:
        """Load cover image."""
        if self.item.cover_url:
            threading.Thread(target=self._load_cover_thread, daemon=True).start()
        else:
            self._set_default_cover()
    
    def _load_cover_thread(self) -> None:
        """Thread to load cover."""
        data = download_cover_image(self.item.cover_url, 200)
        if data:
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            self.cover_label.setPixmap(pixmap.scaled(
                76, 76,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))
        else:
            QTimer.singleShot(0, self._set_default_cover)
    
    def _set_default_cover(self) -> None:
        """Set default cover."""
        self.cover_label.setText("♪")
        self.cover_label.setStyleSheet(
            "border-radius: 8px; background-color: #666; color: white; font-size: 32px;"
        )
    
    def update_display(self) -> None:
        """Update widget display based on item state."""
        # Update progress
        self.progress_bar.setValue(self.item.progress)
        
        # Update status label
        status_texts = {
            DownloadStatus.PENDING: "Pending",
            DownloadStatus.DOWNLOADING: f"Downloading... {self.item.progress}%",
            DownloadStatus.PAUSED: "Paused",
            DownloadStatus.COMPLETED: "Completed",
            DownloadStatus.ERROR: f"Error: {self.item.error_message[:30]}",
            DownloadStatus.CANCELLED: "Cancelled",
        }
        
        status_text = status_texts.get(self.item.status, "Unknown")
        
        # Add speed info if downloading
        if self.item.status == DownloadStatus.DOWNLOADING and self.item.speed_kbps > 0:
            status_text += f" • {self.item.speed_kbps:.1f} KB/s"
        
        # Add size info if available
        if self.item.total_bytes > 0:
            status_text += f" • {format_size(self.item.downloaded_bytes)}/{format_size(self.item.total_bytes)}"
        
        self.status_label.setText(status_text)
        
        # Update control button
        if self.item.status == DownloadStatus.DOWNLOADING:
            self.control_button.setText("⏸")
            self.control_button.setToolTip("Pause")
        elif self.item.status == DownloadStatus.PAUSED:
            self.control_button.setText("▶")
            self.control_button.setToolTip("Resume")
        else:
            self.control_button.setEnabled(False)
    
    def _on_control_clicked(self) -> None:
        """Handle control button click."""
        if self.item.status == DownloadStatus.DOWNLOADING:
            self.pause_signal.emit(self.item.track_id)
        elif self.item.status == DownloadStatus.PAUSED:
            self.resume_signal.emit(self.item.track_id)
    
    def _on_remove_clicked(self) -> None:
        """Handle remove button click."""
        self.remove_signal.emit(self.item.track_id)


class Snackbar(QWidget):
    """Snackbar/Toast notification widget."""
    
    def __init__(self, message: str, parent=None):
        """
        Show snackbar notification.
        
        Args:
            message: Message to display
            parent: Parent widget
        """
        super().__init__(parent)
        self.setup_ui(message)
        self.show_animation()
    
    def setup_ui(self, message: str) -> None:
        """Setup snackbar UI."""
        self.setObjectName("snackbar")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        
        self.message_label = QLabel(message)
        self.message_label.setStyleSheet("color: inherit; font-size: 14px;")
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)
        
        # Auto-hide after 3 seconds
        QTimer.singleShot(3000, self.fade_out)
    
    def show_animation(self) -> None:
        """Show with fade-in animation."""
        self.setWindowOpacity(0)
        self.show()
        
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(300)
        self.animation.setStartValue(0)
        self.animation.setEndValue(1)
        self.animation.start()
    
    def fade_out(self) -> None:
        """Fade out and close."""
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(300)
        self.animation.setStartValue(1)
        self.animation.setEndValue(0)
        self.animation.finished.connect(self.close)
        self.animation.start()


# =============================================================================
# MAIN WINDOW
# =============================================================================

class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        """Initialize main window."""
        super().__init__()
        
        # Load configuration
        self.config = load_config()
        
        # Initialize API
        self.api = YandexMusicAPI()
        
        # Try to load token from keyring
        self._load_token()
        
        # Initialize queue manager
        self.queue_manager = QueueManager(self.api, self.config)
        
        # Setup UI
        self.setup_ui()
        self.apply_theme()
        
        # Connect signals
        self._connect_signals()
        
        logger.info("Application initialized")
    
    def setup_ui(self) -> None:
        """Setup main window UI."""
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Sidebar
        self.sidebar = self._create_sidebar()
        main_layout.addWidget(self.sidebar)
        
        # Content area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # Header
        self.header = self._create_header()
        content_layout.addWidget(self.header)
        
        # Stacked widget for pages
        self.stack = QStackedWidget()
        self.stack.addWidget(self._create_search_page())
        self.stack.addWidget(self._create_queue_page())
        self.stack.addWidget(self._create_settings_page())
        self.stack.addWidget(self._create_help_page())
        self.stack.addWidget(self._create_about_page())
        content_layout.addWidget(self.stack)
        
        main_layout.addWidget(content_widget, 1)
    
    def _create_sidebar(self) -> QWidget:
        """Create sidebar navigation."""
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(256)
        
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 24, 16, 24)
        layout.setSpacing(8)
        
        # App logo/title
        logo_label = QLabel("🎵 Yandex Music")
        logo_label.setObjectName("titleLabel")
        logo_label.setStyleSheet("font-size: 20px; font-weight: 700; padding: 16px 0;")
        layout.addWidget(logo_label)
        
        layout.addSpacing(24)
        
        # Navigation buttons
        nav_buttons = [
            ("🔍", "Поиск", 0),
            ("📥", "Загрузки", 1),
            ("⚙️", "Настройки", 2),
            ("❓", "Справка", 3),
            ("ℹ️", "О программе", 4),
        ]
        
        for icon, text, index in nav_buttons:
            btn = QPushButton(f"{icon}  {text}")
            btn.setCheckable(True)
            btn.setChecked(index == 0)
            btn.setFixedHeight(56)
            btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding-left: 20px;
                    border-radius: 16px;
                    background-color: transparent;
                    color: inherit;
                }
                QPushButton:checked {
                    background-color: var(--primary-container);
                }
                QPushButton:hover:!checked {
                    background-color: rgba(128, 128, 128, 0.1);
                }
            """)
            btn.clicked.connect(lambda checked, i=index: self._navigate_to(i))
            layout.addWidget(btn)
        
        layout.addStretch()
        
        return sidebar
    
    def _create_header(self) -> QWidget:
        """Create header with search bar."""
        header = QWidget()
        header.setObjectName("header")
        header.setFixedHeight(80)
        
        layout = QHBoxLayout(header)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(16)
        
        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск треков, альбомов, исполнителей...")
        self.search_input.returnPressed.connect(self._perform_search)
        layout.addWidget(self.search_input)
        
        # Search button
        search_btn = QPushButton("🔍 Поиск")
        search_btn.setFixedWidth(120)
        search_btn.clicked.connect(self._perform_search)
        layout.addWidget(search_btn)
        
        # Auth status
        self.auth_label = QLabel("Не авторизован")
        self.auth_label.setObjectName("captionLabel")
        layout.addWidget(self.auth_label)
        
        # Login button
        self.login_btn = QPushButton("Войти")
        self.login_btn.setObjectName("textButton")
        self.login_btn.clicked.connect(self._show_login_dialog)
        layout.addWidget(self.login_btn)
        
        return header
    
    def _create_search_page(self) -> QWidget:
        """Create search results page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # Results label
        self.results_label = QLabel("Результаты поиска")
        self.results_label.setObjectName("titleLabel")
        layout.addWidget(self.results_label)
        
        # Scroll area for results
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(12)
        self.results_layout.addStretch()
        
        scroll.setWidget(self.results_container)
        layout.addWidget(scroll)
        
        return page
    
    def _create_queue_page(self) -> QWidget:
        """Create downloads queue page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # Header with controls
        header_layout = QHBoxLayout()
        
        queue_label = QLabel("Очередь загрузок")
        queue_label.setObjectName("titleLabel")
        header_layout.addWidget(queue_label)
        
        header_layout.addStretch()
        
        # Pause all button
        pause_all_btn = QPushButton("⏸ Пауза")
        pause_all_btn.setObjectName("textButton")
        pause_all_btn.clicked.connect(self.queue_manager.pause_all)
        header_layout.addWidget(pause_all_btn)
        
        # Resume all button
        resume_all_btn = QPushButton("▶ Старт")
        resume_all_btn.setObjectName("textButton")
        resume_all_btn.clicked.connect(self.queue_manager.resume_all)
        header_layout.addWidget(resume_all_btn)
        
        # Clear completed button
        clear_btn = QPushButton("🗑 Очистить")
        clear_btn.setObjectName("textButton")
        clear_btn.clicked.connect(self.queue_manager.clear_completed)
        header_layout.addWidget(clear_btn)
        
        layout.addLayout(header_layout)
        
        # Queue list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.queue_container = QWidget()
        self.queue_layout = QVBoxLayout(self.queue_container)
        self.queue_layout.setContentsMargins(0, 0, 0, 0)
        self.queue_layout.setSpacing(8)
        self.queue_layout.addStretch()
        
        scroll.setWidget(self.queue_container)
        layout.addWidget(scroll)
        
        return page
    
    def _create_settings_page(self) -> QWidget:
        """Create settings page."""
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)
        
        # Download Settings
        download_group = QGroupBox("📥 Настройки загрузки")
        download_layout = QFormLayout()
        download_layout.setSpacing(16)
        
        # Download path
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit(self.config.download_path)
        path_layout.addWidget(self.path_input)
        browse_btn = QPushButton("Обзор...")
        browse_btn.clicked.connect(self._browse_download_path)
        path_layout.addWidget(browse_btn)
        download_layout.addRow("Папка:", path_layout)
        
        # Max parallel downloads
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 5)
        self.parallel_spin.setValue(self.config.max_parallel_downloads)
        download_layout.addRow("Потоков:", self.parallel_spin)
        
        # Quality preference
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Lossless (FLAC)", "Высокое (MP3 320kbps)"])
        self.quality_combo.setCurrentIndex(0 if self.config.preferred_quality == "lossless" else 1)
        download_layout.addRow("Качество:", self.quality_combo)
        
        # Auto retry
        self.retry_check = QCheckBox("Автоматический повтор при ошибке")
        self.retry_check.setChecked(self.config.auto_retry)
        download_layout.addRow("", self.retry_check)
        
        # Max retries
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(1, 10)
        self.retries_spin.setValue(self.config.max_retries)
        download_layout.addRow("Макс. попыток:", self.retries_spin)
        
        download_group.setLayout(download_layout)
        layout.addWidget(download_group)
        
        # File Organization
        org_group = QGroupBox("📁 Организация файлов")
        org_layout = QVBoxLayout()
        org_layout.setSpacing(16)
        
        self.artist_folder_check = QCheckBox("Создавать папку исполнителя")
        self.artist_folder_check.setChecked(self.config.create_artist_folder)
        org_layout.addWidget(self.artist_folder_check)
        
        self.album_folder_check = QCheckBox("Создавать папку альбома")
        self.album_folder_check.setChecked(self.config.create_album_folder)
        org_layout.addWidget(self.album_folder_check)
        
        self.cover_check = QCheckBox("Сохранять обложку")
        self.cover_check.setChecked(self.config.save_cover)
        org_layout.addWidget(self.cover_check)
        
        self.lyrics_check = QCheckBox("Сохранять текст песни")
        self.lyrics_check.setChecked(self.config.save_lyrics)
        org_layout.addWidget(self.lyrics_check)
        
        org_group.setLayout(org_layout)
        layout.addWidget(org_group)
        
        # Appearance
        appearance_group = QGroupBox("🎨 Внешний вид")
        appearance_layout = QFormLayout()
        appearance_layout.setSpacing(16)
        
        # Theme mode
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Системная", "Светлая", "Тёмная"])
        theme_index = {"system": 0, "light": 1, "dark": 2}.get(self.config.theme_mode, 0)
        self.theme_combo.setCurrentIndex(theme_index)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        appearance_layout.addRow("Тема:", self.theme_combo)
        
        # Accent color
        color_layout = QHBoxLayout()
        self.color_input = QLineEdit(self.config.accent_color)
        self.color_input.setPlaceholderText("#6750A4")
        self.color_input.setFixedWidth(120)
        color_layout.addWidget(self.color_input)
        
        color_preview = QFrame()
        color_preview.setFixedSize(40, 40)
        color_preview.setStyleSheet(f"background-color: {self.config.accent_color}; border-radius: 20px;")
        self.color_preview = color_preview
        color_layout.addWidget(color_preview)
        
        self.color_input.textChanged.connect(self._on_accent_color_changed)
        appearance_layout.addRow("Акцентный цвет:", color_layout)
        
        appearance_group.setLayout(appearance_layout)
        layout.addWidget(appearance_group)
        
        layout.addStretch()
        
        # Save button
        save_btn = QPushButton("💾 Сохранить настройки")
        save_btn.setFixedHeight(56)
        save_btn.clicked.connect(self._save_settings)
        layout.addWidget(save_btn)
        
        container.setLayout(layout)
        scroll.setWidget(container)
        
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)
        
        return page
    
    def _create_help_page(self) -> QWidget:
        """Create help page with instructions."""
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)
        
        # Title
        title = QLabel("📖 Справка и Руководство")
        title.setObjectName("titleLabel")
        title.setStyleSheet("font-size: 28px; font-weight: 700;")
        layout.addWidget(title)
        
        # How to get token section
        token_section = QGroupBox("🔑 Как получить API токен Яндекс Музыки")
        token_layout = QVBoxLayout()
        token_layout.setSpacing(16)
        
        token_steps = QTextEdit()
        token_steps.setReadOnly(True)
        token_steps.setHtml("""
        <h3>Способ 1: Через браузер (рекомендуется)</h3>
        <ol>
            <li>Откройте <a href="https://music.yandex.ru" style="color: #6750A4;">music.yandex.ru</a> в браузере</li>
            <li>Войдите в свой аккаунт Яндекса</li>
            <li>Откройте инструменты разработчика (F12)</li>
            <li>Перейдите на вкладку Network (Сеть)</li>
            <li>Обновите страницу (F5)</li>
            <li>Найдите запрос к API (обычно содержит "api.music.yandex.net")</li>
            <li>В заголовках запроса найдите параметр <code>Authorization</code> или <code>oauth_token</code></li>
            <li>Скопируйте значение токена (длинная строка символов)</li>
        </ol>
        
        <h3>Способ 2: Через мобильное приложение</h3>
        <ol>
            <li>Установите приложение Яндекс Музыка на телефон</li>
            <li>Войдите в свой аккаунт</li>
            <li>Используйте приложение для перехвата трафика (например, HTTP Canary на Android)</li>
            <li>Найдите токен в запросах к API</li>
        </ol>
        
        <h3>Способ 3: Готовые библиотеки</h3>
        <p>Можно использовать библиотеку <code>yandex-music</code> для получения токена:</p>
        <pre style="background: #f5f5f5; padding: 12px; border-radius: 8px;">
from yandex_music.utils import Token
        
# Следуйте инструкциям из документации библиотеки
# https://yandex-music.readthedocs.io/
        </pre>
        
        <p style="color: #B3261E;"><strong>Важно:</strong> Токен является конфиденциальной информацией. Не передавайте его третьим лицам!</p>
        """)
        token_layout.addWidget(token_steps)
        token_section.setLayout(token_layout)
        layout.addWidget(token_section)
        
        # Usage section
        usage_section = QGroupBox("📱 Как пользоваться программой")
        usage_layout = QVBoxLayout()
        usage_layout.setSpacing(16)
        
        usage_text = QTextEdit()
        usage_text.setReadOnly(True)
        usage_text.setHtml("""
        <h3>1. Авторизация</h3>
        <ul>
            <li>Нажмите кнопку "Войти" в правом верхнем углу</li>
            <li>Вставьте полученный токен в поле ввода</li>
            <li>Нажмите "Сохранить"</li>
        </ul>
        
        <h3>2. Поиск музыки</h3>
        <ul>
            <li>Введите название трека, альбома или исполнителя в строку поиска</li>
            <li>Нажмите Enter или кнопку "Поиск"</li>
            <li>В результатах поиска нажмите "+" чтобы добавить трек в очередь</li>
        </ul>
        
        <h3>3. Управление загрузками</h3>
        <ul>
            <li>Перейдите на вкладку "Загрузки"</li>
            <li>Используйте кнопки ⏸ и ▶ для паузы/возобновления отдельных треков</li>
            <li>Кнопка ✕ удаляет трек из очереди</li>
            <li>Кнопки "Пауза" и "Старт" управляют всеми загрузками</li>
        </ul>
        
        <h3>4. Настройки</h3>
        <ul>
            <li>Выберите папку для сохранения музыки</li>
            <li>Настройте количество одновременных загрузок (1-5)</li>
            <li>Выберите предпочтительное качество (Lossless или HQ)</li>
            <li>Настройте организацию файлов (папки исполнителя/альбома)</li>
            <li>Измените тему оформления и акцентный цвет</li>
        </ul>
        """)
        usage_layout.addWidget(usage_text)
        usage_section.setLayout(usage_layout)
        layout.addWidget(usage_section)
        
        # FAQ section
        faq_section = QGroupBox("❓ Часто задаваемые вопросы")
        faq_layout = QVBoxLayout()
        faq_layout.setSpacing(16)
        
        faq_text = QTextEdit()
        faq_text.setReadOnly(True)
        faq_text.setHtml("""
        <h3>Почему некоторые треки не скачиваются?</h3>
        <p>Некоторые треки могут быть недоступны для скачивания из-за ограничений правообладателей или региональных ограничений.</p>
        
        <h3>Какое максимальное качество доступно?</h3>
        <p>Приложение автоматически выбирает наилучшее доступное качество. Если доступен Lossless (FLAC), будет загружен он. В противном случае - MP3 320 kbps.</p>
        
        <h3>Где хранятся скачанные файлы?</h3>
        <p>По умолчанию в папке ~/Music/YandexMusic. Вы можете изменить это в настройках.</p>
        
        <h3>Что делать если программа зависает?</h3>
        <p>Уменьшите количество параллельных загрузок в настройках. Также проверьте скорость интернет-соединения.</p>
        
        <h3>Как обновить токен?</h3>
        <p>Токены имеют ограниченный срок действия. Если перестала работать авторизация, получите новый токен и введите его в настройках.</p>
        """)
        faq_layout.addWidget(faq_text)
        faq_section.setLayout(faq_layout)
        layout.addWidget(faq_section)
        
        layout.addStretch()
        container.setLayout(layout)
        scroll.setWidget(container)
        
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)
        
        return page
    
    def _create_about_page(self) -> QWidget:
        """Create about page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Logo/icon
        logo_label = QLabel("🎵")
        logo_label.setStyleSheet("font-size: 72px;")
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo_label)
        
        # App name
        name_label = QLabel(APP_NAME)
        name_label.setObjectName("titleLabel")
        name_label.setStyleSheet("font-size: 32px; font-weight: 700;")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)
        
        # Version
        version_label = QLabel(f"Версия {APP_VERSION}")
        version_label.setObjectName("subtitleLabel")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)
        
        layout.addSpacing(24)
        
        # Description
        desc_text = QTextEdit()
        desc_text.setReadOnly(True)
        desc_text.setMaximumWidth(600)
        desc_text.setHtml("""
        <p style="text-align: center; font-size: 16px; line-height: 1.6;">
        Современное десктопное приложение для поиска и скачивания музыки из Яндекс Музыки 
        в максимальном качестве с автоматическим тегированием и красивым интерфейсом 
        в стиле Material You.
        </p>
        """)
        desc_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc_text)
        
        layout.addSpacing(24)
        
        # Features
        features_label = QLabel(
            "✨ Особенности:\n\n"
            "• Поиск треков, альбомов и исполнителей\n"
            "• Пакетная загрузка с очередью\n"
            "• Автоматическое тегирование (ID3/FLAC)\n"
            "• Обложки и тексты песен\n"
            "• Material You дизайн\n"
            "• Тёмная и светлая темы\n"
            "• Параллельные загрузки"
        )
        features_label.setStyleSheet("font-size: 14px; line-height: 1.8;")
        features_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(features_label)
        
        layout.addSpacing(24)
        
        # Tech stack
        tech_label = QLabel(
            "Технологии:\n"
            "Python 3.10+ • PyQt6 • yandex-music • mutagen"
        )
        tech_label.setObjectName("captionLabel")
        tech_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(tech_label)
        
        layout.addStretch()
        
        # Copyright
        copyright_label = QLabel(f"© 2024 {APP_NAME}. Все права защищены.")
        copyright_label.setObjectName("captionLabel")
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(copyright_label)
        
        return page
    
    def _connect_signals(self) -> None:
        """Connect queue manager signals."""
        self.queue_manager.item_added.connect(self._on_queue_item_added)
        self.queue_manager.item_updated.connect(self._on_queue_item_updated)
        self.queue_manager.item_removed.connect(self._on_queue_item_removed)
        self.queue_manager.queue_completed.connect(self._on_queue_completed)
    
    def _navigate_to(self, index: int) -> None:
        """Navigate to page by index."""
        self.stack.setCurrentIndex(index)
    
    def _perform_search(self) -> None:
        """Perform search query."""
        query = self.search_input.text().strip()
        if not query:
            self._show_snackbar("Введите поисковый запрос")
            return
        
        if not self.api.is_authenticated():
            self._show_snackbar("Требуется авторизация для поиска")
            return
        
        # Clear previous results
        while self.results_layout.count() > 1:
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.results_label.setText(f"Поиск: {query}")
        
        # Run search in thread
        def search_thread():
            results = self.api.search(query, type_="track")
            return results
        
        def search_done(results):
            if results and results.tracks:
                for track in results.tracks.results[:50]:  # Limit to 50 results
                    card = SearchResultCard(track)
                    card.add_to_queue_signal.connect(self._add_to_queue)
                    self.results_layout.insertWidget(self.results_layout.count() - 1, card)
            else:
                no_results = QLabel("Ничего не найдено")
                no_results.setStyleSheet("font-size: 18px; color: gray; padding: 40px;")
                no_results.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.results_layout.insertWidget(self.results_layout.count() - 1, no_results)
        
        # Show loading
        loading = QLabel("Поиск...")
        loading.setStyleSheet("font-size: 18px; color: gray; padding: 40px;")
        loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.results_layout.insertWidget(self.results_layout.count() - 1, loading)
        
        # Start search thread
        threading.Thread(target=lambda: QTimer.singleShot(0, lambda: search_done(search_thread())), daemon=True).start()
        search_thread()
        QTimer.singleShot(100, lambda: search_done(search_thread()))
    
    def _add_to_queue(self, item: DownloadItem) -> None:
        """Add item to download queue."""
        self.queue_manager.add_item(item)
        self._show_snackbar(f"Добавлено: {item.title}")
    
    def _on_queue_item_added(self, item: DownloadItem) -> None:
        """Handle queue item added."""
        widget = QueueItemWidget(item)
        widget.remove_signal.connect(self.queue_manager.remove_item)
        widget.pause_signal.connect(self.queue_manager.pause_item)
        widget.resume_signal.connect(self.queue_manager.resume_item)
        
        # Store widget reference
        item._widget = widget
        
        self.queue_layout.insertWidget(self.queue_layout.count() - 1, widget)
    
    def _on_queue_item_updated(self, item: DownloadItem) -> None:
        """Handle queue item updated."""
        if hasattr(item, '_widget'):
            item._widget.update_display()
    
    def _on_queue_item_removed(self, track_id: str) -> None:
        """Handle queue item removed."""
        # Find and remove widget
        for i in range(self.queue_layout.count()):
            item = self.queue_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, QueueItemWidget) and widget.item.track_id == track_id:
                    widget.deleteLater()
                    break
    
    def _on_queue_completed(self) -> None:
        """Handle queue completion."""
        self._show_snackbar("Все загрузки завершены!")
    
    def _show_login_dialog(self) -> None:
        """Show login dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Авторизация")
        dialog.setMinimumWidth(500)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(16)
        
        # Instructions
        instr = QLabel(
            "Для работы приложения необходим токен Яндекс Музыки.\n"
            "Инструкции по получению токена смотрите во вкладке 'Справка'."
        )
        instr.setWordWrap(True)
        layout.addWidget(instr)
        
        # Token input
        token_input = QLineEdit()
        token_input.setPlaceholderText("Введите токен")
        token_input.setText(self.api.token or "")
        layout.addWidget(token_input)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Отмена")
        cancel_btn.setObjectName("textButton")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(lambda: self._save_token(token_input.text(), dialog))
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
        
        dialog.exec()
    
    def _save_token(self, token: str, dialog: QDialog) -> None:
        """Save token to keyring."""
        if token.strip():
            try:
                keyring.set_password(SERVICE_NAME, "token", token)
                self.api.set_token(token)
                self._update_auth_status()
                dialog.accept()
                self._show_snackbar("Токен сохранён")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить токен: {e}")
        else:
            QMessageBox.warning(self, "Ошибка", "Введите токен")
    
    def _load_token(self) -> None:
        """Load token from keyring."""
        try:
            token = keyring.get_password(SERVICE_NAME, "token")
            if token:
                self.api.set_token(token)
                self._update_auth_status()
        except Exception as e:
            logger.warning(f"Failed to load token: {e}")
    
    def _update_auth_status(self) -> None:
        """Update auth status label."""
        if self.api.is_authenticated():
            self.auth_label.setText("✓ Авторизован")
            self.auth_label.setStyleSheet("color: #4CAF50; font-weight: 600;")
            self.login_btn.setText("Выйти")
            self.login_btn.clicked.connect(self._logout)
        else:
            self.auth_label.setText("Не авторизован")
            self.auth_label.setStyleSheet("color: gray;")
            self.login_btn.setText("Войти")
            self.login_btn.clicked.connect(self._show_login_dialog)
    
    def _logout(self) -> None:
        """Logout and clear token."""
        try:
            keyring.delete_password(SERVICE_NAME, "token")
        except Exception:
            pass
        self.api.set_token(None)
        self._update_auth_status()
        self._show_snackbar("Выход выполнен")
    
    def _browse_download_path(self) -> None:
        """Browse for download path."""
        path = QFileDialog.getExistingDirectory(self, "Выберите папку для загрузок")
        if path:
            self.path_input.setText(path)
    
    def _on_theme_changed(self, index: int) -> None:
        """Handle theme mode change."""
        modes = ["system", "light", "dark"]
        self.config.theme_mode = modes[index]
        self.apply_theme()
    
    def _on_accent_color_changed(self, color: str) -> None:
        """Handle accent color change."""
        if color.startswith("#") and len(color) == 7:
            try:
                self.color_preview.setStyleSheet(f"background-color: {color}; border-radius: 20px;")
                self.config.accent_color = color
                self.apply_theme()
            except Exception:
                pass
    
    def apply_theme(self) -> None:
        """Apply current theme."""
        # Determine theme mode
        if self.config.theme_mode == "system":
            is_dark = darkdetect.isDark()
        elif self.config.theme_mode == "dark":
            is_dark = True
        else:
            is_dark = False
        
        # Generate and apply stylesheet
        qss = MaterialStyleSheet.generate(self.config.accent_color, is_dark)
        self.setStyleSheet(qss)
    
    def _save_settings(self) -> None:
        """Save settings to config."""
        # Update config from UI
        self.config.download_path = self.path_input.text()
        self.config.max_parallel_downloads = self.parallel_spin.value()
        self.config.preferred_quality = "lossless" if self.quality_combo.currentIndex() == 0 else "hq"
        self.config.auto_retry = self.retry_check.isChecked()
        self.config.max_retries = self.retries_spin.value()
        self.config.create_artist_folder = self.artist_folder_check.isChecked()
        self.config.create_album_folder = self.album_folder_check.isChecked()
        self.config.save_cover = self.cover_check.isChecked()
        self.config.save_lyrics = self.lyrics_check.isChecked()
        
        # Save to file
        save_config(self.config)
        self._show_snackbar("Настройки сохранены")
    
    def _show_snackbar(self, message: str) -> None:
        """Show snackbar notification."""
        snackbar = Snackbar(message, self)
        
        # Position at bottom center
        screen_geo = self.screen().geometry()
        snackbar_width = 400
        snackbar_height = 60
        
        x = (screen_geo.width() - snackbar_width) // 2
        y = screen_geo.height() - snackbar_height - 80
        
        snackbar.move(x, y)
    
    def closeEvent(self, event) -> None:
        """Handle window close."""
        # Stop all downloads
        self.queue_manager.pause_all()
        
        # Save config
        save_config(self.config)
        
        event.accept()


# =============================================================================
# APPLICATION ENTRY POINT
# =============================================================================

def main():
    """Main entry point."""
    # Enable High DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("YandexMusicDownloader")
    
    # Set application font
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
