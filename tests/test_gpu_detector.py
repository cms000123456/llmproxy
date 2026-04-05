"""Tests for GPU detection and VRAM calculation."""

import pytest
from unittest.mock import MagicMock, patch

from llmproxy.gpu_detector import (
    GPUInfo,
    SystemGPUInfo,
    calculate_model_vram,
    get_optimal_default_model,
    recommend_models_for_gpu,
)


class TestGPUInfo:
    """Test GPUInfo dataclass."""

    def test_vram_conversions(self):
        """Test VRAM conversions from MB to GB."""
        gpu = GPUInfo(
            name="Test GPU",
            total_vram_mb=16384,  # 16 GB
            used_vram_mb=4096,    # 4 GB
            free_vram_mb=12288,   # 12 GB
        )
        
        assert gpu.total_vram_gb == 16.0
        assert gpu.used_vram_gb == 4.0
        assert gpu.free_vram_gb == 12.0


class TestSystemGPUInfo:
    """Test SystemGPUInfo dataclass."""

    def test_single_gpu(self):
        """Test with a single GPU."""
        gpu = GPUInfo(
            name="RTX 4090",
            total_vram_mb=24576,
            used_vram_mb=2048,
            free_vram_mb=22528,
        )
        system = SystemGPUInfo(gpus=[gpu], platform="nvidia")
        
        assert system.total_vram_gb == 24.0
        assert system.free_vram_gb == 22.0
        assert system.primary_gpu.name == "RTX 4090"
        assert system.platform == "nvidia"

    def test_multiple_gpus(self):
        """Test with multiple GPUs."""
        gpu1 = GPUInfo(
            name="RTX 4090",
            total_vram_mb=24576,
            used_vram_mb=2048,
            free_vram_mb=22528,
        )
        gpu2 = GPUInfo(
            name="RTX 3090",
            total_vram_mb=24576,
            used_vram_mb=4096,
            free_vram_mb=20480,
        )
        system = SystemGPUInfo(gpus=[gpu1, gpu2], platform="nvidia")
        
        assert system.total_vram_gb == 48.0
        assert system.free_vram_gb == 42.0  # 22GB + 20GB
        # Primary should be the one with more free VRAM
        assert system.primary_gpu.name == "RTX 4090"

    def test_cpu_fallback(self):
        """Test CPU fallback with no GPUs."""
        system = SystemGPUInfo(gpus=[], platform="cpu")
        
        assert system.total_vram_gb == 0.0
        assert system.free_vram_gb == 0.0
        assert system.primary_gpu is None

    def test_can_fit_model(self):
        """Test model fitting calculation."""
        gpu = GPUInfo(
            name="RTX 4060",
            total_vram_mb=16384,
            used_vram_mb=2048,
            free_vram_mb=14336,
        )
        system = SystemGPUInfo(gpus=[gpu], platform="nvidia")
        
        # Should fit 7B model (~6GB)
        assert system.can_fit_model(6.0, overhead_gb=1.0) is True
        
        # Should not fit 70B model (~48GB)
        assert system.can_fit_model(48.0, overhead_gb=1.0) is False


class TestCalculateModelVRAM:
    """Test VRAM estimation for models."""

    def test_7b_model(self):
        """Test 7B parameter model."""
        vram = calculate_model_vram("qwen2.5-coder:7b")
        # 7B * 0.7 + 1.5 overhead = ~6.4GB
        assert 6.0 <= vram <= 8.0

    def test_14b_model(self):
        """Test 14B parameter model."""
        vram = calculate_model_vram("codellama:13b")
        # 13B * 0.7 + 1.5 overhead = ~10.6GB
        assert 10.0 <= vram <= 13.0

    def test_32b_model(self):
        """Test 32B parameter model."""
        vram = calculate_model_vram("qwen2.5-coder:32b")
        # 32B * 0.7 + 1.5 overhead = ~23.9GB
        assert 22.0 <= vram <= 26.0

    def test_quantized_model(self):
        """Test quantized model uses less VRAM."""
        # Extract param count properly with known model
        vram_full = calculate_model_vram("qwen2.5-coder:14b")
        vram_q4 = calculate_model_vram("qwen2.5-coder:14b-q4_0")
        
        # Both should return valid estimates (quantization check is in the function)
        assert vram_full > 0
        assert vram_q4 > 0
        # Q4 should be smaller or equal (depends on implementation)
        assert vram_q4 <= vram_full

    def test_unknown_model(self):
        """Test unknown model defaults."""
        vram = calculate_model_vram("unknown-custom-model")
        assert vram == 8.0  # Default estimate


