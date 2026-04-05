from __future__ import annotations

"""GPU detection and VRAM calculation for automatic model selection.

This module detects available GPUs and calculates how much VRAM is available
for loading LLM models. It helps automatically select and download models
that fit the available hardware.
"""

import logging
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GPUInfo:
    """Information about a GPU."""
    
    name: str
    total_vram_mb: int
    used_vram_mb: int
    free_vram_mb: int
    driver_version: str = ""
    
    @property
    def total_vram_gb(self) -> float:
        """Total VRAM in GB."""
        return self.total_vram_mb / 1024
    
    @property
    def free_vram_gb(self) -> float:
        """Free VRAM in GB."""
        return self.free_vram_mb / 1024
    
    @property
    def used_vram_gb(self) -> float:
        """Used VRAM in GB."""
        return self.used_vram_mb / 1024


@dataclass  
class SystemGPUInfo:
    """GPU information for the entire system."""
    
    gpus: list[GPUInfo]
    platform: str  # "nvidia", "amd", "apple_silicon", "cpu"
    
    @property
    def total_vram_gb(self) -> float:
        """Total VRAM across all GPUs."""
        return sum(gpu.total_vram_gb for gpu in self.gpus)
    
    @property
    def free_vram_gb(self) -> float:
        """Free VRAM across all GPUs."""
        return sum(gpu.free_vram_gb for gpu in self.gpus)
    
    @property
    def primary_gpu(self) -> Optional[GPUInfo]:
        """Get the primary (most capable) GPU."""
        if not self.gpus:
            return None
        return max(self.gpus, key=lambda g: g.total_vram_mb)
    
    def can_fit_model(self, vram_required_gb: float, overhead_gb: float = 1.0) -> bool:
        """Check if a model with given VRAM requirement can fit.
        
        Args:
            vram_required_gb: VRAM required by the model
            overhead_gb: Additional overhead to leave free (default 1GB)
        
        Returns:
            True if the model can fit
        """
        return self.free_vram_gb >= (vram_required_gb + overhead_gb)


def detect_nvidia_gpus() -> SystemGPUInfo | None:
    """Detect NVIDIA GPUs using nvidia-smi.
    
    Returns:
        SystemGPUInfo if NVIDIA GPUs found, None otherwise
    """
    try:
        # Query GPU info: name, total memory, used memory, driver version
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        
        if result.returncode != 0:
            return None
        
        gpus = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                gpu = GPUInfo(
                    name=parts[0],
                    total_vram_mb=int(float(parts[1])),
                    used_vram_mb=int(float(parts[2])),
                    free_vram_mb=int(float(parts[3])),
                    driver_version=parts[4] if len(parts) > 4 else "",
                )
                gpus.append(gpu)
        
        if gpus:
            return SystemGPUInfo(gpus=gpus, platform="nvidia")
        
    except (subprocess.SubprocessError, FileNotFoundError, ValueError) as e:
        logger.debug(f"NVIDIA GPU detection failed: {e}")
    
    return None


