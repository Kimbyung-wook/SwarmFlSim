@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
cd /d %~dp0..
for %%P in (msvc-debug msvc-release) do (
  echo === configure %%P
  cmake --preset %%P -DVCPKG_INSTALL_OPTIONS=--x-buildtrees-root=C:/b/bt -DCMAKE_PREFIX_PATH=C:/dev/zenoh || exit /b 1
  echo === build %%P
  cmake --build --preset %%P || exit /b 1
)
echo === ALL DONE
