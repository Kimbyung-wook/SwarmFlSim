@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
cd /d %~dp0..
cmake --preset msvc-debug -DVCPKG_INSTALL_OPTIONS=--x-buildtrees-root=C:/b/bt -DCMAKE_PREFIX_PATH=C:/dev/zenoh || exit /b 1
cmake --build --preset msvc-debug || exit /b 1
echo === ALL DONE