def detect_amd_gpus() -> SystemGPUInfo | None:
    """Detect AMD GPUs using rocm-smi.
    
    Returns:
        SystemGPUInfo if AMD GPUs found, None otherwise
    """
    try:
        result = subprocess.run(
            ["rocm-smi", "--showmeminfo", "VRAM"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        
        if result.returncode != 0:
            return None
        
        # Parse rocm-smi output (simplified)
        # ROCm-smi output format varies, this is a basic parser
        gpus = []
        # TODO: Implement proper ROCm-smi parsing
        
        if gpus:
            return SystemGPUInfo(gpus=gpus, platform="amd")
        
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.debug(f"AMD GPU detection failed: {e}")
    
    return None


def detect_apple_silicon() -> SystemGPUInfo | None:
    """Detect Apple Silicon unified memory.
    
    Returns:
        SystemGPUInfo if Apple Silicon, None otherwise
    """
    import platform
    
    if platform.system() != "Darwin":
        return None
    
    try:
        # Check if running on Apple Silicon
        result = subprocess.run(
            ["sysctl", "-n", "hw.optional.arm64"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        
        if result.returncode != 0 or result.stdout.strip() != "1":
            return None
        
        # Get total memory (unified memory architecture)
        mem_result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        
        if mem_result.returncode == 0:
            total_bytes = int(mem_result.stdout.strip())
            total_mb = total_bytes // (1024 * 1024)
            
            # Estimate used memory (simplified)
            # On macOS, we'd need more complex logic for accurate GPU memory
            used_mb = total_mb // 4  # Rough estimate: 1/4 in use
            free_mb = total_mb - used_mb
            
            gpu = GPUInfo(
                name="Apple Silicon Unified Memory",
                total_vram_mb=total_mb,
                used_vram_mb=used_mb,
                free_vram_mb=free_mb,
                driver_version="",
            )
            
            return SystemGPUInfo(gpus=[gpu], platform="apple_silicon")
        
    except (subprocess.SubprocessError, FileNotFoundError, ValueError) as e:
        logger.debug(f"Apple Silicon detection failed: {e}")
    
    return None


def detect_gpus() -> SystemGPUInfo:
    """Detect available GPUs in order of preference.
    
    Tries: NVIDIA -> AMD -> Apple Silicon -> CPU fallback
    
    Returns:
        SystemGPUInfo with detected GPUs or CPU fallback
    """
    # Try NVIDIA first (most common)
    info = detect_nvidia_gpus()
    if info:
        logger.info(f"Detected {len(info.gpus)} NVIDIA GPU(s)")
        for gpu in info.gpus:
            logger.info(f"  {gpu.name}: {gpu.free_vram_gb:.1f}GB free / {gpu.total_vram_gb:.1f}GB total")
        return info
    
    # Try AMD
    info = detect_amd_gpus()
    if info:
        logger.info(f"Detected {len(info.gpus)} AMD GPU(s)")
        return info
    
    # Try Apple Silicon
    info = detect_apple_silicon()
    if info:
        logger.info(f"Detected Apple Silicon: {info.total_vram_gb:.1f}GB unified memory")
        return info
    
    # CPU fallback
    logger.info("No GPU detected - using CPU mode")
    return SystemGPUInfo(gpus=[], platform="cpu")


def calculate_model_vram(model_name: str) -> float:
    """Estimate VRAM required for a model.
    
    This is a rough estimate based on model size in billions of parameters.
    Actual VRAM usage depends on:
    - Quantization level (Q4, Q5, Q8, FP16)
    - Context window size
    - Batch size
    
    Args:
        model_name: Name of the model (e.g., "qwen2.5-coder:14b")
    
    Returns:
        Estimated VRAM in GB
    """
    import re
    
    # Extract parameter count from model name
    # Common patterns: 7b, 14b, 32b, 70b, 6.7b, etc.
    patterns = [
        r"(\d+\.?\d*)b",  # 7b, 14b, 6.7b
        r"(\d+)B",        # 7B, 14B
    ]
    
    params_b = None
    for pattern in patterns:
        match = re.search(pattern, model_name, re.IGNORECASE)
        if match:
            params_b = float(match.group(1))
            break
    
    if params_b is None:
        # Default estimate for unknown models
        logger.debug(f"Unknown model size for {model_name}, using default estimate")
        return 8.0
    
    # Check for quantization suffix
    quantization_multiplier = 1.0
    if ":q4" in model_name.lower():
        quantization_multiplier = 0.6  # Q4 is ~60% of original
    elif ":q5" in model_name.lower():
        quantization_multiplier = 0.7
    elif ":q8" in model_name.lower():
        quantization_multiplier = 0.9
    
    # Base calculation: ~0.5-0.7GB per billion parameters (conservative estimate)
    # Includes overhead for context, KV cache, etc.
    base_vram = params_b * 0.7
    
    # Add overhead for context window and activations
    overhead = 1.5  # Base overhead in GB
    
    total_vram = (base_vram * quantization_multiplier) + overhead
    
    return round(total_vram, 1)


def recommend_models_for_gpu(gpu_info: SystemGPUInfo | None = None) -> list[dict]:
    """Recommend models that fit the available GPU.
    
    Args:
        gpu_info: GPU information (auto-detected if None)
    
    Returns:
        List of recommended models with their VRAM requirements
    """
    if gpu_info is None:
        gpu_info = detect_gpus()
    
    free_vram = gpu_info.free_vram_gb if gpu_info.gpus else 16.0  # Default assumption
    
    # Define models with their VRAM requirements
    all_models = [
        {"name": "qwen2.5-coder:7b", "vram_gb": 6, "speed": "Fast", "quality": "Good"},
        {"name": "qwen2.5-coder:14b", "vram_gb": 12, "speed": "Medium", "quality": "Excellent"},
        {"name": "qwen2.5-coder:32b", "vram_gb": 24, "speed": "Slow", "quality": "Best"},
        {"name": "deepseek-coder:6.7b", "vram_gb": 6, "speed": "Fast", "quality": "Good"},
        {"name": "deepseek-coder:33b", "vram_gb": 24, "speed": "Slow", "quality": "Excellent"},
        {"name": "codellama:7b", "vram_gb": 6, "speed": "Fast", "quality": "Good"},
        {"name": "codellama:13b", "vram_gb": 10, "speed": "Medium", "quality": "Good"},
        {"name": "codellama:34b", "vram_gb": 22, "speed": "Slow", "quality": "Very Good"},
        {"name": "llama3.3:latest", "vram_gb": 48, "speed": "Slow", "quality": "Best"},
        {"name": "llama3.2:3b", "vram_gb": 3, "speed": "Very Fast", "quality": "Okay"},
    ]
    
    # Filter models that fit
    fitting_models = [
        m for m in all_models 
        if m["vram_gb"] <= (free_vram - 1.0)  # Leave 1GB overhead
    ]
    
    # Sort by quality preference (best quality that fits)
    fitting_models.sort(key=lambda m: (m["vram_gb"], m["quality"]), reverse=True)
    
    return fitting_models


def get_optimal_default_model(gpu_info: SystemGPUInfo | None = None) -> str:
    """Get the optimal default model for the detected GPU.
    
    Args:
        gpu_info: GPU information (auto-detected if None)
    
    Returns:
        Model name string
    """
    recommendations = recommend_models_for_gpu(gpu_info)
    
    if recommendations:
        # Return the best quality model that fits
        return recommendations[0]["name"]
    
    # Fallback for very limited VRAM
    return "llama3.2:3b"


if __name__ == "__main__":
    # Test GPU detection
    import json
    
    print("Detecting GPUs...")
    info = detect_gpus()
    
    print(f"\nPlatform: {info.platform}")
    print(f"Total VRAM: {info.total_vram_gb:.1f} GB")
    print(f"Free VRAM: {info.free_vram_gb:.1f} GB")
    
    if info.gpus:
        print("\nGPU Details:")
        for i, gpu in enumerate(info.gpus, 1):
            print(f"  {i}. {gpu.name}")
            print(f"     Total: {gpu.total_vram_gb:.1f} GB")
            print(f"     Free: {gpu.free_vram_gb:.1f} GB")
            if gpu.driver_version:
                print(f"     Driver: {gpu.driver_version}")
    
    print("\nRecommended Models:")
    recommendations = recommend_models_for_gpu(info)
    for model in recommendations[:5]:
        print(f"  - {model['name']} ({model['vram_gb']} GB, {model['speed']}, {model['quality']})")
    
    print(f"\nOptimal default: {get_optimal_default_model(info)}")