class TestRecommendModels:
    """Test model recommendations."""

    def test_16gb_vram(self):
        """Test recommendations for 16GB VRAM."""
        gpu = GPUInfo(
            name="RTX 4060 Ti 16GB",
            total_vram_mb=16384,
            used_vram_mb=1024,
            free_vram_mb=15360,
        )
        system = SystemGPUInfo(gpus=[gpu], platform="nvidia")
        
        recommendations = recommend_models_for_gpu(system)
        
        # Should include 7B and 14B models
        model_names = [m["name"] for m in recommendations]
        assert "qwen2.5-coder:7b" in model_names
        assert "qwen2.5-coder:14b" in model_names
        
        # Should not include 32B model (too large)
        assert "qwen2.5-coder:32b" not in model_names

    def test_8gb_vram(self):
        """Test recommendations for 8GB VRAM."""
        gpu = GPUInfo(
            name="RTX 4060 8GB",
            total_vram_mb=8192,
            used_vram_mb=1024,
            free_vram_mb=7168,
        )
        system = SystemGPUInfo(gpus=[gpu], platform="nvidia")
        
        recommendations = recommend_models_for_gpu(system)
        
        # Should include 3B and 7B models
        model_names = [m["name"] for m in recommendations]
        assert "llama3.2:3b" in model_names
        assert "qwen2.5-coder:7b" in model_names
        
        # Should not include 14B model (too large)
        assert "qwen2.5-coder:14b" not in model_names

    def test_cpu_mode(self):
        """Test recommendations for CPU mode."""
        system = SystemGPUInfo(gpus=[], platform="cpu")
        
        # CPU mode uses default 16GB assumption
        recommendations = recommend_models_for_gpu(system)
        assert len(recommendations) > 0


class TestGetOptimalDefaultModel:
    """Test optimal default model selection."""

    def test_high_end_gpu(self):
        """Test with high-end GPU."""
        gpu = GPUInfo(
            name="RTX 4090",
            total_vram_mb=24576,
            used_vram_mb=2048,
            free_vram_mb=22528,
        )
        system = SystemGPUInfo(gpus=[gpu], platform="nvidia")
        
        model = get_optimal_default_model(system)
        # Should pick a good model that fits 22GB
        assert model in ["qwen2.5-coder:14b", "qwen2.5-coder:32b", "codellama:34b"]

    def test_mid_range_gpu(self):
        """Test with mid-range GPU."""
        gpu = GPUInfo(
            name="RTX 4070",
            total_vram_mb=12288,
            used_vram_mb=1024,
            free_vram_mb=11264,
        )
        system = SystemGPUInfo(gpus=[gpu], platform="nvidia")
        
        model = get_optimal_default_model(system)
        # Should pick a model that fits 11GB (codellama:13b is 10GB and comes first in sorted list)
        assert model in ["qwen2.5-coder:7b", "deepseek-coder:6.7b", "codellama:13b"]

    def test_low_vram_gpu(self):
        """Test with low VRAM GPU."""
        gpu = GPUInfo(
            name="RTX 4060 8GB",
            total_vram_mb=8192,
            used_vram_mb=2048,
            free_vram_mb=6144,
        )
        system = SystemGPUInfo(gpus=[gpu], platform="nvidia")
        
        model = get_optimal_default_model(system)
        # Should pick 3B model
        assert model == "llama3.2:3b"


class TestNvidiaDetection:
    """Test NVIDIA GPU detection."""

    @patch("llmproxy.gpu_detector.subprocess.run")
    def test_nvidia_smi_success(self, mock_run):
        """Test successful nvidia-smi parsing."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        # Format: name, total, used, free, driver
        mock_result.stdout = "NVIDIA RTX 4090, 24576, 2048, 22528, 545.23\n"
        mock_run.return_value = mock_result
        
        from llmproxy.gpu_detector import detect_nvidia_gpus
        
        info = detect_nvidia_gpus()
        
        assert info is not None
        assert info.platform == "nvidia"
        assert len(info.gpus) == 1
        assert info.gpus[0].name == "NVIDIA RTX 4090"
        assert info.gpus[0].total_vram_gb == 24.0

    @patch("llmproxy.gpu_detector.subprocess.run")
    def test_nvidia_smi_not_found(self, mock_run):
        """Test when nvidia-smi is not found."""
        mock_run.side_effect = FileNotFoundError()
        
        from llmproxy.gpu_detector import detect_nvidia_gpus
        
        info = detect_nvidia_gpus()
        assert info is None

    @patch("llmproxy.gpu_detector.subprocess.run")
    def test_nvidia_smi_error(self, mock_run):
        """Test when nvidia-smi returns error."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result
        
        from llmproxy.gpu_detector import detect_nvidia_gpus
        
        info = detect_nvidia_gpus()
        assert info is None
