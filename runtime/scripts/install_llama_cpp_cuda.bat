@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b 1
set "CUDA_PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.3"
set "CUDACXX=%CUDA_PATH%\bin\nvcc.exe"
set "PATH=%CUDA_PATH%\bin\x64;%CUDA_PATH%\bin;C:\Users\mikaj\AppData\Local\Programs\Python\Python312\Scripts;%PATH%"
set CMAKE_GENERATOR=Ninja
set "CMAKE_ARGS=-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=120 -DGGML_CCACHE=OFF"
set FORCE_CMAKE=1
set CMAKE_BUILD_PARALLEL_LEVEL=8
"%PIP%" install ninja
"%PIP%" install llama-cpp-python --force-reinstall --no-cache-dir
