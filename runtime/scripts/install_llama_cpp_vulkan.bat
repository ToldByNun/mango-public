@echo off
setlocal
REM Install prebuilt llama-cpp-python Vulkan wheel (AMD / Intel / NVIDIA).
REM Prefers abetlen's Vulkan index; falls back to a from-source Vulkan build.
if "%PIP%"=="" set "PIP=python -m pip"

echo Installing llama-cpp-python Vulkan wheel ...
%PIP% install "llama-cpp-python>=0.3.0" --force-reinstall --no-cache-dir --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/vulkan
if errorlevel 1 (
  echo Wheel install failed; building from source with GGML_VULKAN=on ...
  set "CMAKE_ARGS=-DGGML_VULKAN=on"
  set FORCE_CMAKE=1
  set CMAKE_GENERATOR=Ninja
  %PIP% install llama-cpp-python --force-reinstall --no-cache-dir
)

echo.
echo Verify:
python -c "from mango_runtime.gpu_env import detect_gpu_backend, has_backend_dll; print('backend', detect_gpu_backend(), 'vulkan_dll', has_backend_dll('vulkan'))"
echo Done. Restart the Mango sidecar / Electron app.
