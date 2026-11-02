# vcpkg 의존성을 프로젝트와 같은 C++20으로 빌드한다 (QA-007).
# protobuf의 ABI(GlobalEmptyString)가 언어 모드에 따라 달라 C++17 빌드 DLL과 C++20 릴리스 링크가 어긋난다.
set(VCPKG_TARGET_ARCHITECTURE x64)
set(VCPKG_CRT_LINKAGE dynamic)
set(VCPKG_LIBRARY_LINKAGE dynamic)
set(VCPKG_C_FLAGS "/std:c++20")
set(VCPKG_CXX_FLAGS "/std:c++20")
