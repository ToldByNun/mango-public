@echo off
setlocal
REM Build llama-cpp-python with Vulkan backend (AMD / Intel / NVIDIA on Windows).
set "PIP=python -m pip"
set "CMAKE_ARGS=-DGGML_VULKAN=on"
set FORCE_CMAKE=1
set CMAKE_GENERATOR=Ninja
"%PIP%" install llama-cpp-python --force-reinstall --no-cache-dir
echo Done. Verify with: python -c "from mango_runtime.gpu_env import detect_gpu_backend; print(detect_gpu_backend())"
