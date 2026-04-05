from __future__ import annotations

"""Automatic model management for local LLM mode.

This module provides automatic downloading and updating of Ollama models
based on available GPU resources. It can:
- Detect GPU capabilities
- Calculate which models fit
- Automatically download recommended models
- Keep models updated
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from .gpu_detector import (
    SystemGPUInfo,
    calculate_model_vram,
    detect_gpus,
    get_optimal_default_model,
    recommend_models_for_gpu,
)

logger = logging.getLogger(__name__)


@dataclass
class ModelDownloadStatus:
    """Status of a model download operation."""
    
    model_name: str
    status: str  # "pending", "downloading", "complete", "error"
    progress: float = 0.0  # 0-100
    error_message: Optional[str] = None
    total_size: Optional[str] = None
    completed_size: Optional[str] = None


class ModelManager:
    """Manages Ollama model downloads and updates."""
    
    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        auto_download: bool = False,
        auto_download_best: bool = True,
    ):
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.auto_download = auto_download
        self.auto_download_best = auto_download_best
        self._client: Optional[httpx.AsyncClient] = None
        self._gpu_info: Optional[SystemGPUInfo] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=300.0)  # Long timeout for downloads
        return self._client
    
    async def is_ollama_running(self) -> bool:
        """Check if Ollama is running."""
        try:
            client = await self._get_client()
            resp = await client.get(f"{self.ollama_base_url}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False
    
    async def list_installed_models(self) -> list[str]:
        """List models already installed in Ollama."""
        try:
            client = await self._get_client()
            resp = await client.get(f"{self.ollama_base_url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.error(f"Failed to list installed models: {e}")
        return []
    
    async def get_model_info(self, model_name: str) -> Optional[dict]:
        """Get information about a specific model."""
        try:
            client = await self._get_client()
            resp = await client.post(
                f"{self.ollama_base_url}/api/show",
                json={"name": model_name},
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.debug(f"Failed to get model info for {model_name}: {e}")
        return None
    
    async def download_model(
        self,
        model_name: str,
        progress_callback: Optional[callable] = None,
    ) -> ModelDownloadStatus:
        """Download a model from Ollama.
        
        Args:
            model_name: Name of the model to download
            progress_callback: Optional callback(status) for progress updates
        
        Returns:
            ModelDownloadStatus with final status
        """
        status = ModelDownloadStatus(model_name=model_name, status="downloading")
        
        try:
            client = await self._get_client()
            
            logger.info(f"Starting download of {model_name}...")
            
            # Stream the download
            async with client.stream(
                "POST",
                f"{self.ollama_base_url}/api/pull",
                json={"name": model_name, "stream": True},
            ) as response:
                if response.status_code != 200:
                    status.status = "error"
                    status.error_message = f"HTTP {response.status_code}"
                    return status
                
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    
                    try:
                        data = json.loads(line)
                        
                        # Update status from stream
                        if "total" in data and "completed" in data:
                            status.total_size = self._format_size(data["total"])
                            status.completed_size = self._format_size(data["completed"])
                            if data["total"] > 0:
                                status.progress = (data["completed"] / data["total"]) * 100
                        
                        if "status" in data:
                            if data["status"] == "success":
                                status.status = "complete"
                                status.progress = 100.0
                            elif "error" in data:
                                status.status = "error"
                                status.error_message = data.get("error", "Unknown error")
                        
                        if progress_callback:
                            progress_callback(status)
                            
                    except json.JSONDecodeError:
                        continue
            
            if status.status == "downloading":
                # If we got here without error, assume complete
                status.status = "complete"
                status.progress = 100.0
            
            logger.info(f"Download of {model_name} completed")
            
        except Exception as e:
            logger.error(f"Failed to download {model_name}: {e}")
            status.status = "error"
            status.error_message = str(e)
        
        return status
    
    def _format_size(self, bytes_val: int) -> str:
        """Format bytes to human readable string."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes_val < 1024.0:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.1f} PB"
    
    async def ensure_recommended_models(
        self,
        gpu_info: Optional[SystemGPUInfo] = None,
        progress_callback: Optional[callable] = None,
    ) -> list[ModelDownloadStatus]:
        """Ensure recommended models are downloaded.
        
        Downloads the best models that fit the available GPU VRAM.
        
        Args:
            gpu_info: GPU info (auto-detected if None)
            progress_callback: Optional callback(model_name, status) for progress
        
        Returns:
            List of download statuses
        """
        if gpu_info is None:
            gpu_info = detect_gpus()
        
        self._gpu_info = gpu_info
        
        # Get recommended models
        recommendations = recommend_models_for_gpu(gpu_info)
        
        if not recommendations:
            logger.warning("No models recommended for available GPU")
            return []
        
        # Get already installed models
        installed = await self.list_installed_models()
        
        # Determine which models to download
        if self.auto_download_best:
            # Download only the best model that fits
            models_to_download = [recommendations[0]["name"]]
        else:
            # Download top 3 recommended models
            models_to_download = [m["name"] for m in recommendations[:3]]
        
        # Filter out already installed
        models_to_download = [m for m in models_to_download if m not in installed]
        
        if not models_to_download:
            logger.info("All recommended models are already installed")
            return []
        
        # Download models
        results = []
        for model_name in models_to_download:
            def make_callback(name):
                return lambda status: progress_callback and progress_callback(name, status)
            
            status = await self.download_model(model_name, make_callback(model_name))
            results.append(status)
        
        return results
    
    async def delete_model(self, model_name: str) -> bool:
        """Delete a model from Ollama.
        
        Args:
            model_name: Name of the model to delete
        
        Returns:
            True if successful
        """
        try:
            client = await self._get_client()
            resp = await client.delete(f"{self.ollama_base_url}/api/delete", json={"name": model_name})
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Failed to delete {model_name}: {e}")
            return False
    
    async def update_model(self, model_name: str) -> ModelDownloadStatus:
        """Update a model to the latest version.
        
        Args:
            model_name: Name of the model to update
        
        Returns:
            ModelDownloadStatus
        """
        logger.info(f"Updating {model_name}...")
        # In Ollama, pulling an existing model updates it
        return await self.download_model(model_name)
    
    async def get_recommended_default(self) -> str:
        """Get the recommended default model for the system.
        
        Returns:
            Model name string
        """
        if self._gpu_info is None:
            self._gpu_info = detect_gpus()
        
        return get_optimal_default_model(self._gpu_info)
    
    async def aclose(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


async def auto_setup_models(
    ollama_base_url: str = "http://localhost:11434",
    progress_callback: Optional[callable] = None,
) -> list[ModelDownloadStatus]:
    """Convenience function for automatic model setup.
    
    Detects GPU and downloads appropriate models automatically.
    
    Args:
        ollama_base_url: Ollama server URL
        progress_callback: Optional callback(model_name, status)
    
    Returns:
        List of download statuses
    """
    manager = ModelManager(
        ollama_base_url=ollama_base_url,
        auto_download=True,
        auto_download_best=True,
    )
    
    if not await manager.is_ollama_running():
        logger.error("Ollama is not running. Start it with: ollama serve")
        return []
    
    results = await manager.ensure_recommended_models(progress_callback=progress_callback)
    await manager.aclose()
    
    return results


# Global manager instance
_manager: Optional[ModelManager] = None


def get_model_manager(
    ollama_base_url: str = "http://localhost:11434",
) -> ModelManager:
    """Get or create the global model manager."""
    global _manager
    if _manager is None:
        _manager = ModelManager(ollama_base_url=ollama_base_url)
    return _manager
