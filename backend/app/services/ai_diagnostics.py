"""
SmartGuard AI — AI Runtime Diagnostics Service (Phase 2)

Detects available compute devices (CUDA/CPU), installed AI libraries
(InsightFace, FastALPR, ONNX Runtime), and reports readiness status.
"""
import logging
import os
import platform
import subprocess
import sys
from typing import Optional

logger = logging.getLogger("smartguard.ai_diagnostics")


# ---------------------------------------------------------------------------
# GPU / CUDA detection
# ---------------------------------------------------------------------------

def _detect_cuda_via_nvidia_smi() -> dict:
    """Run nvidia-smi and parse basic GPU info."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
            gpus = []
            for line in lines:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4:
                    gpus.append({
                        "name": parts[0],
                        "driver_version": parts[1],
                        "memory_total_mb": int(parts[2]) if parts[2].isdigit() else None,
                        "utilization_pct": int(parts[3]) if parts[3].isdigit() else None,
                    })
            return {"available": True, "gpus": gpus, "error": None}
    except FileNotFoundError:
        return {"available": False, "gpus": [], "error": "nvidia-smi not found"}
    except subprocess.TimeoutExpired:
        return {"available": False, "gpus": [], "error": "nvidia-smi timed out"}
    except Exception as exc:
        return {"available": False, "gpus": [], "error": str(exc)}
    return {"available": False, "gpus": [], "error": "unexpected return code"}


def _detect_cuda_via_torch() -> dict:
    """Try importing torch to check CUDA availability."""
    try:
        import torch  # type: ignore
        return {
            "torch_available": True,
            "cuda_available": torch.cuda.is_available(),
            "cuda_device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
            "cuda_device_name": (
                torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
            ),
        }
    except ImportError:
        return {"torch_available": False, "cuda_available": False}
    except Exception as exc:
        return {"torch_available": False, "cuda_available": False, "error": str(exc)}


def _detect_onnxruntime() -> dict:
    """Check ONNX Runtime installation and available execution providers."""
    try:
        import onnxruntime as ort  # type: ignore
        providers = ort.get_available_providers()
        return {
            "available": True,
            "version": ort.__version__,
            "providers": providers,
            "cuda_provider": "CUDAExecutionProvider" in providers,
        }
    except ImportError:
        return {"available": False, "error": "onnxruntime not installed"}
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def _detect_insightface() -> dict:
    """Check InsightFace installation and model readiness."""
    try:
        import insightface  # type: ignore
        version = getattr(insightface, "__version__", "unknown")

        # Check if model cache directory exists
        home = os.path.expanduser("~")
        model_cache = os.path.join(home, ".insightface", "models")
        cache_exists = os.path.isdir(model_cache)
        cached_models = []
        if cache_exists:
            try:
                cached_models = [
                    d for d in os.listdir(model_cache)
                    if os.path.isdir(os.path.join(model_cache, d))
                ]
            except Exception:
                pass

        return {
            "available": True,
            "version": version,
            "model_cache_exists": cache_exists,
            "cached_models": cached_models,
        }
    except ImportError:
        return {"available": False, "error": "insightface not installed"}
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def _detect_fast_alpr() -> dict:
    """Check FastALPR installation."""
    try:
        import fast_alpr  # type: ignore
        version = getattr(fast_alpr, "__version__", "unknown")
        return {"available": True, "version": version}
    except ImportError:
        return {"available": False, "error": "fast-alpr not installed"}
    except Exception as exc:
        return {"available": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_ai_diagnostics() -> dict:
    """
    Return a comprehensive AI runtime diagnostics report.
    All sections are non-fatal — errors are reported, not raised.
    """
    nvidia = _detect_cuda_via_nvidia_smi()
    torch_info = _detect_cuda_via_torch()
    ort_info = _detect_onnxruntime()
    insightface_info = _detect_insightface()
    alpr_info = _detect_fast_alpr()

    # Determine recommended execution provider
    if ort_info.get("cuda_provider") and nvidia.get("available"):
        recommended_provider = "CUDAExecutionProvider"
        compute_device = "GPU"
    else:
        recommended_provider = "CPUExecutionProvider"
        compute_device = "CPU"

    return {
        "system": {
            "platform": platform.system(),
            "python_version": sys.version,
            "os_version": platform.version(),
        },
        "gpu": {
            "nvidia_smi": nvidia,
            "torch": torch_info,
        },
        "onnxruntime": ort_info,
        "insightface": insightface_info,
        "fast_alpr": alpr_info,
        "recommendation": {
            "compute_device": compute_device,
            "execution_provider": recommended_provider,
            "face_recognition_ready": insightface_info.get("available", False),
            "alpr_ready": alpr_info.get("available", False),
        },
    }


def get_execution_providers() -> list[str]:
    """
    Return the best available ONNX Runtime execution providers in priority order.
    Falls back gracefully to CPU.
    """
    try:
        import onnxruntime as ort  # type: ignore
        available = ort.get_available_providers()
        preferred = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        return [p for p in preferred if p in available] or ["CPUExecutionProvider"]
    except Exception:
        return ["CPUExecutionProvider"]
